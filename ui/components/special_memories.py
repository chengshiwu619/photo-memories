import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QRect, QPoint, QTimer
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QPixmapCache

from logger_setup import logger
from core.models import Memory


class StackedCard(QFrame):
    """层叠扑克式单张照片卡片"""
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data: dict, parent=None):
        super().__init__(parent)
        self.photo_data = photo_data
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedSize(80, 100)
        self.setStyleSheet("""
            StackedCard {
                background: #222;
                border-radius: 6px;
                border: 2px solid #3a3a5e;
            }
            StackedCard:hover {
                border-color: #667eea;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._thumb = QLabel(self)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setFixedSize(76, 96)
        self._thumb.setText("...")
        self._thumb.setStyleSheet("color: #444; font-size: 10px; background: transparent;")

    def load_thumbnail(self):
        thumb = self.photo_data.get("thumbnail_path", "")
        if not thumb:
            return
        pixmap = QPixmapCache.find(thumb)
        if not pixmap:
            pixmap = QPixmap(thumb)
            if not pixmap.isNull():
                QPixmapCache.insert(thumb, pixmap)
        if not pixmap.isNull():
            self._thumb.setPixmap(
                pixmap.scaled(76, 96, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.photo_data)
        super().mousePressEvent(event)


class PokerStack(QWidget):
    """层叠扑克式布局容器 - 照片像扑克牌一样重叠排列"""
    expanded = pyqtSignal(int)  # memory_id

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._expanded = False
        self._cards = []
        self._photos = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # 标题行
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        type_colors = {
            "on_this_day": "#ff6b6b",
            "person": "#6bcb77",
            "event": "#4d96ff",
            "scene": "#9b59b6",
            "recent": "#ffd93d",
            "special_date": "#ff9f43",
            "folder": "#54a0ff",
        }
        color = type_colors.get(self._memory.memory_type, "#667eea")

        type_dot = QLabel("●")
        type_dot.setFont(QFont("Microsoft YaHei", 10))
        type_dot.setStyleSheet(f"color: {color};")
        header_layout.addWidget(type_dot)

        title = QLabel(self._memory.title)
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        header_layout.addWidget(title)

        count = QLabel(f"{len(self._memory.get_photo_id_list())}张")
        count.setFont(QFont("Microsoft YaHei", 8))
        count.setStyleSheet("color: #666;")
        header_layout.addWidget(count)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 堆叠区域（用容器+绝对定位）
        self._stack_container = QWidget()
        self._stack_container.setStyleSheet("background: transparent;")
        self._stack_container.setMinimumHeight(110)
        layout.addWidget(self._stack_container)

    def load_photos(self, photos: list):
        """加载照片到扑克堆叠中"""
        # 清理旧卡片
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._photos = list(photos)

        if not self._photos:
            return

        max_visible = 6 if not self._expanded else min(len(self._photos), 20)
        visible_photos = self._photos[:max_visible]

        if self._expanded:
            # 展开态：正常间距排列
            x_offset = 0
            for i, photo in enumerate(visible_photos):
                card = StackedCard(photo, self._stack_container)
                card.move(x_offset, 6)
                card.load_thumbnail()
                card.clicked.connect(lambda p, mid=self._memory.id: self._on_card_clicked(p, mid))
                card.show()
                self._cards.append(card)
                x_offset += 86  # 展开间距
        else:
            # 折叠态：重叠排列，每张露出30px
            x_offset = 0
            for i, photo in enumerate(visible_photos):
                card = StackedCard(photo, self._stack_container)
                card.move(x_offset, 6)
                card.raise_()  # 后面的卡片覆盖前面的
                card.load_thumbnail()
                card.clicked.connect(lambda p, mid=self._memory.id: self._on_card_clicked(p, mid))
                card.show()
                self._cards.append(card)
                x_offset += 30  # 重叠间距

            # 额外照片计数
            if len(self._photos) > max_visible:
                more = QLabel(f"+{len(self._photos) - max_visible}", self._stack_container)
                more.setFont(QFont("Microsoft YaHei", 9))
                more.setStyleSheet("color: #888; background: transparent;")
                more.move(x_offset + 4, 40)
                more.show()
                self._cards.append(more)  # 复用列表方便清理

        # 更新容器尺寸
        if self._expanded:
            total_w = max_visible * 86 + 10
        else:
            total_w = min(max_visible, len(self._photos)) * 30 + 60
        self._stack_container.setFixedWidth(max(total_w, 200))
        self._stack_container.setFixedHeight(112)

    def _on_card_clicked(self, photo_data, memory_id):
        if not self._expanded:
            self._expanded = True
            self.load_photos(self._photos)  # 重新布局为展开态
        else:
            self.expanded.emit(memory_id)

    def toggle_collapse(self):
        """折叠回扑克堆叠"""
        if self._expanded:
            self._expanded = False
            self.load_photos(self._photos)


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
        self._stacks = []
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
        self._layout.setSpacing(8)
        self._layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def load_memories(self, memories: list):
        for s in self._stacks:
            s.setParent(None)
        self._stacks.clear()

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
            "person": "👤 人物回忆",
            "event": "🎯 事件与旅行",
            "scene": "🏞️ 场景回忆",
            "recent": "🕐 近期回忆",
            "special_date": "🎯 特殊日期",
            "folder": "📁 文件夹回忆",
        }

        for mt in type_order:
            label = type_labels.get(mt, mt)
            header = QLabel(label)
            header.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
            header.setStyleSheet("color: #e0e0e0; padding: 8px 0 4px 0;")
            self._layout.insertWidget(self._layout.count() - 1, header)

            for m in type_groups[mt][:6]:
                stack = PokerStack(m)
                stack.expanded.connect(self.memory_clicked.emit)
                stack.setStyleSheet("""
                    PokerStack {
                        background: #222240;
                        border-radius: 8px;
                        border: 1px solid #3a3a5e;
                    }
                    PokerStack:hover {
                        border-color: #4a4a7e;
                    }
                """)
                self._layout.insertWidget(self._layout.count() - 1, stack)
                self._stacks.append(stack)

                # 异步加载照片
                QTimer.singleShot(0, lambda s=stack, mem=m: self._load_stack_photos(s, mem))

    def _load_stack_photos(self, stack, memory):
        from db_manager import Database
        from ui.recommendation import load_photos_from_ids

        photo_ids = memory.get_photo_id_list()
        if not photo_ids:
            return

        db = Database()
        conn = db.get_persistent_connection()
        try:
            photos = load_photos_from_ids(conn, photo_ids)
            stack.load_photos(photos)
        except Exception as e:
            logger.error(f"加载回忆照片失败 memory_id={memory.id}: {e}")

    def _on_dismiss(self, memory_id: int):
        from business.memory.memory_reasoning import record_feedback
        record_feedback(memory_id, "dismiss")
        self.memory_dismissed.emit(memory_id)
