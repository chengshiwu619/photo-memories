import json
import os
import sqlite3
import subprocess
import sys

from scripts.run_ai_recognition import run_ai_recognition_validation


def _create_ai_recognition_db(db_path, thumb_dir):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
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
            """
        )

        thumb_1 = os.path.join(thumb_dir, "1.jpg")
        thumb_2 = os.path.join(thumb_dir, "2.jpg")
        thumb_4 = os.path.join(thumb_dir, "4.jpg")
        with open(thumb_1, "wb") as fh:
            fh.write(b"ok")
        with open(thumb_2, "wb") as fh:
            fh.write(b"ok")

        conn.executemany(
            "INSERT INTO files (id, file_path, is_image) VALUES (?, ?, ?)",
            [
                (1, "D:/photos/source-1.jpg", 1),
                (2, "D:/photos/source-2.jpg", 1),
                (3, "D:/photos/source-3.jpg", 1),
                (4, "D:/photos/source-4.jpg", 1),
                (5, "D:/photos/source-5.jpg", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO photo_metadata (file_id, thumbnail_path, is_duplicate_of) VALUES (?, ?, ?)",
            [
                (1, thumb_1, None),
                (2, thumb_2, None),
                (3, "__FAILED__", None),
                (4, thumb_4, None),
                (5, thumb_1, 1),
            ],
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            (2, "existing-tag", "siglip"),
        )
        conn.commit()
    finally:
        conn.close()


def test_ai_recognition_dry_run_selects_only_eligible_items_and_writes_nothing(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    def _boom(_file_ids):
        raise AssertionError("dry-run should not call generate_tags_batch")

    monkeypatch.setattr("scripts.run_ai_recognition._generate_siglip_tags", _boom)
    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: False)

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=True)
    conn = sqlite3.connect(db_path)
    try:
        tag_count = conn.execute("SELECT COUNT(*) FROM photo_tags").fetchone()[0]
    finally:
        conn.close()

    assert result["dry_run"] is True
    assert result["selected"] == 1
    assert result["skipped"] == 2
    assert result["processed"] == 0
    assert result["model_loaded"] is False
    assert result["db_updated"] == 0
    assert tag_count == 1
    assert result["file_results"][0]["file_id"] == 1
    assert result["file_results"][0]["status"] == "planned"


def test_ai_recognition_apply_writes_siglip_tags_for_small_batch(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    monkeypatch.setattr(
        "scripts.run_ai_recognition._generate_siglip_tags",
        lambda file_ids: {file_ids[0]: ["beach", "sunset"]},
    )

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT tag, source FROM photo_tags WHERE file_id = ? ORDER BY tag",
            (1,),
        ).fetchall()
    finally:
        conn.close()

    assert result["selected"] == 1
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["model_loaded"] is True
    assert result["db_updated"] == 2
    assert result["file_results"][0]["labels"] == ["beach", "sunset"]
    assert result["file_results"][0]["status"] == "succeeded_with_tags"
    assert rows == [("beach", "siglip"), ("sunset", "siglip")]


def test_ai_recognition_apply_maps_thumbnail_path_keys_to_file_ids(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    thumb_path = os.path.join(str(thumb_dir), "1.jpg")
    monkeypatch.setattr(
        "scripts.run_ai_recognition._generate_siglip_tags",
        lambda _file_ids: {thumb_path: ["mountain"]},
    )

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT tag, source FROM photo_tags WHERE file_id = ?",
            (1,),
        ).fetchall()
    finally:
        conn.close()

    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["db_updated"] == 1
    assert result["file_results"][0]["status"] == "succeeded_with_tags"
    assert rows == [("mountain", "siglip")]


def test_ai_recognition_apply_maps_numeric_string_keys_to_file_ids(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    monkeypatch.setattr(
        "scripts.run_ai_recognition._generate_siglip_tags",
        lambda _file_ids: {"1": ["river"]},
    )

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["db_updated"] == 1
    assert result["file_results"][0]["status"] == "succeeded_with_tags"


def test_ai_recognition_apply_maps_list_of_dict_results(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    monkeypatch.setattr(
        "scripts.run_ai_recognition._generate_siglip_tags",
        lambda _file_ids: [{"file_id": 1, "tags": ["forest", "lake"]}],
    )

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["db_updated"] == 2
    assert result["file_results"][0]["status"] == "succeeded_with_tags"


def test_ai_recognition_apply_records_no_tags_without_failing(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    monkeypatch.setattr("scripts.run_ai_recognition._generate_siglip_tags", lambda _file_ids: {1: []})

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)
    conn = sqlite3.connect(db_path)
    try:
        tag_count = conn.execute("SELECT COUNT(*) FROM photo_tags WHERE file_id = ?", (1,)).fetchone()[0]
    finally:
        conn.close()

    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["db_updated"] == 0
    assert result["file_results"][0]["status"] == "succeeded_no_tags"
    assert result["file_results"][0]["reason"] == "no_tags_above_threshold"
    assert tag_count == 0


def test_ai_recognition_apply_marks_missing_result_as_mapping_failure(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    monkeypatch.setattr("scripts.run_ai_recognition._generate_siglip_tags", lambda _file_ids: {})

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)
    conn = sqlite3.connect(db_path)
    try:
        tag_count = conn.execute("SELECT COUNT(*) FROM photo_tags WHERE file_id = ?", (1,)).fetchone()[0]
    finally:
        conn.close()

    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["db_updated"] == 0
    assert result["file_results"][0]["status"] == "failed_result_mapping"
    assert result["file_results"][0]["reason"] == "no_encoded_images_or_empty_result"
    assert result["result_type"] == "dict"
    assert result["result_len"] == 0
    assert result["result_key_sample"] == []
    assert result["candidate_file_id_sample"] == [1]
    assert len(result["candidate_thumbnail_path_sample"]) == 1
    assert len(result["candidate_source_path_sample"]) == 1
    assert tag_count == 0


def test_ai_recognition_apply_reports_unmapped_keys_with_samples(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    monkeypatch.setattr("scripts.run_ai_recognition._siglip_dependency_available", lambda: True)
    monkeypatch.setattr(
        "scripts.run_ai_recognition._generate_siglip_tags",
        lambda _file_ids: [("Z:/mismatch/thumb.jpg", ["clouds"])],
    )

    result = run_ai_recognition_validation(db_path=str(db_path), limit=10, dry_run=False)

    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["file_results"][0]["status"] == "failed_result_mapping"
    assert result["file_results"][0]["reason"] == "result_mapping_missing"
    assert result["result_type"] == "list"
    assert result["result_len"] == 1
    assert result["result_key_sample"] == ["Z:/mismatch/thumb.jpg"]
    assert "result_key_sample" in result["file_results"][0]["error"]
    assert "candidate_file_id_sample" in result["file_results"][0]["error"]


def test_ai_recognition_cli_json_output_is_valid(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    cache_dir.mkdir()
    thumb_dir.mkdir()
    db_path = cache_dir / "photos.db"
    _create_ai_recognition_db(str(db_path), str(thumb_dir))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ai_recognition.py",
            "--db-path",
            str(db_path),
            "--limit",
            "10",
            "--dry-run",
            "--json",
        ],
        cwd="d:\\photo-memories-source",
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["mode"] == "siglip_tag_validation"
    assert payload["selected"] == 1
    assert payload["file_results"][0]["file_id"] == 1
    assert payload["file_results"][0]["status"] == "planned"
