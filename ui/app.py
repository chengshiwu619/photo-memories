import os
import sys
import shutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from logger_setup import logger
from config import (
    CATEGORY_LIFE, CATEGORY_SAMPLE, CATEGORY_PHOTOGRAPHY, CATEGORY_ADULT,
    CATEGORY_NAMES, is_configured,
)
from db_manager import Database
from ui.components.virtual_waterfall import VirtualCategoryPage as CategoryPage
from ui.components.startup_window import StartupWindow
from ui.components.image_viewer import ImageViewer
from ui.recommendation import rank_category_photos, load_category_photos_batch, load_starred_photos
from ui.recommendation import CATEGORY_COLORS, PAGE_SIZE


from services.background_task_manager import BackgroundTaskManager

CATEGORIES = [
    (CATEGORY_LIFE, CATEGORY_NAMES[CATEGORY_LIFE]),
    (CATEGORY_SAMPLE, CATEGORY_NAMES[CATEGORY_SAMPLE]),
    (CATEGORY_PHOTOGRAPHY, CATEGORY_NAMES[CATEGORY_PHOTOGRAPHY]),
    (CATEGORY_ADULT, CATEGORY_NAMES[CATEGORY_ADULT]),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NAS 照片回忆")
        self.setMinimumSize(600, 500)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.55), int(screen.height() * 0.85))
        self.move(int(screen.width() * 0.22), int(screen.height() * 0.08))

        self.current_page = 0
        self.pages = []
        self.starred_only = False
        self._cat_photos = {}
        self._cat_offsets = {}
        self._cat_all_loaded = {}
        self._folder_viewer_photos = []
        self._folder_view_counts = {}
        self._suppressed_folders = set()
        self._last_scroll_val = 0
        self._is_fullscreen = False
        self._window_drag_pos = None
        self._first_load_done = False
        self._is_dragging = False

        self.setStyleSheet("""
            QMainWindow {
                background: transparent;
            }
        """)

        _db = Database()
        _db.init_tables()
        self.db = _db.get_persistent_connection()
        self.setup_ui()

        self.image_viewer = ImageViewer()
        self.image_viewer.star_toggled.connect(self._on_star_toggled)
        self.image_viewer.closed.connect(self._on_viewer_closed)
        self.image_viewer.recategorize.connect(self._on_recategorize)
        self.image_viewer.hide()

        self.load_memories()

    def closeEvent(self, event):
        logger.info("MainWindow 正在关闭，等待后台线程...")
        BackgroundTaskManager.get_instance().wait_all(5000)
        super().closeEvent(event)

    def setup_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        central.setStyleSheet("""
            #centralWidget {
                background: #1a1a2e;
                border-radius: 10px;
            }
        """)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar.setStyleSheet("""
            #topBar {
                background: #2c3e50;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
        """)
        top_bar.setFixedHeight(52)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 8, 12, 8)

        title = QLabel("NAS 照片回忆")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; background: transparent;")
        top_layout.addWidget(title)

        top_layout.addStretch()

        self.star_btn = QPushButton("优秀回忆")
        self.star_btn.setStyleSheet("""
            QPushButton { background: #34495e; color: white; border: none;
                padding: 6px 16px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background: #4a6a8a; }
            QPushButton:checked { background: #e74c3c; }
        """)
        self.star_btn.setCheckable(True)
        self.star_btn.clicked.connect(self.toggle_starred)
        top_layout.addWidget(self.star_btn)

        settings_btn = QPushButton("⚙ 设置")
        settings_btn.setStyleSheet("""
            QPushButton { background: #34495e; color: white; border: none;
                padding: 6px 16px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background: #4a6a8a; }
        """)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        top_layout.addWidget(settings_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: rgba(255,255,255,0.6);
                border: none; border-radius: 18px; font-size: 16px; font-weight: bold; }
            QPushButton:hover { background: #e74c3c; color: white; }
        """)
        close_btn.clicked.connect(self.close)
        top_layout.addWidget(close_btn)

        main_layout.addWidget(top_bar)
        self.top_bar = top_bar

        nav_bar = QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setStyleSheet("""
            #navBar {
                background: #ecf0f1;
            }
        """)
        nav_bar.setFixedHeight(40)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(4)

        self.nav_buttons = []
        for cat_id, cat_name in CATEGORIES:
            btn = QPushButton(cat_name)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { background: transparent; border: none;
                    padding: 8px 16px; border-radius: 4px; font-size: 13px; color: #666; }
                QPushButton:hover { background: #ddd; }
                QPushButton:checked { background: #3498db; color: white; font-weight: bold; }
            """)
            btn.clicked.connect(lambda checked, idx=len(self.nav_buttons): self.switch_page(idx))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        main_layout.addWidget(nav_bar)
        self.nav_bar = nav_bar

        self.stack = QStackedWidget()

        for cat_id, cat_name in CATEGORIES:
            page = CategoryPage(cat_id, cat_name)
            page.photo_clicked.connect(self.on_photo_clicked)
            if hasattr(page, 'load_more_requested'):
                page.load_more_requested.connect(lambda cat=cat_id: self._on_load_more(cat))
            else:
                logger.warning(f"CategoryPage 缺少 load_more_requested 信号, 跳过连接")
            page.scroll.verticalScrollBar().valueChanged.connect(
                lambda v, p=page: self._on_page_scroll(p, v)
            )
            self.stack.addWidget(page)
            self.pages.append(page)

        main_layout.addWidget(self.stack)

        self.nav_buttons[0].setChecked(True)

        self.drag_start = None

    def switch_page(self, index):
        if self.image_viewer.isVisible():
            self.image_viewer.hide_viewer()
        self.current_page = index
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.load_category(index)

    def toggle_starred(self):
        self.starred_only = self.star_btn.isChecked()
        self.load_memories()

    def _open_settings(self):
        from ui.components.setup_window import SetupWindow
        self._settings_window = SetupWindow(edit_mode=True)
        self._settings_window.config_saved.connect(self._on_settings_saved)
        self._settings_window.show()

    def _on_settings_saved(self):
        logger.info("配置已更新，重新加载")
        self._settings_window.close()
        self._settings_window = None
        self.load_memories()

    def load_memories(self):
        self._suppressed_folders.clear()
        self._folder_view_counts.clear()
        self._cat_offsets = {}
        self._cat_all_loaded = {}

        for cat_id, _ in CATEGORIES:
            mem = self.db.execute(
                "SELECT title FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT 1",
                (cat_id,),
            ).fetchone()
            summary = f"「{mem['title']}」" if mem else ""
            self.pages[next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)].set_memory_summary(summary)

        for i in range(self.stack.count()):
            self.load_category(i)
        self.stack.setCurrentIndex(self.current_page)

    def load_category(self, index):
        if index >= len(CATEGORIES):
            return
        cat_id, _ = CATEGORIES[index]

        self._cat_offsets[cat_id] = 0
        self._cat_all_loaded[cat_id] = False

        if self.starred_only:
            photos = load_starred_photos(self.db, cat_id)
        else:
            photos = rank_category_photos(self.db, cat_id)

        self._cat_photos[cat_id] = list(photos)
        self._cat_offsets[cat_id] = len(photos)
        if not self._first_load_done:
            self._first_load_done = True
            QTimer.singleShot(30, lambda p=self.pages[index], ph=photos: p.load_photos(ph))
        else:
            self.pages[index].load_photos(photos)

    def _on_load_more(self, cat_id):
        if self._cat_all_loaded.get(cat_id, False):
            return
        page_index = next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)
        offset = self._cat_offsets.get(cat_id, 0)
        new_photos = load_category_photos_batch(self.db, cat_id, offset)
        if not new_photos or len(new_photos) < PAGE_SIZE:
            self._cat_all_loaded[cat_id] = True
        self._cat_offsets[cat_id] = offset + len(new_photos)
        if new_photos:
            self._cat_photos[cat_id].extend(new_photos)
            self.pages[page_index].append_photos(new_photos)
        else:
            self.pages[page_index].append_photos([])

    def _on_page_scroll(self, page, value):
        if value > 10:
            page.memory_summary.hide()

        delta = value - self._last_scroll_val
        if abs(delta) > 5:
            if delta > 0 and value > 40:
                self.top_bar.hide()
                self.nav_bar.hide()
            elif delta < 0:
                self.top_bar.show()
                self.nav_bar.show()
            self._last_scroll_val = value

    def on_photo_clicked(self, photo_data):
        clicked_id = photo_data.get("id")
        cat_id = CATEGORIES[self.current_page][0]
        all_photos = self._cat_photos.get(cat_id, [])
        self._record_click(clicked_id, photo_data.get("folder_path", ""))

        clicked_folder = os.path.dirname(photo_data.get("file_path", ""))
        self._folder_view_counts[clicked_folder] = self._folder_view_counts.get(clicked_folder, 0) + 1
        if self._folder_view_counts[clicked_folder] >= 20:
            self._suppressed_folders.add(clicked_folder)

        folder_photos = [p for p in all_photos if os.path.dirname(p.get("file_path", "")) == clicked_folder]
        if not folder_photos:
            folder_photos = all_photos

        idx = next((i for i, p in enumerate(folder_photos) if p.get("id") == clicked_id), 0)

        starred = set()
        for row in self.db.execute("SELECT file_id FROM photo_metadata WHERE is_starred = 1").fetchall():
            starred.add(row["file_id"])

        self._folder_viewer_photos = folder_photos
        self.image_viewer.setParent(self.centralWidget())
        self.image_viewer.setGeometry(self.stack.geometry())
        self.image_viewer.show_photos(folder_photos, idx, starred)
        self.image_viewer.raise_()

    def _record_click(self, file_id, folder_path):
        cat_id = CATEGORIES[self.current_page][0]
        self.db.execute(
            "INSERT INTO click_history (file_id, folder_path, category) VALUES (?, ?, ?)",
            (file_id, folder_path, cat_id),
        )
        self.db.commit()

    def _on_star_toggled(self, file_id, starred):
        self.db.execute(
            "UPDATE photo_metadata SET is_starred = ? WHERE file_id = ?",
            (1 if starred else 0, file_id),
        )
        self.db.commit()

    def _on_viewer_closed(self):
        pass

    def _on_recategorize(self, file_id, photo_index):
        if self.image_viewer.isVisible():
            self.image_viewer.hide_viewer()

        photo = self._folder_viewer_photos[photo_index] if photo_index < len(self._folder_viewer_photos) else None
        if not photo:
            return

        self._recategorize_target_id = photo.get("id")
        folder_path = os.path.dirname(photo.get("file_path", ""))
        if not folder_path:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("调整分类")
        dialog.setMinimumSize(300, 220)
        dialog.setStyleSheet("background: #1a1a2e;")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(24, 20, 24, 20)
        dlg_layout.setSpacing(12)

        name_label = QLabel(os.path.basename(folder_path))
        name_label.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #e0e0e0;")
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dlg_layout.addWidget(name_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        for cat_id, cat_name in {1: "生活", 2: "样片", 3: "摄影", 4: "色情"}.items():
            btn = QPushButton(cat_name)
            btn.setFont(QFont("Microsoft YaHei", 11))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {CATEGORY_COLORS[cat_id]}; color: white; border: none;
                    border-radius: 6px; padding: 8px 4px; font-size: 12px; }}
            """)
            btn.clicked.connect(lambda checked, c=cat_id: self._apply_recategorize(dialog, folder_path, c))
            btn_layout.addWidget(btn, 1)

        dlg_layout.addLayout(btn_layout)
        dlg_layout.addStretch()
        dialog.exec()

    def _apply_recategorize(self, dialog, folder_path, new_category):
        from classifier.folder_classifier import set_folder_category, find_similar_photos_in_folder

        target_file_id = getattr(self, "_recategorize_target_id", None)
        self._recategorize_target_id = None

        set_folder_category(folder_path, new_category, "manual")

        if target_file_id and len(self._folder_viewer_photos) > 1:
            similar_ids = find_similar_photos_in_folder(target_file_id, folder_path)
            if similar_ids:
                placeholders = ",".join("?" * len(similar_ids))
                rows = self.db.execute(
                    f"SELECT DISTINCT folder_path FROM files WHERE id IN ({placeholders})",
                    similar_ids
                ).fetchall()
                for row in rows:
                    sf = row[0]
                    if sf != folder_path:
                        set_folder_category(sf, new_category, "manual-similar")
                logger.info(f"LLM 相似移动: {len(similar_ids)} 张照片 -> 分类 {new_category}")

        from classifier.folder_classifier import build_classification_history
        build_classification_history()
        dialog.accept()
        self.load_memories()

    def keyPressEvent(self, event):
        if self.image_viewer.isVisible():
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Escape):
                self.image_viewer.keyPressEvent(event)
                return

        if event.key() == Qt.Key.Key_F:
            if self._is_fullscreen:
                self.showNormal()
                self._is_fullscreen = False
            else:
                self.showFullScreen()
                self._is_fullscreen = True
            return

        if event.key() == Qt.Key.Key_Left:
            self.switch_page((self.current_page - 1) % 4)
        elif event.key() == Qt.Key.Key_Right:
            self.switch_page((self.current_page + 1) % 4)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            child = self.childAt(pos)
            if child is not None and child is not self.centralWidget():
                super().mousePressEvent(event)
                return
            self.drag_start = event.position().toPoint()
            self._window_drag_pos = event.globalPosition().toPoint()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._window_drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._window_drag_pos
            if abs(delta.x()) > 6 or abs(delta.y()) > 6:
                self._is_dragging = True
                self.move(self.pos() + delta)
                self._window_drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_start is not None and not self._is_dragging:
            delta = event.position().toPoint() - self.drag_start
            if abs(delta.x()) > 80:
                if delta.x() > 0:
                    self.switch_page((self.current_page - 1) % 4)
                else:
                    self.switch_page((self.current_page + 1) % 4)
        self.drag_start = None
        self._window_drag_pos = None
        super().mouseReleaseEvent(event)


def _cleanup_pycache():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for root, dirs, _ in os.walk(project_root):
        if "__pycache__" in dirs:
            cache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(cache_path)
            except Exception:
                pass


def main():
    _cleanup_pycache()
    logger.info("=" * 50)
    logger.info("NAS 照片回忆 启动")
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setFont(QFont("Microsoft YaHei", 10))
        main_window = [None]
        startup_ref = [None]
        _bg_scan_started = [False]
        _bg_index_started = [False]

        def show_main_window():
            logger.info("show_main_window 开始, 优先构建主界面...")
            try:
                logger.info("构建 MainWindow...")
                main_window[0] = MainWindow()
                logger.info("MainWindow 构建完成, 调用 show()")
                main_window[0].show()
                logger.info("主界面已显示")
            except Exception as e:
                logger.exception("MainWindow 构建失败!")
                import traceback
                err_path = os.path.join(os.path.dirname(__file__), "..", "error.log")
                with open(err_path, "w", encoding="utf-8") as f:
                    traceback.print_exc(file=f)
                raise
            st = startup_ref[0]
            if st:
                st.hide()
                st.close()

        def start_background_scan():
            if _bg_scan_started[0]:
                logger.info("后台扫描已在运行，跳过重复启动")
                return
            _bg_scan_started[0] = True
            from PyQt6.QtCore import QThread

            class BgScanWorker(QThread):
                def run(self):
                    from scanner.fast_scan import full_scan, get_checkpoint_status, clear_checkpoint, ScanState
                    while True:
                        cp = get_checkpoint_status()
                        if cp.get("has_checkpoint") and cp.get("state") in (ScanState.PAUSED, ScanState.STOPPED):
                            logger.info(f"后台扫描: 检查点状态={cp['state']}，清除后继续")
                            clear_checkpoint()
                        else:
                            break
                    logger.info("后台扫描开始")
                    result = full_scan(progress_callback=lambda cur, tot: None)
                    if result.get("paused"):
                        logger.info(f"后台扫描暂停: 已扫描 {result.get('total_scanned', 0)}, 共 {result.get('total_found', 0)}")
                    else:
                        logger.info(f"后台扫描全部完成: 总计 {result.get('total', 0)} 文件, 新增 {result.get('new', 0)}, 移除 {result.get('removed', 0)}")

            bg = BgScanWorker()
            bg.finished.connect(lambda: logger.info("后台扫描线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台扫描线程已启动")

        def start_background_index():
            if _bg_index_started[0]:
                logger.info("后台索引已在运行，跳过重复启动")
                return
            _bg_index_started[0] = True
            from PyQt6.QtCore import QThread, pyqtSignal

            class BgIndexWorker(QThread):
                progress = pyqtSignal(int, int)

                def run(self):
                    from indexer.photo_indexer import index_photos, get_checkpoint_status, clear_checkpoint, IndexState
                    while True:
                        cp = get_checkpoint_status()
                        if cp.get("has_checkpoint") and cp.get("state") in (IndexState.PAUSED, IndexState.STOPPED):
                            logger.info(f"后台索引: 检查点状态={cp['state']}，清除后继续")
                            clear_checkpoint()
                        else:
                            break
                    logger.info("后台索引开始")
                    result = index_photos(progress_callback=lambda cur, tot: None)
                    if result.get("paused"):
                        logger.info(f"后台索引暂停: {result.get('indexed', 0)}/{result.get('total', 0)}")
                    else:
                        logger.info(f"后台索引全部完成: 总计 {result.get('total', 0)}, 已索引 {result.get('indexed', 0)}")

            bg = BgIndexWorker()
            bg.progress.connect(lambda cur, tot: logger.info(f"后台索引: {cur}/{tot}"))
            bg.finished.connect(lambda: logger.info("后台索引线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台索引线程已启动")

        def launch_startup():
            startup = StartupWindow()
            startup_ref[0] = startup
            startup.transition_to_main.connect(show_main_window)
            startup.background_scan_needed.connect(start_background_scan)
            startup.background_index_needed.connect(start_background_index)
            startup.show()
            startup.start()

        if not is_configured():
            logger.info("未检测到配置，展示设置窗口")
            from ui.components.setup_window import SetupWindow
            setup = SetupWindow()
            setup.config_saved.connect(lambda: (
                setup.hide(),
                setup.close(),
                launch_startup()
            ))
            setup.show()
        else:
            launch_startup()

        sys.exit(app.exec())
    except Exception as e:
        logger.exception("启动失败!")
        import traceback
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise


if __name__ == "__main__":
    main()
