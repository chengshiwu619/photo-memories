import json
from enum import Enum

from logger_setup import logger


class CheckpointState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class CheckpointManager:
    def __init__(self, db, task_type, task_key="default"):
        self.db = db
        self.task_type = task_type
        self.task_key = task_key

    def load(self):
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    "SELECT status_json FROM task_checkpoints WHERE task_type = ? AND task_key = ?",
                    (self.task_type, self.task_key)
                ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.warning(f"加载断点失败: {e}")
        return None

    def save(self, state, **kwargs):
        try:
            data = {"state": state}
            data.update(kwargs)
            status_json = json.dumps(data, ensure_ascii=False)
            with self.db.connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO task_checkpoints (task_type, task_key, status_json, updated_at)
                       VALUES (?, ?, ?, datetime('now'))""",
                    (self.task_type, self.task_key, status_json)
                )
        except Exception as e:
            logger.warning(f"保存断点失败: {e}")

    def clear(self):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "DELETE FROM task_checkpoints WHERE task_type = ? AND task_key = ?",
                    (self.task_type, self.task_key)
                )
        except Exception as e:
            logger.warning(f"清除断点失败: {e}")

    def get_status(self):
        cp = self.load()
        if cp is None:
            return {"has_checkpoint": False}
        return {"has_checkpoint": True, "state": cp.get("state"), "data": cp}

    def request_pause(self):
        cp = self.load()
        if cp and cp["state"] == CheckpointState.RUNNING:
            cp["state"] = CheckpointState.PAUSED
            self.save(CheckpointState.PAUSED, **{k: v for k, v in cp.items() if k != "state"})
            logger.info("断点已标记为暂停")

    def request_stop(self):
        cp = self.load()
        if cp and cp["state"] in (CheckpointState.RUNNING, CheckpointState.PAUSED):
            self.save(CheckpointState.STOPPED, **{k: v for k, v in cp.items() if k != "state"})
            logger.info("断点已标记为停止")

    def is_pause_or_stop_requested(self):
        cp = self.load()
        if cp and cp["state"] in (CheckpointState.PAUSED, CheckpointState.STOPPED):
            return True
        return False
