import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger


from services.background_task_manager import Pipeline, ScanStage, ClassifyStage, IndexStage


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
        pipeline = Pipeline()
        pipeline.add_stage(ScanStage())
        pipeline.add_stage(ClassifyStage())
        pipeline.add_stage(IndexStage())
        self.worker = pipeline
        pipeline.stage_changed.connect(self.stage_label.setText)
        pipeline.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        pipeline.all_done.connect(self._on_all_done, Qt.ConnectionType.QueuedConnection)
        pipeline.error_occurred.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        pipeline.interactive_classify_needed.connect(self._on_classify_needed, Qt.ConnectionType.QueuedConnection)
        pipeline.background_scan_needed.connect(self.background_scan_needed.emit)
        pipeline.background_index_needed.connect(self.background_index_needed.emit)
        pipeline.finished.connect(self._on_worker_finished)
        pipeline.start()
        logger.info("Pipeline 启动流程开始")

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



