import os
import random

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from logger_setup import logger
from db_manager import Database
from ui.recommendation import CATEGORY_COLORS


def _get_sample_photos(folder_path, count=2):
    db = Database()
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT f.file_path, pm.thumbnail_path
               FROM files f
               LEFT JOIN photo_metadata pm ON f.id = pm.file_id
               WHERE f.folder_path LIKE ? AND f.is_image = 1
               LIMIT 50""",
            (folder_path + "%",),
        ).fetchall()

    if not rows:
        return []

    if len(rows) > count:
        rows = random.sample(rows, count)

    results = []
    for row in rows:
        img_path = row[1] or row[0]
        results.append(img_path)
    return results


class BranchClassifierDialog(QDialog):
    result_ready = pyqtSignal(list)

    def __init__(self, branches, parent=None):
        super().__init__(parent)
        self.branches = branches
        self.index = 0
        self.results = []
        self.setWindowTitle("文件夹分类确认")
        self.setMinimumSize(600, 300)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setup_ui()
        self._show_current()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.count_label = QLabel()
        self.count_label.setFont(QFont("Microsoft YaHei", 10))
        self.count_label.setStyleSheet("color: #a0a0b0;")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.count_label)

        self.folder_label = QLabel()
        self.folder_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        self.folder_label.setStyleSheet("color: #e0e0e0;")
        self.folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_label.setWordWrap(True)
        self.folder_label.setMinimumHeight(36)
        layout.addWidget(self.folder_label)

        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(12)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_labels = []
        for _ in range(2):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(250, 150)
            lbl.setStyleSheet("""
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                background: #111;
                color: #555;
                font-size: 12px;
            """)
            lbl.setText("")
            preview_layout.addWidget(lbl)
            self.preview_labels.append(lbl)

        layout.addLayout(preview_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        labels = {1: "生活", 2: "样片", 3: "摄影", 4: "色情"}
        self.cat_btns = {}
        for cat_id in (1, 2, 3, 4):
            btn = QPushButton(labels[cat_id])
            btn.setFont(QFont("Microsoft YaHei", 11))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color = CATEGORY_COLORS[cat_id]
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 4px;
                    font-size: 12px;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
            btn.clicked.connect(lambda checked, c=cat_id: self._classify(c))
            btn_layout.addWidget(btn, 1)
            self.cat_btns[cat_id] = btn

        layout.addLayout(btn_layout)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        skip_btn = QPushButton("跳过")
        skip_btn.setFixedSize(80, 36)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setFont(QFont("Microsoft YaHei", 10))
        skip_btn.setStyleSheet("""
            QPushButton {
                background: #555;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background: #777; }
        """)
        skip_btn.clicked.connect(self._skip_one)
        bottom.addWidget(skip_btn)

        bottom.addStretch()

        done_btn = QPushButton("完成")
        done_btn.setFixedSize(100, 36)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFont(QFont("Microsoft YaHei", 10))
        done_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        done_btn.clicked.connect(self._done)
        bottom.addWidget(done_btn)

        layout.addLayout(bottom)

    def _show_current(self):
        remaining = len(self.branches) - self.index
        self.count_label.setText(
            f"第 {min(self.index + 1, len(self.branches))} / {len(self.branches)} 个  "
            f"(剩余 {max(0, remaining)} 个)"
        )

        for lbl in self.preview_labels:
            lbl.clear()
            lbl.setText("")

        if self.index >= len(self.branches):
            self.folder_label.setText("全部分类完成!")
            for btn in self.cat_btns.values():
                btn.setEnabled(False)
            return

        branch_path = self.branches[self.index]
        name = os.path.basename(branch_path)
        display = name if len(name) < 60 else name[:57] + "..."
        self.folder_label.setText(display)
        self.folder_label.setToolTip(branch_path)

        samples = _get_sample_photos(branch_path, 2)
        for i, img_path in enumerate(samples):
            if i >= len(self.preview_labels):
                break
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    250, 150,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.preview_labels[i].setPixmap(scaled)
            else:
                self.preview_labels[i].setText("无预览")

    def _classify(self, category):
        if self.index < len(self.branches):
            branch = self.branches[self.index]
            self.results.append((branch, category))
            logger.info(f"用户分类分支: {branch} -> {category}")
            self.index += 1
            self._show_current()

    def _skip_one(self):
        if self.index < len(self.branches):
            self.index += 1
            self._show_current()

    def _done(self):
        self.result_ready.emit(self.results)
        self.accept()

    def get_results(self):
        return self.results
