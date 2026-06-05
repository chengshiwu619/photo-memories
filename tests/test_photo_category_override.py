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

    assert result["requested"] == 3
    assert result["updated"] == 2
    assert result["missing"] == 1
    assert [(r["file_id"], r["category"]) for r in rows] == [(1, 2), (2, 2), (3, None)]
