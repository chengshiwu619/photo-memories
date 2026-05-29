import json
import os
import sqlite3
import subprocess
import sys


def _create_minimal_integrity_db(db_path, valid_thumb_path, duplicate_thumb_path, broken_thumb_path):
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

            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type TEXT NOT NULL,
                photo_ids TEXT NOT NULL,
                cover_file_id INTEGER,
                dismissed_at TEXT
            );
            """
        )

        conn.executemany(
            "INSERT INTO files (id, file_path, is_image) VALUES (?, ?, ?)",
            [
                (1, "photo-1.jpg", 1),
                (2, "photo-2.jpg", 1),
                (3, "photo-3.jpg", 1),
                (4, "photo-4.jpg", 1),
                (5, "photo-5.jpg", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO photo_metadata (file_id, thumbnail_path, is_duplicate_of) VALUES (?, ?, ?)",
            [
                (1, valid_thumb_path, None),
                (2, None, None),
                (3, broken_thumb_path, None),
                (4, duplicate_thumb_path, 1),
                (5, "__FAILED__", None),
            ],
        )
        conn.executemany(
            "INSERT INTO memories (memory_type, photo_ids, cover_file_id, dismissed_at) VALUES (?, ?, ?, ?)",
            [
                ("folder", "[1, 999]", 1, None),
                ("person", "[999]", 999, None),
                ("event", "[4]", 4, None),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _run_cli(args, workdir):
    return subprocess.run(
        [sys.executable, "scripts/check_integrity.py", *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=True,
    )


def test_integrity_cli_text_output_contains_check_details(tmp_path):
    photo_data_dir = tmp_path / "cache"
    thumb_dir = photo_data_dir / "thumbnails"
    thumb_dir.mkdir(parents=True)

    valid_thumb = thumb_dir / "1.jpg"
    valid_thumb.write_bytes(b"ok")
    duplicate_thumb = thumb_dir / "4.jpg"
    duplicate_thumb.write_bytes(b"dup")
    broken_thumb = thumb_dir / "3.jpg"

    db_path = photo_data_dir / "photos.db"
    _create_minimal_integrity_db(str(db_path), str(valid_thumb), str(duplicate_thumb), str(broken_thumb))

    result = _run_cli(["--db-path", str(db_path)], "d:\\photo-memories-source")

    assert "Startup Integrity Report" in result.stdout
    assert "db_path:" in result.stdout
    assert "errors:" in result.stdout
    assert "warnings:" in result.stdout
    assert "memories_missing_file_refs | severity=error | count=2" in result.stdout
    assert "sample_ids:" in result.stdout
    assert "suggested_action:" in result.stdout


def test_integrity_cli_json_output_is_valid_json_and_respects_max_samples(tmp_path):
    photo_data_dir = tmp_path / "cache"
    thumb_dir = photo_data_dir / "thumbnails"
    thumb_dir.mkdir(parents=True)

    valid_thumb = thumb_dir / "1.jpg"
    valid_thumb.write_bytes(b"ok")
    duplicate_thumb = thumb_dir / "4.jpg"
    duplicate_thumb.write_bytes(b"dup")
    broken_thumb = thumb_dir / "3.jpg"

    db_path = photo_data_dir / "photos.db"
    _create_minimal_integrity_db(str(db_path), str(valid_thumb), str(duplicate_thumb), str(broken_thumb))

    result = _run_cli(
        ["--db-path", str(db_path), "--json", "--max-samples", "1"],
        "d:\\photo-memories-source",
    )

    report = json.loads(result.stdout)
    checks = {check["check_name"]: check for check in report["checks"]}

    assert report["dry_run"] is True
    assert report["db_path"] == os.path.abspath(db_path)
    assert len(checks["memories_missing_file_refs"]["sample_ids"]) == 1
    assert len(checks["photo_metadata_broken_thumbnail_files"]["sample_paths"]) == 1
