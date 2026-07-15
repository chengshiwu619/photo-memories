from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QRect, QPoint, QTimer
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor

from logger_setup import logger
from core.models import Memory


class _PixmapCache:
    _cache: dict[str, QPixmap] = {}
    _max = 500

    @classmethod
    def find(cls, key: str):
        return cls._cache.get(key)

    @classmethod
    def insert(cls, key: str, pm: QPixmap):
        if len(cls._cache) >= cls._max:
            oldest = list(cls._cache.keys())[:100]
            for k in oldest:
                del cls._cache[k]
        cls._cache[key] = pm


QPixmapCache = _PixmapCache


class StackedCard(QFrame):
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


class GridCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data: dict, size: int, parent=None):
        super().__init__(parent)
        self.photo_data = photo_data
        self._size = size
        self.setFixedSize(size, size)
        self.setStyleSheet("""
            GridCard {
                background: #222;
                border-radius: 2px;
                border: 1px solid #3a3a5e;
            }
            GridCard:hover {
                border-color: #667eea;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._thumb = QLabel(self)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setFixedSize(size, size)
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
            scaled = pixmap.scaled(self._size, self._size,
                                   Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            crop_x = (scaled.width() - self._size) // 2
            crop_y = (scaled.height() - self._size) // 2
            cropped = scaled.copy(crop_x, crop_y, self._size, self._size)
            self._thumb.setPixmap(cropped)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.photo_data)
        super().mousePressEvent(event)


class CoverCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data: dict, width: int, height: int, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.photo_data = photo_data
        self._w = width
        self._h = height
        self.setFixedSize(width, height)
        self.setStyleSheet("""
            CoverCard {
                background: #10101c;
                border-radius: 10px;
                border: 1px solid #33334f;
            }
            CoverCard:hover {
                border-color: #8d8df0;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._thumb = QLabel(self)
        self._thumb.setFixedSize(width, height)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setText("正在打开这段回忆")
        self._thumb.setStyleSheet("color: #777; background: transparent; font-size: 13px;")

        self._shade = QLabel(self)
        self._shade.setGeometry(0, height - 116, width, 116)
        self._shade.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0,0,0,0),
                stop:0.38 rgba(0,0,0,125),
                stop:1 rgba(0,0,0,218)
            );
            border-bottom-left-radius: 10px;
            border-bottom-right-radius: 10px;
        """)

        self._title = QLabel(title, self)
        self._title.setGeometry(22, height - 90, max(100, width - 44), 32)
        self._title.setFont(QFont("Microsoft YaHei", 20, QFont.Weight.Bold))
        self._title.setStyleSheet("color: #fffaf2; background: transparent;")

        self._subtitle = QLabel(subtitle, self)
        self._subtitle.setGeometry(22, height - 52, max(100, width - 44), 24)
        self._subtitle.setFont(QFont("Microsoft YaHei", 10))
        self._subtitle.setStyleSheet("color: #d8d2c8; background: transparent;")

    def load_thumbnail(self):
        thumb = self.photo_data.get("thumbnail_path", "")
        if not thumb:
            return
        pixmap = QPixmapCache.find(thumb)
        if not pixmap:
            pixmap = QPixmap(thumb)
            if not pixmap.isNull():
                QPixmapCache.insert(thumb, pixmap)
        if pixmap.isNull():
            return

        scaled = pixmap.scaled(
            self._w,
            self._h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        crop_x = max(0, (scaled.width() - self._w) // 2)
        crop_y = max(0, (scaled.height() - self._h) // 2)
        self._thumb.setPixmap(scaled.copy(crop_x, crop_y, self._w, self._h))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.photo_data)
        super().mousePressEvent(event)


_EXPAND_COLS = 5
_EXPAND_CARD_SIZE = 80
_EXPAND_GAP = 3


class PokerStack(QWidget):
    expanded = pyqtSignal(int)
    dismissed = pyqtSignal(int)
    photo_clicked = pyqtSignal(object, object)
    collapse_others = pyqtSignal(object)

    def __init__(self, memory: Memory, featured: bool = False, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._featured = featured
        self._expanded = False
        self._cards = []
        self._photos = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18 if self._featured else 12, 14 if self._featured else 8, 18 if self._featured else 12, 16)
        layout.setSpacing(10 if self._featured else 6)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

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

        title_text = "精选回忆" if self._featured else self._memory.title
        title = QLabel(title_text)
        title.setFont(QFont("Microsoft YaHei", 10 if self._featured else 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #bfb8ce;" if self._featured else "color: #e8e8ee;")
        title.setWordWrap(True)
        header_layout.addWidget(title)

        count = QLabel(f"{len(self._memory.get_photo_id_list())}张")
        count.setFont(QFont("Microsoft YaHei", 9))
        count.setStyleSheet("color: #c8c2b8;" if self._featured else "color: #8f8fa8;")
        header_layout.addWidget(count)
        header_layout.addStretch()

        dismiss_btn = QPushButton("暂不显示")
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setFixedHeight(26)
        dismiss_btn.setStyleSheet("""
            QPushButton {
                color: #c9c9d6;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.14); }
        """)
        dismiss_btn.clicked.connect(lambda: self.dismissed.emit(self._memory.id))
        header_layout.addWidget(dismiss_btn)
        layout.addLayout(header_layout)

        self._stack_container = QWidget()
        self._stack_container.setStyleSheet("background: transparent;")
        self._stack_container.setMinimumHeight(340 if self._featured else 110)
        layout.addWidget(self._stack_container)

    def load_photos(self, photos: list):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._photos = list(photos)

        if not self._photos:
            return

        if self._expanded:
            self._layout_expanded()
        elif self._featured:
            self._layout_featured_collapsed()
        else:
            self._layout_collapsed()

    def _layout_featured_collapsed(self):
        container_w = max(520, self._stack_container.width())
        cover_w = min(container_w, 920)
        cover_h = 260

        subtitle = self._memory.description or f"{len(self._photos)} 张照片"
        cover = CoverCard(self._photos[0], cover_w, cover_h, self._memory.title, subtitle, self._stack_container)
        cover.move(0, 0)
        cover.clicked.connect(lambda p: self._on_card_clicked(p))
        cover.show()
        cover.load_thumbnail()
        self._cards.append(cover)

        preview_size = 58
        for i, photo in enumerate(self._photos[1:6]):
            card = GridCard(photo, preview_size, self._stack_container)
            card.move(i * (preview_size + 6), cover_h + 12)
            card.clicked.connect(lambda p: self._on_card_clicked(p))
            card.show()
            card.load_thumbnail()
            self._cards.append(card)

        hint = QLabel("点击展开", self._stack_container)
        hint.setFont(QFont("Microsoft YaHei", 10))
        hint.setStyleSheet("color: #d8d2c8; background: transparent;")
        hint.move(cover_w - 86, cover_h + 28)
        hint.show()
        self._cards.append(hint)

        self._stack_container.setFixedHeight(cover_h + 82)

    def _layout_collapsed(self):
        # 固定展示最多 6 张堆叠
        max_visible = min(len(self._photos), 6)

        visible_photos = self._photos[:max_visible]
        x_offset = 0
        for i, photo in enumerate(visible_photos):
            card = StackedCard(photo, self._stack_container)
            card.move(x_offset, 0)
            card.raise_()
            card.clicked.connect(lambda p: self._on_card_clicked(p))
            card.show()
            card.load_thumbnail()
            self._cards.append(card)
            x_offset += 30

        remaining = len(self._photos) - max_visible
        if remaining > 0:
            more = QLabel(f"+{remaining}", self._stack_container)
            more.setFont(QFont("Microsoft YaHei", 9))
            more.setStyleSheet("color: #888; background: transparent;")
            more.move(x_offset + 4, 40)
            more.show()
            self._cards.append(more)

        # 不设固定宽度 —— 由父布局撑满至全宽
        self._stack_container.setFixedHeight(112)

    def _layout_expanded(self):
        max_visible = min(len(self._photos), 12 if self._featured else 10)
        visible_photos = self._photos[:max_visible]

        # 动态计算卡片尺寸，对齐时间线风格
        container_w = self._stack_container.width()
        if container_w > 0:
            card_size = max(60, (container_w - _EXPAND_GAP * (_EXPAND_COLS + 1)) // _EXPAND_COLS)
        else:
            card_size = _EXPAND_CARD_SIZE

        rows = (len(visible_photos) + _EXPAND_COLS - 1) // _EXPAND_COLS

        for i, photo in enumerate(visible_photos):
            row = i // _EXPAND_COLS
            col = i % _EXPAND_COLS
            card = GridCard(photo, card_size, self._stack_container)
            x = col * (card_size + _EXPAND_GAP)
            y = row * (card_size + _EXPAND_GAP)
            card.move(x, y)
            card.clicked.connect(lambda p, photos=self._photos: self.photo_clicked.emit(p, photos))
            card.show()
            card.load_thumbnail()
            self._cards.append(card)

        total_w = _EXPAND_COLS * (card_size + _EXPAND_GAP) - _EXPAND_GAP
        total_h = rows * (card_size + _EXPAND_GAP) - _EXPAND_GAP
        self._stack_container.setFixedWidth(max(total_w, 200))
        self._stack_container.setFixedHeight(total_h + 12)

    def _on_card_clicked(self, photo_data):
        if not self._expanded:
            self._expanded = True
            self.collapse_others.emit(self)
            self.expanded.emit(self._memory.id)
            self.load_photos(self._photos)

    def toggle_collapse(self):
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
    photo_clicked = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stacks = []
        self._load_generation = 0
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #11111d;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #11111d; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a52; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(28, 22, 28, 22)
        self._layout.setSpacing(14)
        # bottom_spacer 和 end_label 在 load_memories 末尾再添加到底部
        self._bottom_spacer = QWidget()
        self._bottom_spacer.setFixedHeight(0)
        self._bottom_spacer.hide()

        self._end_label = QLabel("")
        self._end_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._end_label.setStyleSheet("color: #555; font-size: 12px; padding: 12px 0 24px 0;")
        self._end_label.hide()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def load_memories(self, memories: list):
        self._load_generation += 1
        generation = self._load_generation
        self._clear_memory_widgets()

        # 把 spacer/end_label 从布局移除，后面按当前状态重新决定是否添加到底部
        self._layout.removeWidget(self._bottom_spacer)
        self._layout.removeWidget(self._end_label)

        if not memories:
            empty = QLabel("还没有准备好一段可展示的回忆")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #8f8fa8; font-size: 14px; padding: 80px 0;")
            self._layout.addWidget(empty)
            self._stacks.append(empty)
            return

        title = QLabel("今日回忆")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #f0ece5;")
        self._layout.addWidget(title)

        for idx, m in enumerate(memories):
            if idx == 1:
                section = QLabel("还可以看看")
                section.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
                section.setStyleSheet("color: #aaa4b8; padding-top: 8px;")
                self._layout.addWidget(section)

            stack = PokerStack(m, featured=(idx == 0))
            stack.expanded.connect(self.memory_clicked.emit)
            stack.dismissed.connect(self._on_dismiss)
            stack.photo_clicked.connect(self.photo_clicked.emit)
            stack.collapse_others.connect(self._on_collapse_others)
            if idx == 0:
                stack.setStyleSheet("""
                    PokerStack {
                        background: #1b1b2f;
                        border-radius: 10px;
                        border: 1px solid #383854;
                    }
                    PokerStack:hover { border-color: #6767a8; }
                """)
            else:
                stack.setStyleSheet("""
                    PokerStack {
                        background: #1a1a2c;
                        border-radius: 8px;
                        border: 1px solid #30304c;
                    }
                    PokerStack:hover { border-color: #565687; }
                """)
            self._layout.addWidget(stack)
            self._stacks.append(stack)

            QTimer.singleShot(0, lambda s=stack, mem=m, gen=generation: self._load_stack_photos(s, mem, gen))

        # 底部留白 + 结束提示
        viewport_h = self._scroll.viewport().height() if self._scroll.viewport() else 400
        spacer_h = max(200, int(viewport_h * 0.5))
        self._bottom_spacer.setFixedHeight(spacer_h)
        self._bottom_spacer.show()
        self._layout.addWidget(self._bottom_spacer)

        self._end_label.hide()

    def _clear_memory_widgets(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if not widget:
                continue
            if widget in (self._bottom_spacer, self._end_label):
                widget.hide()
                continue
            widget.setParent(None)
            widget.deleteLater()
        self._stacks.clear()

    def _load_stack_photos(self, stack, memory, generation: int):
        from db_manager import Database
        from ui.recommendation import load_photos_from_ids

        if generation != self._load_generation or stack not in self._stacks:
            return

        photo_ids = memory.get_photo_id_list()
        if not photo_ids:
            return

        with Database().connect() as conn:
            try:
                photos = load_photos_from_ids(conn, photo_ids, require_thumbnail=True, preserve_order=True)
                if generation != self._load_generation or stack not in self._stacks:
                    return
                stack.load_photos(photos)
            except Exception as e:
                logger.error(f"加载回忆照片失败 memory_id={memory.id}: {e}")

    def _on_collapse_others(self, expanded_stack):
        for s in self._stacks:
            if s is not expanded_stack and s._expanded:
                s.toggle_collapse()

    def _on_dismiss(self, memory_id: int):
        from business.memory.memory_reasoning import record_feedback
        record_feedback(memory_id, "dismiss")
        for stack in list(self._stacks):
            if getattr(stack, "_memory", None) and stack._memory.id == memory_id:
                self._layout.removeWidget(stack)
                self._stacks.remove(stack)
                stack.setParent(None)
                stack.deleteLater()
                break
        self.memory_dismissed.emit(memory_id)
