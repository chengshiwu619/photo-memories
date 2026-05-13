from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap

COL_COUNT = 3
GAP = 2


class PhotoCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data):
        super().__init__()
        self.photo_data = photo_data
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("PhotoCard { background: transparent; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_anim.setDuration(40)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setup_ui()

    def fade_in(self):
        self._fade_anim.start()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setScaledContents(True)
        self.thumb_label.setMinimumHeight(20)

        thumb_path = self.photo_data.get("thumbnail_path", "")
        if thumb_path:
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                self.thumb_label.setPixmap(pixmap)
            else:
                self.thumb_label.setText("?")
                self.thumb_label.setStyleSheet("color: #333; font-size: 10px;")
        else:
            self.thumb_label.setText("?")
            self.thumb_label.setStyleSheet("color: #333; font-size: 10px;")

        layout.addWidget(self.thumb_label)

    def mousePressEvent(self, event):
        self.clicked.emit(self.photo_data)


class WaterfallLayout:
    def __init__(self, column_count):
        self._col_count = column_count
        self._cols = []
        self._card_widgets = []
        self._container = QWidget()
        h = QHBoxLayout(self._container)
        h.setContentsMargins(GAP, GAP, GAP, GAP)
        h.setSpacing(GAP)
        for i in range(column_count):
            col = QWidget()
            cl = QVBoxLayout(col)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(GAP)
            cl.addStretch()
            h.addWidget(col, 1)
            self._cols.append(cl)

    def add_card(self, card, column_index):
        col = self._cols[column_index]
        col.insertWidget(col.count() - 1, card)
        self._card_widgets.append(card)

    def shortest_column(self):
        return min(range(self._col_count), key=lambda i: sum(
            self._cols[i].itemAt(j).widget().sizeHint().height()
            for j in range(self._cols[i].count() - 1)
            if self._cols[i].itemAt(j) and self._cols[i].itemAt(j).widget()
        ))

    def clear(self):
        for w in self._card_widgets:
            w.deleteLater()
        self._card_widgets.clear()
        for col in self._cols:
            while col.count() > 1:
                item = col.takeAt(0)
                if item:
                    if item.widget():
                        item.widget().deleteLater()

    def card_count(self):
        return len(self._card_widgets)


class CategoryPage(QWidget):
    photo_clicked = pyqtSignal(dict)
    load_more_requested = pyqtSignal()

    def __init__(self, category_id, category_name):
        super().__init__()
        self.category_id = category_id
        self.category_name = category_name
        self.all_photos = []
        self.loaded_count = 0
        self._loading_more = False
        self._all_loaded = False
        self.waterfall = None

        self._reveal_timer = QTimer(self)
        self._reveal_timer.setInterval(4)
        self._reveal_timer.timeout.connect(self._reveal_one_card)
        self._reveal_index = 0
        self._reveal_photos = []
        self._reveal_card_width = 80

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: #111; }")
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: #111;")
        self.grid_layout = QVBoxLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(0)

        self.memory_summary = QLabel()
        self.memory_summary.setStyleSheet("""
            font-size: 12px; color: #aaa; padding: 6px 10px;
            background: rgba(0,0,0,0.5);
        """)
        self.memory_summary.setWordWrap(True)
        self.memory_summary.hide()
        self.grid_layout.addWidget(self.memory_summary)

        self.scroll.setWidget(self.grid_widget)
        layout.addWidget(self.scroll)

    def set_memory_summary(self, text):
        if text:
            self.memory_summary.setText(text)
            self.memory_summary.show()
        else:
            self.memory_summary.hide()

    def _reveal_one_card(self):
        if self._reveal_index >= len(self._reveal_photos):
            self._reveal_timer.stop()
            self.loaded_count = len(self._reveal_photos)
            return

        photo = self._reveal_photos[self._reveal_index]
        card = PhotoCard(photo)
        card.clicked.connect(self.photo_clicked.emit)

        thumb = photo.get("thumbnail_path", "")
        if thumb:
            pixmap = QPixmap(thumb)
            if not pixmap.isNull():
                pw = pixmap.width()
                ph = pixmap.height()
                card_h = int(self._reveal_card_width * ph / max(pw, 1))
                card_h = max(60, min(card_h, 800))
                card.setFixedHeight(card_h)
                card.setFixedWidth(self._reveal_card_width)
                card.thumb_label.setFixedSize(self._reveal_card_width, card_h)
            else:
                card.setFixedHeight(self._reveal_card_width)
                card.setFixedWidth(self._reveal_card_width)
                card.thumb_label.setFixedSize(self._reveal_card_width, self._reveal_card_width)
        else:
            card.setFixedHeight(self._reveal_card_width)
            card.setFixedWidth(self._reveal_card_width)
            card.thumb_label.setFixedSize(self._reveal_card_width, self._reveal_card_width)

        col = self.waterfall.shortest_column()
        self.waterfall.add_card(card, col)
        card.fade_in()

        self._reveal_index += 1

    def load_photos(self, photos):
        self._reveal_timer.stop()
        if self.waterfall:
            self.waterfall.clear()
            idx = self.grid_layout.indexOf(self.waterfall._container)
            if idx >= 0:
                self.grid_layout.takeAt(idx)
                self.waterfall._container.deleteLater()
            self.waterfall = None

        self.all_photos = list(photos)
        self._all_loaded = False
        self._loading_more = False

        total_w = max(400, self.width())
        self._reveal_card_width = (total_w - GAP * (COL_COUNT + 1)) // COL_COUNT
        self._reveal_card_width = max(80, self._reveal_card_width)

        self.waterfall = WaterfallLayout(COL_COUNT)
        self.grid_layout.addWidget(self.waterfall._container)

        self._reveal_photos = list(photos)
        self._reveal_index = 0
        self._reveal_timer.start()

    def append_photos(self, new_photos):
        if not new_photos:
            self._all_loaded = True
            return

        self.all_photos.extend(new_photos)
        self._reveal_photos = list(new_photos)
        self._reveal_index = 0

        total_w = max(400, self.width())
        self._reveal_card_width = (total_w - GAP * (COL_COUNT + 1)) // COL_COUNT
        self._reveal_card_width = max(80, self._reveal_card_width)

        self._reveal_timer.start()

    def _on_scroll(self, value):
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() > 0 and value >= bar.maximum() - 150:
            if not self._reveal_timer.isActive():
                if self.loaded_count >= len(self.all_photos) and not self._all_loaded:
                    self._load_more()

    def _load_more(self):
        if not self._all_loaded:
            self._loading_more = True
            self.load_more_requested.emit()

    def clear(self):
        if self.waterfall:
            self.waterfall.clear()
            idx = self.grid_layout.indexOf(self.waterfall._container)
            if idx >= 0:
                self.grid_layout.takeAt(idx)
                self.waterfall._container.deleteLater()
            self.waterfall = None
        self.all_photos = []
        self.loaded_count = 0
        self._all_loaded = False
