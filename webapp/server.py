from __future__ import annotations

import json
import mimetypes
import os
import shutil
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from business.classifier.nsfw_review import (
    dismiss_review_candidates,
    load_review_candidates,
    mark_review_candidates_as_sample,
)
from business.classifier.photo_category_override import batch_set_photo_category
from business.classifier.category_rules import category_match_sql
from business.deletion_queue import (
    delete_pending_originals,
    load_pending_deletions,
    pending_delete_filter_sql,
    pending_deletion_count,
    pending_deletion_ids,
    queue_for_deletion,
    restore_from_deletion,
)
from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from db_manager import Database
from logger_setup import logger
from business.recommendation import count_category_photos, load_category_photos_batch
from webapp.hot_cache import WebHotCache


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_JSON_BODY = 2 * 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"
SUPPORTED_ORIGINAL_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".avif",
}


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


def _compact_folder(path: str | None) -> str:
    parts = [part for part in (path or "").replace("\\", "/").split("/") if part]
    return " / ".join(parts[-3:])


def _photo_tags_by_id(conn, file_ids: Iterable[int], per_photo=12) -> dict[int, list[str]]:
    ids = _normalize_ids(file_ids, limit=1000)
    result = {file_id: [] for file_id in ids}
    for start in range(0, len(ids), 400):
        batch = ids[start:start + 400]
        placeholders = ",".join("?" for _ in batch)
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
            if tag and len(result[file_id]) < per_photo and tag not in result[file_id]:
                result[file_id].append(tag)
    return result


def _photo_payload(photo: dict) -> dict:
    file_id = int(photo.get("id") or photo.get("file_id"))
    width = photo.get("width")
    height = photo.get("height")
    return {
        "id": file_id,
        "name": photo.get("file_name") or f"照片 {file_id}",
        "folder": _compact_folder(photo.get("folder_path")),
        "date": photo.get("date_taken") or photo.get("file_mtime") or "",
        "width": int(width) if width else None,
        "height": int(height) if height else None,
        "thumbnailUrl": f"/media/thumbnail/{file_id}",
        "originalUrl": f"/media/original/{file_id}",
        "reasons": list(photo.get("reasons") or []),
        "reasonText": photo.get("reason_text") or "",
        "starred": bool(photo.get("is_starred")),
        "tags": list(photo.get("tags") or []),
    }


class WebPhotoService:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self._stats_cache: tuple[float, dict] | None = None
        self._stats_lock = threading.Lock()
        self.hot_cache: WebHotCache | None = None
        try:
            self.hot_cache = WebHotCache(self.db)
            was_ready = self.hot_cache.ready
            self.hot_cache.ensure_ready()
            if was_ready:
                self.hot_cache.refresh_if_stale_async()
        except Exception:
            logger.exception("网页热启动快照不可用，回退到实时查询")
            self.hot_cache = None

    def list_photos(
        self,
        category: int,
        limit: int,
        offset: int = 0,
        random_order: bool = True,
        exclude_ids: Iterable[int] | None = None,
        starred_only: bool = False,
    ) -> dict:
        if self.hot_cache and self.hot_cache.ready:
            items, total = self.hot_cache.page(
                category,
                limit,
                offset=offset,
                timeline=not random_order,
                starred_only=starred_only,
            )
            return {
                "items": items,
                "hasMore": offset + len(items) < total,
                "hot": True,
            }
        with self.db.connect() as conn:
            photos = load_category_photos_batch(
                conn,
                category,
                offset,
                limit=limit,
                random_order=random_order,
                exclude_ids=_normalize_ids(exclude_ids, limit=800),
                require_thumbnail=True,
                starred_only=starred_only,
            )
            tags_by_id = _photo_tags_by_id(conn, (photo["id"] for photo in photos))
            for photo in photos:
                photo["tags"] = tags_by_id.get(int(photo["id"]), [])
        items = [_photo_payload(photo) for photo in photos]
        return {"items": items, "hasMore": len(items) >= limit, "hot": False}

    def refresh_random(self, category: int, limit=72, starred_only=False) -> dict:
        if category not in {CATEGORY_LIFE, CATEGORY_SAMPLE}:
            raise ValueError("category must be 1 or 2")
        limit = min(max(int(limit), 1), 80)
        if self.hot_cache and self.hot_cache.ready:
            self.hot_cache.rotate_random(category, starred_only=starred_only)
        page = self.list_photos(
            category,
            limit,
            offset=0,
            random_order=True,
            starred_only=starred_only,
        )
        page["offset"] = 0
        return page

    def timeline_index(self, category: int, starred_only: bool = False) -> dict:
        if self.hot_cache and self.hot_cache.ready:
            return self.hot_cache.timeline_index(category, starred_only=starred_only)
        with self.db.connect() as conn:
            total = count_category_photos(conn, category, starred_only=starred_only)
        return {"months": [], "total": total, "hot": False}

    def timeline_location(self, file_id: int, category: int, starred_only: bool = False) -> dict:
        file_id = int(file_id)
        if category not in {CATEGORY_LIFE, CATEGORY_SAMPLE}:
            raise ValueError("category must be 1 or 2")
        if self.hot_cache and self.hot_cache.ready:
            offset = self.hot_cache.timeline_offset(
                file_id,
                category,
                starred_only=starred_only,
            )
            if offset is not None:
                return {"id": file_id, "offset": offset, "hot": True}

        time_sql = "COALESCE(NULLIF(pm.date_taken, ''), NULLIF(f.file_mtime, ''), '')"
        visible_sql = (
            "f.is_image = 1 "
            "AND pm.thumbnail_path IS NOT NULL "
            "AND pm.thumbnail_path != '' "
            "AND pm.thumbnail_path != '__FAILED__' "
            "AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0) "
            "AND (f.path_status IS NULL OR f.path_status NOT IN "
            "('damaged_path', 'missing', 'stat_failed', 'outside_root')) "
            + pending_delete_filter_sql("f")
        )
        category_sql = category_match_sql(category)
        starred_sql = " AND pm.is_starred = 1" if starred_only else ""
        joins = """
            FROM files f
            JOIN photo_metadata pm ON pm.file_id = f.id
            LEFT JOIN folder_categories fc ON fc.folder_path = f.folder_path
        """
        with self.db.connect() as conn:
            current = conn.execute(
                f"SELECT {time_sql} AS date_key {joins} "
                f"WHERE f.id = ? AND {category_sql} AND {visible_sql}{starred_sql}",
                (file_id, category),
            ).fetchone()
            if not current:
                raise FileNotFoundError(file_id)
            row = conn.execute(
                f"SELECT COUNT(*) AS photo_count {joins} "
                f"WHERE {category_sql} AND {visible_sql}{starred_sql} "
                f"AND (({time_sql} > ?) OR ({time_sql} = ? AND f.id > ?))",
                (category, current["date_key"], current["date_key"], file_id),
            ).fetchone()
        return {"id": file_id, "offset": int(row["photo_count"]), "hot": False}

    def review_candidates(self, limit=240, offset=0) -> list[dict]:
        candidates = load_review_candidates(limit=limit, offset=offset, db=self.db)
        return [_photo_payload(candidate) for candidate in candidates]

    def review_candidate_ids(self, limit=100000) -> list[int]:
        result = []
        while len(result) < limit:
            batch_limit = min(1000, limit - len(result))
            candidates = load_review_candidates(
                limit=batch_limit,
                offset=len(result),
                db=self.db,
            )
            result.extend(int(candidate["id"]) for candidate in candidates)
            if len(candidates) < batch_limit:
                break
        return result

    def pending_deletions(self, limit=240, offset=0) -> list[dict]:
        return [
            _photo_payload(photo)
            for photo in load_pending_deletions(limit=limit, offset=offset, db=self.db)
        ]

    def pending_deletion_ids(self, limit=100000) -> list[int]:
        return pending_deletion_ids(limit=limit, db=self.db)

    def queue_deletion(self, ids: Iterable[int]) -> dict:
        normalized = _normalize_ids(ids)
        result = queue_for_deletion(normalized, db=self.db)
        if self.hot_cache:
            self.hot_cache.evict_ids(normalized)
            self.hot_cache.refresh_review_count()
        self.invalidate_stats()
        return result

    def restore_deletion(self, ids: Iterable[int]) -> dict:
        normalized = _normalize_ids(ids)
        result = restore_from_deletion(normalized, db=self.db)
        if self.hot_cache:
            if len(normalized) <= 100:
                self.hot_cache.refresh_ids(normalized)
            else:
                self.hot_cache.refresh_ids_async(normalized)
            self.hot_cache.refresh_review_count()
        self.invalidate_stats()
        return result

    def delete_originals(self, ids: Iterable[int], confirmation: str) -> dict:
        normalized = _normalize_ids(ids, limit=5000)
        result = delete_pending_originals(
            normalized,
            confirmation=confirmation,
            db=self.db,
        )
        if self.hot_cache:
            self.hot_cache.evict_ids(normalized)
            self.hot_cache.refresh_review_count()
        self.invalidate_stats()
        return result

    def photo_context(
        self,
        file_id: int,
        category: int,
        before=120,
        after=120,
        starred_only: bool = False,
    ) -> dict:
        file_id = int(file_id)
        if category not in {CATEGORY_LIFE, CATEGORY_SAMPLE}:
            raise ValueError("category must be 1 or 2")
        before = min(max(int(before), 1), 200)
        after = min(max(int(after), 1), 200)
        if self.hot_cache and self.hot_cache.ready:
            cached = self.hot_cache.context(
                file_id,
                category,
                before=before,
                after=after,
                starred_only=starred_only,
            )
            if cached:
                return cached
        time_sql = "COALESCE(NULLIF(pm.date_taken, ''), NULLIF(f.file_mtime, ''), '')"
        visible_sql = (
            "f.is_image = 1 "
            "AND pm.thumbnail_path IS NOT NULL "
            "AND pm.thumbnail_path != '' "
            "AND pm.thumbnail_path != '__FAILED__' "
            "AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0) "
            "AND (f.path_status IS NULL OR f.path_status NOT IN "
            "('damaged_path', 'missing', 'stat_failed', 'outside_root')) "
            + pending_delete_filter_sql("f")
        )
        select_sql = f"""
            SELECT f.id, f.file_name, f.folder_path, f.file_mtime,
                   f.folder_name AS folder_display, pm.thumbnail_path,
                   pm.width, pm.height, pm.date_taken, pm.is_starred
            FROM files f
            JOIN photo_metadata pm ON pm.file_id = f.id
            LEFT JOIN folder_categories fc ON fc.folder_path = f.folder_path
        """
        category_sql = category_match_sql(category)
        starred_sql = " AND pm.is_starred = 1" if starred_only else ""

        with self.db.connect() as conn:
            current = conn.execute(
                select_sql + " WHERE f.id = ? AND " + visible_sql + starred_sql,
                (file_id,),
            ).fetchone()
            if not current:
                raise FileNotFoundError(file_id)
            pivot = current["date_taken"] or current["file_mtime"] or ""
            older = conn.execute(
                select_sql
                + f"""
                    WHERE {category_sql} AND {visible_sql}{starred_sql}
                      AND (({time_sql} < ?) OR ({time_sql} = ? AND f.id < ?))
                    ORDER BY {time_sql} DESC, f.id DESC
                    LIMIT ?
                """,
                (category, pivot, pivot, file_id, after),
            ).fetchall()
            newer = conn.execute(
                select_sql
                + f"""
                    WHERE {category_sql} AND {visible_sql}{starred_sql}
                      AND (({time_sql} > ?) OR ({time_sql} = ? AND f.id > ?))
                    ORDER BY {time_sql} ASC, f.id ASC
                    LIMIT ?
                """,
                (category, pivot, pivot, file_id, before),
            ).fetchall()

        # Keep exactly the same newest-to-oldest direction as the main timeline.
        rows = list(reversed(newer)) + [current] + list(older)
        return {
            "items": [_photo_payload(dict(row)) for row in rows],
            "index": len(newer),
            "beforeCount": len(newer),
            "afterCount": len(older),
        }

    def stats(self) -> dict:
        now = time.monotonic()
        with self._stats_lock:
            if self._stats_cache and now - self._stats_cache[0] < 20:
                return dict(self._stats_cache[1])
            if self.hot_cache and self.hot_cache.ready:
                counts = self.hot_cache.counts()
                life = counts["life"]
                sample = counts["sample"]
                review = self.hot_cache.review_count()
            else:
                with self.db.connect() as conn:
                    life = count_category_photos(conn, CATEGORY_LIFE)
                    sample = count_category_photos(conn, CATEGORY_SAMPLE)
                review = None
            if review is None:
                review = len(load_review_candidates(limit=600, db=self.db))
            payload = {
                "life": life,
                "sample": sample,
                "review": review,
                "pendingDeletion": pending_deletion_count(db=self.db),
                "total": life + sample,
            }
            self._stats_cache = (now, payload)
            return dict(payload)

    def set_category(self, ids: Iterable[int], category: int) -> dict:
        if category not in {CATEGORY_LIFE, CATEGORY_SAMPLE}:
            raise ValueError("category must be 1 or 2")
        normalized = _normalize_ids(ids)
        result = batch_set_photo_category(normalized, category=category, user="web", db=self.db)
        if self.hot_cache:
            self.hot_cache.evict_ids(normalized)
            if len(normalized) <= 100:
                self.hot_cache.refresh_ids(normalized)
            else:
                self.hot_cache.refresh_ids_async(normalized)
        self.invalidate_stats()
        return result

    def mark_review_sample(self, ids: Iterable[int]) -> dict:
        normalized = _normalize_ids(ids)
        result = mark_review_candidates_as_sample(normalized, db=self.db)
        if self.hot_cache:
            self.hot_cache.evict_ids(normalized)
            if len(normalized) <= 100:
                self.hot_cache.refresh_ids(normalized)
            else:
                self.hot_cache.refresh_ids_async(normalized)
            self.hot_cache.decrement_review_count(result.get("updated", 0))
        self.invalidate_stats()
        return result

    def dismiss_review(self, ids: Iterable[int]) -> dict:
        normalized = _normalize_ids(ids)
        result = dismiss_review_candidates(normalized, db=self.db)
        if self.hot_cache:
            self.hot_cache.decrement_review_count(result.get("inserted", 0))
        self.invalidate_stats()
        return result

    def set_starred_many(self, file_ids: Iterable[int], starred: bool) -> dict:
        ids = _normalize_ids(file_ids, limit=100000)
        if not ids:
            raise ValueError("ids must not be empty")
        with self.db.connect() as conn:
            existing = set()
            for start in range(0, len(ids), 800):
                batch = ids[start:start + 800]
                placeholders = ",".join("?" for _ in batch)
                rows = conn.execute(
                    f"SELECT id FROM files WHERE id IN ({placeholders})",
                    batch,
                ).fetchall()
                existing.update(int(row["id"]) for row in rows)
            if len(ids) == 1 and ids[0] not in existing:
                raise FileNotFoundError(ids[0])
            valid_ids = [file_id for file_id in ids if file_id in existing]
            conn.executemany(
                """
                INSERT INTO photo_metadata (file_id, is_starred, indexed_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(file_id) DO UPDATE SET
                    is_starred = excluded.is_starred,
                    indexed_at = datetime('now')
                """,
                [(file_id, 1 if starred else 0) for file_id in valid_ids],
            )
        if self.hot_cache:
            self.hot_cache.set_starred_many(valid_ids, starred)
        self.invalidate_stats()
        return {
            "id": valid_ids[0] if len(valid_ids) == 1 else None,
            "ids": valid_ids,
            "updated": len(valid_ids),
            "starred": bool(starred),
        }

    def set_starred(self, file_id: int, starred: bool) -> dict:
        file_id = int(file_id)
        self.set_starred_many([file_id], starred)
        return {"id": file_id, "starred": bool(starred)}

    def media_path(self, file_id: int, original: bool = False) -> Path | None:
        if self.hot_cache:
            cached_paths = self.hot_cache.media_paths(file_id)
            if cached_paths:
                thumbnail = Path(cached_paths[0] or "")
                source = Path(cached_paths[1] or "")
                candidates = [thumbnail]
                if original:
                    candidates = [source] if source.suffix.lower() in SUPPORTED_ORIGINAL_EXTENSIONS else []
                for path in candidates:
                    try:
                        if path.is_file():
                            return path
                    except OSError:
                        continue
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT f.file_path, pm.thumbnail_path
                FROM files f
                LEFT JOIN photo_metadata pm ON pm.file_id = f.id
                WHERE f.id = ? AND f.is_image = 1
                """,
                (int(file_id),),
            ).fetchone()
        if not row:
            return None
        thumbnail = Path(row["thumbnail_path"] or "")
        candidates = [thumbnail]
        if original:
            source = Path(row["file_path"] or "")
            candidates = [source] if source.suffix.lower() in SUPPORTED_ORIGINAL_EXTENSIONS else []
        for path in candidates:
            try:
                if path.is_file():
                    return path
            except OSError:
                continue
        return None

    def invalidate_stats(self):
        with self._stats_lock:
            self._stats_cache = None


class PhotoWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler_factory(service: WebPhotoService, static_dir: Path):
    static_root = static_dir.resolve()

    class PhotoRequestHandler(BaseHTTPRequestHandler):
        server_version = "PhotoMemories/1.0"

        def log_message(self, fmt, *args):
            logger.debug("web: " + fmt, *args)

        def do_GET(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/health":
                    self._json({"ok": True, "service": "photo-memories"})
                    return
                if parsed.path == "/api/stats":
                    self._json(service.stats())
                    return
                if parsed.path == "/api/photos":
                    self._get_photos(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/timeline-index":
                    self._get_timeline_index(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/timeline-location":
                    self._get_timeline_location(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/review":
                    self._get_review(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/review/ids":
                    self._get_review_ids(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/deletions":
                    self._get_deletions(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/deletions/ids":
                    self._get_deletion_ids(parse_qs(parsed.query))
                    return
                if parsed.path == "/api/photo-context":
                    self._get_photo_context(parse_qs(parsed.query))
                    return
                if parsed.path.startswith("/media/thumbnail/"):
                    self._send_media(parsed.path.rsplit("/", 1)[-1], original=False)
                    return
                if parsed.path.startswith("/media/original/"):
                    self._send_media(parsed.path.rsplit("/", 1)[-1], original=True)
                    return
                self._send_static(parsed.path)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                logger.exception("网页请求失败: %s", parsed.path)
                self._json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                ids = _normalize_ids(payload.get("ids"))
                if parsed.path == "/api/category":
                    self._json(service.set_category(ids, int(payload.get("category"))))
                    return
                if parsed.path == "/api/review/sample":
                    self._json(service.mark_review_sample(ids))
                    return
                if parsed.path == "/api/review/dismiss":
                    self._json(service.dismiss_review(ids))
                    return
                if parsed.path == "/api/star":
                    if ids:
                        self._json(service.set_starred_many(ids, bool(payload.get("starred"))))
                    else:
                        self._json(service.set_starred(int(payload.get("id")), bool(payload.get("starred"))))
                    return
                if parsed.path == "/api/deletions/queue":
                    self._json(service.queue_deletion(ids))
                    return
                if parsed.path == "/api/deletions/restore":
                    self._json(service.restore_deletion(ids))
                    return
                if parsed.path == "/api/deletions/delete-originals":
                    self._json(service.delete_originals(ids, str(payload.get("confirmation") or "")))
                    return
                if parsed.path == "/api/photos/refresh":
                    category_value = str(payload.get("category") or "life")
                    category = CATEGORY_SAMPLE if category_value in {"2", "sample"} else CATEGORY_LIFE
                    self._json(service.refresh_random(
                        category,
                        limit=int(payload.get("limit") or 72),
                        starred_only=bool(payload.get("starred")),
                    ))
                    return
                self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._json({"error": "photo not found"}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                logger.exception("网页写入请求失败: %s", parsed.path)
                self._json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def _get_photos(self, query: dict):
            category_name = (query.get("category") or ["life"])[0]
            category = CATEGORY_SAMPLE if category_name in {"2", "sample"} else CATEGORY_LIFE
            limit = min(max(int((query.get("limit") or [48])[0]), 1), 80)
            mode = (query.get("mode") or ["random"])[0]
            offset = max(int((query.get("offset") or [0])[0]), 0)
            excludes = []
            for value in query.get("exclude", []):
                excludes.extend(value.split(","))
            page = service.list_photos(
                category,
                limit,
                offset=offset,
                random_order=mode != "timeline",
                exclude_ids=excludes,
                starred_only=(query.get("starred") or ["0"])[0].lower() in {"1", "true", "yes"},
            )
            page["offset"] = offset
            self._json(page)

        def _get_review(self, query: dict):
            limit = min(max(int((query.get("limit") or [240])[0]), 1), 600)
            offset = max(int((query.get("offset") or [0])[0]), 0)
            items = service.review_candidates(limit=limit, offset=offset)
            self._json({"items": items, "hasMore": len(items) >= limit})

        def _get_timeline_index(self, query: dict):
            category_name = (query.get("category") or ["life"])[0]
            category = CATEGORY_SAMPLE if category_name in {"2", "sample"} else CATEGORY_LIFE
            starred_only = (query.get("starred") or ["0"])[0].lower() in {"1", "true", "yes"}
            self._json(service.timeline_index(category, starred_only=starred_only))

        def _get_timeline_location(self, query: dict):
            file_id = int((query.get("id") or [0])[0])
            category_name = (query.get("category") or ["life"])[0]
            category = CATEGORY_SAMPLE if category_name in {"2", "sample"} else CATEGORY_LIFE
            starred_only = (query.get("starred") or ["0"])[0].lower() in {"1", "true", "yes"}
            self._json(service.timeline_location(file_id, category, starred_only=starred_only))

        def _get_review_ids(self, query: dict):
            limit = min(max(int((query.get("limit") or [100000])[0]), 1), 100000)
            ids = service.review_candidate_ids(limit=limit)
            self._json({"ids": ids, "count": len(ids), "truncated": len(ids) >= limit})

        def _get_deletions(self, query: dict):
            limit = min(max(int((query.get("limit") or [240])[0]), 1), 600)
            offset = max(int((query.get("offset") or [0])[0]), 0)
            items = service.pending_deletions(limit=limit, offset=offset)
            self._json({"items": items, "hasMore": len(items) >= limit})

        def _get_deletion_ids(self, query: dict):
            limit = min(max(int((query.get("limit") or [100000])[0]), 1), 100000)
            ids = service.pending_deletion_ids(limit=limit)
            self._json({"ids": ids, "count": len(ids), "truncated": len(ids) >= limit})

        def _get_photo_context(self, query: dict):
            file_id = int((query.get("id") or [0])[0])
            category_name = (query.get("category") or ["life"])[0]
            category = CATEGORY_SAMPLE if category_name in {"2", "sample"} else CATEGORY_LIFE
            before = int((query.get("before") or [120])[0])
            after = int((query.get("after") or [120])[0])
            starred_only = (query.get("starred") or ["0"])[0].lower() in {"1", "true", "yes"}
            self._json(
                service.photo_context(
                    file_id,
                    category,
                    before=before,
                    after=after,
                    starred_only=starred_only,
                )
            )

        def _read_json(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("invalid content length") from exc
            if length <= 0 or length > MAX_JSON_BODY:
                raise ValueError("invalid request body")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            return payload

        def _json(self, payload: dict, status=HTTPStatus.OK):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _send_media(self, raw_id: str, original: bool):
            try:
                file_id = int(unquote(raw_id))
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            path = service.media_path(file_id, original=original)
            if path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            stat = path.stat()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(stat.st_size))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.send_header("X-Photo-Source", "original" if original else "thumbnail")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile, length=256 * 1024)

        def _send_static(self, request_path: str):
            relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
            candidate = (static_root / relative).resolve()
            if static_root not in candidate.parents and candidate != static_root:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not candidate.is_file():
                candidate = static_root / "index.html"
            body = candidate.read_bytes()
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            if candidate.suffix == ".js":
                content_type = "text/javascript"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

    return PhotoRequestHandler


def create_server(
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    db: Database | None = None,
    static_dir: Path | None = None,
) -> PhotoWebServer:
    service = WebPhotoService(db=db)
    handler = _handler_factory(service, Path(static_dir or STATIC_DIR))
    return PhotoWebServer((host, int(port)), handler)


def _create_available_server(host: str, preferred_port: int) -> PhotoWebServer:
    last_error = None
    for port in range(preferred_port, preferred_port + 10):
        try:
            return create_server(host=host, port=port)
        except OSError as exc:
            last_error = exc
    raise OSError(f"无法在 {preferred_port}-{preferred_port + 9} 启动本地网页") from last_error


def run_web(host=DEFAULT_HOST, port=DEFAULT_PORT, open_browser=True):
    server = _create_available_server(host, int(port))
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}/"
    logger.info("本地网页已启动: %s", url)
    print(f"照片回忆网页版已启动：{url}")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url, new=2)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        logger.info("本地网页已停止")
    finally:
        server.server_close()
