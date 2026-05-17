from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QPoint
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


class _YearIndex(QWidget):
    """时间线右侧年月索引拉球（替代原生滚动条）"""
    year_selected = pyqtSignal(int)
    scroll_continuous = pyqtSignal(int)
    drag_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # month_data: [(year, month, photo_count), ...] 按年月降序
        self._month_data: list[tuple[int, int, int]] = []
        self._date_map: list[tuple[int, int]] = []  # dot_index -> (year, month)
        self._total_dots: int = 0
        self._dot_spacing: float = 10.0
        self._ball_y: float = 10.0     # 默认顶部位置，避免初始 0 导致 ym 计算失败
        self._ball_visible: bool = False
        self._is_dragging: bool = False
        self._hover_ym: tuple[int, int] = (0, 0)
        self._indicator: Optional[QLabel] = None
        self._scroll_range: int = 0

        self.setFixedWidth(28)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

    def set_data(self, month_data: list[tuple[int, int, int]]):
        """设置年月数据: [(year, month, photo_count), ...] 按年月降序"""
        self._month_data = month_data
        self._rebuild_dots()
        self.update()

    def set_scroll_range(self, max_val: int):
        self._scroll_range = max_val

    def set_scroll_value(self, val: int):
        if self._is_dragging or self._scroll_range <= 0:
            return
        h = self.height()
        usable_h = h - 20
        ratio = val / self._scroll_range if self._scroll_range > 0 else 0
        self._ball_y = 10 + ratio * usable_h
        self.update()

    def _rebuild_dots(self):
        self._date_map = []
        if not self._month_data:
            self._total_dots = 0
            return

        avg = sum(c for _, _, c in self._month_data) / len(self._month_data)
        avg = max(1, avg)

        for year, month, count in self._month_data:
            self._date_map.append((year, month))
            n = max(1, int(count / avg * 3))
            for _ in range(n):
                self._date_map.append((-1, -1))

        self._total_dots = len(self._date_map)

    def paintEvent(self, event):
        if not self._month_data:
            return
        from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        usable_h = h - 20

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawRoundedRect(2, 0, w - 4, h, 6, 6)

        if self._total_dots == 0:
            return
        self._dot_spacing = usable_h / self._total_dots

        cent_x = w // 2

        for di in range(self._total_dots):
            yr, mo = self._date_map[di]
            dot_y = 10 + di * self._dot_spacing

            if yr == -1:
                painter.setPen(QPen(QColor(60, 60, 90), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(cent_x - 2, int(dot_y) - 2, 4, 4)
            else:
                painter.setPen(QPen(QColor(100, 110, 200), 1))
                painter.setBrush(QBrush(QColor(100, 110, 200)))
                painter.drawEllipse(cent_x - 4, int(dot_y) - 4, 8, 8)

        if self._ball_visible:
            ball_y = int(self._ball_y)
            ball_alpha = 255 if self._is_dragging else 180
            ball_color = QColor(255, 107, 107, ball_alpha)
            painter.setPen(QPen(QColor(255, 150, 150, ball_alpha), 2))
            painter.setBrush(QBrush(ball_color))
            painter.drawEllipse(cent_x - 10, ball_y - 10, 20, 20)

        if self._ball_visible and self._hover_ym and self._hover_ym[0]:
            self._show_indicator(self._hover_ym)

        painter.end()

    def _show_indicator(self, ym: tuple[int, int]):
        year, month = ym
        text = f"{year}年{month}月"
        if not self._indicator:
            self._indicator = QLabel(self.window())
            self._indicator.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
            self._indicator.setStyleSheet("""
                color: #fff; font-size: 14px; font-weight: bold;
                background: #667eea; padding: 4px 10px;
                border-radius: 6px;
            """)
            self._indicator.show()
        self._indicator.setText(text)
        self._indicator.adjustSize()
        # 将拉球中心位置映射到窗口坐标系（indicator 的父控件）
        ball_local = QPoint(0, int(self._ball_y))
        ball_in_window = self.mapTo(self.window(), ball_local)
        label_x = ball_in_window.x() - self._indicator.width() - 10
        label_y = ball_in_window.y() - self._indicator.height() // 2
        self._indicator.move(label_x, label_y)

    def _hide_indicator(self):
        if self._indicator:
            self._indicator.hide()
            self._indicator = None

    def _ball_y_to_ym(self, ball_y: float) -> tuple[int, int]:
        """将拉球位置映射到最近的年月"""
        h = self.height()
        usable_h = h - 20
        if self._total_dots == 0 or self._dot_spacing <= 0:
            return (0, 0)
        di = max(0, min(self._total_dots - 1, int((ball_y - 10) / self._dot_spacing)))
        yr, mo = self._date_map[di]
        if yr != -1:
            return (yr, mo)
        for d in range(di, -1, -1):
            r, m = self._date_map[d]
            if r != -1:
                return (r, m)
        for d in range(di, self._total_dots):
            r, m = self._date_map[d]
            if r != -1:
                return (r, m)
        return (0, 0)

    def _ball_y_to_scroll(self, ball_y: float) -> int:
        """将拉球位置按比例映射到滚动条值"""
        if self._scroll_range <= 0:
            return 0
        h = self.height()
        usable_h = h - 20
        ratio = max(0, min(1, (ball_y - 10) / usable_h))
        return int(ratio * self._scroll_range)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._ball_visible = True
            self._ball_y = max(10, min(self.height() - 10, event.pos().y()))
            ym = self._ball_y_to_ym(self._ball_y)
            self._hover_ym = ym
            if ym[0]:
                sv = self._ball_y_to_scroll(self._ball_y)
                self.scroll_continuous.emit(sv)
            self.update()

    def mouseMoveEvent(self, event):
        h = self.height()
        self._ball_y = max(10, min(h - 10, event.pos().y()))

        if self._is_dragging:
            ym = self._ball_y_to_ym(self._ball_y)
            if ym != self._hover_ym:
                self._hover_ym = ym
            sv = self._ball_y_to_scroll(self._ball_y)
            self.scroll_continuous.emit(sv)
            self.update()
        else:
            self._ball_visible = True
            self._hover_ym = self._ball_y_to_ym(self._ball_y)
            self.update()

    def mouseReleaseEvent(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self.drag_ended.emit()
        self._hide_indicator()
        self.update()

    def enterEvent(self, event):
        self._ball_visible = True
        self._hover_ym = self._ball_y_to_ym(self._ball_y)
        self.update()

    def leaveEvent(self, event):
        if not self._is_dragging:
            self._ball_visible = False
            self._hide_indicator()
        self.update()


class TimelineView(QWidget):
    photo_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._photos: list[dict] = []
        self._groups: list[dict] = []
        self._years: list[int] = []
        self._year_positions: dict[int, int] = {}  # year -> y position
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
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: #111; border: none; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: #111;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(0)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        # 侧边年月索引（挂在 viewport 上，固定在视口右侧不随内容滚动）
        vp = self._scroll.viewport()
        self._year_index = _YearIndex(vp)
        self._year_index.drag_ended.connect(self._on_year_drag_ended)
        self._year_index.scroll_continuous.connect(self._on_continuous_scroll)
        self._year_index.move(vp.width() - 28, 0)
        self._year_index.resize(28, vp.height())
        self._year_index.raise_()

        # 渲染防抖：拖动时避免高频 widget 创建/销毁导致的跳动
        self._render_debounce = QTimer()
        self._render_debounce.setSingleShot(True)
        self._render_debounce.timeout.connect(self._render_visible)

        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._recompute)

        # 回到最新按钮（右下角浮动）
        self._top_btn = QPushButton("△", self._scroll.viewport())
        self._top_btn.setFixedSize(32, 32)
        self._top_btn.setStyleSheet("""
            QPushButton {
                background: rgba(100, 110, 200, 150);
                color: #fff;
                border: none;
                border-radius: 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(100, 110, 200, 230);
            }
        """)
        self._top_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._top_btn.clicked.connect(lambda: self._scroll.verticalScrollBar().setValue(0))
        self._top_btn.hide()
        # 滚动时决定按钮显示/隐藏
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_for_top_btn)

    def _build_year_index(self):
        """构建年月索引，传入 [(year, month, photo_count), ...] 给拉球组件"""
        month_counts: dict[tuple[int, int], int] = {}
        for group in self._groups:
            date_key = group.get("date_key", "")
            if date_key and len(date_key) >= 7:
                try:
                    year = int(date_key[:4])
                    month = int(date_key[5:7])
                    key = (year, month)
                    month_counts[key] = month_counts.get(key, 0) + len(group["photos"])
                except ValueError:
                    pass
        sorted_data = sorted(month_counts.items(), key=lambda x: x[0], reverse=True)
        data_list = [(y, m, c) for (y, m), c in sorted_data]
        self._year_index.set_data(data_list)
        self._year_index.set_scroll_range(self._scroll.verticalScrollBar().maximum())

    def _scroll_to_year(self, year: int):
        """滚动到指定年份（保留以备将来纯点击跳转）"""
        if year in self._year_positions:
            self._scroll.verticalScrollBar().setValue(self._year_positions[year])

    def _on_continuous_scroll(self, scroll_value: int):
        """拉球拖动时连续滚动"""
        self._scroll.verticalScrollBar().setValue(scroll_value)

    def _on_year_drag_ended(self):
        """拉球释放后立即执行一次最终渲染"""
        self._render_debounce.stop()
        self._render_visible()

    def _on_scroll_for_top_btn(self, value: int):
        """滚动时控制回到最新按钮的显示/隐藏"""
        if value > 200:
            self._top_btn.show()
            # 定位在右下角
            vp_w = self._scroll.viewport().width()
            vp_h = self._scroll.viewport().height()
            self._top_btn.move(vp_w - 44, vp_h - 44)
        else:
            self._top_btn.hide()

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
            # 记录年份位置
            date_key = group.get("date_key", "")
            if date_key and len(date_key) >= 4:
                try:
                    year = int(date_key[:4])
                    if year not in self._year_positions:
                        self._year_positions[year] = header_y
                except ValueError:
                    pass

            total_h += _HEADER_H
            n = len(group["photos"])
            rows = (n + _COLS - 1) // _COLS
            row_h = self._card_size + _GAP
            total_h += rows * row_h
            total_h += 8

        self._container.setFixedSize(total_w, max(total_h + 20, self._scroll.viewport().height()))
        self._render_visible()
        self._build_year_index()

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
                            photo_id = photo.get("id", 0)
                            if not photo_id:
                                continue
                            card = _PhotoCard(photo_id, self._card_size)
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
        if self._year_index._is_dragging:
            # 拖动中：防抖渲染，避免高频 widget 操作导致跳动
            self._render_debounce.start(30)
        else:
            self._render_visible()
        self._year_index.set_scroll_value(value)

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
        vp = self._scroll.viewport()
        self._year_index.move(vp.width() - 28, 0)
        self._year_index.resize(28, vp.height())
        self._top_btn.move(vp.width() - 44, vp.height() - 44)
