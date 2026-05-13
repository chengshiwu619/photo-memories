import os
import json
from enum import Enum

from logger_setup import logger


class CheckpointState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class CheckpointManager:
    def __init__(self, checkpoint_file):
        self.file = checkpoint_file

    def load(self):
        try:
            if os.path.exists(self.file):
                with open(self.file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"加载断点失败: {e}")
        return None

    def save(self, state, **kwargs):
        try:
            data = {"state": state}
            data.update(kwargs)
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.file)
        except Exception as e:
            logger.warning(f"保存断点失败: {e}")

    def clear(self):
        try:
            if os.path.exists(self.file):
                os.remove(self.file)
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
