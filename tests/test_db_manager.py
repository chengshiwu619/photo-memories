import os
import sqlite3
import tempfile
import shutil


def test_database_init_tables():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()}
        conn.close()
        expected = {"files", "folder_categories", "photo_metadata",
                    "memories", "click_history", "photo_tags",
                    "face_embeddings", "face_clusters", "events",
                    "memory_reasoning", "migration_log", "task_checkpoints"}
        assert expected.issubset(tables), f"missing tables: {expected - tables}"
    finally:
        shutil.rmtree(tmp)


def test_database_connect_contextmanager():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')"
            )
        with db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 1
    finally:
        shutil.rmtree(tmp)


def test_database_connect_rollback_on_error():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        try:
            with db.connect() as conn:
                conn.execute(
                    "INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')"
                )
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        with db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 0
    finally:
        shutil.rmtree(tmp)


def test_database_persistent_connection():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = db.get_persistent_connection()
        conn.execute(
            "INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')"
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        conn.close()
        assert count == 1
    finally:
        shutil.rmtree(tmp)


def test_database_init_tables_idempotent():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        db.init_tables()
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        assert count >= 12
    finally:
        shutil.rmtree(tmp)


def test_v03_new_columns_exist():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)

        files_cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
        assert "source_dir" in files_cols

        meta_cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        assert "phash" in meta_cols
        assert "is_duplicate_of" in meta_cols

        mem_cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
        assert "last_shown_at" in mem_cols
        assert "click_count" in mem_cols
        assert "dismissed_at" in mem_cols
        assert "payload" in mem_cols

        tags_cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_tags)").fetchall()}
        assert "source" in tags_cols

        conn.close()
    finally:
        shutil.rmtree(tmp)


def test_migration_log_records_version():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT version_to FROM migration_log ORDER BY migrated_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row[0] == "0.3"
    finally:
        shutil.rmtree(tmp)


def test_v02_to_v03_migration():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE files (
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
            CREATE TABLE photo_metadata (
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
                is_starred INTEGER DEFAULT 0
            );
            CREATE TABLE memories (
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
            CREATE TABLE photo_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(file_id, tag)
            );
            INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('a.jpg', 'a.jpg', '/t', 't');
            INSERT INTO photo_metadata (file_id, date_taken) VALUES (1, '2024-01-01');
            INSERT INTO memories (category, memory_type, title, photo_ids) VALUES (1, 'auto', 'Test', '[1]');
            INSERT INTO photo_tags (file_id, tag) VALUES (1, 'sunset');
        """)
        conn.commit()
        conn.close()

        db = Database(db_path)
        db.init_tables()

        conn2 = sqlite3.connect(db_path)
        files_cols = {r[1] for r in conn2.execute("PRAGMA table_info(files)").fetchall()}
        assert "source_dir" in files_cols

        meta_cols = {r[1] for r in conn2.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        assert "phash" in meta_cols
        assert "is_duplicate_of" in meta_cols

        tags_cols = {r[1] for r in conn2.execute("PRAGMA table_info(photo_tags)").fetchall()}
        assert "source" in tags_cols

        tag_source = conn2.execute("SELECT source FROM photo_tags WHERE file_id=1").fetchone()[0]
        assert tag_source == "manual"

        tables = {r[0] for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "face_embeddings" in tables
        assert "face_clusters" in tables
        assert "events" in tables
        assert "task_checkpoints" in tables

        row = conn2.execute(
            "SELECT version_from, version_to FROM migration_log ORDER BY migrated_at DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "0.2"
        assert row[1] == "0.3"

        conn2.close()
    finally:
        shutil.rmtree(tmp)
