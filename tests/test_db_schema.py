import os
import sqlite3
import tempfile
import shutil
from unittest.mock import patch


def _init_db_in_temp(tmp_dir):
    db_path = os.path.join(tmp_dir, "photos.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            file_size INTEGER,
            file_mtime TEXT,
            file_hash TEXT,
            is_image INTEGER DEFAULT 1,
            scanned_at TEXT
        );
        CREATE TABLE IF NOT EXISTS folder_categories (
            folder_path TEXT PRIMARY KEY,
            category INTEGER NOT NULL,
            confidence TEXT,
            classified_at TEXT
        );
        CREATE TABLE IF NOT EXISTS photo_metadata (
            file_id INTEGER PRIMARY KEY,
            date_taken TEXT,
            camera_model TEXT,
            gps_lat REAL,
            gps_lon REAL,
            width INTEGER,
            height INTEGER,
            thumbnail_path TEXT,
            exif_json TEXT,
            indexed_at TEXT,
            is_starred INTEGER DEFAULT 0,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category INTEGER NOT NULL,
            memory_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            photo_ids TEXT NOT NULL,
            cover_file_id INTEGER,
            created_at TEXT,
            is_starred INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS click_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            folder_path TEXT NOT NULL,
            category INTEGER,
            clicked_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (file_id) REFERENCES files(id)
        );
        CREATE TABLE IF NOT EXISTS photo_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (file_id) REFERENCES files(id),
            UNIQUE(file_id, tag)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def test_all_tables_created():
    tmp = tempfile.mkdtemp()
    try:
        db_path = _init_db_in_temp(tmp)
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()}
        conn.close()
        expected = {"files", "folder_categories", "photo_metadata",
                    "memories", "click_history", "photo_tags"}
        assert expected.issubset(tables), f"missing tables: {expected - tables}"
    finally:
        shutil.rmtree(tmp)


def test_files_table_columns():
    tmp = tempfile.mkdtemp()
    try:
        db_path = _init_db_in_temp(tmp)
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
        conn.close()
        required = {"id", "file_path", "file_name", "folder_path", "folder_name",
                    "file_size", "file_mtime", "file_hash", "is_image", "scanned_at"}
        assert required.issubset(cols), f"missing columns: {required - cols}"
    finally:
        shutil.rmtree(tmp)


def test_photo_metadata_has_is_starred():
    tmp = tempfile.mkdtemp()
    try:
        db_path = _init_db_in_temp(tmp)
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        conn.close()
        assert "is_starred" in cols
    finally:
        shutil.rmtree(tmp)


def test_memories_has_is_starred():
    tmp = tempfile.mkdtemp()
    try:
        db_path = _init_db_in_temp(tmp)
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
        conn.close()
        assert "is_starred" in cols
    finally:
        shutil.rmtree(tmp)


def test_photo_tags_unique_constraint():
    tmp = tempfile.mkdtemp()
    try:
        db_path = _init_db_in_temp(tmp)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')")
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO photo_tags (file_id, tag) VALUES (?, 'sunset')", (fid,))
        conn.commit()
        try:
            conn.execute("INSERT INTO photo_tags (file_id, tag) VALUES (?, 'sunset')", (fid,))
            assert False, "should have raised IntegrityError"
        except sqlite3.IntegrityError:
            pass
        conn.close()
    finally:
        shutil.rmtree(tmp)


def test_init_all_tables_idempotent():
    import config
    tmp = tempfile.mkdtemp()
    original_db = config.DB_PATH
    try:
        config.DB_PATH = os.path.join(tmp, "photos.db")
        config.init_all_tables()
        config.init_all_tables()
        conn = sqlite3.connect(config.DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        assert count >= 6
    finally:
        config.DB_PATH = original_db
        shutil.rmtree(tmp)
