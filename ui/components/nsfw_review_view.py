from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class NsfwCandidateCard(QFrame):
    mark_sample_requested = pyqtSignal(int)
    dismiss_requested = pyqtSignal(int)
    drag_started = pyqtSignal(int)
    drag_entered = pyqtSignal(int)
    drag_finished = pyqtSignal()

    def __init__(self, candidate: dict, index: int, parent=None):
        super().__init__(parent)
        self._candidate = candidate
        self._index = index
        self._selected = False
        self._setup_ui()

    def _apply_selected_style(self):
        border = "#f5c26b" if self._selected else "#343451"
        self.setStyleSheet(f"""
            #nsfwCandidateCard {{
                background: #202033;
                border: 2px solid {border};
                border-radius: 6px;
            }}
            #nsfwCandidateCard:hover {{
                border-color: #667eea;
            }}
            QLabel {{
                background: transparent;
            }}
        """)

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_selected_style()

    def _setup_ui(self):
        self.setObjectName("nsfwCandidateCard")
        self.setFixedWidth(168)
        self._apply_selected_style()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        thumb = QLabel()
        thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        thumb.setFixedSize(156, 126)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("background: #111; color: #666; border-radius: 4px;")
        thumb.setText("...")
        pixmap = QPixmap(self._candidate.get("thumbnail_path", ""))
        if not pixmap.isNull():
            thumb.setPixmap(
                pixmap.scaled(
                    156,
                    126,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(thumb)

        name = QLabel(self._candidate.get("file_name", ""))
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        name.setWordWrap(True)
        name.setMaximumHeight(34)
        name.setStyleSheet("color: #f0f0f5; font-size: 11px; font-weight: bold;")
        layout.addWidget(name)

        reason = QLabel(self._candidate.get("reason_text", ""))
        reason.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        reason.setWordWrap(True)
        reason.setMaximumHeight(30)
        reason.setStyleSheet("color: #f5c26b; font-size: 10px;")
        layout.addWidget(reason)

        path = QLabel(self._candidate.get("folder_path", ""))
        path.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        path.setWordWrap(True)
        path.setMaximumHeight(28)
        path.setStyleSheet("color: #9a9ab2; font-size: 10px;")
        layout.addWidget(path)

        actions = QHBoxLayout()
        actions.setSpacing(5)

        sample_btn = QPushButton("转样片")
        sample_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sample_btn.setStyleSheet("""
            QPushButton {
                background: #2980b9; color: white; border: none;
                padding: 5px 8px; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background: #3498db; }
        """)
        sample_btn.clicked.connect(lambda: self.mark_sample_requested.emit(int(self._candidate["id"])))
        actions.addWidget(sample_btn)

        dismiss_btn = QPushButton("忽略")
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a4f; color: #ddd; border: none;
                padding: 5px 8px; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background: #55556e; }
        """)
        dismiss_btn.clicked.connect(lambda: self.dismiss_requested.emit(int(self._candidate["id"])))
        actions.addWidget(dismiss_btn)
        layout.addLayout(actions)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_started.emit(self._index)
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.drag_entered.emit(self._index)
        super().enterEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class NsfwReviewView(QWidget):
    mark_sample_requested = pyqtSignal(int)
    mark_remaining_sample_requested = pyqtSignal()
    dismiss_requested = pyqtSignal(int)
    dismiss_many_requested = pyqtSignal(object)
    photo_clicked = pyqtSignal(dict)
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[NsfwCandidateCard] = []
        self._candidates: list[dict] = []
        self._rendered_columns = 0
        self._drag_anchor = None
        self._drag_current = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #171728;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("疑似样片")
        title.setStyleSheet("color: #f4f4f8; font-size: 20px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #aaa; font-size: 12px;")
        header.addWidget(self._count_label)

        self._bulk_sample_btn = QPushButton("剩余全转样片")
        self._bulk_sample_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bulk_sample_btn.setStyleSheet("""
            QPushButton {
                background: #2980b9; color: white; border: none;
                padding: 6px 14px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background: #3498db; }
            QPushButton:disabled { background: #2b3440; color: #777; }
        """)
        self._bulk_sample_btn.clicked.connect(self.mark_remaining_sample_requested)
        header.addWidget(self._bulk_sample_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #34495e; color: white; border: none;
                padding: 6px 14px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background: #4a6a8a; }
        """)
        refresh_btn.clicked.connect(self.refresh_requested)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self._empty_label = QLabel("暂时没有疑似样片候选")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #777; font-size: 14px; padding: 36px;")
        self._empty_label.hide()

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QGridLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setHorizontalSpacing(8)
        self._content_layout.setVerticalSpacing(8)
        self._content_layout.addWidget(self._empty_label, 0, 0)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

    def load_candidates(self, candidates: list[dict]):
        self._candidates = list(candidates)
        self._render_candidates()

    def _column_count(self) -> int:
        available = max(168, self._scroll.viewport().width() - 8)
        return max(1, available // 176)

    def _render_candidates(self):
        for card in self._cards:
            card.hide()
            card.deleteLater()
        self._cards.clear()

        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._empty_label:
                widget.deleteLater()

        self._count_label.setText(f"{len(self._candidates)} 个候选")
        self._bulk_sample_btn.setEnabled(bool(self._candidates))
        if not self._candidates:
            self._content_layout.addWidget(self._empty_label, 0, 0)
            self._empty_label.show()
            return

        self._empty_label.hide()
        columns = self._column_count()
        self._rendered_columns = columns
        for index, candidate in enumerate(self._candidates):
            card = NsfwCandidateCard(candidate, index, self._content)
            card.mark_sample_requested.connect(self.mark_sample_requested)
            card.dismiss_requested.connect(self.dismiss_requested)
            card.drag_started.connect(self._begin_drag_ignore)
            card.drag_entered.connect(self._extend_drag_ignore)
            card.drag_finished.connect(self._finish_drag_ignore)
            self._cards.append(card)
            self._content_layout.addWidget(card, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._candidates and self._column_count() != self._rendered_columns:
            self._render_candidates()

    def _begin_drag_ignore(self, index: int):
        self._drag_anchor = index
        self._drag_current = index
        self._update_drag_selection()

    def _extend_drag_ignore(self, index: int):
        if self._drag_anchor is None:
            return
        self._drag_current = index
        self._update_drag_selection()

    def _update_drag_selection(self):
        if self._drag_anchor is None or self._drag_current is None:
            return
        start = min(self._drag_anchor, self._drag_current)
        end = max(self._drag_anchor, self._drag_current)
        for index, card in enumerate(self._cards):
            card.set_selected(start <= index <= end)

    def _finish_drag_ignore(self):
        if self._drag_anchor is None or self._drag_current is None:
            return
        start = min(self._drag_anchor, self._drag_current)
        end = max(self._drag_anchor, self._drag_current)
        ids = [
            int(item["id"])
            for item in self._candidates[start:end + 1]
            if item.get("id") is not None
        ]
        self._drag_anchor = None
        self._drag_current = None
        for card in self._cards:
            card.set_selected(False)
        if ids:
            self.dismiss_many_requested.emit(ids)
