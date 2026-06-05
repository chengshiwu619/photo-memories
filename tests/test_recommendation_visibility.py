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


def test_category_batch_can_exclude_recently_shown_photos(tmp_path):
    from ui.recommendation import load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, thumbnail=True)
        _insert_photo(conn, tmp_path, 2, thumbnail=True)
        conn.execute(
            """
            INSERT INTO photo_shown_history (file_id, category, shown_at)
            VALUES (1, 1, datetime('now'))
            """
        )

    conn = db.get_persistent_connection()
    try:
        photos = load_category_photos_batch(
            conn,
            1,
            0,
            limit=10,
            exclude_recent_days=30,
            random_order=False,
        )
    finally:
        conn.close()

    assert [p["id"] for p in photos] == [2]


def test_sample_keyword_in_file_name_overrides_life_folder_for_random_category(tmp_path):
    from config import CATEGORY_LIFE, CATEGORY_SAMPLE
    from ui.recommendation import count_category_photos, load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            category=CATEGORY_LIFE,
            thumbnail=True,
            folder="Mixed",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "JP-Riko-Matsudaira-松平璃子-Vol-1.jpg",
                str(tmp_path / "Mixed" / "JP-Riko-Matsudaira-松平璃子-Vol-1.jpg"),
            ),
        )
        conn.execute("INSERT INTO sample_keywords (keyword) VALUES (?)", ("JP-",))

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert [p["id"] for p in sample_photos] == [1]
    assert life_photos == []
    assert sample_count == 1
    assert life_count == 0


def test_sample_keyword_in_parent_folder_path_overrides_child_life_category(tmp_path):
    from config import CATEGORY_LIFE, CATEGORY_SAMPLE
    from ui.recommendation import count_category_photos, load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    parent = tmp_path / "样片搜集"
    child = parent / "子文件夹"
    thumb = tmp_path / "thumbs" / "1.jpg"
    _write_thumb(thumb)

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO files
                (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                1,
                str(child / "normal-name.jpg"),
                "normal-name.jpg",
                str(child),
                "子文件夹",
                "2026-06-02T12:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
            (str(child), CATEGORY_LIFE, "llm-branch"),
        )
        conn.execute(
            """
            INSERT INTO photo_metadata
                (file_id, thumbnail_path, width, height, date_taken)
            VALUES (?, ?, 100, 80, ?)
            """,
            (1, str(thumb), "2026-06-02T12:00:00"),
        )
        conn.execute("INSERT INTO sample_keywords (keyword) VALUES (?)", ("样片搜集",))

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert [p["id"] for p in sample_photos] == [1]
    assert life_photos == []
    assert sample_count == 1
    assert life_count == 0


def test_rank_category_prefers_unshown_random_pool_when_enough_candidates(tmp_path):
    from ui.recommendation import rank_category_photos

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 66):
            day = f"2026-06-{((photo_id - 1) // 5) + 1:02d}"
            _insert_photo(conn, tmp_path, photo_id, thumbnail=True, day=day)
        conn.executemany(
            """
            INSERT INTO photo_shown_history (file_id, category, shown_at)
            VALUES (?, 1, datetime('now'))
            """,
            [(photo_id,) for photo_id in range(61, 66)],
        )

    conn = db.get_persistent_connection()
    try:
        ranked, metrics = rank_category_photos(conn, 1, return_metrics=True)
    finally:
        conn.close()

    ranked_ids = {p["id"] for p in ranked}
    assert len(ranked) == 60
    assert ranked_ids == set(range(1, 61))
    assert ranked_ids.isdisjoint(set(range(61, 66)))
    assert metrics["excluded_recent"] is True
