import os
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger


class StartupWorker(QThread):
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
        self._classify_event = threading.Event()
        self._classify_results = []

    def cancel(self):
        self._cancelled = True
        from scanner.fast_scan import set_stopped as scan_stopped
        from indexer.photo_indexer import set_stopped as index_stopped
        scan_stopped()
        index_stopped()
        self._classify_event.set()
        logger.info("用户取消启动流程")

    def set_classify_results(self, results):
        self._classify_results = results
        self._classify_event.set()

    def run(self):
        try:
            from scanner.fast_scan import full_scan as scan_drive, clear_checkpoint as clear_scan
            from classifier.folder_classifier import classify_folders, propagate_branch_category
            from indexer.photo_indexer import index_photos, clear_checkpoint as clear_index
            from memory.memory_generator import generate_all_memories

            clear_scan()
            clear_index()

            self.stage_changed.emit("正在扫描 Y 盘文件...")
            self.progress.emit(0, 0)
            logger.info("启动阶段 1/4: 扫描文件")
            bg_scan_needed = False
            if _skip_scan():
                result = {"total": _db_file_count(), "new": 0, "removed": 0}
                logger.info("测试模式: 跳过扫描")
            else:
                result = scan_drive(progress_callback=self._on_scan_progress, batch_limit=500)
            if self._cancelled:
                self.error_occurred.emit("扫描已取消")
                return
            if result.get("batch_limit_reached"):
                bg_scan_needed = True
                logger.info(f"扫描热身: {result.get('new', 0)} 条, 剩余后台继续")
            elif result.get("paused"):
                self.error_occurred.emit("扫描已取消")
                return
            logger.info(f"扫描阶段完成: 总计 {result.get('total', 0)} 文件")

            self.stage_changed.emit("正在 LLM 预分类文件夹...")
            self.progress.emit(0, 0)
            logger.info("启动阶段 2/4: 分类文件夹")
            classify_result = classify_folders(progress_callback=self._on_classify_progress)
            if self._cancelled:
                self.error_occurred.emit("分类已取消")
                return
            logger.info(f"分类完成: 已分类 {classify_result.get('classified', 0)}, 需确认 {len(classify_result.get('needs_user', []))}")

            needs_user = classify_result.get("needs_user", [])
            if needs_user and not self._cancelled:
                logger.info(f"请求用户确认 {len(needs_user)} 个分支文件夹分类")
                self.interactive_classify_needed.emit(needs_user)
                self._classify_event.wait()
                self._classify_event.clear()
                if self._cancelled:
                    self.error_occurred.emit("分类已取消")
                    return
                for branch_path, category in self._classify_results:
                    propagate_branch_category(branch_path, category)
                logger.info(f"用户确认 {len(self._classify_results)} 个分支分类")

            self.stage_changed.emit("正在生成缩略图...")
            self.progress.emit(0, 0)
            logger.info("启动阶段 3/4: 生成缩略图")
            bg_needed = False
            try:
                if _skip_index():
                    logger.info("缩略图已足够 (>=100), 跳过前台索引，稍后后台补索引")
                    index_result = {"total": 0, "indexed": 0}
                    bg_needed = True
                else:
                    index_result = index_photos(progress_callback=self._on_index_progress, batch_limit=100)
                if self._cancelled:
                    self.error_occurred.emit("索引已取消")
                    return
                if index_result.get("batch_limit_reached"):
                    bg_needed = True
                    logger.info(f"索引热身完成: {index_result.get('indexed', 0)}/{index_result.get('total', 0)}, 剩余后台继续")
                elif index_result.get("paused"):
                    self.error_occurred.emit("索引已取消")
                    return
                else:
                    logger.info(f"索引完成: {index_result.get('indexed', 0)}/{index_result.get('total', 0)}")
            except Exception as e:
                logger.warning(f"索引异常，跳过: {e}")

            self.stage_changed.emit("正在生成回忆...")
            self.progress.emit(0, 0)
            logger.info("启动阶段 4/4: 生成回忆")
            memories_result = generate_all_memories(progress_callback=self._on_memory_progress)
            if self._cancelled:
                self.error_occurred.emit("回忆生成已取消")
                return
            logger.info("所有阶段完成")

            self.stage_changed.emit("初始化完成")
            self.progress.emit(100, 100)
            if bg_scan_needed:
                self.background_scan_needed.emit()
            if bg_needed:
                self.background_index_needed.emit()
            self.all_done.emit()

        except Exception as e:
            logger.exception("启动流程异常")
            self.error_occurred.emit(str(e))

    def _on_scan_progress(self, scanned, found):
        self.progress.emit(scanned, found)
        self.stage_changed.emit(f"扫描中... 已发现 {found} 个文件")

    def _on_classify_progress(self, current, total):
        if total > 0:
            self.progress.emit(current, total)
            self.stage_changed.emit(f"分类中... {current}/{total}")

    def _on_index_progress(self, current, total):
        if total > 0:
            self.progress.emit(current, total)
            self.stage_changed.emit(f"索引中... {current}/{total}")

    def _on_memory_progress(self, current, total, category_name, state):
        self.progress.emit(current, total)
        if state == "thinking":
            self.stage_changed.emit(f"回忆生成中... {category_name}")
        else:
            self.stage_changed.emit(f"回忆完成: {category_name}")


class StartupWindow(QWidget):
    transition_to_main = pyqtSignal()
    background_scan_needed = pyqtSignal()
    background_index_needed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.worker = None
        self._cancelled = False
        self._transitioned = False
        self.setup_ui()
        self.center_on_screen()

    def setup_ui(self):
        self.setWindowTitle("NAS 照片回忆")
        self.setFixedSize(460, 260)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        title = QLabel("NAS 照片回忆")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.stage_label = QLabel("正在初始化...")
        self.stage_label.setFont(QFont("Microsoft YaHei", 11))
        self.stage_label.setStyleSheet("color: #a0a0b0;")
        self.stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage_label.setWordWrap(True)
        layout.addWidget(self.stage_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a5e;
                border-radius: 4px;
                background: #2a2a3e;
                text-align: center;
                color: #ccc;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消初始化")
        self.cancel_btn.setFixedSize(130, 36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #e74c3c;
            }
            QPushButton:disabled {
                background: #666;
            }
        """)
        self.cancel_btn.clicked.connect(self.on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._btn_layout = btn_layout

        layout.addStretch()

    def center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def start(self):
        self.worker = StartupWorker()
        self.worker.stage_changed.connect(self.stage_label.setText)
        self.worker.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        self.worker.all_done.connect(self._on_all_done, Qt.ConnectionType.QueuedConnection)
        self.worker.error_occurred.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        self.worker.interactive_classify_needed.connect(self._on_classify_needed, Qt.ConnectionType.QueuedConnection)
        self.worker.background_scan_needed.connect(self.background_scan_needed.emit)
        self.worker.background_index_needed.connect(self.background_index_needed.emit)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        logger.info("一键启动流程开始")

    def _on_progress(self, current, total):
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(min(pct, 100))
            self.progress_bar.setFormat(f"{current}/{total}")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("")

    def _on_all_done(self):
        self._transitioned = True
        logger.info("启动流程全部完成，跳转主窗口")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("完成")
        self.worker = None
        self.transition_to_main.emit()

    def _on_worker_finished(self):
        if not self._transitioned and not self._cancelled:
            logger.warning("all_done 信号未送达，通过 finished 兜底触发主界面")
            self._transitioned = True
            self.transition_to_main.emit()

    def _on_error(self, msg):
        self._transitioned = True
        logger.warning(f"启动流程中断: {msg}")
        self.stage_label.setText(f"已中断: {msg}")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")

        self.cancel_btn.hide()

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #666;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #888;
            }
        """)
        close_btn.clicked.connect(self.close)
        close_btn.clicked.connect(QApplication.instance().quit)
        self._btn_layout.insertWidget(0, close_btn)

        continue_btn = QPushButton("进入主界面")
        continue_btn.setFixedSize(130, 36)
        continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        continue_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2ecc71;
            }
        """)
        continue_btn.clicked.connect(self.background_scan_needed.emit)
        continue_btn.clicked.connect(self.background_index_needed.emit)
        continue_btn.clicked.connect(self.transition_to_main.emit)
        self._btn_layout.insertWidget(1, continue_btn)

        self.worker = None

    def _on_classify_needed(self, branches):
        from ui.components.folder_classifier_dialog import BranchClassifierDialog
        self.stage_label.setText("请为文件夹分支选择分类...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.cancel_btn.setEnabled(False)

        self._classify_results = []
        self._classify_dialog = BranchClassifierDialog(branches, self)
        self._classify_dialog.result_ready.connect(self._on_classify_dialog_done)
        self._classify_dialog.finished.connect(self._on_classify_dialog_closed)
        logger.info(f"显示分类对话框，待分类 {len(branches)} 个分支")
        self._classify_dialog.show()

    def _on_classify_dialog_done(self, results):
        logger.info(f"分类对话框完成，获得 {len(results)} 个结果")
        self._classify_results = results
        if self.worker:
            self.worker.set_classify_results(results)
            self.cancel_btn.setEnabled(True)
            self.stage_label.setText("分类完成，继续...")

    def _on_classify_dialog_closed(self):
        if not self._classify_results and self.worker:
            logger.info("分类对话框被关闭，视为跳过分类")
            self.worker.set_classify_results([])
            self.cancel_btn.setEnabled(True)
            self.stage_label.setText("分类跳过，继续...")
        self._classify_dialog = None

    def on_cancel(self):
        self._cancelled = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("取消中...")
        self.stage_label.setText("正在取消...")
        if self.worker:
            self.worker.cancel()

    def closeEvent(self, event):
        if hasattr(self, '_classify_dialog') and self._classify_dialog:
            self._classify_dialog.close()
        if hasattr(self, 'worker') and self.worker:
            self.worker.cancel()
        logger.info("StartupWindow 关闭，清理资源")
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)


def _skip_scan():
    return os.environ.get("PHOTO_TEST_MODE", "").lower() in ("1", "true", "yes")


def _skip_index():
    from db_manager import Database
    try:
        db = Database()
        with db.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NOT NULL"
            ).fetchone()[0]
        return n >= 100
    except Exception:
        return False


def _db_file_count():
    from db_manager import Database
    db = Database()
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(1) FROM files").fetchone()[0]
    return n
