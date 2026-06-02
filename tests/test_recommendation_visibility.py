from db_manager import Database


def _write_thumb(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"thumb")


def _insert_photo(conn, tmp_path, photo_id, category=1, thumbnail=True, failed=False, folder="A", day="2026-06-02"):
    folder_path = str(tmp_path / folder)
    file_path = str(tmp_path / folder / f"{photo_id}.jpg")
    thumb_path = str(tmp_path / "thumbs" / f"{photo_id}.jpg") if thumbnail and not failed else ""
    if thumb_path:
        _write_thumb(tmp_path / "thumbs" / f"{photo_id}.jpg")
    if failed:
        thumb_path = "__FAILED__"
    conn.execute(
        """
        INSERT INTO files
            (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (photo_id, file_path, f"{photo_id}.jpg", folder_path, folder, f"{day}T12:00:00"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO folder_categories (folder_path, category) VALUES (?, ?)",
        (folder_path, category),
    )
    conn.execute(
        """
        INSERT INTO photo_metadata
            (file_id, thumbnail_path, width, height, date_taken)
        VALUES (?, ?, 100, 80, ?)
        """,
        (photo_id, thumb_path or None, f"{day}T12:00:00"),
    )


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


def test_memory_photos_filter_failed_refs_without_empty_slots(tmp_path):
    from ui.recommendation import _load_ranked_memory_photos
    import json

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 21):
            _insert_photo(conn, tmp_path, photo_id, failed=photo_id <= 5)
        conn.execute(
            """
            INSERT INTO memories (category, memory_type, title, photo_ids)
            VALUES (1, 'recent', 'partial', ?)
            """,
            (json.dumps(list(range(1, 21))),),
        )

    conn = db.get_persistent_connection()
    try:
        photos = _load_ranked_memory_photos(conn, 1)
    finally:
        conn.close()

    ids = [p["id"] for p in photos]
    assert ids == list(range(6, 21))
    assert all(p["thumbnail_path"] and p["thumbnail_path"] != "__FAILED__" for p in photos)


def test_memory_below_visible_threshold_is_skipped(tmp_path):
    from ui.recommendation import _load_ranked_memory_photos
    import json

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 6):
            _insert_photo(conn, tmp_path, photo_id, failed=photo_id > 3)
        conn.execute(
            """
            INSERT INTO memories (category, memory_type, title, photo_ids)
            VALUES (1, 'recent', 'too small', ?)
            """,
            (json.dumps(list(range(1, 6))),),
        )

    conn = db.get_persistent_connection()
    try:
        photos = _load_ranked_memory_photos(conn, 1)
    finally:
        conn.close()

    assert photos == []


def test_memory_below_threshold_can_be_supplemented(tmp_path):
    from ui.recommendation import _load_ranked_memory_photos
    import json

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 4):
            _insert_photo(conn, tmp_path, photo_id, folder="same")
        _insert_photo(conn, tmp_path, 4, folder="same")
        for photo_id in range(5, 8):
            _insert_photo(conn, tmp_path, photo_id, failed=True, folder="same")
        conn.execute(
            """
            INSERT INTO memories (category, memory_type, title, photo_ids)
            VALUES (1, 'recent', 'supplement', ?)
            """,
            (json.dumps([1, 2, 3, 5, 6, 7]),),
        )

    conn = db.get_persistent_connection()
    try:
        photos = _load_ranked_memory_photos(conn, 1)
    finally:
        conn.close()

    assert [p["id"] for p in photos] == [1, 2, 3, 4]


def test_rank_category_filters_pending_and_missing_thumbnails(tmp_path):
    from ui.recommendation import load_category_photos_batch, rank_category_photos

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, thumbnail=True)
        _insert_photo(conn, tmp_path, 2, thumbnail=False)
        _insert_photo(conn, tmp_path, 3, thumbnail=True)
        missing_thumb = tmp_path / "thumbs" / "3.jpg"
        missing_thumb.unlink()

    conn = db.get_persistent_connection()
    try:
        batch = load_category_photos_batch(conn, 1, 0, limit=10)
        ranked = rank_category_photos(conn, 1)
    finally:
        conn.close()

    assert [p["id"] for p in batch] == [1, 2]
    assert [p["id"] for p in ranked] == [1]
    assert ranked[0]["thumbnail_path"]
