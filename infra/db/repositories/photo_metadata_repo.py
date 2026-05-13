from typing import List, Optional
from core.models import PhotoMetadata


class PhotoMetadataRepository:
    def __init__(self, db):
        self.db = db

    def get_unindexed_photos(self) -> List[tuple]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id, f.file_path FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1 AND pm.file_id IS NULL
            """).fetchall()
        return rows

    def insert_or_replace(self, metadata: PhotoMetadata):
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO photo_metadata
                (file_id, date_taken, camera_model, gps_lat, gps_lon, width, height, thumbnail_path, exif_json, indexed_at, is_starred)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                metadata.as_row()
            )

    def set_starred(self, file_id: int, starred: bool):
        with self.db.connect() as conn:
            conn.execute("UPDATE photo_metadata SET is_starred = ? WHERE file_id = ?", (1 if starred else 0, file_id))

    def get_starred_file_ids(self, category: Optional[int] = None) -> List[int]:
        query = "SELECT file_id FROM photo_metadata WHERE is_starred = 1"
        params = []
        if category is not None:
            query += " AND file_id IN (SELECT id FROM files f JOIN folder_categories fc ON f.folder_path = fc.folder_path WHERE fc.category = ?)"
            params.append(category)
        with self.db.connect() as conn:
            return [r[0] for r in conn.execute(query, params).fetchall()]
