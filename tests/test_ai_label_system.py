import json
import os
import sqlite3
import subprocess
import sys

from scripts.run_ai_labeling import _extract_path_tags, run_ai_labeling


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


def test_path_label_cleaning_filters_capacity_and_generic_noise():
    payload = _extract_path_tags(
        {
            "source_path": r"D:/photos/2.79GB/2050P+28V/p-3/no/希威社/私房写真未流出/photo.jpg",
            "source_folder": r"D:/photos/2.79GB/2050P+28V/p-3/no/希威社/私房写真未流出",
            "folder_category": 2,
        }
    )

    assert "category:sample" in payload["cleaned_tags"]
    assert "希威社" in payload["cleaned_tags"]
    assert "私房写真未流出" in payload["cleaned_tags"]
    assert "2.79GB" in payload["filtered_tags"]
    assert "2050P+28V" in payload["filtered_tags"]
    assert "p-3" in payload["filtered_tags"]
    assert "no" in payload["filtered_tags"]
    assert "photos" in payload["filtered_tags"]


def test_path_label_cleaning_filters_numbered_series_and_count_size_fragments():
    payload = _extract_path_tags(
        {
            "source_path": r"D:/photos/希威社/NO.041 其他 [2050P+28V 6.6GB]/私房写真未流出 [490P-3.86 GB]/希威摄影 Vol.004 私房写真未流出合集 [76P-553MB]/photo.jpg",
            "source_folder": r"D:/photos/希威社/NO.041 其他 [2050P+28V 6.6GB]/私房写真未流出 [490P-3.86 GB]/希威摄影 Vol.004 私房写真未流出合集 [76P-553MB]",
            "folder_category": 2,
        }
    )

    assert "希威摄影" in payload["cleaned_tags"]
    assert "vol.004" in payload["cleaned_tags"]
    assert "私房写真未流出合集" in payload["cleaned_tags"]
    assert "NO.041" in payload["filtered_tags"]
    assert "490P-3.86" in payload["filtered_tags"]
    assert "76P-553MB" in payload["filtered_tags"]


def test_path_label_cleaning_keeps_chinese_semantic_tags_and_category():
    payload = _extract_path_tags(
        {
            "source_path": r"D:/photos/screenshots/成人/写真/欣欣/无水印/photo.jpg",
            "source_folder": r"D:/photos/screenshots/成人/写真/欣欣/无水印",
            "folder_category": 1,
        }
    )

    assert "category:life" in payload["cleaned_tags"]
    assert "screenshots" in payload["cleaned_tags"]
    assert "成人" in payload["cleaned_tags"]
    assert "写真" in payload["cleaned_tags"]
    assert "欣欣" in payload["cleaned_tags"]
    assert "无水印" in payload["cleaned_tags"]


def test_dry_run_exposes_raw_cleaned_and_filtered_tags(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM photo_tags WHERE source = 'path'")
        conn.execute("UPDATE files SET file_path = ? WHERE id = 2", (r"D:/photos/2.79GB/2050P+28V/p+28v/希威社/无水印/photo-2.jpg",))
        conn.commit()
    finally:
        conn.close()

    result = run_ai_labeling(
        db_path=str(db_path),
        source="path",
        limit=10,
        dry_run=True,
        sample_mode="sequential",
    )

    file_result = next(item for item in result["file_results"] if item["file_id"] == 2)
    assert "raw_tags" in file_result
    assert "cleaned_tags" in file_result
    assert "filtered_tags" in file_result
    assert "希威社" in file_result["cleaned_tags"]
    assert "无水印" in file_result["cleaned_tags"]
    assert "2050P+28V" in file_result["filtered_tags"]
    assert "p+28v" in file_result["filtered_tags"]


def test_apply_writes_only_cleaned_tags(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_label_db(str(db_path), str(thumb_dir))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM photo_tags WHERE source = 'path'")
        conn.execute("UPDATE files SET file_path = ? WHERE id = 2", (r"D:/photos/2.79GB/2050P+28V/p-7/希威社/无水印/photo-2.jpg",))
        conn.commit()
    finally:
        conn.close()

    result = run_ai_labeling(db_path=str(db_path), source="path", limit=10, dry_run=False)
    assert result["tags_inserted"] > 0

    conn = sqlite3.connect(db_path)
    try:
        tags = {
            row[0]
            for row in conn.execute(
                "SELECT tag FROM photo_tags WHERE source = 'path' AND file_id = 2"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "希威社" in tags
    assert "无水印" in tags
    assert "2.79GB" not in tags
    assert "2050P+28V" not in tags
    assert "p-7" not in tags
