from typing import List
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
