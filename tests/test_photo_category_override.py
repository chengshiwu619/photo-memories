from db_manager import Database


def _insert_file(conn, file_id, folder_path="/photos/life"):
    conn.execute(
        """
        INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (file_id, f"{folder_path}/{file_id}.jpg", f"{file_id}.jpg", folder_path, "life"),
    )
    conn.execute(
        "INSERT INTO photo_metadata (file_id, thumbnail_path) VALUES (?, ?)",
        (file_id, f"/thumbs/{file_id}.jpg"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO folder_categories (folder_path, category, confidence) VALUES (?, 1, 'test')",
        (folder_path,),
    )


def test_batch_set_photo_category_updates_only_requested_files(tmp_path):
    from config import CATEGORY_SAMPLE
    from business.classifier.photo_category_override import batch_set_photo_category

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_file(conn, 1)
        _insert_file(conn, 2)
        _insert_file(conn, 3)

    result = batch_set_photo_category([1, 2, 999], CATEGORY_SAMPLE, batch_size=1, db=db)

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT file_id, category FROM photo_metadata ORDER BY file_id"
        ).fetchall()
        confirmed_ids = {
            row[0]
            for row in conn.execute(
                "SELECT file_id FROM photo_tags WHERE tag = 'category:confirmed-sample' AND source = 'manual'"
            ).fetchall()
        }

    assert result["requested"] == 3
    assert result["updated"] == 2
    assert result["missing"] == 1
    assert [(r["file_id"], r["category"]) for r in rows] == [(1, 2), (2, 2), (3, None)]
    assert confirmed_ids == {1, 2}


def test_setting_photo_back_to_life_removes_confirmed_sample_override(tmp_path):
    from config import CATEGORY_LIFE, CATEGORY_SAMPLE
    from business.classifier.photo_category_override import batch_set_photo_category

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_file(conn, 1, folder_path="/Photos/Moments/new")

    batch_set_photo_category([1], CATEGORY_SAMPLE, db=db)
    batch_set_photo_category([1], CATEGORY_LIFE, db=db)

    with db.connect() as conn:
        category = conn.execute(
            "SELECT category FROM photo_metadata WHERE file_id = 1"
        ).fetchone()[0]
        marker = conn.execute(
            "SELECT 1 FROM photo_tags WHERE file_id = 1 AND tag = 'category:confirmed-sample' AND source = 'manual'"
        ).fetchone()

    assert category == CATEGORY_LIFE
    assert marker is None
