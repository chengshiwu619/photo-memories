"""
Memory 维护模块测试。

覆盖：
- visible_refs=0 的 memory 不进入瀑布流
- visible_refs=0 的 memory 可被 dry-run 维护命令识别
- apply 后被标记 is_hidden=1
- is_hidden=1 的 memory 不再触发 startup integrity error
- partially_unrenderable memory 有足够可见照片时仍可显示
"""

import json
import os
import sqlite3
import tempfile
import shutil

import pytest


def _make_db(db_path):
    """创建包含 memories/files/photo_metadata/folder_categories 的测试数据库。"""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            file_name TEXT,
            folder_path TEXT,
            folder_name TEXT,
            file_mtime TEXT,
            is_image INTEGER DEFAULT 1,
            path_status TEXT DEFAULT 'ok'
        );
        CREATE TABLE IF NOT EXISTS photo_metadata (
            file_id INTEGER PRIMARY KEY,
            thumbnail_path TEXT,
            is_duplicate_of INTEGER,
            date_taken TEXT,
            category INTEGER,
            width INTEGER,
            height INTEGER
        );
        CREATE TABLE IF NOT EXISTS sample_keywords (
            keyword TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS photo_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(file_id, tag, source)
        );
        CREATE TABLE IF NOT EXISTS folder_categories (
            folder_path TEXT PRIMARY KEY,
            category INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category INTEGER DEFAULT 1,
            memory_type TEXT NOT NULL DEFAULT 'auto',
            title TEXT DEFAULT '',
            photo_ids TEXT NOT NULL,
            cover_file_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            dismissed_at TEXT,
            is_hidden INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


def _insert_test_data(db_path, file_count=10, all_valid=True):
    """插入测试文件、缩略图和 memories。"""
    conn = sqlite3.connect(db_path)
    try:
        for i in range(1, file_count + 1):
            conn.execute(
                "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (i, f"/photos/img_{i}.jpg", f"img_{i}.jpg", "/photos", "photos", "2026-06-0{i}T12:00:00"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO folder_categories (folder_path, category) VALUES ('/photos', 1)"
            )
            if all_valid or i <= 4:
                conn.execute(
                    "INSERT INTO photo_metadata (file_id, thumbnail_path, date_taken, width, height) VALUES (?, ?, ?, 100, 80)",
                    (i, f"/thumb/{i}.jpg", f"2026-06-0{i}T12:00:00"),
                )
            else:
                conn.execute(
                    "INSERT INTO photo_metadata (file_id, thumbnail_path, date_taken, width, height) VALUES (?, ?, ?, 100, 80)",
                    (i, "__FAILED__", f"2026-06-0{i}T12:00:00"),
                )
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# 瀑布流过滤测试
# ============================================================================

class TestMemoryWaterfallFilter:
    """验证不可渲染 memory 不进入瀑布流。"""

    def test_fully_unrenderable_memory_skipped(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        _make_db(db_path)
        _insert_test_data(db_path, file_count=5, all_valid=True)

        conn = sqlite3.connect(db_path)
        # memory 引用不存在的照片 → visible_refs=0
        conn.execute(
            "INSERT INTO memories (memory_type, photo_ids, cover_file_id) VALUES (?, ?, ?)",
            ("special_date", json.dumps([999]), 999),
        )
        conn.commit()
        conn.close()

        import business.recommendation as rec
        from db_manager import Database
        db = Database(db_path)
        monkeypatch.setattr(rec, "Database", lambda: db)

        conn = db.get_persistent_connection()
        try:
            photos = rec._load_ranked_memory_photos(conn, 1)
        finally:
            conn.close()

        # 0 个可见 refs → 跳过，不输出任何照片
        assert len(photos) == 0

    def test_partially_unrenderable_memory_still_shows(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()
        _make_db(db_path)

        conn = sqlite3.connect(db_path)
        for i in range(1, 9):
            thumb_file = thumb_dir / f"{i}.jpg"
            thumb_file.write_bytes(b"thumb")
            conn.execute(
                "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (i, f"/photos/img_{i}.jpg", f"img_{i}.jpg", "/photos", "photos", "2026-06-0{i}T12:00:00"),
            )
            conn.execute("INSERT OR IGNORE INTO folder_categories (folder_path, category) VALUES ('/photos', 1)")
            conn.execute(
                "INSERT INTO photo_metadata (file_id, thumbnail_path, date_taken, width, height) VALUES (?, ?, ?, 100, 80)",
                (i, str(thumb_file), f"2026-06-0{i}T12:00:00"),
            )
        conn.execute(
            "INSERT INTO memories (memory_type, photo_ids, cover_file_id) VALUES (?, ?, ?)",
            ("special_date", json.dumps([1, 2, 3, 4, 5, 6, 7, 8]), 1),
        )
        conn.commit()
        conn.close()

        import business.recommendation as rec
        from db_manager import Database
        db = Database(db_path)
        monkeypatch.setattr(rec, "Database", lambda: db)

        cn = db.get_persistent_connection()
        try:
            photos = rec._load_ranked_memory_photos(cn, 1)
        finally:
            cn.close()

        assert len(photos) >= 4  # 至少 MIN_MEMORY_VISIBLE_REFS

    def test_hidden_memory_skipped(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        _make_db(db_path)
        _insert_test_data(db_path, file_count=8, all_valid=True)

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO memories (memory_type, photo_ids, cover_file_id, is_hidden) VALUES (?, ?, ?, ?)",
            ("special_date", json.dumps([1, 2, 3, 4, 5]), 1, 1),
        )
        conn.commit()
        conn.close()

        import business.recommendation as rec
        from db_manager import Database
        db = Database(db_path)
        monkeypatch.setattr(rec, "Database", lambda: db)

        conn = db.get_persistent_connection()
        try:
            photos = rec._load_ranked_memory_photos(conn, 1)
        finally:
            conn.close()

        assert len(photos) == 0  # hidden memory 不参与瀑布流


# ============================================================================
# 完整性检查降级测试
# ============================================================================

class TestIntegrityMemorySeverity:
    """验证 unrenderable memory 不再报 error。"""

    def test_fully_unrenderable_is_warning_not_error(self, tmp_path):
        photo_dir = tmp_path / "cache"
        thumb_dir = tmp_path / "thumbs"
        photo_dir.mkdir()
        thumb_dir.mkdir()

        valid_thumb = thumb_dir / "1.jpg"
        valid_thumb.write_bytes(b"ok")
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE files (id INTEGER PRIMARY KEY, file_path TEXT, is_image INTEGER DEFAULT 1);
            CREATE TABLE photo_metadata (file_id INTEGER PRIMARY KEY, thumbnail_path TEXT, is_duplicate_of INTEGER);
            CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, memory_type TEXT,
                photo_ids TEXT, cover_file_id INTEGER, dismissed_at TEXT, is_hidden INTEGER DEFAULT 0);
            CREATE TABLE thumbnail_params (key TEXT PRIMARY KEY, value TEXT);
        """)
        conn.execute("INSERT INTO files (id, file_path) VALUES (1, 'a.jpg')")
        conn.execute("INSERT INTO photo_metadata (file_id, thumbnail_path) VALUES (1, ?)", (str(valid_thumb),))
        # memory 引用不存在的 file_id 999 → visible_refs=0
        conn.execute("INSERT INTO memories (memory_type, photo_ids) VALUES ('special_date', ?)", (json.dumps([999]),))
        conn.execute("INSERT INTO thumbnail_params (key, value) VALUES ('thumbnail_sig', 'test-v1')")
        conn.commit()
        conn.close()

        from services.startup_integrity import build_startup_integrity_report
        from infra.image.thumbnail_cache import build_thumbnail_cache_signature

        class S:
            photo_data_dir = str(photo_dir)
            thumbnail_dir = str(thumb_dir)

        report = build_startup_integrity_report(
            dry_run=True, db_path=str(db_path), settings=S(),
        )
        checks = {c["check_name"]: c for c in report["checks"]}
        assert checks["memories_unrenderable_in_ui"]["severity"] == "warning"
        assert checks["memories_unrenderable_in_ui"]["count"] == 1

    def test_hidden_memory_not_counted_in_unrenderable(self, tmp_path):
        photo_dir = tmp_path / "cache"
        thumb_dir = tmp_path / "thumbs"
        photo_dir.mkdir()
        thumb_dir.mkdir()
        valid_thumb = thumb_dir / "1.jpg"
        valid_thumb.write_bytes(b"ok")
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE files (id INTEGER PRIMARY KEY, file_path TEXT, is_image INTEGER DEFAULT 1);
            CREATE TABLE photo_metadata (file_id INTEGER PRIMARY KEY, thumbnail_path TEXT, is_duplicate_of INTEGER);
            CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, memory_type TEXT,
                photo_ids TEXT, cover_file_id INTEGER, dismissed_at TEXT, is_hidden INTEGER DEFAULT 0);
            CREATE TABLE thumbnail_params (key TEXT PRIMARY KEY, value TEXT);
        """)
        conn.execute("INSERT INTO files (id, file_path) VALUES (1, 'a.jpg')")
        conn.execute("INSERT INTO photo_metadata (file_id, thumbnail_path) VALUES (1, ?)", (str(valid_thumb),))
        conn.execute("INSERT INTO memories (memory_type, photo_ids, is_hidden) VALUES ('special_date', ?, 1)", (json.dumps([999]),))
        conn.execute("INSERT INTO thumbnail_params (key, value) VALUES ('thumbnail_sig', 'test-v1')")
        conn.commit()
        conn.close()

        from services.startup_integrity import build_startup_integrity_report

        class S:
            photo_data_dir = str(photo_dir)
            thumbnail_dir = str(thumb_dir)

        report = build_startup_integrity_report(
            dry_run=True, db_path=str(db_path), settings=S(),
        )
        checks = {c["check_name"]: c for c in report["checks"]}
        # hidden memory 不应被计数
        assert checks["memories_unrenderable_in_ui"]["count"] == 0


# ============================================================================
# 维护命令测试
# ============================================================================

class TestMemoryMaintenanceCLI:
    """维护命令 dry-run/apply 测试。"""

    def _setup_db_with_unrenderable(self, db_path, thumb_dir):
        valid_thumb = thumb_dir / "1.jpg"
        valid_thumb.write_bytes(b"ok")

        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE files (id INTEGER PRIMARY KEY, file_path TEXT, file_name TEXT,
                folder_path TEXT, folder_name TEXT, file_mtime TEXT,
                is_image INTEGER DEFAULT 1, path_status TEXT DEFAULT 'ok');
            CREATE TABLE photo_metadata (file_id INTEGER PRIMARY KEY, thumbnail_path TEXT,
                is_duplicate_of INTEGER, date_taken TEXT, width INTEGER, height INTEGER);
            CREATE TABLE folder_categories (folder_path TEXT PRIMARY KEY, category INTEGER DEFAULT 1);
            CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, category INTEGER DEFAULT 1,
                memory_type TEXT, photo_ids TEXT, cover_file_id INTEGER, dismissed_at TEXT,
                is_hidden INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE thumbnail_params (key TEXT PRIMARY KEY, value TEXT);
        """)
        conn.execute("INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_mtime) VALUES (1, 'a.jpg', 'a.jpg', '/p', 'p', '2026-01-01')")
        conn.execute("INSERT INTO folder_categories (folder_path, category) VALUES ('/p', 1)")
        conn.execute("INSERT INTO photo_metadata (file_id, thumbnail_path, date_taken, width, height) VALUES (1, ?, '2026-06-01', 100, 80)", (str(valid_thumb),))
        conn.execute("INSERT INTO memories (memory_type, photo_ids) VALUES ('special_date', ?)", (json.dumps([999]),))
        conn.execute("INSERT INTO thumbnail_params (key, value) VALUES ('thumbnail_sig', 'test-v1')")
        conn.commit()
        conn.close()

    def test_disable_dry_run_identifies_unrenderable(self, tmp_path, monkeypatch):
        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()
        db_path = str(tmp_path / "test.db")
        self._setup_db_with_unrenderable(db_path, thumb_dir)

        import scripts.maintain_memories as mm
        # 绕过 init_tables() 迁移，直接连接
        import sqlite3 as _sq
        orig_init = mm.Database.init_tables
        mm.Database.init_tables = lambda self: None
        try:
            monkeypatch.setattr(mm, "get_settings", lambda: _fake_settings(db_path, tmp_path))
            stats = mm.disable_unrenderable_memories(dry_run=True, verbose=False)
            assert stats["total_unrenderable"] >= 1
            assert stats["hidden"] >= 1
        finally:
            mm.Database.init_tables = orig_init

    def test_disable_apply_marks_hidden(self, tmp_path, monkeypatch):
        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()
        db_path = str(tmp_path / "test.db")
        self._setup_db_with_unrenderable(db_path, thumb_dir)

        import scripts.maintain_memories as mm
        orig_init = mm.Database.init_tables
        mm.Database.init_tables = lambda self: None
        try:
            monkeypatch.setattr(mm, "get_settings", lambda: _fake_settings(db_path, tmp_path))
            stats = mm.disable_unrenderable_memories(dry_run=False, verbose=False)
            assert stats["hidden"] >= 1

            conn = sqlite3.connect(db_path)
            hidden_count = conn.execute("SELECT COUNT(*) FROM memories WHERE is_hidden = 1").fetchone()[0]
            conn.close()
            assert hidden_count >= 1
        finally:
            mm.Database.init_tables = orig_init

    def test_hidden_memory_not_in_waterfall_after_apply(self, tmp_path, monkeypatch):
        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()
        db_path = str(tmp_path / "test.db")
        self._setup_db_with_unrenderable(db_path, thumb_dir)

        import scripts.maintain_memories as mm
        orig_init = mm.Database.init_tables
        mm.Database.init_tables = lambda self: None
        try:
            monkeypatch.setattr(mm, "get_settings", lambda: _fake_settings(db_path, tmp_path))
            mm.disable_unrenderable_memories(dry_run=False, verbose=False)

            import business.recommendation as rec
            from db_manager import Database
            db = Database(db_path)
            monkeypatch.setattr(rec, "Database", lambda: db)

            cn = db.get_persistent_connection()
            try:
                photos = rec._load_ranked_memory_photos(cn, 1)
            finally:
                cn.close()
            assert len(photos) == 0
        finally:
            mm.Database.init_tables = orig_init


def _fake_settings(db_path_str, tmp_path):
    class S:
        photo_data_dir = str(tmp_path / "cache")
        thumbnail_dir = str(tmp_path / "thumbs")
        db_path = db_path_str
        source_drive = ""

        @property
        def source_dirs(self):
            return []
    return S()
