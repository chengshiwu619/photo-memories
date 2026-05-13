from typing import Optional
from PyQt6.QtCore import QThread
from logger_setup import logger


class BackgroundTaskManager:
    _instance: Optional["BackgroundTaskManager"] = None

    def __init__(self):
        self._threads: list[QThread] = []

    @classmethod
    def get_instance(cls) -> "BackgroundTaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, thread: QThread):
        self._threads.append(thread)
        logger.debug(f"后台任务注册: {thread}")

    def unregister(self, thread: QThread):
        if thread in self._threads:
            self._threads.remove(thread)

    def wait_all(self, timeout_ms: int = 5000):
        for t in self._threads[:]:
            t.wait(timeout_ms)
            if t.isRunning():
                logger.warning(f"后台线程 {t} 未能在 {timeout_ms}ms 内结束")
        self._threads.clear()

    def cancel_all(self):
        for t in self._threads[:]:
            if t.isRunning():
                t.quit()
                t.wait(500)
