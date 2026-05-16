import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QRect, QPoint
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor

from logger_setup import logger
from core.models import Memory


class MemoryCard(QWidget):
    clicked = pyqtSignal(int)
    dismissed = pyqtSignal(int)

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(220)
        self.setStyleSheet("""
            MemoryCard {
                background: #2a2a4e;
                border-radius: 12px;
                border: 1px solid #3a3a5e;
            }
            MemoryCard:hover {
                border-color: #667eea;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        type_label = QLabel(self._memory.memory_type)
        type_label.setFont(QFont("Microsoft YaHei", 8))
        type_label.setStyleSheet("color: #667eea; text-transform: uppercase;")
        layout.addWidget(type_label)

        title = QLabel(self._memory.title)
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setWordWrap(True)
        layout.addWidget(title)

        if self._memory.description:
            desc = QLabel(self._memory.description)
            desc.setFont(QFont("Microsoft YaHei", 9))
            desc.setStyleSheet("color: #a0a0b0;")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        photo_count = len(self._memory.get_photo_id_list())
        count_label = QLabel(f"{photo_count} 张照片")
        count_label.setFont(QFont("Microsoft YaHei", 8))
        count_label.setStyleSheet("color: #666;")
        layout.addWidget(count_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._memory.id)
        super().mousePressEvent(event)


class ShatterWidget(QWidget):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._pieces = []
        self._animations = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def shatter(self):
        if self._pixmap.isNull():
            return

        piece_size = 40
        w, h = self._pixmap.width(), self._pixmap.height()

        for y in range(0, h, piece_size):
            for x in range(0, w, piece_size):
                pw = min(piece_size, w - x)
                ph = min(piece_size, h - y)
                piece = self._pixmap.copy(x, y, pw, ph)
                self._pieces.append({
                    "pixmap": piece,
                    "pos": QPoint(x, y),
                    "dx": (x - w // 2) * 3,
                    "dy": (y - h // 2) * 3 - 200,
                })

        self.update()
        self._animate()

    def _animate(self):
        import random
        for i, piece in enumerate(self._pieces):
            anim = QPropertyAnimation(self, b"geometry")
            start_rect = QRect(piece["pos"].x(), piece["pos"].y(),
                               piece["pixmap"].width(), piece["pixmap"].height())
            end_x = piece["pos"].x() + piece["dx"] + random.randint(-50, 50)
            end_y = piece["pos"].y() + piece["dy"] + random.randint(-30, 30)
            end_rect = QRect(end_x, end_y, 0, 0)
            anim.setStartValue(start_rect)
            anim.setEndValue(end_rect)
            anim.setDuration(600 + random.randint(0, 300))
            anim.start()
            self._animations.append(anim)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(0.8)
        for piece in self._pieces:
            painter.drawPixmap(piece["pos"], piece["pixmap"])
        painter.end()


class SpecialMemoriesView(QWidget):
    memory_clicked = pyqtSignal(int)
    memory_dismissed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def load_memories(self, memories: list):
        for c in self._cards:
            c.setParent(None)
        self._cards.clear()

        type_groups = {}
        type_order = []
        for m in memories:
            mt = m.memory_type
            if mt not in type_groups:
                type_groups[mt] = []
                type_order.append(mt)
            type_groups[mt].append(m)

        type_labels = {
            "on_this_day": "📅 那年今日",
            "recent": "🕐 近期回忆",
            "person": "👤 人物回忆",
            "event": "🎯 事件回忆",
            "scene": "🏞️ 场景回忆",
        }

        for mt in type_order:
            label = type_labels.get(mt, mt)
            header = QLabel(label)
            header.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
            header.setStyleSheet("color: #e0e0e0; padding: 8px 0 4px 0;")
            self._layout.insertWidget(self._layout.count() - 1, header)

            row = QHBoxLayout()
            row.setSpacing(10)

            for m in type_groups[mt][:6]:
                card = MemoryCard(m)
                card.clicked.connect(self.memory_clicked.emit)
                card.dismissed.connect(self._on_dismiss)
                row.addWidget(card)

            row.addStretch()
            row_widget = QWidget()
            row_widget.setLayout(row)
            row_widget.setStyleSheet("background: transparent;")
            self._layout.insertWidget(self._layout.count() - 1, row_widget)
            self._cards.extend(type_groups[mt][:6])

    def _on_dismiss(self, memory_id: int):
        from business.memory.memory_reasoning import record_feedback
        record_feedback(memory_id, "dismiss")
        self.memory_dismissed.emit(memory_id)
