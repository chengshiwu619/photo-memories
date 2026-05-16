from typing import List, Optional, Tuple
from core.models import Memory


class MemoriesRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, memory: Memory) -> int:
        with self.db.connect() as conn:
            result = conn.execute(
                """INSERT INTO memories
                (category, memory_type, title, description, photo_ids, cover_file_id, is_starred, last_shown_at, click_count, dismissed_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory.category, memory.memory_type, memory.title, memory.description,
                 memory.photo_ids, memory.cover_file_id, memory.is_starred,
                 memory.last_shown_at, memory.click_count, memory.dismissed_at, memory.payload)
            )
            return result.lastrowid

    def set_starred(self, memory_id: int, starred: bool):
        with self.db.connect() as conn:
            conn.execute("UPDATE memories SET is_starred = ? WHERE id = ?", (1 if starred else 0, memory_id))

    def get_by_id(self, memory_id: int) -> Optional[Memory]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at, last_shown_at, click_count, dismissed_at, payload FROM memories WHERE id = ?",
                (memory_id,)
            ).fetchone()
        if not row:
            return None
        return Memory(
            id=row[0], category=row[1], memory_type=row[2], title=row[3], description=row[4],
            photo_ids=row[5], cover_file_id=row[6], is_starred=row[7], created_at=row[8],
            last_shown_at=row[9], click_count=row[10], dismissed_at=row[11], payload=row[12]
        )

    def get_all(self, category: Optional[int] = None, starred_only: bool = False) -> List[Memory]:
        query = "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at, last_shown_at, click_count, dismissed_at, payload FROM memories WHERE 1=1"
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
                photo_ids=row[5], cover_file_id=row[6], is_starred=row[7], created_at=row[8],
                last_shown_at=row[9], click_count=row[10], dismissed_at=row[11], payload=row[12]
            )
            memories.append(m)
        return memories

    def get_latest_title(self, category: int) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT title FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT 1", (category,)).fetchone()
        return row[0] if row else None

    def get_undismissed(self, category: Optional[int] = None) -> List[Memory]:
        query = "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at, last_shown_at, click_count, dismissed_at, payload FROM memories WHERE dismissed_at IS NULL"
        params = []
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        memories = []
        for row in rows:
            m = Memory(
                id=row[0], category=row[1], memory_type=row[2], title=row[3], description=row[4],
                photo_ids=row[5], cover_file_id=row[6], is_starred=row[7], created_at=row[8],
                last_shown_at=row[9], click_count=row[10], dismissed_at=row[11], payload=row[12]
            )
            memories.append(m)
        return memories

    def get_undismissed_by_type(self, memory_type: str) -> List[Memory]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, category, memory_type, title, description, photo_ids,
                       cover_file_id, is_starred, created_at, last_shown_at,
                       click_count, dismissed_at, payload
                FROM memories
                WHERE memory_type = ? AND dismissed_at IS NULL
                ORDER BY created_at DESC
            """, (memory_type,)).fetchall()
        return [
            Memory(
                id=r[0], category=r[1], memory_type=r[2], title=r[3], description=r[4],
                photo_ids=r[5], cover_file_id=r[6], is_starred=r[7], created_at=r[8],
                last_shown_at=r[9], click_count=r[10], dismissed_at=r[11], payload=r[12]
            )
            for r in rows
        ]

    def find_by_type_and_payload_key(self, memory_type: str) -> List[Tuple[int, str]]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, payload FROM memories
                WHERE memory_type = ? AND dismissed_at IS NULL
                ORDER BY created_at DESC
            """, (memory_type,)).fetchall()
        return [(r[0], r[1]) for r in rows]

    def update_shown(self, memory_id: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memories SET last_shown_at = datetime('now'), click_count = click_count + 1 WHERE id = ?",
                (memory_id,)
            )

    def dismiss(self, memory_id: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memories SET dismissed_at = datetime('now') WHERE id = ?",
                (memory_id,)
            )

    def increment_click(self, memory_id: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memories SET click_count = click_count + 1 WHERE id = ?",
                (memory_id,)
            )
