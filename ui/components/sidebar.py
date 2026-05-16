from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal


_NAV_BTN_STYLE = """
    QPushButton {
        background: transparent;
        color: #a0a0b0;
        border: none;
        border-left: 3px solid transparent;
        padding: 10px 0;
        font-size: 11px;
        text-align: center;
    }
    QPushButton:hover {
        color: #e0e0e0;
        border-left: 3px solid #5a5a8e;
    }
    QPushButton[active="true"] {
        color: #ffffff;
        border-left: 3px solid #7c7cff;
        font-weight: bold;
    }
"""

_NAV_ITEMS = [
    ("random", "回忆"),
    ("timeline", "时间线"),
    ("special", "收藏"),
]


class Sidebar(QWidget):
    navigation_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = "random"
        self._buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedWidth(48)
        self.setStyleSheet("background: #1a1a2e; border-right: 1px solid #2a2a4e;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(2)

        for nav_id, label in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setStyleSheet(_NAV_BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda checked, nid=nav_id: self._on_nav(nid))
            layout.addWidget(btn)
            self._buttons[nav_id] = btn

        layout.addStretch()

        self._update_active()

    def _on_nav(self, nav_id: str):
        if nav_id == self._current:
            return
        self._current = nav_id
        self._update_active()
        self.navigation_changed.emit(nav_id)

    def _update_active(self):
        for nav_id, btn in self._buttons.items():
            btn.setProperty("active", nav_id == self._current)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def current_nav(self) -> str:
        return self._current

    def set_nav(self, nav_id: str):
        if nav_id in self._buttons:
            self._current = nav_id
            self._update_active()
