from typing import List, Optional, Tuple
from core.models import PhotoMetadata
from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from business.classifier.category_rules import category_match_sql


PhotoDiscoveryRow = Tuple[int, str, Optional[str], Optional[int]]


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

    def get_by_file_id(self, file_id: int) -> Optional[PhotoMetadata]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT file_id, date_taken, camera_model, gps_lat, gps_lon, width, height,
                       thumbnail_path, exif_json, indexed_at, is_starred, phash, is_duplicate_of
                FROM photo_metadata WHERE file_id = ?
            """, (file_id,)).fetchone()
        if row:
            return PhotoMetadata(*row)
        return None

    def insert_or_replace(self, metadata: PhotoMetadata):
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO photo_metadata
                (file_id, date_taken, camera_model, gps_lat, gps_lon, width, height, thumbnail_path, exif_json, indexed_at, is_starred, phash, is_duplicate_of)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                metadata.as_row()
            )

    def set_starred(self, file_id: int, starred: bool):
        with self.db.connect() as conn:
            conn.execute("UPDATE photo_metadata SET is_starred = ? WHERE file_id = ?", (1 if starred else 0, file_id))

    def get_starred_file_ids(self, category: Optional[int] = None) -> List[int]:
        query = "SELECT pm.file_id FROM photo_metadata pm"
        params = []
        if category is not None:
            query += """
                JOIN files f ON pm.file_id = f.id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE pm.is_starred = 1
                  AND """ + category_match_sql(category)
            params.append(category)
        else:
            query += " WHERE pm.is_starred = 1"
        with self.db.connect() as conn:
            return [r[0] for r in conn.execute(query, params).fetchall()]

    def get_photos_without_phash(self, limit: int = 100) -> List[int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT file_id FROM photo_metadata WHERE phash IS NULL LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows]

    def get_photos_without_siglip_tags(self, limit: int = 10000) -> List[int]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1 AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                AND f.id NOT IN (SELECT DISTINCT file_id FROM photo_tags WHERE source = 'siglip')
                LIMIT ?
            """, (limit,)).fetchall()
        return [r[0] for r in rows]

    def get_photos_by_month_day(self, month_days: List[str]) -> List[PhotoDiscoveryRow]:
        if not month_days:
            return []
        conditions = " OR ".join("substr(pm.date_taken, 6, 5) = ?" for _ in month_days)
        life_match = category_match_sql(CATEGORY_LIFE)
        with self.db.connect() as conn:
            rows = conn.execute(f"""
                SELECT f.id, f.folder_path, pm.date_taken,
                       CASE WHEN {life_match} THEN {CATEGORY_LIFE} ELSE {CATEGORY_SAMPLE} END AS category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND pm.is_duplicate_of IS NULL
                  AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                  AND ({conditions})
                ORDER BY pm.date_taken DESC
            """, [CATEGORY_LIFE] + month_days).fetchall()
        return rows

    def get_recent_photos(self, since: str, limit: int = 200) -> List[PhotoDiscoveryRow]:
        life_match = category_match_sql(CATEGORY_LIFE)
        with self.db.connect() as conn:
            rows = conn.execute(f"""
                SELECT f.id, f.folder_path, pm.date_taken,
                       CASE WHEN {life_match} THEN {CATEGORY_LIFE} ELSE {CATEGORY_SAMPLE} END AS category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND pm.is_duplicate_of IS NULL
                  AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                  AND pm.date_taken >= ?
                ORDER BY pm.date_taken DESC
                LIMIT ?
            """, (CATEGORY_LIFE, since, limit)).fetchall()
        return rows

    def update_phash(self, file_id: int, phash: str, is_duplicate_of: Optional[int] = None):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE photo_metadata SET phash = ?, is_duplicate_of = ? WHERE file_id = ?",
                (phash, is_duplicate_of, file_id)
            )
