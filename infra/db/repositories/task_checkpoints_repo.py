from typing import Optional
from core.models import TaskCheckpoint
import json


class TaskCheckpointsRepository:
    def __init__(self, db):
        self.db = db

    def save(self, checkpoint: TaskCheckpoint):
        with self.db.connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO task_checkpoints
                (task_type, task_key, status_json, updated_at)
                VALUES (?, ?, ?, ?)
            """, (checkpoint.task_type, checkpoint.task_key,
                  checkpoint.status_json, checkpoint.updated_at))

    def get(self, task_type: str, task_key: str) -> Optional[TaskCheckpoint]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT task_type, task_key, status_json, updated_at
                FROM task_checkpoints
                WHERE task_type = ? AND task_key = ?
            """, (task_type, task_key)).fetchone()
        if row:
            return TaskCheckpoint(
                task_type=row[0], task_key=row[1],
                status_json=row[2], updated_at=row[3]
            )
        return None

    def get_status(self, task_type: str, task_key: str) -> Optional[dict]:
        cp = self.get(task_type, task_key)
        if cp and cp.status_json:
            try:
                return json.loads(cp.status_json)
            except Exception:
                pass
        return None

    def save_status(self, task_type: str, task_key: str, status: dict):
        import datetime
        now = datetime.datetime.now().isoformat()
        checkpoint = TaskCheckpoint(
            task_type=task_type,
            task_key=task_key,
            status_json=json.dumps(status),
            updated_at=now
        )
        self.save(checkpoint)

    def delete(self, task_type: str, task_key: str):
        with self.db.connect() as conn:
            conn.execute("""
                DELETE FROM task_checkpoints
                WHERE task_type = ? AND task_key = ?
            """, (task_type, task_key))
