import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QPixmap, QGraphicsOpacityEffect

from core.models import Memory


class MemoryPhotoCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data: dict):
        super().__init__()
        self.photo_data = photo_data
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("MemoryPhotoCard { background: transparent; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_anim.setDuration(40)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet("background: #1a1a2e; border-radius: 4px;")
        layout.addWidget(self._img_label)

    def load_thumbnail(self):
        path = self.photo_data.get("thumbnail_path")
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                w = min(pm.width(), 200)
                self._img_label.setPixmap(
                    pm.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
                )
        self._fade_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.photo_data)
        super().mousePressEvent(event)


class MemoryCardWidget(QFrame):
    clicked = pyqtSignal(int)
    dismissed = pyqtSignal(int)

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            MemoryCardWidget {
                background: #2a2a4e;
                border-radius: 12px;
                border: 1px solid #3a3a5e;
                padding: 8px;
            }
            MemoryCardWidget:hover {
                border-color: #667eea;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        type_colors = {
            "on_this_day": "#ff6b6b",
            "recent": "#ffd93d",
            "person": "#6bcb77",
            "event": "#4d96ff",
            "scene": "#9b59b6",
        }
        color = type_colors.get(self._memory.memory_type, "#667eea")

        type_label = QLabel(self._memory.memory_type)
        type_label.setFont(QFont("Microsoft YaHei", 8))
        type_label.setStyleSheet(f"color: {color};")
        layout.addWidget(type_label)

        title = QLabel(self._memory.title)
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setWordWrap(True)
        layout.addWidget(title)

        if self._memory.description:
            desc = QLabel(self._memory.description)
            desc.setFont(QFont("Microsoft YaHei", 9))
            desc.setStyleSheet("color: #a0a0b0;")
            desc.setWordWrap(True)
            desc.setMaximumHeight(40)
            layout.addWidget(desc)

        photo_ids = self._memory.get_photo_id_list()
        if photo_ids:
            row = QHBoxLayout()
            row.setSpacing(2)
            for fid in photo_ids[:4]:
                thumb = QLabel()
                thumb.setFixedSize(48, 48)
                thumb.setStyleSheet("background: #1a1a2e; border-radius: 3px;")
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row.addWidget(thumb)
            if len(photo_ids) > 4:
                more = QLabel(f"+{len(photo_ids) - 4}")
                more.setFont(QFont("Microsoft YaHei", 8))
                more.setStyleSheet("color: #666;")
                more.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row.addWidget(more)
            row.addStretch()
            layout.addLayout(row)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._memory.id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        dismiss_action = menu.addAction("不再显示")
        action = menu.exec(event.globalPos())
        if action == dismiss_action:
            self.dismissed.emit(self._memory.id)
