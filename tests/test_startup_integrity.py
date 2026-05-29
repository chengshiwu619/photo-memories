import os
import sqlite3

from services.startup_integrity import build_startup_integrity_report, run_startup_integrity_check


class _FakeSettings:
    def __init__(self, photo_data_dir, thumbnail_dir, db_path):
        self.photo_data_dir = photo_data_dir
        self.thumbnail_dir = thumbnail_dir
        self.db_path = db_path


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
                ("folder", "[999]", 999, "2026-01-01T00:00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _check_by_name(report):
    return {check["check_name"]: check for check in report["checks"]}


def test_run_startup_integrity_check_reports_expected_issues(tmp_path):
    photo_data_dir = tmp_path / "cache"
    thumb_dir = tmp_path / "thumbs"
    photo_data_dir.mkdir()
    thumb_dir.mkdir()

    valid_thumb = thumb_dir / "1.jpg"
    valid_thumb.write_bytes(b"ok")
    duplicate_thumb = thumb_dir / "4.jpg"
    duplicate_thumb.write_bytes(b"dup")
    broken_thumb = thumb_dir / "3.jpg"

    db_path = tmp_path / "photos.db"
    _create_minimal_integrity_db(str(db_path), str(valid_thumb), str(duplicate_thumb), str(broken_thumb))

    settings = _FakeSettings(str(photo_data_dir), str(thumb_dir), str(db_path))
    before_count = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    report = run_startup_integrity_check(dry_run=True, db_path=str(db_path), settings=settings)
    checks = _check_by_name(report)

    assert report["dry_run"] is True
    assert report["has_errors"] is True
    assert report["summary"]["error_count"] == 4
    assert report["summary"]["warning_count"] == 5
    assert checks["photo_data_dir_exists"]["severity"] == "info"
    assert checks["thumbnail_dir_exists"]["severity"] == "info"
    assert checks["memories_missing_file_refs"]["count"] == 2
    assert checks["memories_unrenderable_in_ui"]["count"] == 2
    assert checks["memories_partially_unrenderable"]["count"] == 1
    assert checks["memories_invalid_cover_file"]["count"] == 1
    assert checks["photo_metadata_missing_thumbnail_ref"]["count"] == 1
    assert checks["photo_metadata_failed_thumbnail_ref"]["count"] == 1
    assert checks["photo_metadata_broken_thumbnail_files"]["count"] == 1

    after_count = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert after_count == before_count


def test_build_startup_integrity_report_respects_max_samples(tmp_path):
    photo_data_dir = tmp_path / "cache"
    thumb_dir = tmp_path / "thumbs"
    photo_data_dir.mkdir()
    thumb_dir.mkdir()

    valid_thumb = thumb_dir / "1.jpg"
    valid_thumb.write_bytes(b"ok")
    duplicate_thumb = thumb_dir / "4.jpg"
    duplicate_thumb.write_bytes(b"dup")
    broken_thumb = thumb_dir / "3.jpg"

    db_path = tmp_path / "photos.db"
    _create_minimal_integrity_db(str(db_path), str(valid_thumb), str(duplicate_thumb), str(broken_thumb))
    settings = _FakeSettings(str(photo_data_dir), str(thumb_dir), str(db_path))

    report = build_startup_integrity_report(
        dry_run=True,
        db_path=str(db_path),
        settings=settings,
        max_samples=1,
    )
    checks = _check_by_name(report)

    assert len(checks["memories_missing_file_refs"]["sample_ids"]) == 1
    assert len(checks["photo_metadata_broken_thumbnail_files"]["sample_paths"]) == 1


def test_run_startup_integrity_check_reports_missing_config_dirs(tmp_path):
    db_path = tmp_path / "missing.db"

    settings = _FakeSettings(
        str(tmp_path / "missing-cache"),
        str(tmp_path / "missing-thumbs"),
        str(db_path),
    )

    report = run_startup_integrity_check(dry_run=True, db_path=str(db_path), settings=settings)
    checks = _check_by_name(report)

    assert checks["photo_data_dir_exists"]["severity"] == "warning"
    assert checks["photo_data_dir_exists"]["count"] == 1
    assert checks["thumbnail_dir_exists"]["severity"] == "warning"
    assert checks["thumbnail_dir_exists"]["count"] == 1
    assert checks["database_file_exists"]["severity"] == "warning"
