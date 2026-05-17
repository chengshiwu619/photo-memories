from abc import ABC, abstractmethod
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from logger_setup import logger


class Stage(ABC):
    name: str = "未命名阶段"

    @abstractmethod
    def run(self, progress_callback=None) -> dict:
        pass


class ScanStage(Stage):
    name = "扫描文件"

    def __init__(self, batch_limit: int | None = 500):
        super().__init__()
        self._batch_limit = batch_limit

    def run(self, progress_callback=None) -> dict:
        import os
        from business.scanner.fast_scan import full_scan, clear_checkpoint
        clear_checkpoint()
        if os.environ.get("PHOTO_TEST_MODE", "").lower() in ("1", "true", "yes"):
            from db_manager import Database
            db = Database()
            with db.connect() as conn:
                n = conn.execute("SELECT COUNT(1) FROM files").fetchone()[0]
            return {"total": n, "new": 0, "removed": 0}
        return full_scan(progress_callback=progress_callback, batch_limit=self._batch_limit)


class ClassifyStage(Stage):
    name = "分类文件夹"

    def run(self, progress_callback=None) -> dict:
        from business.classifier.folder_classifier import classify_folders
        return classify_folders(progress_callback=progress_callback)

    def apply_user_results(self, results: list):
        from business.classifier.folder_classifier import propagate_branch_category
        for branch_path, category in results:
            propagate_branch_category(branch_path, category)


class IndexStage(Stage):
    name = "生成缩略图"

    def __init__(self, batch_limit: int | None = 100):
        super().__init__()
        self._batch_limit = batch_limit

    def run(self, progress_callback=None) -> dict:
        from business.indexer.photo_indexer import clear_checkpoint
        clear_checkpoint()
        from db_manager import Database
        db = Database()
        with db.connect() as conn:
            n = conn.execute("""
                SELECT COUNT(*) FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1
                  AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL OR pm.thumbnail_path = '__FAILED__')
            """).fetchone()[0]
        if n > 0:
            logger.info(f"检测到 {n} 张待索引照片，全部交给后台线程处理")
        # 不在启动流水线中阻塞生成缩略图，全部交给后台 BgIndexWorker
        return {"total": n, "indexed": 0, "batch_limit_reached": n > 0}


class MemoryStage(Stage):
    name = "生成回忆"

    def run(self, progress_callback=None) -> dict:
        from memory.memory_generator import generate_all_memories
        return generate_all_memories(progress_callback=progress_callback)


class Pipeline(QThread):
    stage_changed = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    all_done = pyqtSignal()
    error_occurred = pyqtSignal(str)
    interactive_classify_needed = pyqtSignal(list)
    background_scan_needed = pyqtSignal()
    background_index_needed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._cancelled = False
        self._stages: list[Stage] = []
        self._classify_stage: Optional[ClassifyStage] = None
        self._pending_classify_results: list = []
        import threading
        self._classify_event = threading.Event()

    def add_stage(self, stage: Stage):
        self._stages.append(stage)
        if isinstance(stage, ClassifyStage):
            self._classify_stage = stage

    def cancel(self):
        self._cancelled = True
        from business.scanner.fast_scan import set_stopped as scan_stopped
        from business.indexer.photo_indexer import set_stopped as index_stopped
        scan_stopped()
        index_stopped()
        if self._classify_event:
            self._classify_event.set()

    def set_classify_results(self, results: list):
        self._pending_classify_results = results
        if self._classify_event:
            self._classify_event.set()

    def run(self):
        try:
            total_stages = len(self._stages)
            bg_scan_needed = False
            bg_index_needed = False

            for stage_idx, stage in enumerate(self._stages):
                if self._cancelled:
                    self.error_occurred.emit(f"{stage.name} 已取消")
                    return

                self.stage_changed.emit(f"正在 {stage.name}...")
                self.progress.emit(0, 0)

                if isinstance(stage, ClassifyStage):
                    self._classify_event.clear()
                    result = stage.run(progress_callback=self._on_progress)
                    needs_user = result.get("needs_user", [])
                    if needs_user:
                        self.interactive_classify_needed.emit(needs_user)
                        self._classify_event.wait()
                        self._classify_event.clear()
                        stage.apply_user_results(self._pending_classify_results)
                else:
                    result = stage.run(progress_callback=self._on_progress)

                if self._cancelled:
                    self.error_occurred.emit(f"{stage.name} 已取消")
                    return

                if isinstance(stage, ScanStage) and result.get("batch_limit_reached"):
                    bg_scan_needed = True

                if isinstance(stage, IndexStage) and result.get("batch_limit_reached"):
                    bg_index_needed = True

            self.stage_changed.emit("初始化完成")
            self.progress.emit(100, 100)
            if bg_scan_needed:
                self.background_scan_needed.emit()
            if bg_index_needed:
                self.background_index_needed.emit()
            self.all_done.emit()

        except Exception as e:
            import traceback
            logger.exception("Pipeline 执行异常")
            self.error_occurred.emit(str(e))

    def _on_progress(self, current, total, *args):
        self.progress.emit(current, total)


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
