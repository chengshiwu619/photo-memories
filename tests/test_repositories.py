import os
import tempfile
import shutil
from datetime import datetime


def test_repositories_infrastructure():
    from core.models import File, FolderCategory, PhotoMetadata, Memory, ClickHistory, PhotoTag
    from db_manager import Database

    temp_dir = tempfile.mkdtemp()
    try:
        temp_db = os.path.join(temp_dir, "test.db")
        db = Database(temp_db)
        db.init_tables()

        file = File(file_path="D:\\test\\photo.jpg", file_name="photo.jpg", folder_path="D:\\test", folder_name="test", file_size=12345, file_mtime=datetime.now().isoformat(), is_image=1, scanned_at=datetime.now().isoformat())
        assert db.files.insert_or_ignore(file) >= 0

        db.folder_categories.set_folder_category("D:\\test", 1, "high")
        assert db.folder_categories.get_folder_category("D:\\test") == 1

        meta = PhotoMetadata(file_id=1, date_taken=datetime.now().isoformat(), camera_model="Test Camera", gps_lat=39.9, gps_lon=116.4, width=1920, height=1080, thumbnail_path="D:\\test\\thumb.jpg", indexed_at=datetime.now().isoformat(), is_starred=0)
        db.photo_metadata.insert_or_replace(meta)

        memory = Memory(category=1, memory_type="auto", title="Test Memory", description="Test Desc", photo_ids="[1]", cover_file_id=1, created_at=datetime.now().isoformat(), is_starred=0)
        mem_id = db.memories.insert(memory)
        assert mem_id > 0

        assert len(db.memories.get_all(category=1)) == 1

        click = ClickHistory(file_id=1, folder_path="D:\\test", category=1, clicked_at=datetime.now().isoformat())
        db.click_history.insert(click)

        tag = PhotoTag(file_id=1, tag="test", created_at=datetime.now().isoformat())
        db.photo_tags.insert_or_ignore(tag)

        assert len(db.photo_tags.get_tags_for_file(1)) == 1

    finally:
        shutil.rmtree(temp_dir)
