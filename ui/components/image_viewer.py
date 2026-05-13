from PyQt6.QtWidgets import QWidget, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QTransform

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
register_heif_opener()
Image.MAX_IMAGE_PIXELS = 500_000_000


class ImageViewer(QWidget):
    closed = pyqtSignal()
    star_toggled = pyqtSignal(int, bool)
    recategorize = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.photos = []
        self.current_index = 0
        self.starred_ids = set()
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background: #000000;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.image_label = QLabel(self)
        self.image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #000000;")

        arrow_style = """
            QPushButton {
                background: rgba(0,0,0,0.35);
                color: rgba(255,255,255,0.7);
                border: none;
                border-radius: 32px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
                color: white;
            }
            QPushButton:disabled {
                color: rgba(255,255,255,0.1);
                background: rgba(0,0,0,0.2);
            }
        """

        self.prev_btn = QPushButton("◀", self)
        self.prev_btn.setFixedSize(64, 64)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setStyleSheet(arrow_style)
        self.prev_btn.clicked.connect(self.prev_photo)

        self.next_btn = QPushButton("▶", self)
        self.next_btn.setFixedSize(64, 64)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet(arrow_style)
        self.next_btn.clicked.connect(self.next_photo)

        small_style = """
            QPushButton {
                background: rgba(0,0,0,0.4);
                color: rgba(255,255,255,0.7);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 3px;
                font-size: 11px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); color: white; }
        """

        self.star_btn = QPushButton("☆", self)
        self.star_btn.setFixedSize(40, 28)
        self.star_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.star_btn.setStyleSheet(small_style + """
            QPushButton { font-size: 16px; padding: 4px 8px; }
        """)
        self.star_btn.clicked.connect(self._toggle_star)

        self.cat_btn = QPushButton("分类", self)
        self.cat_btn.setFixedSize(52, 28)
        self.cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cat_btn.setStyleSheet(small_style)
        self.cat_btn.clicked.connect(self._change_category)

        self.open_btn = QPushButton("打开", self)
        self.open_btn.setFixedSize(52, 28)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet(small_style)
        self.open_btn.clicked.connect(self._open_file)

        self.info_label = QLabel(self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.info_label.setStyleSheet("""
            color: rgba(255,255,255,0.35);
            font-size: 10px;
            background: transparent;
            padding: 4px 10px;
        """)

    def show_photos(self, photos, index, starred_ids):
        self.photos = photos
        self.current_index = index
        self.starred_ids = starred_ids
        self.show()
        self.raise_()
        self._load_current()

    def hide_viewer(self):
        self.hide()
        self.closed.emit()

    def _load_current(self):
        if not self.photos or self.current_index < 0:
            return
        if self.current_index >= len(self.photos):
            self.current_index = len(self.photos) - 1

        photo = self.photos[self.current_index]
        file_path = photo.get("file_path", "")

        pixmap = self._load_rotated_pixmap(file_path)
        if pixmap is None or pixmap.isNull():
            thumb_path = photo.get("thumbnail_path", "")
            if thumb_path:
                pixmap = QPixmap(thumb_path)
        if pixmap is None or pixmap.isNull():
            self.image_label.setText("无法加载")
            self.image_label.setStyleSheet("color: #333; font-size: 18px; background: #000;")
            self._update_buttons()
            return

        avail = self.size()
        scaled = pixmap.scaled(
            avail, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setGeometry(0, 0, avail.width(), avail.height())
        self._update_buttons()

    def _load_rotated_pixmap(self, file_path):
        try:
            img = Image.open(file_path)
            img = ImageOps.exif_transpose(img)
            import tempfile
            import os
            fd, temp_path = tempfile.mkstemp(suffix='.jpg')
            os.close(fd)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(temp_path, "JPEG", quality=92)
            pixmap = QPixmap(temp_path)
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            return pixmap
        except Exception:
            return QPixmap(file_path)

    def _update_buttons(self):
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        file_name = photo.get("file_name", "")
        self.info_label.setText(f"{self.current_index + 1}/{len(self.photos)}  {file_name}")

        photo_id = photo.get("id")
        if photo_id in self.starred_ids:
            self.star_btn.setText("★")
            self.star_btn.setStyleSheet(self.star_btn.styleSheet() + "QPushButton { color: #f1c40f; }")
        else:
            self.star_btn.setText("☆")

        self.prev_btn.setVisible(self.current_index > 0)
        self.next_btn.setVisible(self.current_index < len(self.photos) - 1)

    def prev_photo(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current()

    def next_photo(self):
        if self.current_index < len(self.photos) - 1:
            self.current_index += 1
            self._load_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        self.image_label.setGeometry(0, 0, w, h)

        self.prev_btn.move(12, (h - 64) // 2)
        self.next_btn.move(w - 76, (h - 64) // 2)

        self.star_btn.move(w - 48, h - 40)
        self.cat_btn.move(w - 108, h - 40)
        self.open_btn.move(w - 168, h - 40)
        self.info_label.setGeometry(0, 0, w, 22)

        self._load_current()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.prev_photo()
        elif event.key() == Qt.Key.Key_Right:
            self.next_photo()
        elif event.key() == Qt.Key.Key_Escape:
            self.hide_viewer()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            btn_geo = self.prev_btn.geometry().united(self.next_btn.geometry())
            btn_geo = btn_geo.united(self.star_btn.geometry())
            btn_geo = btn_geo.united(self.cat_btn.geometry())
            btn_geo = btn_geo.united(self.open_btn.geometry())
            if btn_geo.contains(pos):
                super().mousePressEvent(event)
                return
            self.hide_viewer()
        super().mousePressEvent(event)

    def _toggle_star(self):
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        photo_id = photo.get("id")
        if photo_id is None:
            return
        if photo_id in self.starred_ids:
            self.starred_ids.discard(photo_id)
            self.star_toggled.emit(photo_id, False)
        else:
            self.starred_ids.add(photo_id)
            self.star_toggled.emit(photo_id, True)
        self._update_buttons()

    def _change_category(self):
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        photo_id = photo.get("id")
        if photo_id is None:
            return
        self.recategorize.emit(photo_id, self.current_index)

    def _open_file(self):
        import subprocess
        import os
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        file_path = photo.get("file_path", "")
        folder = os.path.dirname(file_path)
        if folder and os.path.exists(folder):
            subprocess.Popen(["explorer", "/select,", file_path])
