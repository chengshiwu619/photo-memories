from db_manager import Database


def test_category_batch_includes_unclassified_photo_without_thumbnail(tmp_path):
    from ui.recommendation import load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (1, r"D:\Photos\New\a.jpg", "a.jpg", r"D:\Photos\New", "New"),
        )

    conn = db.get_persistent_connection()
    try:
        photos = load_category_photos_batch(conn, 1, 0, limit=10)
    finally:
        conn.close()

    assert [photo["id"] for photo in photos] == [1]
    assert photos[0]["thumbnail_path"] == ""


def test_category_batch_includes_video_without_thumbnail(tmp_path):
    from ui.recommendation import load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 0)",
            (1, r"D:\Photos\Video\v.mp4", "v.mp4", r"D:\Photos\Video", "Video"),
        )

    conn = db.get_persistent_connection()
    try:
        photos = load_category_photos_batch(conn, 1, 0, limit=10)
    finally:
        conn.close()

    assert [photo["id"] for photo in photos] == [1]
    assert photos[0]["thumbnail_path"] == ""
