from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QPixmap, QFont

from logger_setup import logger

_COLS = 5
_GAP = 3
_HEADER_H = 36
_ROW_H = 0
_SCROLL_BUFFER = 600
_DEBOUNCE_MS = 150

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _format_date(date_str: str) -> str:
    try:
        dt = datetime.fromisoformat(date_str[:19])
        return "{}年{}月{}日 · {}".format(dt.year, dt.month, dt.day, _WEEKDAYS[dt.weekday()])
    except Exception:
        return date_str[:10] if date_str else "未知日期"


class _PhotoCard(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, file_id: int, size: int):
        super().__init__()
        self._file_id = file_id
        self._size = size
        self.setFixedSize(size, size)
        self.setStyleSheet("background: #222; border-radius: 2px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._thumb = QLabel(self)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setFixedSize(size, size)
        self._thumb.setText("…")
        self._thumb.setStyleSheet("color: #444; font-size: 10px; background: transparent;")

    def load_thumbnail(self, thumbnail_path: str):
        if not thumbnail_path:
            return
        pm = QPixmapCache.find(thumbnail_path)
        if not pm:
            pm = QPixmap(thumbnail_path)
            if not pm.isNull():
                QPixmapCache.insert(thumbnail_path, pm)
        if not pm.isNull():
            scaled = pm.scaled(self._size, self._size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            crop_x = (scaled.width() - self._size) // 2
            crop_y = (scaled.height() - self._size) // 2
            cropped = scaled.copy(crop_x, crop_y, self._size, self._size)
            self._thumb.setPixmap(cropped)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._file_id)
        super().mousePressEvent(event)


class _PixmapCache:
    _cache: dict[str, QPixmap] = {}
    _max = 500

    @classmethod
    def find(cls, key: str) -> Optional[QPixmap]:
        return cls._cache.get(key)

    @classmethod
    def insert(cls, key: str, pm: QPixmap):
        if len(cls._cache) >= cls._max:
            oldest = list(cls._cache.keys())[:100]
            for k in oldest:
                del cls._cache[k]
        cls._cache[key] = pm


QPixmapCache = _PixmapCache


class TimelineView(QWidget):
    photo_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._photos: list[dict] = []
        self._groups: list[dict] = []
        self._card_size = 80
        self._visible_cards: dict[tuple, _PhotoCard] = {}
        self._visible_headers: dict[int, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #111;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: #111; border: none; }
            QScrollBar:vertical {
                background: #111; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #444; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: #111;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(0)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._recompute)

    def load_photos(self, photos: list[dict]):
        self._clear_all()
        self._photos = photos
        self._build_groups()
        self._recompute()

    def _build_groups(self):
        groups: dict[str, list[dict]] = {}
        order = []
        for p in self._photos:
            date_key = (p.get("date_taken") or p.get("file_mtime") or "")[:10]
            if not date_key:
                date_key = "未知日期"
            if date_key not in groups:
                order.append(date_key)
            groups[date_key].append(p) if date_key in groups else groups.setdefault(date_key, []).append(p)

        self._groups = []
        for dk in order:
            self._groups.append({"date_key": dk, "photos": groups[dk]})

    def _recompute(self):
        total_w = max(400, self._scroll.viewport().width())
        self._card_size = max(60, (total_w - _GAP * (_COLS + 1)) // _COLS)

        self._clear_all()

        total_h = 0
        for gi, group in enumerate(self._groups):
            header_y = total_h
            total_h += _HEADER_H
            n = len(group["photos"])
            rows = (n + _COLS - 1) // _COLS
            row_h = self._card_size + _GAP
            total_h += rows * row_h
            total_h += 8

        self._container.setFixedSize(total_w, max(total_h + 20, self._scroll.viewport().height()))
        self._render_visible()

    def _render_visible(self):
        scroll_y = self._scroll.verticalScrollBar().value()
        view_h = self._scroll.viewport().height()
        visible_top = scroll_y - _SCROLL_BUFFER
        visible_bottom = scroll_y + view_h + _SCROLL_BUFFER

        needed_cards: set[tuple] = set()
        needed_headers: set[int] = set()
        y = 0
        for gi, group in enumerate(self._groups):
            header_y = y
            y += _HEADER_H

            n = len(group["photos"])
            rows = (n + _COLS - 1) // _COLS
            row_h = self._card_size + _GAP
            group_bottom = y + rows * row_h

            if header_y <= visible_bottom and group_bottom >= visible_top:
                needed_headers.add(gi)
                if gi not in self._visible_headers:
                    lbl = QLabel(_format_date(group["date_key"]))
                    lbl.setParent(self._container)
                    lbl.setFixedHeight(_HEADER_H)
                    lbl.setFixedWidth(self._container.width() - _GAP * 2)
                    lbl.move(_GAP, header_y)
                    lbl.setStyleSheet("color: #c0c0c0; font-size: 13px; font-weight: bold; background: #111; padding-left: 4px;")
                    lbl.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                    lbl.show()
                    self._visible_headers[gi] = lbl

                for ri in range(rows):
                    row_y = y + ri * row_h
                    if row_y + row_h < visible_top or row_y > visible_bottom:
                        continue
                    for ci in range(_COLS):
                        idx = ri * _COLS + ci
                        if idx >= n:
                            break
                        key = (gi, ri, ci)
                        needed_cards.add(key)
                        if key not in self._visible_cards:
                            photo = group["photos"][idx]
                            card = _PhotoCard(photo.get("file_id", 0), self._card_size)
                            card_x = _GAP + ci * (self._card_size + _GAP)
                            card_y = row_y
                            card.move(card_x, card_y)
                            card.setParent(self._container)
                            card.show()
                            card.clicked.connect(self.photo_clicked.emit)
                            thumb = photo.get("thumbnail_path", "")
                            if thumb:
                                card.load_thumbnail(thumb)
                            self._visible_cards[key] = card

            y = group_bottom + 8

        to_remove = [k for k in self._visible_cards if k not in needed_cards]
        for k in to_remove:
            card = self._visible_cards.pop(k)
            card.deleteLater()

        to_remove_h = [k for k in self._visible_headers if k not in needed_headers]
        for k in to_remove_h:
            lbl = self._visible_headers.pop(k)
            lbl.deleteLater()

    def _on_scroll(self, value):
        self._render_visible()

    def _clear_all(self):
        for card in self._visible_cards.values():
            card.deleteLater()
        self._visible_cards.clear()
        for lbl in self._visible_headers.values():
            lbl.deleteLater()
        self._visible_headers.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(_DEBOUNCE_MS)
