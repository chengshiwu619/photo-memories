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
    save_config, get_settings,
)

_INPUT_STYLE = """
    QLineEdit {
        background: #2a2a3e; color: #e0e0e0;
        border: 1px solid #3a3a5e; border-radius: 4px;
        padding: 8px 10px; font-size: 13px;
    }
    QLineEdit:focus { border-color: #667eea; }
"""

_BROWSE_STYLE = """
    QPushButton {
        background: #34495e; color: #ccc; border: none;
        border-radius: 4px; font-size: 11px;
    }
    QPushButton:hover { background: #4a6a8a; }
"""


class SetupWindow(QWidget):
    config_saved = pyqtSignal()

    def __init__(self, edit_mode=False):
        super().__init__()
        self._edit_mode = edit_mode
        self.setup_ui()
        self.center_on_screen()
        self._load_current()

    def setup_ui(self):
        self.setWindowTitle("配置 - NAS 照片回忆" if self._edit_mode else "初次配置 - NAS 照片回忆")
        self.setMinimumSize(520, 400)
        self.setMaximumSize(520, 560)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("修改配置" if self._edit_mode else "首次使用 - 请配置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form = QVBoxLayout()
        form.setSpacing(10)

        form.addLayout(self._make_row("照片库文件夹", "src_edit", self._browse_src))
        form.addLayout(self._make_row("缓存数据文件夹", "data_edit", self._browse_data))
        form.addLayout(self._make_text_row("DeepSeek API Key", "api_edit", "sk-..."))

        self._advanced_toggle = QPushButton("▶ 高级选项")
        self._advanced_toggle.setFont(QFont("Microsoft YaHei", 9))
        self._advanced_toggle.setStyleSheet("""
            QPushButton { background: transparent; color: #667eea; border: none;
                font-size: 11px; text-align: left; padding: 2px 0; }
            QPushButton:hover { color: #7b93f5; }
        """)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        form.addWidget(self._advanced_toggle)

        self._advanced_widget = QWidget()
        adv_layout = QVBoxLayout(self._advanced_widget)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(10)
        adv_layout.addLayout(self._make_text_row("Base URL", "base_url_edit", "https://api.deepseek.com"))
        adv_layout.addLayout(self._make_text_row("Model", "model_edit", "deepseek-chat"))
        self._advanced_widget.hide()
        form.addWidget(self._advanced_widget)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setFont(QFont("Microsoft YaHei", 9))
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_text = "保存" if self._edit_mode else "保存并开始"
        self.save_btn = QPushButton(btn_text)
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

        if self._edit_mode:
            cancel_btn = QPushButton("取消")
            cancel_btn.setFixedSize(100, 38)
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background: #555; color: #ccc; border: none;
                    border-radius: 6px; font-size: 13px;
                }
                QPushButton:hover { background: #777; }
            """)
            cancel_btn.clicked.connect(self.close)
            btn_layout.addWidget(cancel_btn)

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
        edit.setStyleSheet(_INPUT_STYLE)
        inner.addWidget(edit, 1)

        btn = QPushButton("浏览")
        btn.setFixedSize(60, 34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_BROWSE_STYLE)
        btn.clicked.connect(browse_fn)
        inner.addWidget(btn)

        row.addLayout(inner)
        setattr(self, attr_name, edit)
        return row

    def _make_text_row(self, label_text, attr_name, placeholder=""):
        row = QVBoxLayout()
        row.setSpacing(4)
        label = QLabel(label_text)
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setStyleSheet("color: #a0a0b0;")
        row.addWidget(label)

        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFont(QFont("Microsoft YaHei", 10))
        edit.setStyleSheet(_INPUT_STYLE)
        row.addWidget(edit)

        setattr(self, attr_name, edit)
        return row

    def _toggle_advanced(self):
        visible = self._advanced_widget.isVisible()
        if visible:
            self._advanced_widget.hide()
            self._advanced_toggle.setText("▶ 高级选项")
        else:
            self._advanced_widget.show()
            self._advanced_toggle.setText("▼ 高级选项")

    def _browse_src(self):
        path = QFileDialog.getExistingDirectory(self, "选择照片库文件夹", self.src_edit.text() or "D:\\")
        if path:
            self.src_edit.setText(path)

    def _browse_data(self):
        path = QFileDialog.getExistingDirectory(self, "选择缓存数据文件夹", self.data_edit.text() or "D:\\")
        if path:
            self.data_edit.setText(path)

    def _load_current(self):
        try:
            s = get_settings()
        except Exception:
            return

        if s.source_drive and s.source_drive != "D:\\测试":
            self.src_edit.setText(s.source_drive)
        if s.photo_data_dir:
            self.data_edit.setText(s.photo_data_dir)
        if s.deepseek_api_key:
            self.api_edit.setText(s.deepseek_api_key)
        if s.deepseek_base_url:
            self.base_url_edit.setText(s.deepseek_base_url)
        if s.deepseek_model:
            self.model_edit.setText(s.deepseek_model)

    def _on_save(self):
        src = self.src_edit.text().strip()
        data = self.data_edit.text().strip()
        api_key = self.api_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://api.deepseek.com"
        model = self.model_edit.text().strip() or "deepseek-chat"

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

        save_config(src, data, api_key, base_url, model)

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
