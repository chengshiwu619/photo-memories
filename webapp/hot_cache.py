import json
import random
import threading
import time
from pathlib import Path
from typing import Iterable

from business.classifier.category_rules import category_match_sql
from business.classifier.nsfw_review import load_review_candidates
from business.deletion_queue import pending_delete_filter_sql
from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from logger_setup import logger
from business.recommendation import _sequence_memory_segments


CACHE_SCHEMA_VERSION = "3"
CACHE_BATCH_SIZE = 800
VISIBLE_SQL = """
    f.is_image IN (0, 1)
    AND pm.thumbnail_path IS NOT NULL
    AND pm.thumbnail_path != ''
    AND pm.thumbnail_path != '__FAILED__'
    AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
    AND (f.path_status IS NULL OR f.path_status NOT IN
        ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
""" + pending_delete_filter_sql("f")


def _compact_folder(path: str | None) -> str:
    parts = [part for part in (path or "").replace("\\", "/").split("/") if part]
    return " / ".join(parts[-3:])


def _normalize_ids(values: Iterable[object] | None, limit=100000) -> list[int]:
    result = []
    seen = set()
    for value in values or []:
        try:
            file_id = int(value)
        except (TypeError, ValueError):
            continue
        if file_id <= 0 or file_id in seen:
            continue
        seen.add(file_id)
        result.append(file_id)
        if len(result) >= limit:
            break
    return result


class WebHotCache:
    """Rebuildable, denormalized SQLite snapshot for the web photo feed."""

    def __init__(self, db):
        self.db = db
        self._active_generation: int | None = None
        self._rotations: dict[tuple[int, int, bool], int] = {}
        self._path_cache: dict[int, tuple[str, str]] = {}
        self._count_cache: dict[tuple[int, int, bool], int] = {}
        self._timeline_index_cache: dict[tuple[int, int, bool], dict] = {}
        self._segment_starts_cache: dict[tuple[int, int], list[int]] = {}
        self._build_lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._rotation_lock = threading.Lock()
        self.ensure_schema()
        self._active_generation = self._read_active_generation()

    @property
    def ready(self) -> bool:
        return self._active_generation is not None

    def ensure_schema(self):
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_cache_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS web_photo_cache (
                    generation INTEGER NOT NULL,
                    category INTEGER NOT NULL,
                    file_id INTEGER NOT NULL,
                    random_rank INTEGER NOT NULL,
                    segment_start INTEGER NOT NULL DEFAULT 0,
                    date_key TEXT NOT NULL,
                    starred INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    thumbnail_path TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    PRIMARY KEY (generation, category, file_id)
                );
                CREATE INDEX IF NOT EXISTS idx_web_cache_random
                    ON web_photo_cache(generation, category, starred, random_rank, file_id);
                CREATE INDEX IF NOT EXISTS idx_web_cache_random_all
                    ON web_photo_cache(generation, category, random_rank, file_id);
                CREATE INDEX IF NOT EXISTS idx_web_cache_timeline
                    ON web_photo_cache(generation, category, starred, date_key DESC, file_id DESC);
                CREATE INDEX IF NOT EXISTS idx_web_cache_timeline_all
                    ON web_photo_cache(generation, category, date_key DESC, file_id DESC);
                CREATE INDEX IF NOT EXISTS idx_web_cache_file
                    ON web_photo_cache(generation, file_id);
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(web_photo_cache)").fetchall()}
            if "segment_start" not in columns:
                conn.execute(
                    "ALTER TABLE web_photo_cache ADD COLUMN segment_start INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_web_cache_segment_starts
                ON web_photo_cache(generation, category, segment_start, random_rank)
                """
            )

    def _state(self, key: str, default=None):
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM web_cache_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_states(self, values: dict[str, object]):
        with self.db.connect() as conn:
            conn.executemany(
                """
                INSERT INTO web_cache_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                [(key, str(value)) for key, value in values.items()],
            )

    def _read_active_generation(self) -> int | None:
        value = self._state("active_generation")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def source_signature(self) -> str:
        with self.db.connect() as conn:
            files = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(scanned_at), '') FROM files"
            ).fetchone()
            metadata = conn.execute(
                """
                SELECT COUNT(*), COALESCE(MAX(indexed_at), ''),
                       COALESCE(SUM(COALESCE(is_starred, 0)), 0),
                       COALESCE(SUM(COALESCE(category, 0)), 0)
                FROM photo_metadata
                """
            ).fetchone()
            tags = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM photo_tags"
            ).fetchone()
            folders = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(classified_at), '') FROM folder_categories"
            ).fetchone()
        return "|".join(str(value) for row in (files, metadata, tags, folders) for value in row)

    def ensure_ready(self) -> bool:
        if self.ready:
            return True
        return self.build_snapshot()

    def refresh_if_stale(self):
        if (
            not self.ready
            or self._state("schema_version", "") != CACHE_SCHEMA_VERSION
            or self._state("source_signature", "") != self.source_signature()
        ):
            self.build_snapshot()

    def refresh_if_stale_async(self, delay=1.5):
        def run():
            if delay:
                time.sleep(delay)
            try:
                self.refresh_if_stale()
            except Exception:
                logger.exception("网页热启动快照后台刷新失败")

        threading.Thread(target=run, name="web-hot-cache-refresh", daemon=True).start()

    def _load_source_rows(self, category: int, file_ids: list[int] | None = None) -> list[dict]:
        category_sql = category_match_sql(category)
        id_sql = ""
        params: list[object] = [category]
        if file_ids is not None:
            if not file_ids:
                return []
            placeholders = ",".join("?" for _ in file_ids)
            id_sql = f" AND f.id IN ({placeholders})"
            params.extend(file_ids)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT f.id, f.file_path, f.file_name, f.folder_path, f.file_mtime,
                       pm.thumbnail_path, pm.width, pm.height, pm.date_taken,
                       pm.phash, COALESCE(pm.is_starred, 0) AS is_starred
                FROM files f
                JOIN photo_metadata pm ON pm.file_id = f.id
                LEFT JOIN folder_categories fc ON fc.folder_path = f.folder_path
                WHERE {category_sql} AND {VISIBLE_SQL} {id_sql}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _tags_by_id(self, file_ids: list[int]) -> dict[int, list[str]]:
        result = {file_id: [] for file_id in file_ids}
        for start in range(0, len(file_ids), CACHE_BATCH_SIZE):
            batch = file_ids[start:start + CACHE_BATCH_SIZE]
            placeholders = ",".join("?" for _ in batch)
            with self.db.connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT file_id, tag
                    FROM photo_tags
                    WHERE file_id IN ({placeholders})
                      AND source IN ('siglip', 'manual')
                      AND lower(tag) NOT LIKE 'category:%'
                      AND lower(tag) NOT LIKE 'nsfw-review:%'
                    ORDER BY file_id, tag
                    """,
                    batch,
                ).fetchall()
            for row in rows:
                file_id = int(row["file_id"])
                tag = (row["tag"] or "").strip()
                if tag and len(result[file_id]) < 12 and tag not in result[file_id]:
                    result[file_id].append(tag)
        return result

    @staticmethod
    def _payload(row: dict, tags: list[str]) -> dict:
        file_id = int(row["id"])
        return {
            "id": file_id,
            "name": row.get("file_name") or f"照片 {file_id}",
            "folder": _compact_folder(row.get("folder_path")),
            "date": row.get("date_taken") or row.get("file_mtime") or "",
            "width": int(row["width"]) if row.get("width") else None,
            "height": int(row["height"]) if row.get("height") else None,
            "thumbnailUrl": f"/media/thumbnail/{file_id}",
            "originalUrl": f"/media/original/{file_id}",
            "reasons": [],
            "reasonText": "",
            "starred": bool(row.get("is_starred")),
            "tags": tags,
        }

    def _insert_rows(
        self,
        generation: int,
        category: int,
        rows: list[dict],
        ranks=None,
        segment_starts=None,
    ):
        segment_starts = set(segment_starts or [])
        for start in range(0, len(rows), CACHE_BATCH_SIZE):
            batch = rows[start:start + CACHE_BATCH_SIZE]
            tags_by_id = self._tags_by_id([int(row["id"]) for row in batch])
            values = []
            for offset, row in enumerate(batch, start=start):
                file_id = int(row["id"])
                rank = ranks[offset] if ranks is not None else random.randint(0, max(len(rows), 1))
                payload = self._payload(row, tags_by_id.get(file_id, []))
                values.append(
                    (
                        generation,
                        category,
                        file_id,
                        int(rank),
                        1 if (offset in segment_starts or ranks is None) else 0,
                        payload["date"],
                        1 if payload["starred"] else 0,
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        row.get("thumbnail_path") or "",
                        row.get("file_path") or "",
                    )
                )
            with self.db.connect() as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO web_photo_cache
                        (generation, category, file_id, random_rank, segment_start, date_key, starred,
                         payload_json, thumbnail_path, original_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )

    def build_snapshot(self) -> bool:
        if not self._build_lock.acquire(blocking=False):
            return self.ready
        started = time.perf_counter()
        generation = int(time.time() * 1000)
        try:
            logger.info("开始构建网页热启动快照")
            with self.db.connect() as conn:
                conn.execute("DELETE FROM web_photo_cache WHERE generation = ?", (generation,))
            counts = {}
            for category in (CATEGORY_LIFE, CATEGORY_SAMPLE):
                rows = self._load_source_rows(category)
                rng = random.Random(generation ^ category)
                rng.shuffle(rows)
                ordered, segment_starts = _sequence_memory_segments(
                    rows,
                    rng=rng,
                    with_boundaries=True,
                )
                self._insert_rows(
                    generation,
                    category,
                    ordered,
                    ranks=list(range(len(ordered))),
                    segment_starts=segment_starts,
                )
                counts[category] = len(ordered)

            signature = self.source_signature()
            review_count = len(load_review_candidates(limit=600, offset=0, db=self.db))
            self._set_states(
                {
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "active_generation": generation,
                    "source_signature": signature,
                    "life_count": counts.get(CATEGORY_LIFE, 0),
                    "sample_count": counts.get(CATEGORY_SAMPLE, 0),
                    "review_count": review_count,
                    "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
            self._active_generation = generation
            self._rotations.clear()
            self._path_cache.clear()
            self._count_cache.clear()
            self._timeline_index_cache.clear()
            self._segment_starts_cache.clear()
            with self.db.connect() as conn:
                conn.execute("DELETE FROM web_photo_cache WHERE generation != ?", (generation,))
            logger.info(
                "网页热启动快照完成: life=%s sample=%s elapsed=%.2fs",
                counts.get(CATEGORY_LIFE, 0),
                counts.get(CATEGORY_SAMPLE, 0),
                time.perf_counter() - started,
            )
            return True
        except Exception:
            logger.exception("网页热启动快照构建失败")
            with self.db.connect() as conn:
                conn.execute("DELETE FROM web_photo_cache WHERE generation = ?", (generation,))
            return self.ready
        finally:
            self._build_lock.release()

    def _count(self, category: int, starred_only=False) -> int:
        if not self.ready:
            return 0
        key = (int(self._active_generation), int(category), bool(starred_only))
        if key in self._count_cache:
            return self._count_cache[key]
        with self.db.connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) FROM web_photo_cache
                WHERE generation = ? AND category = ?
                  {"AND starred = 1" if starred_only else ""}
                """,
                (self._active_generation, category),
            ).fetchone()
        count = int(row[0]) if row else 0
        self._count_cache[key] = count
        return count

    def counts(self) -> dict[str, int]:
        return {
            "life": self._count(CATEGORY_LIFE),
            "sample": self._count(CATEGORY_SAMPLE),
        }

    def timeline_index(self, category: int, starred_only=False) -> dict:
        if not self.ready:
            return {"months": [], "total": 0, "hot": False}
        generation = int(self._active_generation)
        key = (generation, int(category), bool(starred_only))
        cached = self._timeline_index_cache.get(key)
        if cached is not None:
            return cached
        starred_sql = "AND starred = 1" if starred_only else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT substr(date_key, 1, 7) AS month_key, COUNT(*) AS photo_count
                FROM web_photo_cache
                WHERE generation = ? AND category = ?
                  {starred_sql}
                  AND length(date_key) >= 7
                GROUP BY month_key
                ORDER BY month_key DESC
                """,
                (generation, int(category)),
            ).fetchall()
        months = []
        offset = 0
        for row in rows:
            count = int(row["photo_count"])
            months.append({"month": row["month_key"], "count": count, "offset": offset})
            offset += count
        total = self._count(category, starred_only=starred_only)
        if offset < total:
            months.append({"month": "未知日期", "count": total - offset, "offset": offset})
        result = {"months": months, "total": total, "hot": True}
        self._timeline_index_cache[key] = result
        return result

    def timeline_offset(self, file_id: int, category: int, starred_only=False) -> int | None:
        """Return the photo's zero-based position in newest-first timeline order."""
        if not self.ready:
            return None
        generation = int(self._active_generation)
        starred_sql = "AND starred = 1" if starred_only else ""
        with self.db.connect() as conn:
            current = conn.execute(
                f"""
                SELECT date_key
                FROM web_photo_cache
                WHERE generation = ? AND category = ? AND file_id = ? {starred_sql}
                """,
                (generation, int(category), int(file_id)),
            ).fetchone()
            if not current:
                return None
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS photo_count
                FROM web_photo_cache
                WHERE generation = ? AND category = ? {starred_sql}
                  AND (date_key > ? OR (date_key = ? AND file_id > ?))
                """,
                (
                    generation,
                    int(category),
                    current["date_key"],
                    current["date_key"],
                    int(file_id),
                ),
            ).fetchone()
        return int(row["photo_count"]) if row else 0

    def review_count(self) -> int | None:
        value = self._state("review_count")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def decrement_review_count(self, amount: int):
        current = self.review_count()
        if current is not None:
            self._set_states(
                {
                    "review_count": max(0, current - max(int(amount), 0)),
                    "source_signature": self.source_signature(),
                }
            )

    def refresh_review_count(self):
        if not self.ready:
            return
        count = len(load_review_candidates(limit=600, offset=0, db=self.db))
        self._set_states(
            {
                "review_count": count,
                "source_signature": self.source_signature(),
            }
        )

    def _segment_starts(self, category: int) -> list[int]:
        generation = int(self._active_generation)
        key = (generation, int(category))
        cached = self._segment_starts_cache.get(key)
        if cached is not None:
            return cached
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT random_rank
                FROM web_photo_cache
                WHERE generation = ? AND category = ? AND segment_start = 1
                ORDER BY random_rank
                """,
                (generation, int(category)),
            ).fetchall()
        starts = [int(row["random_rank"]) for row in rows]
        self._segment_starts_cache[key] = starts
        return starts

    def page(self, category: int, limit: int, offset=0, timeline=False, starred_only=False) -> tuple[list[dict], int]:
        if not self.ready:
            return [], 0
        total = self._count(category, starred_only=starred_only)
        if total <= 0 or offset >= total:
            return [], total
        generation = int(self._active_generation)
        order_sql = "date_key DESC, file_id DESC" if timeline else "random_rank ASC, file_id ASC"
        logical_offset = int(offset)
        if not timeline:
            rotation_key = (generation, category, bool(starred_only))
            if rotation_key not in self._rotations:
                segment_starts = [] if starred_only else self._segment_starts(category)
                self._rotations[rotation_key] = (
                    random.choice(segment_starts) if segment_starts else random.randrange(total)
                )
            rotation = self._rotations[rotation_key]
            logical_offset = (rotation + int(offset)) % total

        starred_sql = "AND starred = 1" if starred_only else ""

        def fetch(fetch_limit: int, fetch_offset: int):
            with self.db.connect() as conn:
                return conn.execute(
                    f"""
                    SELECT file_id, payload_json, thumbnail_path, original_path
                    FROM web_photo_cache
                    WHERE generation = ? AND category = ?
                      {starred_sql}
                    ORDER BY {order_sql}
                    LIMIT ? OFFSET ?
                    """,
                    (
                        generation,
                        category,
                        fetch_limit,
                        fetch_offset,
                    ),
                ).fetchall()

        target_limit = min(limit, total - int(offset))
        first_limit = min(target_limit, total - logical_offset)
        rows = list(fetch(first_limit, logical_offset))
        if len(rows) < target_limit:
            rows.extend(fetch(target_limit - len(rows), 0))
        items = []
        for row in rows:
            file_id = int(row["file_id"])
            self._path_cache[file_id] = (row["thumbnail_path"], row["original_path"])
            items.append(json.loads(row["payload_json"]))
        return items, total

    def rotate_random(self, category: int, starred_only=False) -> int | None:
        if not self.ready:
            return None
        generation = int(self._active_generation)
        category = int(category)
        total = self._count(category, starred_only=starred_only)
        if total <= 0:
            return None
        key = (generation, category, bool(starred_only))
        candidates = [] if starred_only else self._segment_starts(category)
        with self._rotation_lock:
            current = self._rotations.get(key)
            if candidates:
                available = [candidate for candidate in candidates if candidate != current]
                next_rotation = random.choice(available or candidates)
            else:
                next_rotation = random.randrange(total)
                if total > 1 and next_rotation == current:
                    next_rotation = (next_rotation + random.randrange(1, total)) % total
            self._rotations[key] = int(next_rotation)
            return int(next_rotation)

    def context(self, file_id: int, category: int, before=120, after=120, starred_only=False) -> dict | None:
        if not self.ready:
            return None
        generation = int(self._active_generation)
        starred_sql = "AND starred = 1" if starred_only else ""
        with self.db.connect() as conn:
            current = conn.execute(
                f"""
                SELECT file_id, date_key, payload_json, thumbnail_path, original_path
                FROM web_photo_cache
                WHERE generation = ? AND category = ? AND file_id = ? {starred_sql}
                """,
                (generation, category, int(file_id)),
            ).fetchone()
            if not current:
                return None
            newer = conn.execute(
                f"""
                SELECT file_id, payload_json, thumbnail_path, original_path
                FROM web_photo_cache
                WHERE generation = ? AND category = ? {starred_sql}
                  AND (date_key > ? OR (date_key = ? AND file_id > ?))
                ORDER BY date_key ASC, file_id ASC
                LIMIT ?
                """,
                (generation, category, current["date_key"], current["date_key"], int(file_id), int(before)),
            ).fetchall()
            older = conn.execute(
                f"""
                SELECT file_id, payload_json, thumbnail_path, original_path
                FROM web_photo_cache
                WHERE generation = ? AND category = ? {starred_sql}
                  AND (date_key < ? OR (date_key = ? AND file_id < ?))
                ORDER BY date_key DESC, file_id DESC
                LIMIT ?
                """,
                (generation, category, current["date_key"], current["date_key"], int(file_id), int(after)),
            ).fetchall()
        rows = list(reversed(newer)) + [current] + list(older)
        items = []
        for row in rows:
            row_id = int(row["file_id"])
            self._path_cache[row_id] = (row["thumbnail_path"], row["original_path"])
            items.append(json.loads(row["payload_json"]))
        return {
            "items": items,
            "index": len(newer),
            "beforeCount": len(newer),
            "afterCount": len(older),
            "hot": True,
        }

    def media_paths(self, file_id: int) -> tuple[str, str] | None:
        file_id = int(file_id)
        cached = self._path_cache.get(file_id)
        if cached:
            return cached
        if not self.ready:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT thumbnail_path, original_path
                FROM web_photo_cache
                WHERE generation = ? AND file_id = ?
                LIMIT 1
                """,
                (self._active_generation, file_id),
            ).fetchone()
        if not row:
            return None
        value = (row["thumbnail_path"], row["original_path"])
        self._path_cache[file_id] = value
        return value

    def set_starred_many(self, file_ids: Iterable[int], starred: bool):
        ids = _normalize_ids(file_ids, limit=100000)
        if not ids or not self.ready:
            return
        generation = int(self._active_generation)
        with self.db.connect() as conn:
            for start in range(0, len(ids), CACHE_BATCH_SIZE):
                batch = ids[start:start + CACHE_BATCH_SIZE]
                placeholders = ",".join("?" for _ in batch)
                rows = conn.execute(
                    f"""
                    SELECT category, file_id, payload_json
                    FROM web_photo_cache
                    WHERE generation = ? AND file_id IN ({placeholders})
                    """,
                    [generation, *batch],
                ).fetchall()
                updates = []
                for row in rows:
                    payload = json.loads(row["payload_json"])
                    payload["starred"] = bool(starred)
                    updates.append((
                        1 if starred else 0,
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        generation,
                        int(row["category"]),
                        int(row["file_id"]),
                    ))
                conn.executemany(
                    """
                    UPDATE web_photo_cache SET starred = ?, payload_json = ?
                    WHERE generation = ? AND category = ? AND file_id = ?
                    """,
                    updates,
                )
        self._set_states({"source_signature": self.source_signature()})
        self._count_cache.clear()
        self._timeline_index_cache.clear()
        self._segment_starts_cache.clear()

    def set_starred(self, file_id: int, starred: bool):
        if not self.ready:
            return
        self.set_starred_many([file_id], starred)

    def evict_ids(self, file_ids: Iterable[int]):
        ids = _normalize_ids(file_ids)
        if not ids or not self.ready:
            return
        generation = int(self._active_generation)
        for start in range(0, len(ids), CACHE_BATCH_SIZE):
            batch = ids[start:start + CACHE_BATCH_SIZE]
            placeholders = ",".join("?" for _ in batch)
            with self.db.connect() as conn:
                conn.execute(
                    f"DELETE FROM web_photo_cache WHERE generation = ? AND file_id IN ({placeholders})",
                    [generation, *batch],
                )
        for file_id in ids:
            self._path_cache.pop(file_id, None)
        self._rotations.clear()
        self._count_cache.clear()
        self._timeline_index_cache.clear()
        self._segment_starts_cache.clear()

    def refresh_ids(self, file_ids: Iterable[int]):
        ids = _normalize_ids(file_ids)
        if not ids or not self.ready:
            return
        with self._refresh_lock:
            generation = int(self._active_generation)
            for start in range(0, len(ids), CACHE_BATCH_SIZE):
                batch = ids[start:start + CACHE_BATCH_SIZE]
                placeholders = ",".join("?" for _ in batch)
                with self.db.connect() as conn:
                    conn.execute(
                        f"DELETE FROM web_photo_cache WHERE generation = ? AND file_id IN ({placeholders})",
                        [generation, *batch],
                    )
                for category in (CATEGORY_LIFE, CATEGORY_SAMPLE):
                    rows = self._load_source_rows(category, batch)
                    self._insert_rows(generation, category, rows)
            self._path_cache.clear()
            self._rotations.clear()
            self._count_cache.clear()
            self._timeline_index_cache.clear()
            self._segment_starts_cache.clear()
            counts = self.counts()
            self._set_states(
                {
                    "source_signature": self.source_signature(),
                    "life_count": counts["life"],
                    "sample_count": counts["sample"],
                }
            )

    def refresh_ids_async(self, file_ids: Iterable[int]):
        ids = _normalize_ids(file_ids)
        if not ids:
            return

        def run():
            try:
                self.refresh_ids(ids)
            except Exception:
                logger.exception("网页热启动快照增量刷新失败")

        threading.Thread(target=run, name="web-hot-cache-incremental", daemon=True).start()
