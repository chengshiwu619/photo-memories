from db_manager import Database
from webapp.hot_cache import WebHotCache


def test_web_hot_cache_reopens_and_pages_without_live_recomputation(tmp_path):
    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    folder = str(tmp_path / "Photos" / "Moments")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, 1, 'manual')",
            (folder,),
        )
        conn.executemany(
            """
            INSERT INTO files
                (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image, path_status)
            VALUES (?, ?, ?, ?, 'Moments', ?, 1, 'ok')
            """,
            [
                (
                    file_id,
                    str(tmp_path / f"photo-{file_id}.jpg"),
                    f"photo-{file_id}.jpg",
                    folder,
                    f"2026-07-{(file_id % 28) + 1:02d}T12:00:00",
                )
                for file_id in range(1, 241)
            ],
        )
        conn.executemany(
            """
            INSERT INTO photo_metadata
                (file_id, thumbnail_path, width, height, date_taken, category)
            VALUES (?, ?, 1200, 800, ?, 1)
            """,
            [
                (
                    file_id,
                    str(tmp_path / "thumbs" / f"{file_id}.jpg"),
                    f"2026-07-{(file_id % 28) + 1:02d}T12:00:00",
                )
                for file_id in range(1, 241)
            ],
        )
        conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (1, 'family', 'siglip')")

    cold = WebHotCache(db)
    assert cold.ensure_ready() is True
    first, total = cold.page(1, 48, offset=0)
    second, _ = cold.page(1, 48, offset=48)
    assert total == 240
    assert len(first) == len(second) == 48
    assert {item["id"] for item in first}.isdisjoint(item["id"] for item in second)
    with db.connect() as conn:
        segment_starts = [
            int(row["random_rank"])
            for row in conn.execute(
                """
                SELECT random_rank FROM web_photo_cache
                WHERE generation = ? AND category = 1 AND segment_start = 1
                ORDER BY random_rank
                """,
                (cold._active_generation,),
            ).fetchall()
        ]
    assert segment_starts
    assert cold._rotations[(cold._active_generation, 1, False)] in segment_starts
    segment_lengths = [
        (segment_starts[index + 1] if index + 1 < len(segment_starts) else total) - start
        for index, start in enumerate(segment_starts)
    ]
    assert all(length <= 25 for length in segment_lengths)
    assert sum(length < 25 for length in segment_lengths) <= 1
    previous_rotation = cold._rotations[(cold._active_generation, 1, False)]
    next_rotation = cold.rotate_random(1)
    refreshed, _ = cold.page(1, 48, offset=0)
    assert next_rotation != previous_rotation
    assert refreshed[0]["id"] != first[0]["id"]

    reopened = WebHotCache(db)
    assert reopened.ready is True
    timeline, timeline_total = reopened.page(1, 48, offset=0, timeline=True)
    assert timeline_total == 240
    assert len(timeline) == 48
    timeline_index = reopened.timeline_index(1)
    assert timeline_index == {
        "months": [{"month": "2026-07", "count": 240, "offset": 0}],
        "total": 240,
        "hot": True,
    }
    context = reopened.context(timeline[20]["id"], 1, before=5, after=5)
    assert context is not None
    assert context["items"][context["index"]]["id"] == timeline[20]["id"]


def test_web_hot_cache_migrates_existing_snapshot_with_segment_marker(tmp_path):
    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE web_cache_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE web_photo_cache (
                generation INTEGER NOT NULL,
                category INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                random_rank INTEGER NOT NULL,
                date_key TEXT NOT NULL,
                starred INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                thumbnail_path TEXT NOT NULL,
                original_path TEXT NOT NULL,
                PRIMARY KEY (generation, category, file_id)
            );
            """
        )

    WebHotCache(db)

    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(web_photo_cache)")}
    assert "segment_start" in columns
