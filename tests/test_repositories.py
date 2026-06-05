import os
import tempfile
import shutil
from datetime import datetime


def test_database_basic_operations():
    from db_manager import Database

    temp_dir = tempfile.mkdtemp()
    try:
        temp_db = os.path.join(temp_dir, "test.db")
        db = Database(temp_db)
        db.init_tables()

        with db.connect() as conn:
            conn.execute(
                "INSERT INTO files (file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image, scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("D:\\test\\photo.jpg", "photo.jpg", "D:\\test", "test", 12345, datetime.now().isoformat(), 1, datetime.now().isoformat()),
            )
            row = conn.execute("SELECT * FROM files WHERE file_path = ?", ("D:\\test\\photo.jpg",)).fetchone()
            assert row is not None

            conn.execute(
                "INSERT OR REPLACE INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
                ("D:\\test", 1, "high"),
            )
            cat = conn.execute("SELECT category FROM folder_categories WHERE folder_path = ?", ("D:\\test",)).fetchone()
            assert cat[0] == 1

            conn.execute(
                "INSERT OR REPLACE INTO photo_metadata (file_id, date_taken, camera_model, gps_lat, gps_lon, width, height, thumbnail_path, indexed_at, is_starred) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, datetime.now().isoformat(), "Test Camera", 39.9, 116.4, 1920, 1080, "D:\\test\\thumb.jpg", datetime.now().isoformat(), 0),
            )
            meta = conn.execute("SELECT * FROM photo_metadata WHERE file_id = ?", (1,)).fetchone()
            assert meta is not None

            conn.execute(
                "INSERT INTO memories (category, memory_type, title, description, photo_ids, cover_file_id, created_at, is_starred) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "auto", "Test Memory", "Test Desc", "[1]", 1, datetime.now().isoformat(), 0),
            )
            mem = conn.execute("SELECT * FROM memories WHERE category = ?", (1,)).fetchall()
            assert len(mem) == 1

            conn.execute(
                "INSERT INTO click_history (file_id, folder_path, category, clicked_at) VALUES (?, ?, ?, ?)",
                (1, "D:\\test", 1, datetime.now().isoformat()),
            )
            click = conn.execute("SELECT * FROM click_history WHERE file_id = ?", (1,)).fetchone()
            assert click is not None

            conn.execute(
                "INSERT OR IGNORE INTO photo_tags (file_id, tag, created_at) VALUES (?, ?, ?)",
                (1, "test", datetime.now().isoformat()),
            )
            tags = conn.execute("SELECT * FROM photo_tags WHERE file_id = ?", (1,)).fetchall()
            assert len(tags) == 1

    finally:
        shutil.rmtree(temp_dir)


def test_photo_tag_status_excludes_processed_and_requeues_changed_file():
    from db_manager import Database
    from infra.db.repositories.photo_tags_repo import PhotoTagsRepository

    temp_dir = tempfile.mkdtemp()
    try:
        temp_db = os.path.join(temp_dir, "test.db")
        db = Database(temp_db)
        db.init_tables()
        with db.connect() as conn:
            for fid in (1, 2, 3):
                conn.execute(
                    """INSERT INTO files
                       (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                    (fid, os.path.join(temp_dir, f"{fid}.jpg"), f"{fid}.jpg", temp_dir, "tmp", 100, "mtime-1"),
                )
                conn.execute(
                    "INSERT INTO photo_metadata (file_id, thumbnail_path, is_duplicate_of) VALUES (?, ?, NULL)",
                    (fid, os.path.join(temp_dir, "thumbs", f"{fid}.jpg")),
                )
            conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (3, 'old', 'siglip')")

        repo = PhotoTagsRepository(db)
        pending, total = repo.get_pending_file_ids("siglip", limit=10)
        assert pending == [1, 2, 3]
        assert total == 3

        assert repo.update_status_many(
            [(1, "processed_ok", None), (2, "failed", "bad image"), (3, "processed_ok", None)],
            "siglip",
        ) == 3
        pending, total = repo.get_pending_file_ids("siglip", limit=10)
        assert pending == []
        assert total == 0

        with db.connect() as conn:
            conn.execute("UPDATE files SET file_size = 101 WHERE id = 2")
        pending, total = repo.get_pending_file_ids("siglip", limit=10)
        assert pending == [2]
        assert total == 1
    finally:
        shutil.rmtree(temp_dir)


def test_photo_tag_pending_requires_usable_thumbnail_state():
    from db_manager import Database
    from infra.db.repositories.photo_tags_repo import PhotoTagsRepository

    temp_dir = tempfile.mkdtemp()
    try:
        temp_db = os.path.join(temp_dir, "test.db")
        db = Database(temp_db)
        db.init_tables()
        rows = [
            (1, "ok.jpg", "ok", None, 1),
            (2, "", "ok", None, 1),
            (3, "__FAILED__", "ok", None, 1),
            (4, "failed.jpg", "failed", None, 1),
            (5, "skipped.jpg", "skipped", None, 1),
            (6, "missing.jpg", "ok", "missing", 1),
            (7, "video.jpg", "ok", None, 0),
            (8, "recovered.jpg", "recovered", None, 1),
        ]
        with db.connect() as conn:
            for fid, thumb, thumb_status, path_status, is_image in rows:
                conn.execute(
                    """INSERT INTO files
                       (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image, path_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fid, os.path.join(temp_dir, f"{fid}.jpg"), f"{fid}.jpg", temp_dir, "tmp", 100, "mtime", is_image, path_status),
                )
                conn.execute(
                    "INSERT INTO photo_metadata (file_id, thumbnail_path, thumbnail_status, is_duplicate_of) VALUES (?, ?, ?, NULL)",
                    (fid, thumb, thumb_status),
                )

        repo = PhotoTagsRepository(db)
        pending, total = repo.get_pending_file_ids("siglip", limit=20)
        assert pending == [1, 8]
        assert total == 2
    finally:
        shutil.rmtree(temp_dir)
