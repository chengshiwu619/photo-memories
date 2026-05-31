import json
import os
import sqlite3
import subprocess
import sys
import threading

from scripts.maintain_thumbnails import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_WORKERS,
    diagnose_failed_thumbnail_item,
    run_thumbnail_maintenance,
)


def _write_test_image(path):
    jpeg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08"
        b"\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e"
        b"\x1d\x1a\x1c\x1c $.' ',#\x1c\x1c(7),01444\x1f'9=82<.342"
        b"\xff\xdb\x00C\x01\x09\x09\x09\x0c\x0b\x0c\x18\x0d\x0d\x182!\x1c!2222"
        b"22222222222222222222222222222222222222222222222222\xff\xc0\x00"
        b"\x11\x08\x00\x01\x00\x01\x03\x01\"\x00\x02\x11\x01\x03\x11\x01\xff\xc4"
        b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5"
        b"\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}"
        b"\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91"
        b"\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*"
        b"456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\xff\xc4\x00\x1f\x01\x00\x03"
        b"\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02"
        b"\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02"
        b"\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04"
        b"\x05!1\x06\x12AQ\x07aq\x13\"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0"
        b"\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&'()*56789:CDEFGHIJSTUVWXYZ"
        b"cdefghijstuvwxyz\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00"
        b"\xfc\xaa(\xa2\x80?\xff\xd9"
    )
    with open(path, "wb") as fh:
        fh.write(jpeg_bytes)


def _create_thumbnail_maintenance_db(
    db_path,
    source_dir,
    thumbnail_dir,
    thumbnail_sig="600x600_q90",
    failed_file_ids=None,
    broken_file_ids=None,
    source_exts=None,
):
    failed_file_ids = set(failed_file_ids or [])
    broken_file_ids = set(broken_file_ids or [])
    source_exts = source_exts or {}
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
            CREATE TABLE thumbnail_params (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO thumbnail_params (key, value) VALUES (?, ?)",
            ("thumbnail_sig", thumbnail_sig),
        )

        files = []
        metadata = []
        for file_id in range(1, 5):
            ext = source_exts.get(file_id, ".jpg")
            file_path = os.path.join(source_dir, f"source-{file_id}{ext}")
            files.append((file_id, file_path, 1))
            if file_id in failed_file_ids:
                thumbnail_path = "__FAILED__"
            elif file_id in broken_file_ids:
                thumbnail_path = os.path.join(thumbnail_dir, f"{file_id}.jpg")
            else:
                thumbnail_path = os.path.join(thumbnail_dir, f"{file_id}.jpg")
                _write_test_image(thumbnail_path)
            metadata.append((file_id, thumbnail_path, None))

        conn.executemany(
            "INSERT INTO files (id, file_path, is_image) VALUES (?, ?, ?)",
            files,
        )
        conn.executemany(
            "INSERT INTO photo_metadata (file_id, thumbnail_path, is_duplicate_of) VALUES (?, ?, ?)",
            metadata,
        )
        conn.commit()
    finally:
        conn.close()


def test_missing_source_is_not_retry_recommended(tmp_path):
    item = {
        "file_id": 1,
        "file_path": str(tmp_path / "missing.jpg"),
        "target_thumbnail_path": str(tmp_path / "thumbs" / "1.jpg"),
    }
    diagnosis = diagnose_failed_thumbnail_item(item)
    assert diagnosis["likely_reason"] == "missing_source"
    assert diagnosis["retry_recommended"] is False


def test_not_file_is_not_retry_recommended(tmp_path):
    source_dir = tmp_path / "folder-source"
    source_dir.mkdir()
    item = {
        "file_id": 1,
        "file_path": str(source_dir),
        "target_thumbnail_path": str(tmp_path / "thumbs" / "1.jpg"),
    }
    diagnosis = diagnose_failed_thumbnail_item(item)
    assert diagnosis["likely_reason"] == "not_file"
    assert diagnosis["retry_recommended"] is False


def test_unsupported_extension_is_not_retry_recommended(tmp_path):
    source_path = tmp_path / "source-1.txt"
    source_path.write_text("not an image", encoding="utf-8")
    item = {
        "file_id": 1,
        "file_path": str(source_path),
        "target_thumbnail_path": str(tmp_path / "thumbs" / "1.jpg"),
    }
    diagnosis = diagnose_failed_thumbnail_item(item)
    assert diagnosis["likely_reason"] == "unsupported_extension"
    assert diagnosis["retry_recommended"] is False


def test_non_ascii_path_diagnosis_is_safe(tmp_path):
    source_path = tmp_path / "中文目录" / "照片.jpg"
    source_path.parent.mkdir()
    _write_test_image(source_path)
    item = {
        "file_id": 1,
        "file_path": str(source_path),
        "target_thumbnail_path": str(tmp_path / "thumbs" / "1.jpg"),
    }
    diagnosis = diagnose_failed_thumbnail_item(item)
    assert diagnosis["has_non_ascii"] is True
    assert diagnosis["retry_recommended"] is True
    assert diagnosis["likely_reason"] in {"non_ascii_path", "source_ok_retry_possible"}


def test_special_char_path_diagnosis_is_safe(tmp_path):
    source_path = tmp_path / "special#name(1).jpg"
    _write_test_image(source_path)
    item = {
        "file_id": 1,
        "file_path": str(source_path),
        "target_thumbnail_path": str(tmp_path / "thumbs" / "1.jpg"),
    }
    diagnosis = diagnose_failed_thumbnail_item(item)
    assert diagnosis["has_special_chars"] is True
    assert diagnosis["retry_recommended"] is True
    assert diagnosis["likely_reason"] == "special_char_path"


def test_readable_supported_source_is_retry_recommended(tmp_path):
    source_path = tmp_path / "source-1.jpg"
    _write_test_image(source_path)
    item = {
        "file_id": 1,
        "file_path": str(source_path),
        "target_thumbnail_path": str(tmp_path / "thumbs" / "1.jpg"),
    }
    diagnosis = diagnose_failed_thumbnail_item(item)
    assert diagnosis["source_exists"] is True
    assert diagnosis["source_is_file"] is True
    assert diagnosis["source_readable"] is True
    assert diagnosis["retry_recommended"] is True
    assert diagnosis["likely_reason"] == "source_ok_retry_possible"


def test_default_dry_run_does_not_write_database_or_files(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1}, broken_file_ids={2})
    missing_target = thumb_dir / "1.jpg"

    result = run_thumbnail_maintenance(db_path=str(db_path))
    conn = sqlite3.connect(db_path)
    try:
        thumb_value = conn.execute("SELECT thumbnail_path FROM photo_metadata WHERE file_id = 1").fetchone()[0]
    finally:
        conn.close()

    assert result["dry_run"] is True
    assert result["db_updated"] == 0
    assert result["attempted"] == 0
    assert result["workers"] == DEFAULT_WORKERS
    assert result["batch_size"] == DEFAULT_BATCH_SIZE
    assert thumb_value == "__FAILED__"
    assert not missing_target.exists()


def test_retry_failed_dry_run_lists_plan_and_diagnostics(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1, 2})

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        limit=1,
        workers=3,
        batch_size=4,
        scope_limited=True,
    )
    plan = result["operations"]["retry_failed"]

    assert result["dry_run"] is True
    assert result["workers"] == 3
    assert result["batch_size"] == 4
    assert plan["found"] == 2
    assert len(plan["selected"]) == 1
    assert result["db_updated"] == 0
    assert result["file_results"][0]["status"] == "planned"
    assert "likely_reason" in result["file_results"][0]
    assert "recommended_action" in result["file_results"][0]
    assert result["next_steps"]


def test_retry_failed_apply_rejects_without_explicit_scope(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1, 2})

    result = run_thumbnail_maintenance(db_path=str(db_path), retry_failed=True, apply=True)

    assert result["attempted"] == 0
    assert result["db_updated"] == 0
    assert result["planned_apply_count"] == 0
    assert any("refused" in warning for warning in result["warnings"])


def test_retry_failed_apply_updates_thumbnail_path_on_success(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    source_path = source_dir / "source-1.jpg"
    _write_test_image(source_path)
    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1})

    def _fake_create_thumbnail_file(source_path, target_path, thumbnail_size, quality):
        _write_test_image(target_path)
        return (16, 16)

    monkeypatch.setattr(
        "scripts.maintain_thumbnails.create_thumbnail_file",
        _fake_create_thumbnail_file,
    )

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        apply=True,
        file_ids=[1],
        scope_limited=True,
    )
    target_path = thumb_dir / "1.jpg"
    conn = sqlite3.connect(db_path)
    try:
        thumb_value = conn.execute("SELECT thumbnail_path FROM photo_metadata WHERE file_id = 1").fetchone()[0]
    finally:
        conn.close()

    assert result["dry_run"] is False
    assert result["succeeded"] == 1
    assert result["db_updated"] == 1
    assert target_path.exists()
    assert thumb_value == str(target_path)
    assert result["file_results"][-1]["status"] == "succeeded"


def test_retry_failed_apply_skips_missing_source_and_keeps_failed_marker(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1})

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        apply=True,
        file_ids=[1],
        scope_limited=True,
    )
    conn = sqlite3.connect(db_path)
    try:
        thumb_value = conn.execute("SELECT thumbnail_path FROM photo_metadata WHERE file_id = 1").fetchone()[0]
    finally:
        conn.close()

    assert result["skipped"] == 1
    assert result["db_updated"] == 0
    assert thumb_value == "__FAILED__"
    assert result["file_results"][0]["status"] == "skipped"
    assert result["file_results"][0]["likely_reason"] == "missing_source"


def test_retry_failed_apply_generation_exception_keeps_failed_marker(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    source_path = source_dir / "source-1.jpg"
    _write_test_image(source_path)
    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1})

    def _boom(*args, **kwargs):
        raise RuntimeError("decoder blew up")

    monkeypatch.setattr(
        "scripts.maintain_thumbnails.create_thumbnail_file",
        _boom,
    )

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        apply=True,
        file_ids=[1],
        scope_limited=True,
    )
    conn = sqlite3.connect(db_path)
    try:
        thumb_value = conn.execute("SELECT thumbnail_path FROM photo_metadata WHERE file_id = 1").fetchone()[0]
    finally:
        conn.close()

    assert result["failed"] == 1
    assert result["db_updated"] == 0
    assert thumb_value == "__FAILED__"
    assert result["file_results"][0]["status"] == "failed"
    assert "decoder blew up" in result["file_results"][0]["error"]


def test_limit_and_file_id_filter_only_select_requested_failed_rows(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1, 2, 3})

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        file_ids=[2, 3],
        limit=1,
        scope_limited=True,
    )
    selected = result["operations"]["retry_failed"]["selected"]

    assert result["operations"]["retry_failed"]["found"] == 2
    assert len(selected) == 1
    assert selected[0]["file_id"] == 2


def test_non_failed_records_are_not_retried(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1})

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        file_ids=[4],
        scope_limited=True,
    )

    assert result["operations"]["retry_failed"]["found"] == 0
    assert result["selected"] == 0


def test_workers_and_batch_size_are_clamped_to_minimum_one(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1})

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        workers=0,
        batch_size=0,
        scope_limited=True,
    )

    assert result["workers"] == 1
    assert result["batch_size"] == 1


def test_database_updates_stay_on_main_thread(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    source_path = source_dir / "source-1.jpg"
    second_source_path = source_dir / "source-2.jpg"
    _write_test_image(source_path)
    _write_test_image(second_source_path)
    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1, 2})

    execute_thread_ids = []
    real_connect = sqlite3.connect
    main_thread_id = threading.get_ident()

    class RecordingConnection:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, *args, **kwargs):
            execute_thread_ids.append(threading.get_ident())
            return self._conn.execute(*args, **kwargs)

        def commit(self):
            return self._conn.commit()

        def close(self):
            return self._conn.close()

        @property
        def row_factory(self):
            return self._conn.row_factory

        @row_factory.setter
        def row_factory(self, value):
            self._conn.row_factory = value

    def _recording_connect(*args, **kwargs):
        return RecordingConnection(real_connect(*args, **kwargs))

    def _fake_create_thumbnail_file(source_path, target_path, thumbnail_size, quality):
        _write_test_image(target_path)
        return (16, 16)

    monkeypatch.setattr("scripts.maintain_thumbnails.sqlite3.connect", _recording_connect)
    monkeypatch.setattr("scripts.maintain_thumbnails.create_thumbnail_file", _fake_create_thumbnail_file)

    result = run_thumbnail_maintenance(
        db_path=str(db_path),
        retry_failed=True,
        apply=True,
        file_ids=[1, 2],
        scope_limited=True,
        workers=2,
        batch_size=1,
    )

    assert result["db_updated"] == 2
    assert execute_thread_ids
    assert all(thread_id == main_thread_id for thread_id in execute_thread_ids)


def test_migrate_signature_dry_run_does_not_write_database(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(
        str(db_path),
        str(source_dir),
        str(thumb_dir),
        thumbnail_sig="600x600_q90",
    )

    result = run_thumbnail_maintenance(db_path=str(db_path), migrate_signature=True)
    conn = sqlite3.connect(db_path)
    try:
        sig = conn.execute("SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'").fetchone()[0]
    finally:
        conn.close()

    assert result["dry_run"] is True
    assert result["db_updated"] == 0
    assert sig == "600x600_q90"


def test_migrate_signature_apply_only_updates_signature(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    existing_thumb = thumb_dir / "2.jpg"
    _write_test_image(existing_thumb)
    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), thumbnail_sig="600x600_q90")

    result = run_thumbnail_maintenance(db_path=str(db_path), migrate_signature=True, apply=True)
    conn = sqlite3.connect(db_path)
    try:
        sig = conn.execute("SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'").fetchone()[0]
        thumb_value = conn.execute("SELECT thumbnail_path FROM photo_metadata WHERE file_id = 2").fetchone()[0]
    finally:
        conn.close()

    assert result["db_updated"] == 1
    assert sig == "v2:600x600:q90"
    assert thumb_value == str(existing_thumb)


def test_migrate_signature_refuses_when_missing_thumbnail_files_exist(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(
        str(db_path),
        str(source_dir),
        str(thumb_dir),
        thumbnail_sig="600x600_q90",
        broken_file_ids={3},
    )

    result = run_thumbnail_maintenance(db_path=str(db_path), migrate_signature=True, apply=True)
    conn = sqlite3.connect(db_path)
    try:
        sig = conn.execute("SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'").fetchone()[0]
    finally:
        conn.close()

    assert result["skipped"] == 1
    assert result["db_updated"] == 0
    assert sig == "600x600_q90"
    assert any("blocked" in warning or "missing thumbnail files" in warning for warning in result["warnings"])


def test_json_output_is_valid_and_contains_diagnostics(tmp_path):
    cache_dir = tmp_path / "cache"
    thumb_dir = cache_dir / "thumbnails"
    source_dir = tmp_path / "sources"
    cache_dir.mkdir()
    thumb_dir.mkdir(parents=True)
    source_dir.mkdir()

    db_path = cache_dir / "photos.db"
    _create_thumbnail_maintenance_db(str(db_path), str(source_dir), str(thumb_dir), failed_file_ids={1})

    result = subprocess.run(
        [sys.executable, "scripts/maintain_thumbnails.py", "--db-path", str(db_path), "--retry-failed", "--json"],
        cwd="d:\\photo-memories-source",
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["mode"] == "retry_failed"
    assert payload["dry_run"] is True
    assert payload["workers"] == DEFAULT_WORKERS
    assert payload["batch_size"] == DEFAULT_BATCH_SIZE
    assert payload["file_results"][0]["status"] == "planned"
    assert "likely_reason" in payload["file_results"][0]
    assert "retry_recommended" in payload["file_results"][0]
    assert payload["next_steps"]
