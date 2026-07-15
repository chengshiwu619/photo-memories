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


def test_category_batch_can_require_existing_thumbnail(tmp_path):
    from ui.recommendation import load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, thumbnail=True)
        _insert_photo(conn, tmp_path, 2, thumbnail=False)
        _insert_photo(conn, tmp_path, 3, thumbnail=True, failed=True)

    conn = db.get_persistent_connection()
    try:
        default_photos = load_category_photos_batch(conn, 1, 0, limit=10)
        thumbnail_photos = load_category_photos_batch(conn, 1, 0, limit=10, require_thumbnail=True)
    finally:
        conn.close()

    assert {p["id"] for p in default_photos} == {1, 2}
    assert [p["id"] for p in thumbnail_photos] == [1]


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


def test_load_photos_from_ids_can_preserve_memory_order(tmp_path):
    from ui.recommendation import load_photos_from_ids

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 14):
            _insert_photo(conn, tmp_path, photo_id, folder="same")
        _insert_photo(conn, tmp_path, 14, folder="other")

    conn = db.get_persistent_connection()
    try:
        ordered = load_photos_from_ids(conn, list(range(1, 15)), require_thumbnail=True, preserve_order=True)
        interleaved = load_photos_from_ids(conn, list(range(1, 15)), require_thumbnail=True)
    finally:
        conn.close()

    assert [p["id"] for p in ordered] == list(range(1, 15))
    assert [p["id"] for p in interleaved] == list(range(1, 13)) + [14, 13]


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


def test_strong_sample_source_overrides_life_folder_for_random_category(tmp_path):
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
            folder="电报色图/Set001",
        )

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


def test_strong_life_source_overrides_sample_folder_for_random_category(tmp_path):
    from config import CATEGORY_LIFE, CATEGORY_SAMPLE
    from ui.recommendation import count_category_photos, load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            category=CATEGORY_SAMPLE,
            thumbnail=True,
            folder="MobileBackup/iPhone/2023/07",
        )
        conn.execute("INSERT INTO sample_keywords (keyword) VALUES (?)", ("iPhone",))

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert sample_photos == []
    assert [p["id"] for p in life_photos] == [1]
    assert sample_count == 0
    assert life_count == 1


def test_strong_sample_filename_overrides_mobile_backup_life_source(tmp_path):
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
            folder="MobileBackup/iPhone/2025/11",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "JP-Mio-Ishikawa-石川澪-幻惑LIPS-0043-0748480480.jpg",
                str(tmp_path / "MobileBackup" / "iPhone" / "2025" / "11" / "JP-Mio-Ishikawa-石川澪-幻惑LIPS-0043-0748480480.jpg"),
            ),
        )

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


def test_photobook_sequence_filename_overrides_mobile_backup_life_source(tmp_path):
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
            folder="MobileBackup/iPhone/2025/11",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "Photobook-2020-12-10-Karen-Kawai-&-Tomoka-Kabasawa-SequenceNumber002-A-00005-0706709245.jpg",
                str(tmp_path / "MobileBackup" / "iPhone" / "2025" / "11" / "Photobook-2020-12-10-Karen-Kawai-&-Tomoka-Kabasawa-SequenceNumber002-A-00005-0706709245.jpg"),
            ),
        )

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


def test_photobook_date_filename_without_sequence_overrides_mobile_backup_life_source(tmp_path):
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
            folder="MobileBackup/iPhone/2025/11",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "Photobook-2021-12-27-Kana-Momonogi-桃乃木かな-Escape-0083-7883659235.jpg",
                str(tmp_path / "MobileBackup" / "iPhone" / "2025" / "11" / "Photobook-2021-12-27-Kana-Momonogi-桃乃木かな-Escape-0083-7883659235.jpg"),
            ),
        )

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


def test_mobile_backup_camera_filename_remains_life(tmp_path):
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
            folder="MobileBackup/iPhone/2023/07",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "IMG_20230708_171732.JPG",
                str(tmp_path / "MobileBackup" / "iPhone" / "2023" / "07" / "IMG_20230708_171732.JPG"),
            ),
        )

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert sample_photos == []
    assert [p["id"] for p in life_photos] == [1]
    assert sample_count == 0
    assert life_count == 1


def test_mobile_backup_nested_camera_filename_stays_life_after_sample_override(tmp_path):
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
            folder="MobileBackup/iPhone/2025/10",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "IMG_20251021_092431.jpg",
                str(tmp_path / "MobileBackup" / "iPhone" / "2025" / "10" / "IMG_20251021_092431.jpg"),
            ),
        )
        conn.execute(
            "UPDATE photo_metadata SET category = ? WHERE file_id = 1",
            (CATEGORY_SAMPLE,),
        )

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert sample_photos == []
    assert [p["id"] for p in life_photos] == [1]
    assert sample_count == 0
    assert life_count == 1


def test_mobile_backup_legacy_iphone_img_number_stays_life_after_sample_override(tmp_path):
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
            folder="MobileBackup/iPhone/2022/08",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "IMG_2670.JPG",
                str(tmp_path / "MobileBackup" / "iPhone" / "2022" / "08" / "IMG_2670.JPG"),
            ),
        )
        conn.execute(
            "UPDATE photo_metadata SET category = ? WHERE file_id = 1",
            (CATEGORY_SAMPLE,),
        )

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert sample_photos == []
    assert [p["id"] for p in life_photos] == [1]
    assert sample_count == 0
    assert life_count == 1


def test_photo_sample_override_beats_moments_source_for_random_category(tmp_path):
    from config import CATEGORY_LIFE, CATEGORY_SAMPLE
    from ui.recommendation import count_category_photos, load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            category=CATEGORY_SAMPLE,
            thumbnail=True,
            folder="Moments/NSFW/2023/07",
        )
        conn.execute(
            "UPDATE photo_metadata SET category = ? WHERE file_id = 1",
            (CATEGORY_SAMPLE,),
        )

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


def test_moments_mobile_dcim_camera_filename_stays_life_even_after_sample_override(tmp_path):
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
            folder="Moments/Mobile/SM-N9600/DCIM/2019-11-25",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "20191125_165104.jpg",
                str(tmp_path / "Moments" / "Mobile" / "SM-N9600" / "DCIM" / "2019-11-25" / "20191125_165104.jpg"),
            ),
        )
        conn.execute(
            "UPDATE photo_metadata SET category = ? WHERE file_id = 1",
            (CATEGORY_SAMPLE,),
        )

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert sample_photos == []
    assert [p["id"] for p in life_photos] == [1]
    assert sample_count == 0
    assert life_count == 1


def test_film_output_life_tree_beats_photo_sample_override_for_random_category(tmp_path):
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
            folder="胶片成图/日常生活/随便",
        )
        conn.execute(
            "UPDATE files SET file_name = ?, file_path = ? WHERE id = 1",
            (
                "heliar-5294-5.jpg",
                str(tmp_path / "胶片成图" / "日常生活" / "随便" / "heliar-5294-5.jpg"),
            ),
        )
        conn.execute(
            "UPDATE photo_metadata SET category = ? WHERE file_id = 1",
            (CATEGORY_SAMPLE,),
        )

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert sample_photos == []
    assert [p["id"] for p in life_photos] == [1]
    assert sample_count == 0
    assert life_count == 1


def test_film_output_sample_collect_exception_stays_sample_for_random_category(tmp_path):
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
            folder="胶片成图/样片搜集/Set001",
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


def test_photo_category_override_moves_single_photo_to_sample(tmp_path):
    from config import CATEGORY_LIFE, CATEGORY_SAMPLE
    from ui.recommendation import count_category_photos, load_category_photos_batch

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, category=CATEGORY_LIFE, thumbnail=True, folder="Mixed")
        _insert_photo(conn, tmp_path, 2, category=CATEGORY_LIFE, thumbnail=True, folder="Mixed")
        conn.execute(
            "UPDATE photo_metadata SET category = ? WHERE file_id = 1",
            (CATEGORY_SAMPLE,),
        )

    conn = db.get_persistent_connection()
    try:
        sample_photos = load_category_photos_batch(conn, CATEGORY_SAMPLE, 0, limit=10)
        life_photos = load_category_photos_batch(conn, CATEGORY_LIFE, 0, limit=10)
        sample_count = count_category_photos(conn, CATEGORY_SAMPLE)
        life_count = count_category_photos(conn, CATEGORY_LIFE)
    finally:
        conn.close()

    assert [p["id"] for p in sample_photos] == [1]
    assert [p["id"] for p in life_photos] == [2]
    assert sample_count == 1
    assert life_count == 1


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


def test_rank_category_photos_excludes_already_loaded_ids(tmp_path, monkeypatch):
    import ui.recommendation as rec
    from ui.recommendation import rank_category_photos

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 71):
            _insert_photo(conn, tmp_path, photo_id, thumbnail=True)

    loaded_ids = set(range(1, 61))
    monkeypatch.setattr(rec.random, "randint", lambda _start, _end: 1)
    conn = db.get_persistent_connection()
    try:
        photos = rank_category_photos(conn, 1, limit=5, exclude_ids=loaded_ids)
    finally:
        conn.close()

    ids = [p["id"] for p in photos]
    assert len(ids) == 5
    assert set(ids).isdisjoint(loaded_ids)
    assert len(ids) == len(set(ids))


def test_rank_category_supplements_after_dedup_to_keep_limited_pool_size(monkeypatch):
    import ui.recommendation as rec

    def photo(photo_id):
        return {
            "id": photo_id,
            "folder_path": f"folder-{photo_id}",
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
            "thumbnail_path": f"thumb-{photo_id}.jpg",
        }

    calls = []

    def fake_batch(_db, _cat_id, _offset, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return [photo(3), photo(4)]
        if len(calls) == 2:
            return [photo(3), photo(4)]
        return [photo(5), photo(6)]

    monkeypatch.setattr(rec, "_load_ranked_memory_photos", lambda *_args, **_kwargs: [photo(1), photo(2)])
    monkeypatch.setattr(rec, "load_category_photos_batch", fake_batch)
    monkeypatch.setattr(rec, "_filter_renderable_photos", lambda photos: list(photos))
    monkeypatch.setattr(rec, "_get_recently_shown_ids", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(rec.random, "shuffle", lambda _items: None)

    ranked = rec.rank_category_photos(object(), 1, limit=6)

    ids = [p["id"] for p in ranked]
    assert ids == [1, 2, 3, 4, 5, 6]
    assert len(calls) == 3
    assert calls[2]["exclude_ids"] == {1, 2, 3, 4}

def test_large_exclude_ids_use_temp_table_for_category_and_starred(tmp_path):
    import ui.recommendation as rec

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    total = rec.SQL_EXCLUDE_TEMP_TABLE_THRESHOLD + 11
    excluded = set(range(1, rec.SQL_EXCLUDE_TEMP_TABLE_THRESHOLD + 2))
    with db.connect() as conn:
        for photo_id in range(1, total + 1):
            _insert_photo(conn, tmp_path, photo_id, thumbnail=True)
        conn.execute("UPDATE photo_metadata SET is_starred = 1")

    conn = db.get_persistent_connection()
    try:
        batch = rec.load_category_photos_batch(conn, 1, 0, limit=5, exclude_ids=excluded)
        temp_count = conn.execute(f"SELECT COUNT(*) FROM {rec.TEMP_EXCLUDED_FILE_IDS_TABLE}").fetchone()[0]
        starred = rec.load_starred_photos(conn, 1, limit=5, exclude_ids=excluded)
    finally:
        conn.close()

    assert temp_count == len(excluded)
    assert len(batch) == 5
    assert len(starred) == 5
    assert {p["id"] for p in batch}.isdisjoint(excluded)
    assert {p["id"] for p in starred}.isdisjoint(excluded)

def test_limited_memory_loading_stops_after_first_memory_batch(monkeypatch):
    import json
    import ui.recommendation as rec

    class FakeCursor:
        def __init__(self):
            self.rows = []
            for memory_index in range(200):
                base = memory_index * 10
                self.rows.append({
                    "id": memory_index + 1,
                    "photo_ids": json.dumps([base + 1, base + 2, base + 3, base + 4]),
                    "cover_file_id": base + 1,
                })
            self.position = 0
            self.fetch_calls = 0

        def fetchmany(self, size):
            self.fetch_calls += 1
            chunk = self.rows[self.position:self.position + size]
            self.position += size
            return chunk

    class FakeDb:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, _sql, _params=()):
            return self.cursor

    cursor = FakeCursor()
    loaded_batches = []

    def fake_load_photos(_db, ids, **_kwargs):
        loaded_batches.append(list(ids))
        return [
            {
                "id": pid,
                "folder_path": f"folder-{pid}",
                "date_taken": "2026-06-01T12:00:00",
                "file_mtime": "2026-06-01T12:00:00",
                "thumbnail_path": f"thumb-{pid}.jpg",
            }
            for pid in ids
        ]

    monkeypatch.setattr(rec, "load_photos_from_ids", fake_load_photos)
    monkeypatch.setattr(rec, "_filter_photos_for_category", lambda _db, _cat_id, photos: list(photos))
    monkeypatch.setattr(rec, "_interleave_small_folders", lambda photos: list(photos))

    photos = rec._load_ranked_memory_photos(FakeDb(cursor), 1, limit=4)

    assert [p["id"] for p in photos] == [1, 2, 3, 4]
    assert cursor.fetch_calls == 1
    assert len(loaded_batches) == 1
    assert len(loaded_batches[0]) == rec.MEMORY_ROW_BATCH_SIZE * 4
    assert loaded_batches[0][:8] == [1, 2, 3, 4, 11, 12, 13, 14]


def test_limited_memory_loading_respects_memory_row_scan_limit(monkeypatch):
    import json
    import ui.recommendation as rec

    class FakeCursor:
        def __init__(self):
            self.rows = []
            for memory_index in range(200):
                self.rows.append({
                    "id": memory_index + 1,
                    "photo_ids": json.dumps([memory_index * 10 + 1]),
                    "cover_file_id": memory_index * 10 + 1,
                })
            self.position = 0
            self.fetch_sizes = []

        def fetchmany(self, size):
            self.fetch_sizes.append(size)
            chunk = self.rows[self.position:self.position + size]
            self.position += size
            return chunk

    class FakeDb:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, _sql, _params=()):
            return self.cursor

    cursor = FakeCursor()
    monkeypatch.setattr(rec, "load_photos_from_ids", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rec, "_filter_photos_for_category", lambda _db, _cat_id, photos: list(photos))
    monkeypatch.setattr(rec, "_supplement_memory_photos", lambda *_args, **_kwargs: [])

    photos = rec._load_ranked_memory_photos(
        FakeDb(cursor),
        1,
        limit=4,
        max_memory_rows=rec.MEMORY_ROW_BATCH_SIZE + 5,
    )

    assert photos == []
    assert cursor.fetch_sizes == [rec.MEMORY_ROW_BATCH_SIZE, 5]
    assert cursor.position == rec.MEMORY_ROW_BATCH_SIZE + 5


def test_rank_category_limited_load_uses_foreground_memory_row_limit(monkeypatch):
    import ui.recommendation as rec

    calls = []

    def fake_memory(_db, _cat_id, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(rec, "_load_ranked_memory_photos", fake_memory)
    monkeypatch.setattr(rec, "load_category_photos_batch", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rec, "_filter_renderable_photos", lambda photos: list(photos))

    rec.rank_category_photos(object(), 1, limit=30)

    assert calls[0]["max_memory_rows"] == rec.FOREGROUND_MEMORY_ROW_SCAN_LIMIT


def test_rank_category_limited_load_uses_foreground_memory_priority_limit(monkeypatch):
    import ui.recommendation as rec

    calls = []

    def fake_memory(_db, _cat_id, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(rec, "_load_ranked_memory_photos", fake_memory)
    monkeypatch.setattr(rec, "load_category_photos_batch", lambda *_args, **_kwargs: [])

    rec.rank_category_photos(object(), 1, limit=360)

    assert calls[0]["limit"] == rec.FOREGROUND_MEMORY_PRIORITY_LIMIT


def test_random_thumbnail_window_does_not_triple_overfetch(monkeypatch):
    import ui.recommendation as rec

    calls = []

    monkeypatch.setattr(rec, "_max_file_id", lambda _db: 1000)
    monkeypatch.setattr(rec.random, "randint", lambda _start, _end: 100)

    def fake_rows(_db, _cat_id, **kwargs):
        calls.append(kwargs)
        return [{"id": i} for i in range(1, kwargs["limit"] + 1)]

    monkeypatch.setattr(rec, "_load_category_photo_rows", fake_rows)
    monkeypatch.setattr(rec, "_rows_to_visible_photos", lambda rows, **_kwargs: list(rows))

    photos = rec._load_category_photos_random_window(object(), 1, 50, require_thumbnail=True)

    assert len(photos) == 50
    assert calls[0]["limit"] == 50


def test_interleave_by_time_preserves_same_day_overflow():
    import ui.recommendation as rec

    photos = [
        {
            "id": photo_id,
            "folder_path": "same",
            "date_taken": "2026-06-01T12:00:00",
            "file_mtime": "2026-06-01T12:00:00",
        }
        for photo_id in range(rec.MAX_SAME_DAY_STREAK + 5)
    ]

    interleaved = rec._interleave_by_time(photos)

    assert len(interleaved) == len(photos)
    assert {p["id"] for p in interleaved} == {p["id"] for p in photos}


def test_spread_nearby_photos_limits_default_folder_density():
    import ui.recommendation as rec

    photos = [
        {
            "id": photo_id,
            "folder_path": "nearby",
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
        }
        for photo_id in range(1, 8)
    ] + [
        {
            "id": photo_id,
            "folder_path": "other",
            "date_taken": f"2026-07-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-07-{photo_id:02d}T12:00:00",
        }
        for photo_id in range(8, 11)
    ]

    spread = rec._spread_nearby_photos(photos)

    max_streak = 0
    streak = 0
    last_folder = None
    for photo in spread:
        folder = photo["folder_path"]
        streak = streak + 1 if folder == last_folder else 1
        max_streak = max(max_streak, streak)
        last_folder = folder

    assert len(spread) == len(photos)
    assert max_streak <= rec.DEFAULT_RANDOM_NEARBY_STREAK


def test_spread_nearby_photos_limits_default_day_density():
    import ui.recommendation as rec

    photos = [
        {
            "id": photo_id,
            "folder_path": f"folder-{photo_id}",
            "date_taken": "2026-06-01T12:00:00",
            "file_mtime": "2026-06-01T12:00:00",
        }
        for photo_id in range(1, 8)
    ] + [
        {
            "id": photo_id,
            "folder_path": f"folder-{photo_id}",
            "date_taken": "2026-07-01T12:00:00",
            "file_mtime": "2026-07-01T12:00:00",
        }
        for photo_id in range(8, 11)
    ]

    spread = rec._spread_nearby_photos(photos)

    max_streak = 0
    streak = 0
    last_day = None
    for photo in spread:
        day = photo["date_taken"][:10]
        streak = streak + 1 if day == last_day else 1
        max_streak = max(max_streak, streak)
        last_day = day

    assert len(spread) == len(photos)
    assert max_streak <= rec.DEFAULT_RANDOM_NEARBY_STREAK


def test_spread_nearby_photos_expands_clicked_or_starred_folder():
    import ui.recommendation as rec

    photos = [
        {
            "id": photo_id,
            "folder_path": "nearby",
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
        }
        for photo_id in range(1, 26)
    ] + [
        {
            "id": 26,
            "folder_path": "other",
            "date_taken": "2026-07-01T12:00:00",
            "file_mtime": "2026-07-01T12:00:00",
        }
    ]

    spread = rec._spread_nearby_photos(photos, expanded_folders={"nearby"})

    assert [p["folder_path"] for p in spread[:rec.EXPANDED_RANDOM_NEARBY_STREAK]] == ["nearby"] * rec.EXPANDED_RANDOM_NEARBY_STREAK


def test_spread_nearby_photos_prioritizes_folder_cap_over_day_cap():
    import ui.recommendation as rec

    photos = [
        {
            "id": photo_id,
            "folder_path": "nearby",
            "date_taken": "2026-06-01T12:00:00",
            "file_mtime": "2026-06-01T12:00:00",
        }
        for photo_id in range(1, rec.EXPANDED_RANDOM_NEARBY_STREAK + 2)
    ] + [
        {
            "id": rec.EXPANDED_RANDOM_NEARBY_STREAK + 2,
            "folder_path": "other",
            "date_taken": "2026-06-01T12:00:00",
            "file_mtime": "2026-06-01T12:00:00",
        }
    ]

    spread = rec._spread_nearby_photos(photos, expanded_folders={"nearby"}, expanded_days={"2026-06-01"})

    assert spread[rec.EXPANDED_RANDOM_NEARBY_STREAK]["folder_path"] == "other"


def test_rank_category_uses_click_or_star_interest_to_allow_nearby_expansion(monkeypatch):
    import ui.recommendation as rec

    def photo(photo_id, folder):
        return {
            "id": photo_id,
            "folder_path": folder,
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
            "thumbnail_path": f"thumb-{photo_id}.jpg",
        }

    batch = [photo(photo_id, "nearby") for photo_id in range(1, 26)] + [photo(26, "other")]
    monkeypatch.setattr(rec, "_load_ranked_memory_photos", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rec, "load_category_photos_batch", lambda *_args, **_kwargs: list(batch))
    monkeypatch.setattr(rec, "_get_recently_shown_ids", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(rec.random, "shuffle", lambda _items: None)
    monkeypatch.setattr(rec, "_load_proximity_interest_keys", lambda *_args, **_kwargs: {"folders": {"nearby"}, "days": set()})

    photos, metrics = rec.rank_category_photos(object(), 1, return_metrics=True, limit=26)

    assert [p["folder_path"] for p in photos[:rec.EXPANDED_RANDOM_NEARBY_STREAK]] == ["nearby"] * rec.EXPANDED_RANDOM_NEARBY_STREAK
    assert metrics["expanded_folder_count"] == 1


def test_rank_category_spreads_nearby_photos_without_interest(monkeypatch):
    import ui.recommendation as rec

    def photo(photo_id, folder):
        return {
            "id": photo_id,
            "folder_path": folder,
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
            "thumbnail_path": f"thumb-{photo_id}.jpg",
        }

    batch = [photo(photo_id, "nearby") for photo_id in range(1, 7)] + [photo(7, "other")]
    monkeypatch.setattr(rec, "_load_ranked_memory_photos", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rec, "load_category_photos_batch", lambda *_args, **_kwargs: list(batch))
    monkeypatch.setattr(rec, "_get_recently_shown_ids", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(rec.random, "shuffle", lambda _items: None)
    monkeypatch.setattr(rec, "_load_proximity_interest_keys", lambda *_args, **_kwargs: {"folders": set(), "days": set()})

    photos = rec.rank_category_photos(object(), 1, limit=7)

    assert [p["folder_path"] for p in photos[:4]] == ["nearby", "nearby", "nearby", "other"]


def test_rank_category_requests_thumbnail_filtered_batches(monkeypatch):
    import ui.recommendation as rec

    def photo(photo_id):
        return {
            "id": photo_id,
            "folder_path": f"folder-{photo_id}",
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
            "thumbnail_path": f"thumb-{photo_id}.jpg",
        }

    calls = []

    def fake_batch(_db, _cat_id, _offset, **kwargs):
        calls.append(kwargs)
        return [photo(1), photo(2)]

    monkeypatch.setattr(rec, "_load_ranked_memory_photos", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rec, "load_category_photos_batch", fake_batch)
    monkeypatch.setattr(
        rec,
        "_filter_renderable_photos",
        lambda _photos: (_ for _ in ()).throw(AssertionError("duplicate thumbnail filter called")),
    )
    monkeypatch.setattr(rec, "_get_recently_shown_ids", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(rec.random, "shuffle", lambda _items: None)

    photos = rec.rank_category_photos(object(), 1, limit=2)

    assert [p["id"] for p in photos] == [1, 2]
    assert calls[0]["require_thumbnail"] is True


def test_rank_category_limited_pool_defers_recent_filter_to_merge(monkeypatch):
    import ui.recommendation as rec

    def photo(photo_id):
        return {
            "id": photo_id,
            "folder_path": f"folder-{photo_id}",
            "date_taken": f"2026-06-{photo_id:02d}T12:00:00",
            "file_mtime": f"2026-06-{photo_id:02d}T12:00:00",
            "thumbnail_path": f"thumb-{photo_id}.jpg",
        }

    calls = []

    def fake_batch(_db, _cat_id, _offset, **kwargs):
        calls.append(kwargs)
        return [photo(1), photo(2)]

    monkeypatch.setattr(rec, "_load_ranked_memory_photos", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rec, "load_category_photos_batch", fake_batch)
    monkeypatch.setattr(rec, "_get_recently_shown_ids", lambda *_args, **_kwargs: {2})
    monkeypatch.setattr(rec.random, "shuffle", lambda _items: None)

    photos, metrics = rec.rank_category_photos(object(), 1, return_metrics=True, limit=2)

    assert [p["id"] for p in photos] == [1, 2]
    assert calls[0]["exclude_recent_days"] is None
    assert metrics["excluded_recent"] is False


def test_recently_shown_lookup_can_be_limited_to_candidate_ids(tmp_path):
    import ui.recommendation as rec

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 30):
            conn.execute(
                "INSERT INTO photo_shown_history (file_id, category, shown_at) VALUES (?, 1, datetime('now'))",
                (photo_id,),
            )

    conn = db.get_persistent_connection()
    try:
        recent = rec._get_recently_shown_ids(conn, 1, file_ids=[2, 4, 100, "bad", 4])
    finally:
        conn.close()

    assert recent == {2, 4}
