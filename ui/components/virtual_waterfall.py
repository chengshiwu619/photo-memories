from PyQt6.QtWidgets import QWidget, QLabel, QFrame, QScrollArea, QVBoxLayout
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter


COL_COUNT = 3
GAP = 2


class VirtualPhotoCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data, width, height, parent=None):
        super().__init__(parent)
        self.photo_data = photo_data
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedSize(width, height)
        self.setStyleSheet("background: #222;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.thumb_label = QLabel(self)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(width, height)
        self.thumb_label.setScaledContents(True)

        thumb = photo_data.get("thumbnail_path", "")
        if thumb:
            pixmap = QPixmap(thumb)
            if not pixmap.isNull():
                self.thumb_label.setPixmap(pixmap)
            else:
                self.thumb_label.setText("?")
                self.thumb_label.setStyleSheet("color: #666; font-size: 12px; background: #333;")
        else:
            self.thumb_label.setText("?")
            self.thumb_label.setStyleSheet("color: #666; font-size: 12px; background: #333;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.photo_data)


class VirtualWaterfallLayout:
    def __init__(self, photos, column_count=COL_COUNT, card_width=80):
        self._photos = photos
        self._col_count = column_count
        self._card_width = card_width
        self._positions = []
        self._total_height = 0
        self._col_heights = [0] * column_count
        self._compute_layout()

    def _compute_layout(self):
        self._positions = []
        self._col_heights = [0] * self._col_count

        for photo in self._photos:
            thumb = photo.get("thumbnail_path", "")
            height = self._card_width
            if thumb:
                pixmap = QPixmap(thumb)
                if not pixmap.isNull():
                    pw, ph = pixmap.width(), pixmap.height()
                    if pw > 0:
                        height = int(self._card_width * ph / pw)
                        height = max(60, min(height, 800))
            height += GAP

            col = self._col_heights.index(min(self._col_heights))
            x = col * (self._card_width + GAP)
            y = self._col_heights[col]
            self._positions.append((x, y, self._card_width, height))
            self._col_heights[col] += height

        self._total_height = max(self._col_heights) + GAP

    def update_card_width(self, width):
        self._card_width = max(80, width)
        self._compute_layout()

    def visible_rect(self, viewport_height, scroll_y):
        top = max(0, scroll_y - 200)
        bottom = scroll_y + viewport_height + 200
        return (top, bottom)

    def cards_in_range(self, scroll_y, viewport_height):
        top, bottom = self.visible_rect(viewport_height, scroll_y)
        result = []
        for i, (x, y, w, h) in enumerate(self._positions):
            card_bottom = y + h
            if y < bottom and card_bottom > top:
                result.append((i, x, y, w, h))
        return result

    @property
    def total_height(self):
        return self._total_height

    @property
    def total_width(self):
        return self._col_count * (self._card_width + GAP) - GAP

    def photo_at(self, index):
        return self._photos[index]


class VirtualCategoryPage(QScrollArea):
    photo_clicked = pyqtSignal(dict)
    load_more_requested = pyqtSignal()

    def __init__(self, category_id, category_name, parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self.category_name = category_name
        self._photos = []
        self._all_loaded = False
        self._loading_more = False
        self._layout = None
        self._card_widgets = {}
        self._buffer = 5

        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: #111; }")

        self._viewport = QWidget(self)
        self._viewport.setStyleSheet("background: #111;")
        self.setWidget(self._viewport)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_photos(self, photos):
        self._photos = list(photos)
        self._all_loaded = False
        self._loading_more = False
        self._destroy_visible_cards()
        self._recompute_layout()
        self._render_visible()

    def append_photos(self, new_photos):
        if not new_photos:
            self._all_loaded = True
            return
        self._photos.extend(new_photos)
        self._destroy_visible_cards()
        self._recompute_layout()
        self._render_visible()

    def _destroy_visible_cards(self):
        for card in self._card_widgets.values():
            card.deleteLater()
        self._card_widgets.clear()

    def _recompute_layout(self):
        total_w = max(400, self.width())
        card_w = (total_w - GAP * (COL_COUNT + 1)) // COL_COUNT
        card_w = max(80, card_w)
        self._layout = VirtualWaterfallLayout(self._photos, COL_COUNT, card_w)
        self._viewport.resize(self._layout.total_width, self._layout.total_height)

    def _render_visible(self):
        scroll_y = self.verticalScrollBar().value()
        vp_h = self.viewport().height()
        for idx, x, y, w, h in self._layout.cards_in_range(scroll_y, vp_h):
            if idx in self._card_widgets:
                continue
            photo = self._layout.photo_at(idx)
            card = VirtualPhotoCard(photo, w, h, self._viewport)
            card.move(x, y)
            card.clicked.connect(self.photo_clicked)
            self._card_widgets[idx] = card

        visible_indices = {idx for idx, _, _, _, _ in self._layout.cards_in_range(scroll_y, vp_h)}
        to_remove = [idx for idx in self._card_widgets if idx not in visible_indices]
        for idx in to_remove:
            self._card_widgets[idx].deleteLater()
            del self._card_widgets[idx]

    def _on_scroll(self, value):
        self._render_visible()
        bar = self.verticalScrollBar()
        if bar.maximum() > 0 and value >= bar.maximum() - 200:
            if not self._loading_more and not self._all_loaded:
                self._loading_more = True
                self.load_more_requested.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._photos:
            self._destroy_visible_cards()
            self._recompute_layout()
            self._render_visible()

    def clear(self):
        self._destroy_visible_cards()
        self._photos = []
        self._all_loaded = False
