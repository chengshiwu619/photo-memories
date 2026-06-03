import os
import sys
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger
from config import (
    CATEGORY_LIFE, CATEGORY_SAMPLE,
    CATEGORY_NAMES, is_configured, get_settings,
)
from db_manager import Database
from infra.db.repositories.memories_repo import MemoriesRepository
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from infra.db.repositories.click_history_repo import ClickHistoryRepository
from core.models import ClickHistory
from ui.components.virtual_waterfall import VirtualCategoryPage as CategoryPage
from ui.components.startup_window import StartupWindow
from ui.components.image_viewer import ImageViewer
from ui.components.sidebar import Sidebar
from ui.components.timeline_view import TimelineView
from ui.components.special_memories import SpecialMemoriesView
from ui.recommendation import rank_category_photos, load_starred_photos, reshuffle_photos
from ui.recommendation import CATEGORY_COLORS, PAGE_SIZE, record_shown_photos


from services.background_task_manager import BackgroundTaskManager
from services.startup_integrity import run_startup_integrity_check, log_startup_integrity_report

CATEGORIES = [
    (CATEGORY_LIFE, CATEGORY_NAMES[CATEGORY_LIFE]),
    (CATEGORY_SAMPLE, CATEGORY_NAMES[CATEGORY_SAMPLE]),
]

RANDOM_FIRST_PAGE_SIZE = 60
CATEGORY_CACHE_TTL_SECONDS = 300
BACKGROUND_BATCH_DELAY_MS = 3000
BACKGROUND_MAX_CONTINUOUS_BATCHES = 3
BACKGROUND_SHUTDOWN_REQUESTED = False


def _should_schedule_background_next(remaining, stopped=False, batches_run=0, max_batches=BACKGROUND_MAX_CONTINUOUS_BATCHES):
    return bool(remaining and remaining > 0 and not stopped and batches_run < max_batches)


def _cache_hit_metrics(stage, started):
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "cache_stage": stage,
        "total_ms": elapsed_ms,
        "memory_ms": 0.0,
        "batch_ms": 0.0,
        "cached_query_ms": 0.0,
        "cached_filter_ms": 0.0,
    }


class CategoryLoadWorker(QThread):
    loaded = pyqtSignal(int, int, list, dict)
    failed = pyqtSignal(int, int, str)

    def __init__(self, token, cat_id, starred_only=False, parent=None):
        super().__init__(parent)
        self._token = token
        self._cat_id = cat_id
        self._starred_only = starred_only

    def run(self):
        started = time.perf_counter()
        conn = None
        try:
            conn = Database().get_persistent_connection()
            if self._starred_only:
                query_started = time.perf_counter()
                photos = load_starred_photos(conn, self._cat_id)
                metrics = {
                    "memory_ms": 0.0,
                    "batch_ms": (time.perf_counter() - query_started) * 1000,
                    "merge_ms": 0.0,
                }
            else:
                photos, metrics = rank_category_photos(conn, self._cat_id, return_metrics=True)
            metrics["total_ms"] = (time.perf_counter() - started) * 1000
            self.loaded.emit(self._token, self._cat_id, photos, metrics)
        except Exception as exc:
            self.failed.emit(self._token, self._cat_id, repr(exc))
        finally:
            if conn is not None:
                conn.close()


def _build_siglip_tag_rows(file_ids, generate_tags_batch, should_stop, batch_size=32):
    pending = []
    processed = 0
    stopped = False
    for i in range(0, len(file_ids), batch_size):
        if should_stop():
            stopped = True
            break
        batch = file_ids[i:i + batch_size]
        tags_dict = generate_tags_batch(batch)
        processed += len(batch)
        if should_stop():
            stopped = True
            break
        for fid, tags in tags_dict.items():
            for tag in tags:
                pending.append((fid, tag, "siglip"))
    return pending, processed, stopped


def safe_path(value) -> str:
    if value is None:
        return ""
    try:
        path = os.fspath(value)
    except TypeError:
        return ""
    if isinstance(path, bytes):
        try:
            path = path.decode(sys.getfilesystemencoding() or "utf-8", errors="replace")
        except Exception:
            return ""
    return path or ""


def is_valid_path(value) -> bool:
    return bool(safe_path(value))


def safe_dirname(value) -> str:
    path = safe_path(value)
    return os.path.dirname(path) if path else ""


def safe_basename(value) -> str:
    path = safe_path(value)
    return os.path.basename(path) if path else ""


def photos_in_same_folder(photos, folder_path: str) -> list:
    if not folder_path:
        return []
    return [p for p in photos if safe_dirname(p.get("file_path")) == folder_path]


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
        self._current_nav = "random"
        self._cat_photos = {}
        self._cat_offsets = {}
        self._cat_all_loaded = {}
        self._cat_shown_ids = {}
        self._cat_load_token = 0
        self._cat_active_tokens = {}
        self._cat_workers = {}
        self._cat_result_cache = {}
        self._folder_viewer_photos = []
        self._folder_view_counts = {}
        self._suppressed_folders = set()
        self._last_scroll_vals = {}
        self._is_fullscreen = False
        self._window_drag_pos = None
        self._first_load_done = False
        self._is_dragging = False
        self._timeline_photos = []
        self._timeline_known_ids = set()
        self._timeline_loaded = False
        self._special_loaded = False
        self._special_stack_photos = []

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

        self._timeline_refresh_timer = QTimer(self)
        self._timeline_refresh_timer.setInterval(30000)
        self._timeline_refresh_timer.timeout.connect(self._refresh_timeline_incremental)

        self._check_file_id_integrity()
        self.load_memories()

    def closeEvent(self, event):
        global BACKGROUND_SHUTDOWN_REQUESTED
        BACKGROUND_SHUTDOWN_REQUESTED = True
        logger.info("MainWindow 正在关闭，等待后台线程...")
        self._timeline_refresh_timer.stop()
        manager = BackgroundTaskManager.get_instance()
        manager.cancel_all()
        manager.wait_all(2000)
        try:
            if self.db:
                self.db.close()
                logger.info("持久连接已关闭")
        except Exception as e:
            logger.warning(f"关闭持久连接时出错: {e}")
        super().closeEvent(event)

    def _check_file_id_integrity(self):
        """启动时执行只读完整性检查，记录潜在脏状态但不自动修复。"""
        try:
            report = run_startup_integrity_check(dry_run=True)
            log_startup_integrity_report(report)
        except Exception as e:
            logger.warning(f"启动时完整性检查失败: {e}")

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

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigation_changed.connect(self._on_nav_changed)
        body_layout.addWidget(self.sidebar)

        self._random_container = QWidget()
        self._random_container.setStyleSheet("background: #1a1a2e;")
        random_layout = QVBoxLayout(self._random_container)
        random_layout.setContentsMargins(0, 0, 0, 0)
        random_layout.setSpacing(0)

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

        random_layout.addWidget(nav_bar)
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

        random_layout.addWidget(self.stack)
        self.nav_buttons[0].setChecked(True)

        self._timeline_view = TimelineView()
        self._timeline_view.photo_clicked.connect(self.on_photo_clicked)
        self._timeline_view._scroll.verticalScrollBar().valueChanged.connect(
            lambda v: self._on_page_scroll(self._timeline_view, v)
        )

        self._special_view = SpecialMemoriesView()
        self._special_view.memory_clicked.connect(self._on_memory_clicked)
        self._special_view.memory_dismissed.connect(self._on_memory_dismissed)
        self._special_view.photo_clicked.connect(self._on_special_photo_clicked)
        self._special_view._scroll.verticalScrollBar().valueChanged.connect(
            lambda v: self._on_page_scroll(self._special_view, v)
        )

        self._nav_stack = QStackedWidget()
        self._nav_stack.addWidget(self._random_container)
        self._nav_stack.addWidget(self._timeline_view)
        self._nav_stack.addWidget(self._special_view)

        body_layout.addWidget(self._nav_stack)
        main_layout.addLayout(body_layout)

        self.drag_start = None

    def _on_nav_changed(self, nav_id: str):
        nav_map = {"random": 0, "timeline": 1, "special": 2}
        idx = nav_map.get(nav_id, 0)
        self._nav_stack.setCurrentIndex(idx)
        self._current_nav = nav_id

        self.top_bar.show()
        if hasattr(self, 'nav_bar'):
            self.nav_bar.show()

        # 暂停/恢复时间线刷新定时器
        if nav_id == "timeline":
            if not self._timeline_loaded:
                self._load_timeline()
            elif self.starred_only:
                self._reload_timeline_starred()
            self._timeline_refresh_timer.start()
        else:
            self._timeline_refresh_timer.stop()
            if nav_id == "special":
                if not self._special_loaded:
                    self._load_special_memories()

    def _load_timeline(self):
        starred_clause = "AND pm.is_starred = 1" if self.starred_only else ""
        rows = self.db.execute(f"""
            SELECT pm.file_id as id, pm.thumbnail_path, pm.date_taken,
                   pm.width, pm.height, f.file_path, f.file_name,
                   f.folder_path, f.folder_name as folder_display, f.file_mtime
            FROM photo_metadata pm
            JOIN files f ON pm.file_id = f.id
            JOIN folder_categories fc ON f.folder_path = fc.folder_path
            WHERE pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                  AND fc.category = ?
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                  {starred_clause}
            ORDER BY pm.date_taken DESC, f.file_mtime DESC
        """, (CATEGORY_LIFE,)).fetchall()
        from ui.recommendation import _make_photo_dict
        self._timeline_photos = [_make_photo_dict(r) for r in rows]
        self._timeline_view.load_photos(self._timeline_photos)
        self._timeline_loaded = True
        self._timeline_known_ids = {p["id"] for p in self._timeline_photos}
        self._timeline_refresh_timer.start()

    def _refresh_timeline_incremental(self):
        if not self._timeline_loaded:
            return
        try:
            rows = self.db.execute("""
                SELECT pm.file_id as id, pm.thumbnail_path, pm.date_taken,
                       pm.width, pm.height, f.file_path, f.file_name,
                       f.folder_path, f.folder_name as folder_display, f.file_mtime
                FROM photo_metadata pm
                JOIN files f ON pm.file_id = f.id
                JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                      AND fc.category = ?
                      AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                ORDER BY pm.date_taken DESC, f.file_mtime DESC
            """, (CATEGORY_LIFE,)).fetchall()
            from ui.recommendation import _make_photo_dict
            new_photos = []
            for r in rows:
                pd = _make_photo_dict(r)
                if pd["id"] not in self._timeline_known_ids:
                    new_photos.append(pd)
            if new_photos:
                self._timeline_photos = [_make_photo_dict(r) for r in rows]
                self._timeline_known_ids = {p["id"] for p in self._timeline_photos}
                self._timeline_view.load_photos(self._timeline_photos)
                logger.info(f"时间线增量刷新: 新增 {len(new_photos)} 张照片")
        except Exception as e:
            logger.warning(f"时间线增量刷新失败: {e}")

    def _get_index_progress(self) -> float:
        """获取索引进度（0.0 ~ 1.0），用于特殊回忆分阶段生成"""
        try:
            total = self.db.execute(
                "SELECT COUNT(*) FROM files WHERE is_image = 1"
            ).fetchone()[0]
            if total == 0:
                return 0.0
            indexed = self.db.execute(
                "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NOT NULL AND thumbnail_path != '__FAILED__'"
            ).fetchone()[0]
            return min(1.0, indexed / total)
        except Exception as e:
            logger.warning(f"获取索引进度失败: {e}")
            return 0.0

    def _get_life_photo_count(self) -> int:
        """获取已索引的生活照片数量（与随机回忆瀑布流口径一致）"""
        try:
            row = self.db.execute("""
                SELECT COUNT(*) FROM files f
                JOIN folder_categories fc ON f.folder_path = fc.folder_path
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE fc.category = 1
                  AND f.is_image = 1
                  AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
            """).fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.warning(f"获取生活照片数量失败: {e}")
            return 0

    def _load_special_memories(self):
        from business.memory.memory_discovery import (
            get_on_this_day_memories,
            discover_on_this_day,
            discover_special_date_memories,
            discover_folder_memories,
            discover_person_memories,
            discover_scene_memories,
            discover_event_memories,
            discover_recent_memories,
        )
        from infra.db.repositories.memories_repo import MemoriesRepository

        life_count = self._get_life_photo_count()
        logger.info(f"特殊回忆加载: 生活照片数={life_count}")

        repo = MemoriesRepository(Database())
        all_memories = repo.get_undismissed()
        on_this_day = get_on_this_day_memories()
        # 那年今日最多展示最近 2 个（按 created_at 降序）
        on_this_day = on_this_day[:2]

        # 始终以现有回忆为基底，避免 discover 只返回新创建而丢失已有
        combined = list(on_this_day) + [m for m in all_memories if m.memory_type != "on_this_day"]
        existing_ids = {m.id for m in combined}

        # Phase 1: <200 张生活照片 → 仅文件夹回忆兜底
        if life_count < 200:
            logger.info(f"特殊回忆 Phase 1: 生活照片{life_count}<200")

        # Phase 3: >=200 张生活照片 → 全量发现（不含文件夹，后面统一决定）
        else:
            logger.info(f"特殊回忆 Phase 3: 生活照片{life_count}>=200，全量生成")
            for discover in [
                lambda: discover_special_date_memories(max_groups=2),
                discover_person_memories,
                discover_scene_memories,
                discover_event_memories,
                discover_recent_memories,
            ]:
                for m in (discover() or []):
                    if m.id not in existing_ids:
                        combined.append(m)
                        existing_ids.add(m.id)

        # 有其他非文件夹回忆时，去掉文件夹回忆（文件夹仅作兜底）
        has_non_folder = any(m.memory_type != "folder" for m in combined)
        if has_non_folder:
            combined = [m for m in combined if m.memory_type != "folder"]
            logger.info(f"特殊回忆: 存在非文件夹回忆，已移除文件夹回忆，剩余 {len(combined)} 条")
        else:
            # 没有任何回忆时，补文件夹回忆兜底
            new_folder = discover_folder_memories(top_n=1)
            for m in (new_folder or []):
                if m.id not in existing_ids:
                    combined.append(m)
                    existing_ids.add(m.id)

        combined = self._limit_special_date_memories(combined, limit=2)
        self._special_view.load_memories(combined)
        self._special_loaded = True

    def _limit_special_date_memories(self, memories, limit=2):
        special_dates = [m for m in memories if m.memory_type == "special_date"]
        if len(special_dates) <= limit:
            return memories

        keep_ids = {m.id for m in special_dates[:limit]}
        return [
            m for m in memories
            if m.memory_type != "special_date" or m.id in keep_ids
        ]

    def _on_memory_clicked(self, memory_id: int):
        from infra.db.repositories.memories_repo import MemoriesRepository
        repo = MemoriesRepository(Database())
        repo.update_shown(memory_id)

    def _on_memory_dismissed(self, memory_id: int):
        logger.info(f"回忆 {memory_id} 已标记不再显示")

    def _on_special_photo_clicked(self, photo_data: dict, stack_photos: list):
        self._special_stack_photos = stack_photos
        self.on_photo_clicked(photo_data)

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
        if self._current_nav == "timeline":
            self._reload_timeline_starred()
        else:
            self._reload_random()

    def _reload_timeline_starred(self):
        """重新加载时间线，根据 starred_only 过滤"""
        self._timeline_loaded = False
        self._load_timeline()

    def _open_settings(self):
        from ui.components.setup_window import SetupWindow
        self._settings_window = SetupWindow(edit_mode=True)
        self._settings_window.config_saved.connect(self._on_settings_saved)
        self._settings_window.show()

    def _on_settings_saved(self):
        logger.info("配置已更新，重新加载")
        self._settings_window.close()
        self._settings_window = None
        self._invalidate_all_caches()
        self.load_memories()

    def load_memories(self):
        self._suppressed_folders.clear()
        self._folder_view_counts.clear()
        self._cat_offsets = {}
        self._cat_all_loaded = {}
        self._cat_shown_ids = {}
        self._cat_active_tokens = {}

        for cat_id, _ in CATEGORIES:
            memories_repo = MemoriesRepository(Database())
            title = memories_repo.get_latest_title(cat_id)
            summary = f"「{title}」" if title else ""
            self.pages[next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)].set_memory_summary(summary)

        for i in range(self.stack.count()):
            self.load_category(i)
        self.stack.setCurrentIndex(self.current_page)

    def _reload_random(self):
        self._suppressed_folders.clear()
        self._folder_view_counts.clear()
        self._cat_offsets = {}
        self._cat_all_loaded = {}
        self._cat_shown_ids = {}
        self._cat_active_tokens = {}

        for cat_id, _ in CATEGORIES:
            memories_repo = MemoriesRepository(Database())
            title = memories_repo.get_latest_title(cat_id)
            summary = f"「{title}」" if title else ""
            self.pages[next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)].set_memory_summary(summary)

        for i in range(self.stack.count()):
            self.load_category(i)
        self.stack.setCurrentIndex(self.current_page)

    def _invalidate_all_caches(self):
        self._timeline_loaded = False
        self._special_loaded = False
        self._cat_result_cache.clear()

    def _random_category_db_version(self):
        try:
            row = self.db.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM files),
                    (SELECT COALESCE(MAX(id), 0) FROM files),
                    (SELECT COUNT(*) FROM photo_metadata),
                    (SELECT COALESCE(MAX(file_id), 0) FROM photo_metadata),
                    (SELECT COUNT(*) FROM memories),
                    (SELECT COALESCE(MAX(id), 0) FROM memories)
                """
            ).fetchone()
            return tuple(row) if row is not None else None
        except Exception as exc:
            logger.debug("随机标签缓存版本读取失败: %s", exc)
            return None

    def load_category(self, index):
        if index >= len(CATEGORIES):
            return
        cat_id, _ = CATEGORIES[index]
        switch_started = time.perf_counter()
        cache_key = (cat_id, bool(self.starred_only))
        now = time.monotonic()
        db_version = self._random_category_db_version()
        cached = self._cat_result_cache.get(cache_key)
        logger.info("随机标签切换开始: cat_id=%s starred=%s", cat_id, self.starred_only)
        cache_version = cached.get("version") if cached else None
        cache_age_ok = (
            cached
            and now - cached.get("created_at", 0) <= CATEGORY_CACHE_TTL_SECONDS
            and (db_version is None or cache_version is None)
        )
        cache_version_ok = cached and db_version is not None and cache_version == db_version
        if cached and (cache_version_ok or cache_age_ok):
            logger.info(
                "随机标签缓存命中: cat_id=%s total=%s age_ms=%.1f version_match=%s",
                cat_id,
                len(cached.get("photos", [])),
                (now - cached.get("created_at", now)) * 1000,
                cache_version_ok,
            )
            self._render_category_photos(
                index,
                cat_id,
                list(cached.get("photos", [])),
                _cache_hit_metrics("visible_cache_hit", switch_started),
                from_cache=True,
            )
            return

        existing_photos = self._cat_photos.get(cat_id) or []
        if existing_photos:
            first_page = existing_photos[:RANDOM_FIRST_PAGE_SIZE]
            self._cat_offsets[cat_id] = len(first_page)
            self._cat_all_loaded[cat_id] = len(first_page) >= len(existing_photos)
            self.pages[index].load_photos(first_page)
            logger.info(
                "随机标签即时复用旧结果: cat_id=%s total=%s first=%s",
                cat_id,
                len(existing_photos),
                len(first_page),
            )

        self._cat_load_token += 1
        token = self._cat_load_token
        self._cat_active_tokens[cat_id] = token

        old_worker = self._cat_workers.get(cat_id)
        if old_worker and old_worker.isRunning():
            old_worker.requestInterruption()

        worker = CategoryLoadWorker(token, cat_id, self.starred_only)
        worker.loaded.connect(self._on_category_loaded)
        worker.failed.connect(self._on_category_failed)
        worker.finished.connect(lambda cat=cat_id, w=worker: self._on_category_worker_finished(cat, w))
        self._cat_workers[cat_id] = worker
        worker.start()

    def _on_category_worker_finished(self, cat_id, worker):
        if self._cat_workers.get(cat_id) is worker:
            del self._cat_workers[cat_id]

    def _on_category_failed(self, token, cat_id, error):
        if self._cat_active_tokens.get(cat_id) != token:
            logger.info("随机标签旧任务失败结果已忽略: cat_id=%s token=%s", cat_id, token)
            return
        page_index = next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)
        logger.warning("随机标签加载失败: cat_id=%s token=%s error=%s", cat_id, token, error)

    def _on_category_loaded(self, token, cat_id, photos, metrics):
        if self._cat_active_tokens.get(cat_id) != token:
            logger.info("随机标签旧任务结果已忽略: cat_id=%s token=%s total=%s", cat_id, token, len(photos))
            return
        page_index = next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)
        cache_key = (cat_id, bool(self.starred_only))
        self._cat_result_cache[cache_key] = {
            "created_at": time.monotonic(),
            "version": self._random_category_db_version(),
            "photos": list(photos),
            "metrics": dict(metrics),
        }
        self._render_category_photos(page_index, cat_id, list(photos), metrics, from_cache=False)

    def _render_category_photos(self, index, cat_id, all_photos, metrics=None, from_cache=False):
        render_started = time.perf_counter()
        metrics = metrics or {}

        self._cat_offsets[cat_id] = 0
        self._cat_all_loaded[cat_id] = False
        self._cat_shown_ids[cat_id] = set()
        self._cat_photos[cat_id] = list(all_photos)

        first_page = all_photos[:RANDOM_FIRST_PAGE_SIZE]
        self._cat_offsets[cat_id] = len(first_page)
        self._cat_shown_ids[cat_id].update(p["id"] for p in first_page)
        self._cat_all_loaded[cat_id] = len(first_page) >= len(all_photos)

        record_shown_photos(first_page, cat_id)

        self.pages[index].load_photos(first_page)
        render_ms = (time.perf_counter() - render_started) * 1000
        logger.info(
            "随机标签切换结束: cat_id=%s cache=%s cache_stage=%s total=%s first=%s query_ms=%.1f "
            "memory_ms=%.1f filter_ms=%.1f render_ms=%.1f",
            cat_id,
            from_cache,
            metrics.get("cache_stage", "worker_result"),
            len(all_photos),
            len(first_page),
            metrics.get("total_ms", 0.0),
            metrics.get("memory_ms", 0.0),
            metrics.get("batch_ms", 0.0),
            render_ms,
        )

    def _on_load_more(self, cat_id):
        page_index = next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)
        offset = self._cat_offsets.get(cat_id, 0)
        all_photos = self._cat_photos.get(cat_id, [])

        if self._cat_all_loaded.get(cat_id, False):
            reshuffled = reshuffle_photos(all_photos, self._cat_shown_ids.get(cat_id))
            if not reshuffled:
                self.pages[page_index].set_all_loaded(has_thumbnails_remaining=True)
                return
            self._cat_photos[cat_id] = reshuffled
            self._cat_offsets[cat_id] = 0
            self._cat_all_loaded[cat_id] = False
            self.pages[page_index].reset_for_shuffle()
            next_page = reshuffled[:PAGE_SIZE]
        else:
            next_page = all_photos[offset:offset + PAGE_SIZE]
            if not next_page:
                self._cat_all_loaded[cat_id] = True
                self.pages[page_index].set_all_loaded(has_thumbnails_remaining=True)
                return

        self._cat_offsets[cat_id] = offset + len(next_page) if not self._cat_all_loaded.get(cat_id, False) else len(next_page)
        if self._cat_offsets[cat_id] >= len(all_photos) and not self._cat_all_loaded.get(cat_id, False):
            self._cat_all_loaded[cat_id] = True

        self._cat_shown_ids.setdefault(cat_id, set()).update(p["id"] for p in next_page)
        record_shown_photos(next_page, cat_id)
        self.pages[page_index].append_photos(next_page)

    def _on_page_scroll(self, page, value):
        if value > 10:
            if hasattr(page, 'memory_summary'):
                page.memory_summary.hide()

        page_key = id(page)
        last_val = self._last_scroll_vals.get(page_key, 0)
        delta = value - last_val
        if abs(delta) > 5:
            if delta > 0 and value > 40:
                self.top_bar.hide()
                if hasattr(self, 'nav_bar'):
                    self.nav_bar.hide()
            elif delta < 0:
                self.top_bar.show()
                if hasattr(self, 'nav_bar'):
                    self.nav_bar.show()
            self._last_scroll_vals[page_key] = value

    def on_photo_clicked(self, photo_data):
        if isinstance(photo_data, int):
            file_id = photo_data
            row = self.db.execute(
                """SELECT f.id, f.file_path, f.file_name, f.folder_path,
                          f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                          pm.width, pm.height, pm.date_taken
                   FROM files f
                   LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                   WHERE f.id = ?""",
                (file_id,),
            ).fetchone()
            if not row:
                logger.warning(f"时间线点击: file_id={file_id} 未找到")
                return
            photo_data = {
                "id": row["id"], "file_path": row["file_path"], "file_name": row["file_name"],
                "folder_path": row["folder_path"],
                "folder_name": row["folder_display"] if "folder_display" in row.keys() else safe_basename(row["folder_path"]),
                "thumbnail_path": row["thumbnail_path"],
                "width": row["width"] if "width" in row.keys() else None,
                "height": row["height"] if "height" in row.keys() else None,
                "date_taken": row["date_taken"] if "date_taken" in row.keys() else None,
                "file_mtime": row["file_mtime"] if "file_mtime" in row.keys() else None,
            }

        if self._current_nav == "timeline":
            cat_id = None
            all_photos = self._timeline_photos
        elif self._current_nav == "special":
            cat_id = None
            all_photos = self._special_stack_photos
        else:
            cat_id = CATEGORIES[self.current_page][0]
            all_photos = self._cat_photos.get(cat_id, [])

        clicked_id = photo_data.get("id")
        if cat_id is not None:
            self._record_click(clicked_id, safe_path(photo_data.get("folder_path")))

        clicked_folder = safe_dirname(photo_data.get("file_path"))
        if clicked_folder:
            self._folder_view_counts[clicked_folder] = self._folder_view_counts.get(clicked_folder, 0) + 1
            if self._folder_view_counts[clicked_folder] >= 20:
                self._suppressed_folders.add(clicked_folder)
            folder_photos = photos_in_same_folder(all_photos, clicked_folder)
        else:
            self._warn_missing_photo_path(clicked_id)
            folder_photos = [photo_data]

        if not folder_photos:
            folder_photos = all_photos

        idx = next((i for i, p in enumerate(folder_photos) if p.get("id") == clicked_id), 0)

        pm_repo = PhotoMetadataRepository(Database())
        starred = set(pm_repo.get_starred_file_ids())

        self._folder_viewer_photos = folder_photos
        self.image_viewer.setParent(self.centralWidget())
        self.image_viewer.setGeometry(self._nav_stack.geometry())
        self.image_viewer.show_photos(folder_photos, idx, starred)
        self.image_viewer.raise_()

    def _warn_missing_photo_path(self, file_id):
        if not hasattr(self, "_missing_file_path_warning_ids"):
            self._missing_file_path_warning_ids = set()
        key = file_id if file_id is not None else "__unknown__"
        if key in self._missing_file_path_warning_ids:
            return
        self._missing_file_path_warning_ids.add(key)
        logger.warning(f"点击照片缺少 file_path, 已跳过同文件夹筛选: file_id={file_id}")

    def _record_click(self, file_id, folder_path):
        cat_id = CATEGORIES[self.current_page][0]
        click_repo = ClickHistoryRepository(Database())
        click_repo.insert(ClickHistory(file_id=file_id, folder_path=folder_path, category=cat_id))

    def _on_star_toggled(self, file_id, starred):
        pm_repo = PhotoMetadataRepository(Database())
        pm_repo.set_starred(file_id, starred)

    def _on_viewer_closed(self):
        pass

    def _on_recategorize(self, file_id, photo_index):
        if self.image_viewer.isVisible():
            self.image_viewer.hide_viewer()

        photo = self._folder_viewer_photos[photo_index] if photo_index < len(self._folder_viewer_photos) else None
        if not photo:
            return

        self._recategorize_target_id = photo.get("id")
        folder_path = safe_dirname(photo.get("file_path"))
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

        name_label = QLabel(safe_basename(folder_path))
        name_label.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #e0e0e0;")
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dlg_layout.addWidget(name_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        for cat_id, cat_name in {1: "生活", 2: "样片"}.items():
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
        from business.classifier.folder_classifier import set_folder_category

        set_folder_category(folder_path, new_category, "manual")

        from business.classifier.folder_classifier import build_classification_history
        build_classification_history()
        dialog.accept()
        self._invalidate_all_caches()
        self._reload_random()

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
            self.switch_page((self.current_page - 1) % 2)
        elif event.key() == Qt.Key.Key_Right:
            self.switch_page((self.current_page + 1) % 2)
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
        if event.buttons() & Qt.MouseButton.LeftButton and self._window_drag_pos is not None:
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
                    self.switch_page((self.current_page - 1) % 2)
                else:
                    self.switch_page((self.current_page + 1) % 2)
        self.drag_start = None
        self._window_drag_pos = None
        super().mouseReleaseEvent(event)


def main():
    global BACKGROUND_SHUTDOWN_REQUESTED
    BACKGROUND_SHUTDOWN_REQUESTED = False
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
        _bg_index_batches = [0]
        _bg_tag_batches = [0]
        _bg_last_tag_batch_ids = [None]
        _bg_classify_started = [False]
        _bg_classify_completed = [False]
        _bg_recover_started = [False]          # recover_existing (562) 队列
        _bg_last_scan_result = [None]          # 保存最近一次扫描结果
        _bg_pipeline_phase = ["scan"]          # 当前 pipeline 阶段

        def show_main_window():
            logger.info("show_main_window 开始, 优先构建主界面...")
            try:
                logger.info("构建 MainWindow...")
                main_window[0] = MainWindow()
                logger.info("MainWindow 构建完成, 调用 show()")
                main_window[0].show()
                logger.info("主界面已显示")
                QTimer.singleShot(100, start_background_scan)
                QTimer.singleShot(1000, start_memory_discovery)
                QTimer.singleShot(3000, start_background_path_maintenance)
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
            QTimer.singleShot(800, start_background_folder_classify)

        def start_memory_discovery():
            from PyQt6.QtCore import QThread
            class BgMemoryWorker(QThread):
                def run(self):
                    from business.memory.memory_discovery import discover_on_this_day, discover_recent_memories
                    try:
                        logger.info("开始发现回忆...")
                        on_this_day = discover_on_this_day()
                        recent = discover_recent_memories()
                        logger.info(f"发现回忆完成: {len(on_this_day)} 个那年今日, {len(recent)} 个近期回忆")
                    except Exception as e:
                        logger.exception("发现回忆失败!")

            bg = BgMemoryWorker()
            bg.finished.connect(lambda: logger.info("回忆发现线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("回忆发现线程已启动")

        _bg_path_maintenance_started = [False]
        PATH_BACKFILL_BATCH_SIZE = 5000

        def start_background_path_maintenance():
            """后台自动 path_status 回填。复用已验证的 maintain_paths.backfill_paths 逻辑。"""
            if BACKGROUND_SHUTDOWN_REQUESTED:
                return
            if _bg_path_maintenance_started[0]:
                return
            _bg_path_maintenance_started[0] = True
            from PyQt6.QtCore import QThread

            class BgPathMaintenanceWorker(QThread):
                def run(self):
                    from scripts.maintain_paths import backfill_paths
                    logger.info("后台 path maintenance 开始")
                    stats = backfill_paths(dry_run=False, limit=PATH_BACKFILL_BATCH_SIZE, verbose=False)
                    pending_after = stats["total_pending"] - stats["processed"]
                    logger.info(
                        "后台 path maintenance 完成: pending_before=%s processed=%s ok=%s missing=%s "
                        "damaged=%s stat_failed=%s outside_root=%s errors=%s pending_after=%s",
                        stats["total_pending"], stats["processed"], stats["ok"], stats["missing"],
                        stats["damaged_path"], stats["stat_failed"], stats["outside_root"],
                        stats["errors"], max(pending_after, 0),
                    )
                    self.stats = stats
                    self.pending_after = max(pending_after, 0)

            bg = BgPathMaintenanceWorker()
            def _on_path_maintenance_finished(worker=bg):
                _bg_path_maintenance_started[0] = False
                pending = getattr(worker, "pending_after", 0)
                if pending > 0 and not BACKGROUND_SHUTDOWN_REQUESTED:
                    logger.info("path maintenance 仍有 pending=%s，3s 后继续下一批", pending)
                    QTimer.singleShot(3000, start_background_path_maintenance)
                else:
                    logger.info("后台 path maintenance 全部完成")

            bg.finished.connect(_on_path_maintenance_finished)
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台 path maintenance 线程已启动")

        def start_background_folder_classify():
            if _bg_classify_started[0] or _bg_classify_completed[0]:
                logger.info("后台文件夹分类已在运行，跳过重复启动")
                return
            _bg_classify_started[0] = True
            from PyQt6.QtCore import QThread

            class BgClassifyWorker(QThread):
                def run(self):
                    manager = BackgroundTaskManager.get_instance()
                    manager.mark_task("folder_classify", "running")
                    try:
                        from business.classifier.folder_classifier import classify_folders, refine_sample_keywords
                        result = classify_folders()
                        refined = refine_sample_keywords()
                        manager.mark_task("folder_classify", "done")
                        logger.info(
                            "后台文件夹分类完成: classified=%s skipped=%s unknown=%s llm_queued=%s refined=%s",
                            result.get("classified", 0),
                            result.get("skipped", 0),
                            result.get("unknown", 0),
                            result.get("llm_queued", 0),
                            refined,
                        )
                    except Exception as exc:
                        manager.mark_task("folder_classify", "error", error=str(exc))
                        logger.exception("后台文件夹分类失败")
                    finally:
                        _bg_classify_started[0] = False
                        _bg_classify_completed[0] = True

            bg = BgClassifyWorker()
            bg.finished.connect(lambda: logger.info("后台文件夹分类线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台文件夹分类线程已启动")

        # ---- thumbnail pending 门控 ----
        THUMBNAIL_P0_THRESHOLD = 0

        def _count_thumbnail_pending():
            """查询当前 P0+P1 pending 缩略图数量（排除 recover_existing）。
            返回 0 表示无需要创建的缩略图，AI 任务可以启动。"""
            try:
                from db_manager import Database
                db = Database()
                with db.connect() as conn:
                    # 只计算真正需要创建缩略图的（排除缩略图文件已存在的回填队列）
                    row = conn.execute("""
                        SELECT COUNT(*) FROM files f
                        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                        WHERE f.is_image = 1
                          AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL
                               OR pm.thumbnail_path = '' OR pm.thumbnail_path = '__FAILED__')
                          AND (f.path_status IS NULL OR f.path_status NOT IN
                               ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
                    """).fetchone()
                    total_pending = row[0] if row else 0
                    # 减去缩略图文件已存在的（recover_existing）
                    _thumb_dir = get_settings().thumbnail_dir
                    # 快速估算：只检查一部分样本
                    if total_pending <= 100:
                        return total_pending
                    # 对大队列，用 SQL 排除已知 existing
                    # 暂时返回全部，后续 index 阶段会正确分级
                    return total_pending
            except Exception as e:
                logger.warning(f"查询 thumbnail pending 失败: {e}")
                return 999999  # 保守：查询失败时阻止 AI 任务

        def _should_defer_ai_for_thumbnails():
            """P0+P1 缩略图 pending 仍明显存在时，延迟 AI 标签/人脸。
            recover_existing (562) 不阻塞 AI 任务。"""
            try:
                from business.indexer.photo_indexer import get_unindexed_photos
                p0 = get_unindexed_photos(priority_filter='new_changed_create')
                p1 = get_unindexed_photos(priority_filter='historical_missing')
                real_pending = len(p0) + len(p1)
            except Exception:
                real_pending = _count_thumbnail_pending()

            if real_pending > THUMBNAIL_P0_THRESHOLD:
                logger.info(
                    "缩略图 P0+P1 仍有 pending=%s (threshold=%s)，延迟启动 AI 标签/人脸/特殊回忆",
                    real_pending, THUMBNAIL_P0_THRESHOLD,
                )
                return True
            return False

        _bg_tags_started = [False]
        _bg_faces_started = [False]

        def start_background_tags():
            """后台生成 SigLIP 标签（P1：缩略图 pending 清完后才启动）"""
            if BACKGROUND_SHUTDOWN_REQUESTED:
                logger.info("后台标签: 关闭中，跳过启动")
                return
            if _bg_tags_started[0]:
                logger.info("后台标签生成已在运行，跳过重复启动")
                return
            # 门控：缩略图 pending > 0 时延迟，避免 SigLIP 模型加载抢占资源
            if _should_defer_ai_for_thumbnails():
                QTimer.singleShot(5000, start_background_tags)
                return
            _bg_tags_started[0] = True
            from PyQt6.QtCore import QThread

            class BgTagsWorker(QThread):
                def __init__(self):
                    super().__init__()
                    self._stop_requested = False
                    self.remaining = 0
                    self.remaining_after = 0
                    self.processed = 0
                    self.ok = 0
                    self.failed = 0
                    self.skipped = 0
                    self.db_updated = 0
                    self.stopped = False
                    self.batch_ids = []

                def request_stop(self):
                    self._stop_requested = True
                    self.stopped = True
                    self.requestInterruption()
                    logger.info("后台标签收到停止请求")

                def _should_stop(self):
                    return self._stop_requested or self.isInterruptionRequested()

                def run(self):
                    from business.image_recognition.tag_generator import generate_tags_batch
                    from infra.db.repositories.photo_tags_repo import PhotoTagsRepository
                    from db_manager import Database

                    tags_repo = PhotoTagsRepository(Database())
                    before_pending = 0
                    file_ids = []
                    manager = BackgroundTaskManager.get_instance()
                    if self._should_stop():
                        logger.info("后台标签启动前已停止")
                        manager.mark_task("ai_tags", "done")
                        self.remaining_after = tags_repo.count_pending("siglip")
                        self.remaining = self.remaining_after
                        logger.info(
                            "后台标签批次结果: before_pending=%s batch_size=%s processed=%s ok=%s "
                            "failed=%s skipped=%s db_updated=%s remaining_after=%s",
                            before_pending,
                            len(file_ids),
                            self.processed,
                            self.ok,
                            self.failed,
                            self.skipped,
                            self.db_updated,
                            self.remaining_after,
                        )
                        return
                    device_info = manager.refresh_ai_device_status()
                    if self._should_stop():
                        logger.info("后台标签设备检测后停止")
                        manager.mark_task("ai_tags", "done")
                        return
                    manager.mark_task("ai_tags", "running")
                    tags_repo = PhotoTagsRepository(Database())
                    if self._should_stop():
                        logger.info("后台标签读取历史后停止")
                        manager.mark_task("ai_tags", "done")
                        return
                    tag_limit = max(int(getattr(get_settings(), "background_ai_tag_limit", 128)), 0)
                    file_ids, before_pending = tags_repo.get_pending_file_ids("siglip", limit=tag_limit)
                    self.batch_ids = list(file_ids)
                    self.remaining = max(before_pending - len(file_ids), 0)
                    if not file_ids:
                        logger.info("后台标签生成: 无新照片需要处理")
                        manager.mark_task("ai_tags", "done")
                        return
                    logger.info(f"后台标签生成: 将处理 {len(file_ids)} 张照片, device={device_info.device}")
                    logger.info(
                        "后台标签生成: 本批处理 %s/%s 张, remaining=%s, device=%s",
                        len(file_ids),
                        before_pending,
                        self.remaining,
                        device_info.device,
                    )
                    batch_size = 32
                    processed = 0
                    try:
                        for i in range(0, len(file_ids), batch_size):
                            if self._should_stop():
                                logger.info("后台标签停止: processed=%s/%s", processed, len(file_ids))
                                manager.mark_task("ai_tags", "done")
                                return
                            batch = file_ids[i:i + batch_size]
                            diagnostics = generate_tags_batch(batch, return_diagnostics=True)
                            if isinstance(diagnostics, dict) and "tags_by_file" in diagnostics:
                                tags_dict = diagnostics.get("tags_by_file", {})
                                encode_errors = diagnostics.get("encode_errors", [])
                            else:
                                tags_dict = diagnostics or {}
                                encode_errors = []
                            processed += len(batch)
                            self.processed = processed
                            if self._should_stop():
                                logger.info("后台标签 batch 后停止: processed=%s/%s", processed, len(file_ids))
                                manager.mark_task("ai_tags", "done")
                                return
                            pending, _, stopped = _build_siglip_tag_rows(
                                batch,
                                lambda _batch, _tags=tags_dict: _tags,
                                self._should_stop,
                                batch_size=batch_size,
                            )
                            if stopped or self._should_stop():
                                logger.info("后台标签写库前停止: processed=%s/%s", processed, len(file_ids))
                                manager.mark_task("ai_tags", "done")
                                return
                            if pending:
                                with Database().connect() as conn:
                                    conn.executemany(
                                        "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
                                        pending,
                                    )
                                self.db_updated += len(pending)
                            error_by_file = {
                                item.get("file_id"): f"{item.get('reason')}: {item.get('error', '')}".strip(": ")
                                for item in encode_errors
                                if item.get("file_id") is not None
                            }
                            status_rows = []
                            for fid in batch:
                                if fid in tags_dict:
                                    self.ok += 1
                                    status_rows.append((fid, "ok", None))
                                elif fid in error_by_file:
                                    self.failed += 1
                                    status_rows.append((fid, "failed", error_by_file[fid]))
                                else:
                                    self.skipped += 1
                                    status_rows.append((fid, "skipped", "no_tag_result"))
                            self.db_updated += tags_repo.update_status_many(status_rows, "siglip")
                            logger.debug(f"后台标签: {i + len(batch)}/{len(file_ids)}")
                        manager.mark_task("ai_tags", "done")
                        logger.info(f"后台标签生成完成: 已处理 {len(file_ids)} 张照片")
                    except Exception as exc:
                        manager.mark_task("ai_tags", "error", error=str(exc))
                        logger.exception("后台标签生成失败")

            bg = BgTagsWorker()
            bg.finished.connect(lambda: logger.info("后台标签生成线程结束"))
            def _on_tags_finished(worker=bg):
                _bg_tags_started[0] = False
                logger.info(
                    "后台标签线程结束: processed=%s remaining=%s stopped=%s",
                    getattr(worker, "processed", 0),
                    getattr(worker, "remaining", 0),
                    getattr(worker, "stopped", False),
                )
                batch_signature = tuple(getattr(worker, "batch_ids", []))
                repeated_batch = bool(batch_signature and batch_signature == _bg_last_tag_batch_ids[0])
                if repeated_batch:
                    logger.warning("后台标签连续两批 file_ids 完全相同，停止接续以避免死循环: batch_size=%s", len(batch_signature))
                _bg_last_tag_batch_ids[0] = batch_signature
                if _should_schedule_background_next(
                    getattr(worker, "remaining", 0),
                    stopped=getattr(worker, "stopped", False) or BACKGROUND_SHUTDOWN_REQUESTED or repeated_batch,
                    batches_run=_bg_tag_batches[0],
                ):
                    _bg_tag_batches[0] += 1
                    logger.info(
                        "后台标签仍有剩余: remaining=%s, next scheduled in %sms",
                        getattr(worker, "remaining", 0),
                        BACKGROUND_BATCH_DELAY_MS,
                    )
                    QTimer.singleShot(BACKGROUND_BATCH_DELAY_MS, start_background_tags)
                else:
                    _bg_tag_batches[0] = 0
                    start_background_faces()

            bg.finished.connect(_on_tags_finished)
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台标签生成线程已启动")

        def start_background_faces():
            """后台人脸检测 + 嵌入提取 + 聚类（需启用 ENABLE_FACE_DETECTION + 缩略图清完）。"""
            settings = get_settings()
            if not getattr(settings, "enable_face_detection", False):
                logger.debug("人脸检测未启用 (ENABLE_FACE_DETECTION=false), 跳过后台人脸处理")
                return
            if _bg_faces_started[0]:
                logger.info("后台人脸处理已在运行，跳过重复启动")
                return
            # 门控：缩略图 pending > 0 时延迟
            if _should_defer_ai_for_thumbnails():
                QTimer.singleShot(5000, start_background_faces)
                return
            _bg_faces_started[0] = True
            from PyQt6.QtCore import QThread

            class BgFaceWorker(QThread):
                def run(self):
                    from infra.image.face_detector import extract_embeddings_batch
                    from db_manager import Database

                    db = Database()
                    with db.connect() as conn:
                        existing = {r[0] for r in conn.execute("SELECT DISTINCT file_id FROM face_embeddings").fetchall()}
                        rows = conn.execute("""
                            SELECT pm.file_id FROM photo_metadata pm
                            WHERE pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                            ORDER BY pm.file_id
                        """).fetchall()
                    file_ids = [r[0] for r in rows if r[0] not in existing]
                    if not file_ids:
                        logger.info("后台人脸处理: 无新照片需要处理，检查是否需要重聚类")
                        _recluster_faces()
                        return
                    logger.info(f"后台人脸处理: 将处理 {len(file_ids)} 张照片")
                    batch_size = 16
                    total = len(file_ids)
                    for i in range(0, total, batch_size):
                        batch = file_ids[i:i + batch_size]
                        embeddings = extract_embeddings_batch(batch)
                        pending = [(fid, emb.astype(np.float32).tobytes()) for fid, emb in embeddings]
                        if pending:
                            with db.connect() as conn:
                                conn.executemany(
                                    "INSERT INTO face_embeddings (file_id, embedding) VALUES (?, ?)",
                                    pending,
                                )
                        logger.debug(f"后台人脸: {i + len(batch)}/{total}")
                    logger.info(f"后台人脸嵌入提取完成，开始重聚类")
                    _recluster_faces()

            def _recluster_faces():
                from business.image_recognition.face_cluster import recluster_all
                try:
                    result = recluster_all()
                    logger.info(f"人脸重聚类完成: {len(result)} 张照片分配到聚类")
                except Exception as e:
                    logger.error(f"人脸重聚类失败: {e}")

            bg = BgFaceWorker()
            bg.finished.connect(lambda: logger.info("后台人脸处理线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台人脸处理线程已启动")

        def start_background_scan():
            if _bg_scan_started[0]:
                logger.info("后台扫描已在运行，跳过重复启动")
                return
            _bg_scan_started[0] = True
            from PyQt6.QtCore import QThread

            class BgScanWorker(QThread):
                def run(self):
                    from business.scanner.fast_scan import incremental_scan, get_checkpoint_status, clear_checkpoint, ScanState
                    manager = BackgroundTaskManager.get_instance()
                    while True:
                        cp = get_checkpoint_status()
                        if cp.get("has_checkpoint") and cp.get("state") in (ScanState.PAUSED, ScanState.STOPPED, ScanState.RUNNING):
                            logger.info(f"后台扫描: 检查点状态={cp['state']}，清除后继续")
                            clear_checkpoint()
                        else:
                            break
                    logger.info("后台扫描开始")
                    manager.mark_task("scan", "running")
                    settings = get_settings()
                    # 启动时全量扫描（limit=0 → incremental_scan 内部转为不限制）
                    # 避免每次只扫 1000 且无 offset 导致无限循环同一批
                    scan_limit = 0  # 0 = 全量扫描
                    result = incremental_scan(
                        progress_callback=lambda cur, tot: None,
                        dry_run=False,
                        limit=scan_limit,
                        es_timeout=max(int(getattr(settings, "everything_timeout_seconds", 20)), 1),
                        status_callback=manager.update_from_scan_result,
                    )
                    manager.update_from_scan_result(result)
                    self.scan_result = result
                    logger.info(
                        "后台增量扫描完成: scanned=%s new=%s existing=%s changed=%s skipped=%s errors=%s",
                        result.get("scanned", 0),
                        result.get("new", 0),
                        result.get("existing", 0),
                        result.get("changed", 0),
                        result.get("skipped", 0),
                        result.get("errors", 0),
                    )

            bg = BgScanWorker()
            bg.finished.connect(lambda: logger.info("后台扫描线程结束"))

            def _on_scan_finished(worker=bg):
                _bg_scan_started[0] = False
                _bg_last_scan_result[0] = getattr(worker, 'scan_result', {})
                _bg_pipeline_phase[0] = "new_thumbnail"
                # 扫描完成后：先索引 new/changed，再处理历史队列
                start_background_index()

            bg.finished.connect(_on_scan_finished)
            bg.finished.connect(start_background_folder_classify)
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台扫描线程已启动")

        def start_background_index():
            """后台缩略图索引：按优先级多阶段执行。

            Pipeline:
            P0: new_changed_create + historical_missing → 第一时间可用
            P1: 扫描更多批次（如果 batch_limit_reached）
            P2: recover_existing (历史 562) → 低优先级回填
            P3: path_backfill (path maintenance)
            P4: AI tags / faces / special memories
            """
            if BACKGROUND_SHUTDOWN_REQUESTED:
                logger.info("后台索引: 关闭中，跳过启动")
                return
            if _bg_index_started[0]:
                logger.info("后台索引已在运行，跳过重复启动")
                return
            _bg_index_started[0] = True
            from PyQt6.QtCore import QThread, pyqtSignal

            class BgIndexWorker(QThread):
                progress = pyqtSignal(int, int)

                def __init__(self):
                    super().__init__()
                    self._stop_requested = False
                    self.result = {}
                    self.remaining = 0
                    self.stopped = False
                    self.phase = "new_changed"

                def request_stop(self):
                    self._stop_requested = True
                    self.stopped = True
                    self.requestInterruption()
                    try:
                        from business.indexer.photo_indexer import set_stopped
                        set_stopped()
                    except Exception:
                        pass
                    logger.info("后台索引收到停止请求")

                def _should_stop(self):
                    return self._stop_requested or self.isInterruptionRequested() or BACKGROUND_SHUTDOWN_REQUESTED

                def run(self):
                    from business.indexer.photo_indexer import (
                        index_new_or_changed_files, recover_existing_thumbnails,
                        index_photos, get_checkpoint_status, clear_checkpoint, IndexState,
                        INDEX_WORKERS as _IDX_WORKERS, INDEX_COMMIT_EVERY as _IDX_COMMIT_EVERY,
                    )
                    if self._should_stop():
                        self.stopped = True
                        logger.info("后台索引启动前已停止")
                        return
                    while True:
                        cp = get_checkpoint_status()
                        if cp.get("has_checkpoint") and cp.get("state") in (IndexState.PAUSED, IndexState.STOPPED):
                            logger.info(f"后台索引: 检查点状态={cp['state']}，清除后继续")
                            clear_checkpoint()
                        else:
                            break
                    manager = BackgroundTaskManager.get_instance()
                    index_limit = max(int(getattr(get_settings(), "background_index_limit", 100)), 1)

                    # ---- Phase 1: new/changed + historical_missing (P0+P1) ----
                    self.phase = "new_changed"
                    logger.info("后台索引 [Phase1]: new/changed + historical_missing 开始")
                    manager.mark_task("thumbnail_index", "running")
                    result_p0 = index_new_or_changed_files(
                        progress_callback=lambda cur, tot: None,
                        workers=_IDX_WORKERS,
                        batch_size=_IDX_COMMIT_EVERY,
                    )
                    p0_created = result_p0.get("thumbnail_created", 0)
                    p0_existing = result_p0.get("thumbnail_existing", 0)
                    p0_total = result_p0.get("total", 0)
                    p0_indexed = result_p0.get("indexed", 0)
                    logger.info(
                        "后台索引 [Phase1] 完成: total=%s created=%s existing=%s db_updated=%s",
                        p0_total, p0_created, p0_existing, result_p0.get("db_updated", 0),
                    )

                    if self._should_stop():
                        self.stopped = True
                        self.result = result_p0
                        self.remaining = 0
                        return

                    # ---- Phase 2: recover_existing / 562 (P2, 低优先级) ----
                    self.phase = "recover_existing"
                    logger.info("后台索引 [Phase2]: recover_existing (562) 开始")
                    result_p2 = recover_existing_thumbnails(
                        progress_callback=lambda cur, tot: None,
                        workers=_IDX_WORKERS,
                        batch_size=_IDX_COMMIT_EVERY,
                        batch_limit=index_limit,
                    )
                    p2_existing = result_p2.get("thumbnail_existing", 0)
                    p2_total = result_p2.get("total", 0)
                    p2_indexed = result_p2.get("indexed", 0)
                    logger.info(
                        "后台索引 [Phase2] 完成: total=%s existing=%s db_updated=%s",
                        p2_total, p2_existing, result_p2.get("db_updated", 0),
                    )

                    if self._should_stop():
                        self.stopped = True
                        self.result = result_p2
                        self.remaining = 0
                        return

                    # 合并结果
                    combined = {
                        "total": p0_total + p2_total,
                        "indexed": p0_indexed + p2_indexed,
                        "processed": result_p0.get("processed", 0) + result_p2.get("processed", 0),
                        "thumbnail_created": p0_created + result_p2.get("thumbnail_created", 0),
                        "thumbnail_existing": p0_existing + p2_existing,
                        "thumbnail_recovered": result_p0.get("thumbnail_recovered", 0) + result_p2.get("thumbnail_recovered", 0),
                        "thumbnail_failed": result_p0.get("thumbnail_failed", 0) + result_p2.get("thumbnail_failed", 0),
                        "thumbnail_skipped": result_p0.get("thumbnail_skipped", 0) + result_p2.get("thumbnail_skipped", 0),
                        "path_invalid": result_p0.get("path_invalid", 0) + result_p2.get("path_invalid", 0),
                        "db_updated": result_p0.get("db_updated", 0) + result_p2.get("db_updated", 0),
                        "output_dir": result_p0.get("output_dir", ""),
                    }
                    self.result = combined

                    # 计算剩余：检查是否还有未处理的
                    from business.indexer.photo_indexer import get_unindexed_photos
                    all_remaining = get_unindexed_photos()
                    self.remaining = len(all_remaining)

                    # pipeline next 日志
                    # 全量扫描后 batch_limit_reached=False，不再重新扫描
                    next_phase = (
                        "historical_thumbnail" if self.remaining > 0 else (
                            "recover_existing" if p2_total > 0 else "done"
                        )
                    )
                    logger.info(
                        "thumbnail batch: created=%s existing=%s recovered=%s failed=%s path_invalid=%s db_updated=%s",
                        combined["thumbnail_created"], combined["thumbnail_existing"],
                        combined["thumbnail_recovered"], combined["thumbnail_failed"],
                        combined["path_invalid"], combined["db_updated"],
                    )
                    logger.info("pipeline next: %s (remaining=%s)", next_phase, self.remaining)

                    manager.update_status(
                        state="done",
                        current_task="thumbnail_index",
                        thumbnail_pending=self.remaining,
                    )

            bg = BgIndexWorker()
            bg.progress.connect(lambda cur, tot: logger.info(f"后台索引: {cur}/{tot}"))
            bg.finished.connect(lambda: logger.info("后台索引线程结束"))
            def _on_index_finished(worker=bg):
                _bg_index_started[0] = False
                remaining = getattr(worker, "remaining", 0)
                logger.info(
                    "后台索引线程结束: indexed=%s total=%s remaining=%s stopped=%s phase=%s",
                    worker.result.get("indexed", 0),
                    worker.result.get("total", 0),
                    remaining,
                    getattr(worker, "stopped", False),
                    getattr(worker, "phase", ""),
                )

                if BACKGROUND_SHUTDOWN_REQUESTED:
                    logger.info("后台索引: 关闭中，不再调度后续任务")
                    return

                # 缩略图仍有 P0+P1 pending → 继续索引
                p0_pending = 0
                try:
                    from business.indexer.photo_indexer import get_unindexed_photos
                    p0_rows = get_unindexed_photos(priority_filter='new_changed_create')
                    p1_rows = get_unindexed_photos(priority_filter='historical_missing')
                    p0_pending = len(p0_rows) + len(p1_rows)
                except Exception:
                    p0_pending = remaining  # fallback

                if p0_pending > THUMBNAIL_P0_THRESHOLD:
                    _bg_index_batches[0] += 1
                    _bg_pipeline_phase[0] = "new_thumbnail"
                    logger.info(
                        "缩略图 P0+P1 仍有 pending=%s，优先继续索引 (batch=%s)",
                        p0_pending, _bg_index_batches[0],
                    )
                    QTimer.singleShot(2000, start_background_index)
                    return

                # P0+P1 清完后，检查是否还有 recover_existing
                p2_pending = 0
                try:
                    from business.indexer.photo_indexer import get_unindexed_photos
                    p2_rows = get_unindexed_photos(priority_filter='recover_existing')
                    p2_pending = len(p2_rows)
                except Exception:
                    pass

                if p2_pending > 0 and not _bg_recover_started[0]:
                    _bg_pipeline_phase[0] = "recover_existing"
                    logger.info("P0+P1 清完，开始 recover_existing (562): pending=%s", p2_pending)
                    start_background_recover_existing()
                    return

                # 所有缩略图处理完毕 → 启动 AI 标签
                _bg_index_batches[0] = 0
                _bg_pipeline_phase[0] = "ai_tags"
                start_background_tags()

            bg.finished.connect(_on_index_finished)
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台索引线程已启动")

        def start_background_recover_existing():
            """低优先级回填历史 562 队列：缩略图文件已存在但 DB 未回填。"""
            if BACKGROUND_SHUTDOWN_REQUESTED:
                return
            if _bg_recover_started[0]:
                return
            _bg_recover_started[0] = True
            from PyQt6.QtCore import QThread

            class BgRecoverWorker(QThread):
                def run(self):
                    from business.indexer.photo_indexer import (
                        recover_existing_thumbnails,
                        INDEX_WORKERS as _IDX_WORKERS,
                        INDEX_COMMIT_EVERY as _IDX_COMMIT_EVERY,
                    )
                    logger.info("后台 recover_existing (562) 开始")
                    result = recover_existing_thumbnails(
                        progress_callback=lambda cur, tot: None,
                        workers=_IDX_WORKERS,
                        batch_size=_IDX_COMMIT_EVERY,
                    )
                    self.result = result
                    logger.info(
                        "后台 recover_existing 完成: total=%s existing=%s db_updated=%s",
                        result.get("total", 0), result.get("thumbnail_existing", 0),
                        result.get("db_updated", 0),
                    )

            bg = BgRecoverWorker()
            def _on_recover_finished(worker=bg):
                _bg_recover_started[0] = False
                result = getattr(worker, 'result', {})
                total = result.get("total", 0)
                # 如果 created=0 且 existing>0，说明是纯回填，不需要继续循环
                if total > 0:
                    logger.info("recover_existing 回填完成: %s 条", total)
                # 回填完后启动 AI 标签
                _bg_pipeline_phase[0] = "ai_tags"
                start_background_tags()

            bg.finished.connect(_on_recover_finished)
            bg.finished.connect(lambda: logger.info("后台 recover_existing 线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台 recover_existing 线程已启动")

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
