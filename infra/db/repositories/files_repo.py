from typing import Set, Optional, List
from core.models import File


class FilesRepository:
    def __init__(self, db):
        self.db = db

    def get_existing_paths(self) -> Set[str]:
        with self.db.connect() as conn:
            return {r[0] for r in conn.execute("SELECT file_path FROM files")}

    def insert_or_ignore(self, file: File) -> int:
        with self.db.connect() as conn:
            result = conn.execute(
                """INSERT OR IGNORE INTO files
                (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                file.as_row()
            )
            return result.rowcount

    def delete_missing(self, missing_paths: Set[str]) -> int:
        if not missing_paths:
            return 0
        with self.db.connect() as conn:
            count = 0
            for path in missing_paths:
                result = conn.execute("DELETE FROM files WHERE file_path = ?", (path,))
                count += result.rowcount
            return count

    def count(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def get_all_file_ids(self) -> List[int]:
        with self.db.connect() as conn:
            return [r[0] for r in conn.execute("SELECT id FROM files WHERE is_image = 1")]
