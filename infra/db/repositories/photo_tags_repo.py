from typing import List
from core.models import PhotoTag


class PhotoTagsRepository:
    def __init__(self, db):
        self.db = db

    def insert_or_ignore(self, tag: PhotoTag) -> int:
        try:
            with self.db.connect() as conn:
                result = conn.execute(
                    "INSERT OR IGNORE INTO photo_tags (file_id, tag, created_at) VALUES (?, ?, ?)",
                    tag.as_row()
                )
                return result.rowcount
        except Exception:
            return 0

    def get_tags_for_file(self, file_id: int) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT tag FROM photo_tags WHERE file_id = ?", (file_id,)).fetchall()
        return [row[0] for row in rows]
