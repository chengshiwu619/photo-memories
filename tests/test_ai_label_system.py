import json
import os
import sqlite3
import subprocess
import sys

from scripts.run_ai_labeling import run_ai_labeling


def _create_ai_label_db(db_path, thumb_dir):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
                folder_path TEXT,
                is_image INTEGER DEFAULT 1
            );

            CREATE TABLE photo_metadata (
                file_id INTEGER PRIMARY KEY,
                thumbnail_path TEXT,
                is_duplicate_of INTEGER
            );

            CREATE TABLE photo_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(file_id, tag, source)
            );

            CREATE TABLE folder_categories (
                folder_path TEXT PRIMARY KEY,
                category INTEGER NOT NULL,
                confidence TEXT,
                classified_at TEXT
            );
            """
        )

        items = [
            (1, r"D:/photos/life/2024-02-14/family_trip/photo-1.jpg", r"D:/photos/life/2024-02-14/family_trip", 1, "1.jpg"),
            (2, r"D:/photos/sample/写真/棚拍A/photo-2.jpg", r"D:/photos/sample/写真/棚拍A", 2, "2.jpg"),
            (3, r"D:/photos/sample/写真/棚拍B/photo-3.jpg", r"D:/photos/sample/写真/棚拍B", 2, "3.jpg"),
            (4, r"D:/photos/misc/screenshots/photo-4.jpg", r"D:/photos/misc/screenshots", None, "__FAILED__"),
            (5, r"D:/photos/life/成人/私房/photo-5.jpg", r"D:/photos/life/成人/私房", 1, "5.jpg"),
            (6, r"D:/photos/life/聚会/客厅/photo-6.jpg", r"D:/photos/life/聚会/客厅", 1, "6.jpg"),
        ]

        for file_id, file_path, folder_path, category, thumb_name in items:
            thumb_path = "__FAILED__" if thumb_name == "__FAILED__" else os.path.join(thumb_dir, thumb_name)
            if thumb_name != "__FAILED__":
                with open(thumb_path, "wb") as fh:
                    fh.write(b"ok")
            conn.execute(
                "INSERT INTO files (id, file_path, folder_path, is_image) VALUES (?, ?, ?, 1)",
                (file_id, file_path, folder_path),
            )
            conn.execute(
                "INSERT INTO photo_metadata (file_id, thumbnail_path, is_duplicate_of) VALUES (?, ?, NULL)",
                (file_id, thumb_path),
            )
            if category is not None:
                conn.execute(
                    "INSERT INTO folder_categories (folder_path, category, confidence, classified_at) VALUES (?, ?, 'manual', datetime('now'))",
                    (folder_path, category),
                )

        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            (6, "existing-path-tag", "path"),
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            (3, "existing-siglip-tag", "siglip"),
        )
        conn.commit()
    finally:
        conn.close()


def test_path_label_dry_run_does_not_write_database(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_labeling._generate_siglip_tags", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("path source should not call siglip")))

    result = run_ai_labeling(db_path=str(db_path), source="path", limit=50, dry_run=True)
    conn = sqlite3.connect(db_path)
    try:
        tag_count = conn.execute("SELECT COUNT(*) FROM photo_tags WHERE source = 'path'").fetchone()[0]
    finally:
        conn.close()

    assert result["source"] == "path"
    assert result["dry_run"] is True
    assert result["db_updated"] == 0
    assert tag_count == 1


def test_path_label_apply_writes_photo_tags_and_deduplicates(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    first = run_ai_labeling(db_path=str(db_path), source="path", limit=50, dry_run=False)
    second = run_ai_labeling(db_path=str(db_path), source="path", limit=50, dry_run=False)

    assert first["tags_inserted"] > 0
    assert first["files_with_tags"] > 0
    assert second["db_updated"] == 0
    assert second["tags_inserted"] == 0


def test_adult_and_chinese_paths_are_not_excluded(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    result = run_ai_labeling(db_path=str(db_path), source="path", limit=50, dry_run=True)
    file_ids = {item["file_id"] for item in result["file_results"]}

    assert 2 in file_ids
    assert 5 in file_ids


def test_failed_thumbnail_is_skipped_from_candidates(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    result = run_ai_labeling(db_path=str(db_path), source="path", limit=50, dry_run=True)
    file_ids = {item["file_id"] for item in result["file_results"]}

    assert 4 not in file_ids
    assert result["invalid_thumbnail_skipped"] >= 1


def test_random_sample_mode_is_reproducible_with_seed(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    result_a = run_ai_labeling(db_path=str(db_path), source="path", limit=3, dry_run=True, sample_mode="random", seed=42)
    result_b = run_ai_labeling(db_path=str(db_path), source="path", limit=3, dry_run=True, sample_mode="random", seed=42)

    ids_a = [item["file_id"] for item in result_a["file_results"]]
    ids_b = [item["file_id"] for item in result_b["file_results"]]
    assert ids_a == ids_b


def test_folder_diverse_selects_multiple_source_folders(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    result = run_ai_labeling(db_path=str(db_path), source="path", limit=4, dry_run=True, sample_mode="folder-diverse", seed=42)

    assert result["selected_folder_count"] >= 2


def test_source_all_keeps_path_flow_when_siglip_dependency_unavailable(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_labeling._siglip_dependency_available", lambda: False)

    result = run_ai_labeling(db_path=str(db_path), source="all", limit=10, dry_run=False)

    assert result["tags_inserted"] > 0
    assert any(item["source"] == "path" and item["status"] == "succeeded_with_tags" for item in result["file_results"])
    assert any(item["source"] == "siglip" and item["status"] == "failed_dependency" for item in result["file_results"])


def test_json_output_contains_summary_and_per_file_results(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ai_labeling.py",
            "--db-path",
            str(db_path),
            "--source",
            "path",
            "--limit",
            "5",
            "--dry-run",
            "--json",
        ],
        cwd="d:\\photo-memories-source",
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["source"] == "path"
    assert payload["selected"] > 0
    assert isinstance(payload["file_results"], list)
