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
                    "memories", "click_history", "photo_tags"}
        assert expected.issubset(tables)
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
        assert count >= 6
    finally:
        shutil.rmtree(tmp)
