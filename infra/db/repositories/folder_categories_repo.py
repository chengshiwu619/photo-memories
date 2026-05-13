from typing import List, Optional
from core.models import FolderCategory


class FolderCategoriesRepository:
    def __init__(self, db):
        self.db = db

    def get_unclassified_folders(self) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT DISTINCT f.folder_path FROM files f
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE fc.folder_path IS NULL
            """).fetchall()
        return [row[0] for row in rows]

    def get_all_folders(self) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT folder_path FROM files").fetchall()
        return [row[0] for row in rows]

    def set_folder_category(self, folder_path: str, category: int, confidence: Optional[str] = None):
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO folder_categories (folder_path, category, confidence, classified_at)
                VALUES (?, ?, ?, datetime('now'))""",
                (folder_path, category, confidence)
            )

    def get_folder_category(self, folder_path: str) -> Optional[int]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT category FROM folder_categories WHERE folder_path = ?", (folder_path,)).fetchone()
        return row[0] if row else None
