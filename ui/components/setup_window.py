import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger
from config import (
    SOURCE_DRIVE, DATA_DIR, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    save_config,
)


class SetupWindow(QWidget):
    config_saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.center_on_screen()
        self._load_current()

    def setup_ui(self):
        self.setWindowTitle("初次配置 - NAS 照片回忆")
        self.setFixedSize(520, 360)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(14)

        title = QLabel("首次使用 - 请配置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        row1 = self._make_row("照片库文件夹", "src_edit", self._browse_src)
        form_layout.addLayout(row1)

        row2 = self._make_row("缓存数据文件夹", "data_edit", self._browse_data)
        form_layout.addLayout(row2)

        row3_layout = QVBoxLayout()
        row3_layout.setSpacing(4)
        api_label = QLabel("DeepSeek API Key")
        api_label.setFont(QFont("Microsoft YaHei", 10))
        api_label.setStyleSheet("color: #a0a0b0;")
        row3_layout.addWidget(api_label)

        self.api_edit = QLineEdit()
        self.api_edit.setPlaceholderText("sk-...")
        self.api_edit.setFont(QFont("Microsoft YaHei", 10))
        self.api_edit.setStyleSheet("""
            QLineEdit {
                background: #2a2a3e; color: #e0e0e0;
                border: 1px solid #3a3a5e; border-radius: 4px;
                padding: 8px 10px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #667eea; }
        """)
        row3_layout.addWidget(self.api_edit)
        form_layout.addLayout(row3_layout)

        layout.addLayout(form_layout)

        self.error_label = QLabel("")
        self.error_label.setFont(QFont("Microsoft YaHei", 9))
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("保存并开始")
        self.save_btn.setFixedSize(150, 38)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white; border: none; border-radius: 6px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7b93f5, stop:1 #9b6bc2);
            }
            QPushButton:disabled { background: #555; }
        """)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._drag_pos = None

    def _make_row(self, label_text, attr_name, browse_fn):
        row = QVBoxLayout()
        row.setSpacing(4)
        label = QLabel(label_text)
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setStyleSheet("color: #a0a0b0;")
        row.addWidget(label)

        inner = QHBoxLayout()
        inner.setSpacing(6)
        edit = QLineEdit()
        edit.setFont(QFont("Microsoft YaHei", 10))
        edit.setStyleSheet("""
            QLineEdit {
                background: #2a2a3e; color: #e0e0e0;
                border: 1px solid #3a3a5e; border-radius: 4px;
                padding: 8px 10px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #667eea; }
        """)
        inner.addWidget(edit, 1)

        btn = QPushButton("浏览")
        btn.setFixedSize(60, 34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: #34495e; color: #ccc; border: none;
                border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background: #4a6a8a; }
        """)
        btn.clicked.connect(browse_fn)
        inner.addWidget(btn)

        row.addLayout(inner)

        setattr(self, attr_name, edit)
        return row

    def _browse_src(self):
        path = QFileDialog.getExistingDirectory(self, "选择照片库文件夹", self.src_edit.text() or "D:\\")
        if path:
            self.src_edit.setText(path)

    def _browse_data(self):
        path = QFileDialog.getExistingDirectory(self, "选择缓存数据文件夹", self.data_edit.text() or "D:\\")
        if path:
            self.data_edit.setText(path)

    def _load_current(self):
        if SOURCE_DRIVE and SOURCE_DRIVE != "D:\\测试":
            self.src_edit.setText(SOURCE_DRIVE)
        if DATA_DIR and DATA_DIR != os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "storage"):
            self.data_edit.setText(DATA_DIR)
        if DEEPSEEK_API_KEY:
            self.api_edit.setText(DEEPSEEK_API_KEY)

    def _on_save(self):
        src = self.src_edit.text().strip()
        data = self.data_edit.text().strip()
        api_key = self.api_edit.text().strip()

        errors = []
        if not src:
            errors.append("请指定照片库文件夹")
        if not data:
            errors.append("请指定缓存数据文件夹")
        if not api_key:
            errors.append("请填入 DeepSeek API Key")

        if errors:
            self.error_label.setText("\n".join(errors))
            return

        if not os.path.exists(src):
            try:
                os.makedirs(src, exist_ok=True)
            except Exception as e:
                self.error_label.setText(f"无法创建照片库文件夹: {e}")
                return

        logger.info(f"保存配置: src={src}, data={data}, api_key={api_key[:8]}...")

        save_config(src, data, api_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)

        self.config_saved.emit()

    def center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
