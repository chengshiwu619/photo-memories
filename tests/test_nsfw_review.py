from db_manager import Database


def _write_thumb(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"thumb")


def _insert_photo(conn, tmp_path, photo_id, folder="MobileBackup/iPhone/2025/11", file_name=None):
    file_name = file_name or f"{photo_id}.jpg"
    folder_path = str(tmp_path / folder)
    file_path = str(tmp_path / folder / file_name)
    thumb_path = tmp_path / "thumbs" / f"{photo_id}.jpg"
    _write_thumb(thumb_path)
    conn.execute(
        """
        INSERT INTO files
            (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (photo_id, file_path, file_name, folder_path, folder, "2026-06-02T12:00:00"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO folder_categories (folder_path, category, confidence) VALUES (?, 1, 'llm-branch')",
        (folder_path,),
    )
    conn.execute(
        """
        INSERT INTO photo_metadata
            (file_id, thumbnail_path, width, height, date_taken)
        VALUES (?, ?, 100, 80, ?)
        """,
        (photo_id, str(thumb_path), "2026-06-02T12:00:00"),
    )


def test_mobile_backup_sample_filename_appears_in_review_candidates(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            file_name="JP-Mio-Ishikawa-Title-0043-0748480480.jpg",
        )

    candidates = load_review_candidates(db=db)

    assert [item["id"] for item in candidates] == [1]
    assert "filename:sample-pattern" in candidates[0]["reasons"]


def test_camera_mobile_backup_filename_does_not_appear_in_review_candidates(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, file_name="IMG_20230708_171732.JPG")

    assert load_review_candidates(db=db) == []


def test_nested_mobile_backup_camera_file_is_not_review_candidate(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates, mark_review_candidates_as_sample

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            folder="MobileBackup/iPhone/2025/10",
            file_name="IMG_20251021_092431.jpg",
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
            (1, "nsfw"),
        )

    assert load_review_candidates(db=db) == []
    assert mark_review_candidates_as_sample([1], db=db) == {"requested": 1, "updated": 0, "missing": 1}


def test_legacy_mobile_backup_img_number_is_not_review_candidate(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates, mark_review_candidates_as_sample

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            folder="MobileBackup/iPhone/2022/08",
            file_name="IMG_2670.JPG",
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
            (1, "nsfw"),
        )

    assert load_review_candidates(db=db) == []
    assert mark_review_candidates_as_sample([1], db=db) == {"requested": 1, "updated": 0, "missing": 1}


def test_moments_mobile_dcim_camera_file_is_not_review_candidate_even_with_visual_tag(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates, mark_review_candidates_as_sample

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            folder="Moments/Mobile/SM-N9600/DCIM/2019-11-25",
            file_name="20191125_165104.jpg",
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
            (1, "nsfw"),
        )

    assert load_review_candidates(db=db) == []
    assert mark_review_candidates_as_sample([1], db=db) == {"requested": 1, "updated": 0, "missing": 1}


def test_film_output_life_file_is_not_review_candidate_even_with_visual_tag(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates, mark_review_candidates_as_sample

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            folder="胶片成图/日常生活/随便",
            file_name="heliar-5294-5.jpg",
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
            (1, "nsfw"),
        )

    assert load_review_candidates(db=db) == []
    assert mark_review_candidates_as_sample([1], db=db) == {"requested": 1, "updated": 0, "missing": 1}


def test_siglip_nsfw_tag_life_photo_appears_and_dismiss_hides_it(tmp_path):
    from business.classifier.nsfw_review import dismiss_review_candidate, load_review_candidates

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, folder="Family/2026", file_name="1.jpg")
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
            (1, "nsfw"),
        )

    candidates = load_review_candidates(db=db)
    assert [item["id"] for item in candidates] == [1]
    assert "visual:nsfw" in candidates[0]["reasons"]

    assert dismiss_review_candidate(1, db=db) is True
    assert load_review_candidates(db=db) == []


def test_dismiss_review_candidates_hides_batch_without_reordering_survivors(tmp_path):
    from business.classifier.nsfw_review import dismiss_review_candidates, load_review_candidates

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        for photo_id in range(1, 5):
            _insert_photo(conn, tmp_path, photo_id, folder=f"Family/{photo_id}", file_name=f"{photo_id}.jpg")
            conn.execute(
                "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
                (photo_id, "nsfw"),
            )
            taken = f"2026-01-0{photo_id}T12:00:00"
            conn.execute("UPDATE files SET file_mtime = ? WHERE id = ?", (taken, photo_id))
            conn.execute("UPDATE photo_metadata SET date_taken = ? WHERE file_id = ?", (taken, photo_id))

    before = [item["id"] for item in load_review_candidates(db=db)]
    result = dismiss_review_candidates([3, 2], db=db)
    after = [item["id"] for item in load_review_candidates(db=db)]

    assert before == [4, 3, 2, 1]
    assert result == {"requested": 2, "inserted": 2}
    assert after == [4, 1]


def test_mark_review_candidate_as_sample_sets_photo_metadata_category(tmp_path):
    from config import CATEGORY_SAMPLE
    from business.classifier.nsfw_review import mark_review_candidate_as_sample

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, file_name="IMG_1.JPG")

    assert mark_review_candidate_as_sample(1, db=db) is True
    with db.connect() as conn:
        row = conn.execute("SELECT category FROM photo_metadata WHERE file_id = 1").fetchone()

    assert row["category"] == CATEGORY_SAMPLE


def test_mark_review_candidates_as_sample_updates_remaining_batch(tmp_path):
    from config import CATEGORY_SAMPLE
    from business.classifier.nsfw_review import mark_review_candidates_as_sample

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1, file_name="IMG_1.JPG")
        _insert_photo(conn, tmp_path, 2, file_name="IMG_2.JPG")

    result = mark_review_candidates_as_sample([1, 2, 999], db=db)
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT file_id, category FROM photo_metadata WHERE file_id IN (1, 2) ORDER BY file_id"
        ).fetchall()

    assert result == {"requested": 3, "updated": 2, "missing": 1}
    assert [(row["file_id"], row["category"]) for row in rows] == [
        (1, CATEGORY_SAMPLE),
        (2, CATEGORY_SAMPLE),
    ]


def test_marked_sample_candidates_do_not_reappear_in_review(tmp_path):
    from business.classifier.nsfw_review import (
        load_review_candidates,
        mark_review_candidates_as_sample,
    )

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            file_name="JP-Mio-Ishikawa-Title-0043-0748480480.jpg",
        )

    assert [item["id"] for item in load_review_candidates(db=db)] == [1]

    result = mark_review_candidates_as_sample([1], db=db)

    assert result["updated"] == 1
    assert load_review_candidates(db=db) == []


def test_review_candidates_are_ordered_by_time_before_filename_priority(tmp_path):
    from business.classifier.nsfw_review import load_review_candidates

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(
            conn,
            tmp_path,
            1,
            folder="MobileBackup/iPhone/2025/11",
            file_name="JP-Old-Model-Title-0001.jpg",
        )
        _insert_photo(conn, tmp_path, 2, folder="Family/2026", file_name="new.jpg")
        conn.execute(
            "UPDATE files SET file_mtime = ? WHERE id = 1",
            ("2024-01-01T12:00:00",),
        )
        conn.execute(
            "UPDATE photo_metadata SET date_taken = ? WHERE file_id = 1",
            ("2024-01-01T12:00:00",),
        )
        conn.execute(
            "UPDATE files SET file_mtime = ? WHERE id = 2",
            ("2026-01-01T12:00:00",),
        )
        conn.execute(
            "UPDATE photo_metadata SET date_taken = ? WHERE file_id = 2",
            ("2026-01-01T12:00:00",),
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, 'siglip')",
            (2, "nsfw"),
        )

    candidates = load_review_candidates(db=db)

    assert [item["id"] for item in candidates] == [2, 1]
