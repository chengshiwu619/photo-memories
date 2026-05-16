from typing import List, Optional
from core.models import MemoryReasoning


class MemoryReasoningRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, reasoning: MemoryReasoning) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO memory_reasoning
                (memory_id, reasoning, feedback_type, created_at)
                VALUES (?, ?, ?, ?)
            """, (reasoning.memory_id, reasoning.reasoning, reasoning.feedback_type, reasoning.created_at))
            return result.lastrowid

    def insert_raw(self, memory_id: int, reasoning: Optional[str], feedback_type: str) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO memory_reasoning
                (memory_id, reasoning, feedback_type)
                VALUES (?, ?, ?)
            """, (memory_id, reasoning, feedback_type))
            return result.lastrowid

    def get_by_memory_id(self, memory_id: int) -> List[MemoryReasoning]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, memory_id, reasoning, feedback_type, created_at
                FROM memory_reasoning WHERE memory_id = ? ORDER BY created_at DESC
            """, (memory_id,)).fetchall()
        return [
            MemoryReasoning(
                id=r[0], memory_id=r[1], reasoning=r[2],
                feedback_type=r[3], created_at=r[4]
            )
            for r in rows
        ]

    def get_all(self) -> List[MemoryReasoning]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, memory_id, reasoning, feedback_type, created_at
                FROM memory_reasoning ORDER BY created_at DESC
            """).fetchall()
        return [
            MemoryReasoning(
                id=r[0], memory_id=r[1], reasoning=r[2],
                feedback_type=r[3], created_at=r[4]
            )
            for r in rows
        ]

    def get_negative_reasons(self, limit: int = 20) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT DISTINCT reasoning
                FROM memory_reasoning
                WHERE feedback_type = 'dismiss' AND reasoning IS NOT NULL
                LIMIT ?
            """, (limit,)).fetchall()
        return [r[0] for r in rows if r[0]]
