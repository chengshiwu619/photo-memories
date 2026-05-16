import os
import sqlite3
import tempfile
import shutil


def test_all_tables_created():
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


def test_files_table_columns():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
        conn.close()
        required = {"id", "file_path", "file_name", "folder_path", "folder_name",
                    "file_size", "file_mtime", "file_hash", "is_image", "scanned_at",
                    "source_dir"}
        assert required.issubset(cols), f"missing columns: {required - cols}"
    finally:
        shutil.rmtree(tmp)


def test_photo_metadata_has_is_starred():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        conn.close()
        assert "is_starred" in cols
    finally:
        shutil.rmtree(tmp)


def test_memories_has_is_starred():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
        conn.close()
        assert "is_starred" in cols
    finally:
        shutil.rmtree(tmp)


def test_photo_tags_unique_constraint():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')")
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (?, 'sunset', 'manual')", (fid,))
        conn.commit()
        try:
            conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (?, 'sunset', 'manual')", (fid,))
            assert False, "should have raised IntegrityError"
        except sqlite3.IntegrityError:
            pass
        conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (?, 'sunset', 'siglip')", (fid,))
        conn.commit()
        conn.close()
    finally:
        shutil.rmtree(tmp)


def test_config_init_all_tables_delegates():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        assert count >= 12
    finally:
        shutil.rmtree(tmp)
