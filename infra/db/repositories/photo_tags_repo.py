from typing import List
from datetime import datetime
from core.models import PhotoTag


class PhotoTagsRepository:
    def __init__(self, db):
        self.db = db

    def insert_or_ignore(self, tag: PhotoTag) -> int:
        try:
            with self.db.connect() as conn:
                result = conn.execute(
                    "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
                    (tag.file_id, tag.tag, tag.source)
                )
                return result.rowcount
        except Exception:
            return 0

    def get_tags_for_file(self, file_id: int) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT tag FROM photo_tags WHERE file_id = ?", (file_id,)).fetchall()
        return [row[0] for row in rows]

    def get_tags_for_file_by_source(self, file_id: int, source: str) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT tag FROM photo_tags WHERE file_id = ? AND source = ?",
                (file_id, source)
            ).fetchall()
        return [row[0] for row in rows]

    def get_file_ids_by_source(self, source: str) -> set:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT file_id FROM photo_tags WHERE source = ?",
                (source,)
            ).fetchall()
        return {r[0] for r in rows}

    def get_pending_file_ids(self, source: str = "siglip", limit: int = 128) -> tuple[list[int], int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT pm.file_id
                FROM photo_metadata pm
                JOIN files f ON f.id = pm.file_id
                LEFT JOIN photo_tag_status ts
                  ON ts.file_id = pm.file_id AND ts.source = ?
                WHERE pm.thumbnail_path IS NOT NULL
                  AND pm.thumbnail_path != ''
                  AND pm.thumbnail_path != '__FAILED__'
                  AND COALESCE(pm.thumbnail_status, 'ok') IN ('ok', 'recovered')
                  AND f.is_image = 1
                  AND (f.path_status IS NULL OR f.path_status NOT IN
                       ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                  AND (
                      ts.file_id IS NULL
                      OR ts.status NOT IN ('processed_ok', 'ok', 'done', 'skipped', 'failed')
                      OR ts.source_file_size IS NULL
                      OR ts.source_file_mtime IS NULL
                      OR ts.source_file_size != f.file_size
                      OR ts.source_file_mtime != f.file_mtime
                  )
                ORDER BY pm.file_id
                """,
                (source,),
            ).fetchall()
        pending = [r[0] for r in rows]
        if limit and limit > 0:
            return pending[:limit], len(pending)
        return pending, len(pending)

    def count_pending(self, source: str = "siglip") -> int:
        return self.get_pending_file_ids(source=source, limit=0)[1]

    def update_status_many(self, results: list[tuple[int, str, str | None]], source: str = "siglip") -> int:
        if not results:
            return 0
        now = datetime.now().isoformat()
        with self.db.connect() as conn:
            rows = []
            for file_id, status, error in results:
                file_row = conn.execute(
                    "SELECT file_size, file_mtime FROM files WHERE id = ?",
                    (file_id,),
                ).fetchone()
                file_size = file_row[0] if file_row else None
                file_mtime = file_row[1] if file_row else None
                rows.append((file_id, source, status, error, file_size, file_mtime, now))
            conn.executemany(
                """
                INSERT INTO photo_tag_status
                    (file_id, source, status, error, source_file_size, source_file_mtime, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id, source) DO UPDATE SET
                    status = excluded.status,
                    error = excluded.error,
                    source_file_size = excluded.source_file_size,
                    source_file_mtime = excluded.source_file_mtime,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return len(results)
