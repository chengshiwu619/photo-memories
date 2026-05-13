from typing import List, Optional
from core.models import Memory


class MemoriesRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, memory: Memory) -> int:
        with self.db.connect() as conn:
            result = conn.execute(
                """INSERT INTO memories (category, memory_type, title, description, photo_ids, cover_file_id, created_at, is_starred)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                memory.as_row()
            )
            return result.lastrowid

    def set_starred(self, memory_id: int, starred: bool):
        with self.db.connect() as conn:
            conn.execute("UPDATE memories SET is_starred = ? WHERE id = ?", (1 if starred else 0, memory_id))

    def get_all(self, category: Optional[int] = None, starred_only: bool = False) -> List[Memory]:
        query = "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at FROM memories WHERE 1=1"
        params = []
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if starred_only:
            query += " AND is_starred = 1"
        query += " ORDER BY created_at DESC"
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        memories = []
        for row in rows:
            m = Memory(
                id=row[0], category=row[1], memory_type=row[2], title=row[3], description=row[4],
                photo_ids=row[5], cover_file_id=row[6], created_at=row[8], is_starred=row[7]
            )
            memories.append(m)
        return memories

    def get_latest_title(self, category: int) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT title FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT 1", (category,)).fetchone()
        return row[0] if row else None
