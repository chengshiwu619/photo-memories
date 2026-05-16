import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QApplication, QListWidget, QListWidgetItem,
    QScrollArea,
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
        padding: 6px 10px; font-size: 13px; min-height: 22px;
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

_SMALL_BTN_STYLE = """
    QPushButton {
        background: #34495e; color: #ccc; border: none;
        border-radius: 4px; font-size: 11px; padding: 4px 10px;
    }
    QPushButton:hover { background: #4a6a8a; }
"""

_REMOVE_BTN_STYLE = """
    QPushButton {
        background: #c0392b; color: white; border: none;
        border-radius: 4px; font-size: 11px; padding: 4px 10px;
    }
    QPushButton:hover { background: #e74c3c; }
"""

_SCROLL_STYLE = """
    QScrollArea {
        border: none; background: transparent;
    }
    QScrollBar:vertical {
        background: #1a1a2e; width: 8px; border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #3a3a5e; border-radius: 4px; min-height: 30px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
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
        self.setMaximumSize(580, 800)
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

        self._basic_widget = QWidget()
        basic_layout = QVBoxLayout(self._basic_widget)
        basic_layout.setContentsMargins(0, 0, 0, 0)
        basic_layout.setSpacing(10)
        basic_layout.addLayout(self._make_row("照片库文件夹（多个用分号分隔）", "src_edit", self._browse_src))
        basic_layout.addLayout(self._make_row("缓存数据文件夹", "data_edit", self._browse_data))
        basic_layout.addLayout(self._make_text_row("DeepSeek API Key", "api_edit", "sk-..."))
        layout.addWidget(self._basic_widget)

        self._advanced_toggle = QPushButton("▶ 高级选项")
        self._advanced_toggle.setFont(QFont("Microsoft YaHei", 9))
        self._advanced_toggle.setStyleSheet("""
            QPushButton { background: transparent; color: #667eea; border: none;
                font-size: 11px; text-align: left; padding: 2px 0; }
            QPushButton:hover { color: #7b93f5; }
        """)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self._advanced_toggle)

        self._scroll_area = QScrollArea()
        self._scroll_area.setStyleSheet(_SCROLL_STYLE)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._advanced_content = QWidget()
        adv_layout = QVBoxLayout(self._advanced_content)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(10)
        adv_layout.addLayout(self._make_text_row("Base URL", "base_url_edit", "https://api.deepseek.com"))
        adv_layout.addLayout(self._make_text_row("Model", "model_edit", "deepseek-chat"))
        adv_layout.addLayout(self._make_keyword_section(
            "样片关键词（匹配文件夹名/文件名自动归为样片）",
            "sample",
        ))
        adv_layout.addLayout(self._make_keyword_section(
            "生活关键词（匹配文件夹名/文件名自动归为生活照片）",
            "life",
        ))
        adv_layout.addStretch()

        self._scroll_area.setWidget(self._advanced_content)
        self._scroll_area.hide()
        layout.addWidget(self._scroll_area, 1)

        self.error_label = QLabel("")
        self.error_label.setFont(QFont("Microsoft YaHei", 9))
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

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

    def _make_keyword_section(self, label_text, kw_type):
        section = QVBoxLayout()
        section.setSpacing(4)

        label = QLabel(label_text)
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setStyleSheet("color: #a0a0b0;")
        section.addWidget(label)

        kw_list = QListWidget()
        kw_list.setStyleSheet("""
            QListWidget {
                background: #2a2a3e; color: #e0e0e0;
                border: 1px solid #3a3a5e; border-radius: 4px;
                font-size: 12px; padding: 4px;
            }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:selected { background: #3a3a5e; }
        """)
        kw_list.setMaximumHeight(120)
        section.addWidget(kw_list)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        kw_input = QLineEdit()
        kw_input.setPlaceholderText("输入新关键词")
        kw_input.setFont(QFont("Microsoft YaHei", 10))
        kw_input.setFixedHeight(30)
        kw_input.setStyleSheet(_INPUT_STYLE)
        input_row.addWidget(kw_input, 1)

        add_btn = QPushButton("添加")
        add_btn.setFixedSize(60, 30)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(_SMALL_BTN_STYLE)
        input_row.addWidget(add_btn)

        remove_btn = QPushButton("删除")
        remove_btn.setFixedSize(60, 30)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(_REMOVE_BTN_STYLE)
        input_row.addWidget(remove_btn)

        section.addLayout(input_row)

        if kw_type == "sample":
            self._sample_kw_list = kw_list
            self._sample_kw_input = kw_input
            add_btn.clicked.connect(self._add_sample_keyword)
            remove_btn.clicked.connect(self._remove_sample_keyword)
            self._load_sample_keywords()
        else:
            self._life_kw_list = kw_list
            self._life_kw_input = kw_input
            add_btn.clicked.connect(self._add_life_keyword)
            remove_btn.clicked.connect(self._remove_life_keyword)
            self._load_life_keywords()

        return section

    def _load_sample_keywords(self):
        self._sample_kw_list.clear()
        try:
            from business.classifier.folder_classifier import get_sample_keywords
            builtin, custom = get_sample_keywords()
            for kw in builtin:
                item = QListWidgetItem(f"[内置] {kw}")
                item.setData(Qt.ItemDataRole.UserRole, ("builtin", kw))
                item.setForeground(Qt.GlobalColor.gray)
                self._sample_kw_list.addItem(item)
            for kw in custom:
                item = QListWidgetItem(kw)
                item.setData(Qt.ItemDataRole.UserRole, ("custom", kw))
                self._sample_kw_list.addItem(item)
        except Exception as e:
            logger.warning(f"加载样片关键词失败: {e}")

    def _add_sample_keyword(self):
        kw = self._sample_kw_input.text().strip()
        if not kw:
            return
        from business.classifier.folder_classifier import add_sample_keyword
        if add_sample_keyword(kw):
            self._sample_kw_input.clear()
            self._load_sample_keywords()

    def _remove_sample_keyword(self):
        current = self._sample_kw_list.currentItem()
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data or data[0] == "builtin":
            return
        from business.classifier.folder_classifier import remove_sample_keyword
        if remove_sample_keyword(data[1]):
            self._load_sample_keywords()

    def _load_life_keywords(self):
        self._life_kw_list.clear()
        try:
            from business.classifier.folder_classifier import get_life_keywords
            builtin, custom = get_life_keywords()
            for kw in builtin:
                item = QListWidgetItem(f"[内置] {kw}")
                item.setData(Qt.ItemDataRole.UserRole, ("builtin", kw))
                item.setForeground(Qt.GlobalColor.gray)
                self._life_kw_list.addItem(item)
            for kw in custom:
                item = QListWidgetItem(kw)
                item.setData(Qt.ItemDataRole.UserRole, ("custom", kw))
                self._life_kw_list.addItem(item)
        except Exception as e:
            logger.warning(f"加载生活关键词失败: {e}")

    def _add_life_keyword(self):
        kw = self._life_kw_input.text().strip()
        if not kw:
            return
        from business.classifier.folder_classifier import add_life_keyword
        if add_life_keyword(kw):
            self._life_kw_input.clear()
            self._load_life_keywords()

    def _remove_life_keyword(self):
        current = self._life_kw_list.currentItem()
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data or data[0] == "builtin":
            return
        from business.classifier.folder_classifier import remove_life_keyword
        if remove_life_keyword(data[1]):
            self._load_life_keywords()

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
        visible = self._scroll_area.isVisible()
        if visible:
            self._scroll_area.hide()
            self._basic_widget.show()
            self._advanced_toggle.setText("▶ 高级选项")
        else:
            self._basic_widget.hide()
            self._scroll_area.show()
            self._advanced_toggle.setText("◀ 返回基本配置")

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
        else:
            for p in src.split(";"):
                p = p.strip()
                if p and not os.path.exists(p):
                    errors.append(f"照片库路径不存在: {p}")
        if not data:
            errors.append("请指定缓存数据文件夹")
        if not api_key:
            errors.append("请填入 DeepSeek API Key")

        if errors:
            self.error_label.setText("\n".join(errors))
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
