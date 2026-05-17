from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QGridLayout, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from logger_setup import logger
from db_manager import Database
from business.image_recognition.face_cluster import (
    get_clusters, get_cluster_members, rename_cluster,
    reassign_face, create_cluster_from_face
)

_db = Database()


class FaceThumbnail(QLabel):
    clicked = pyqtSignal(int)

    def __init__(self, file_id: int, parent=None):
        super().__init__(parent)
        self._file_id = file_id
        self.setFixedSize(80, 80)
        self.setStyleSheet("background: #2a2a3e; border-radius: 4px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._file_id)
        super().mousePressEvent(event)


class PersonCard(QWidget):
    clicked = pyqtSignal(int)
    rename_requested = pyqtSignal(int)

    def __init__(self, cluster_id: int, name: str, member_count: int, parent=None):
        super().__init__(parent)
        self._cluster_id = cluster_id
        self._name = name
        self._setup_ui(member_count)

    def _setup_ui(self, member_count: int):
        self.setFixedSize(160, 120)
        self.setStyleSheet("""
            PersonCard {
                background: #2a2a4e;
                border-radius: 10px;
                border: 1px solid #3a3a5e;
            }
            PersonCard:hover { border-color: #667eea; }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("👤")
        icon.setFont(QFont("Segoe UI Emoji", 24))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        name = QLabel(self._name or f"人物 {self._cluster_id}")
        name.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        name.setStyleSheet("color: #e0e0e0;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        count = QLabel(f"{member_count} 张照片")
        count.setFont(QFont("Microsoft YaHei", 8))
        count.setStyleSheet("color: #666;")
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(count)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.rename_requested.emit(self._cluster_id)
            else:
                self.clicked.emit(self._cluster_id)
        super().mousePressEvent(event)


class PersonDetailView(QWidget):
    back_requested = pyqtSignal()
    photo_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_cluster_id = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(24, 16, 24, 16)
        self._main_layout.setSpacing(12)

        self._header = QHBoxLayout()
        back_btn = QPushButton("← 返回")
        back_btn.setFont(QFont("Microsoft YaHei", 10))
        back_btn.setStyleSheet("color: #667eea; background: transparent; border: none; padding: 4px 8px;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)
        self._header.addWidget(back_btn)

        self._name_label = QLabel("人物详情")
        self._name_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        self._name_label.setStyleSheet("color: #e0e0e0;")
        self._header.addWidget(self._name_label)
        self._header.addStretch()

        rename_btn = QPushButton("✏️ 重命名")
        rename_btn.setFont(QFont("Microsoft YaHei", 9))
        rename_btn.setStyleSheet("color: #667eea; background: transparent; border: none; padding: 4px 8px;")
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.clicked.connect(self._on_rename)
        self._header.addWidget(rename_btn)
        self._main_layout.addLayout(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
        """)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(8)
        self._scroll.setWidget(self._grid_container)
        self._main_layout.addWidget(self._scroll)

    def show_person(self, cluster_id: int):
        self._current_cluster_id = cluster_id
        clusters = get_clusters()
        cluster = next((c for c in clusters if c.cluster_id == cluster_id), None)
        if cluster:
            name = cluster.person_name or f"人物 {cluster_id}"
            self._name_label.setText(name)

        members = get_cluster_members(cluster_id)
        self._load_thumbnails(members)

    def _load_thumbnails(self, file_ids: list):
        for i in reversed(range(self._grid.count())):
            w = self._grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        import os
        from config import get_settings

        cols = 6
        _thumb_dir = get_settings().thumbnail_dir
        for i, fid in enumerate(file_ids):
            thumb = FaceThumbnail(fid)
            thumb_path = os.path.join(_thumb_dir, f"{fid}.jpg")
            if os.path.exists(thumb_path):
                pm = QPixmap(thumb_path)
                if not pm.isNull():
                    thumb.setPixmap(pm.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            thumb.clicked.connect(self.photo_clicked.emit)
            self._grid.addWidget(thumb, i // cols, i % cols)

    def _on_rename(self):
        if self._current_cluster_id is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名人物", "请输入人物名称："
        )
        if ok and name.strip():
            rename_cluster(self._current_cluster_id, name.strip())
            self._name_label.setText(name.strip())


class PersonListView(QWidget):
    person_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QGridLayout(self._container)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._scroll.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

    def refresh(self):
        for i in reversed(range(self._layout.count())):
            w = self._layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._cards.clear()

        clusters = get_clusters()
        cols = 4
        for i, c in enumerate(clusters):
            members = get_cluster_members(c.cluster_id)
            card = PersonCard(c.cluster_id, c.person_name, len(members))
            card.clicked.connect(self.person_clicked.emit)
            self._layout.addWidget(card, i // cols, i % cols)
            self._cards.append(card)
