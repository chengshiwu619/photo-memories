import os
from datetime import datetime

from db_manager import Database


class _Settings:
    def __init__(self, source_dir, data_dir):
        self.source_drive = str(source_dir)
        self.photo_data_dir = str(data_dir)
        self.thumbnail_dir = os.path.join(str(data_dir), "thumbnails")
        self.thumbnail_size = (600, 600)

    @property
    def source_dirs(self):
        return [self.source_drive]

    @property
    def db_path(self):
        return os.path.join(self.photo_data_dir, "photos.db")


def _configure(tmp_path, monkeypatch):
    import db_manager as db_mod
    import business.scanner.fast_scan as scan_mod

    source_dir = tmp_path / "照片源"
    data_dir = tmp_path / "cache"
    source_dir.mkdir()
    data_dir.mkdir()
    settings = _Settings(source_dir, data_dir)
    monkeypatch.setattr(db_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(scan_mod, "get_settings", lambda: settings)
    db = Database(settings.db_path)
    db.init_tables()
    return scan_mod, db, settings, source_dir


def test_incremental_scan_inserts_new_file_with_uppercase_extension_and_chinese_path(tmp_path, monkeypatch):
    scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
    photo_dir = source_dir / "旅行"
    photo_dir.mkdir()
    photo = photo_dir / "新照片.JPEG"
    photo.write_bytes(b"jpeg-ish")

    result = scan_mod.incremental_scan(
        dry_run=False,
        prefer_everything=False,
        db=db,
        settings=settings,
    )

    assert result["new"] == 1
    assert result["db_inserted"] == 1
    with db.connect() as conn:
        row = conn.execute("SELECT file_path, is_image FROM files").fetchone()
    assert row["file_path"] == os.path.normpath(str(photo))
    assert row["is_image"] == 1


def test_incremental_scan_dry_run_does_not_write_database(tmp_path, monkeypatch):
    scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
    (source_dir / "only.webp").write_bytes(b"webp-ish")

    result = scan_mod.incremental_scan(
        dry_run=True,
        prefer_everything=False,
        db=db,
        settings=settings,
    )

    assert result["new"] == 1
    assert result["db_inserted"] == 0
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0


def test_incremental_scan_existing_file_is_not_duplicated_after_path_normalize(tmp_path, monkeypatch):
    scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
    photo = source_dir / "SameCase.jpg"
    photo.write_bytes(b"same")
    existing_path = os.path.normpath(str(photo)).upper()
    with db.connect() as conn:
        current_mtime = datetime.fromtimestamp(photo.stat().st_mtime).isoformat()
        conn.execute(
            """INSERT INTO files
               (file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image, scanned_at, source_dir)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                existing_path,
                "SameCase.jpg",
                os.path.dirname(existing_path),
                os.path.basename(os.path.dirname(existing_path)),
                photo.stat().st_size,
                current_mtime,
                1,
                "2000-01-01T00:00:00",
                settings.source_drive,
            ),
        )

    result = scan_mod.incremental_scan(
        dry_run=False,
        prefer_everything=False,
        db=db,
        settings=settings,
    )

    assert result["new"] == 0
    assert result["existing"] == 1
    assert result["changed"] == 0
    assert result["db_inserted"] == 0
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1


def test_incremental_scan_changed_file_resets_thumbnail_and_siglip_state(tmp_path, monkeypatch):
    scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
    photo = source_dir / "changed.jpg"
    photo.write_bytes(b"new-content")
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO files
               (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image, scanned_at, source_dir)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                1,
                os.path.normpath(str(photo)),
                photo.name,
                os.path.normpath(str(source_dir)),
                source_dir.name,
                1,
                "2000-01-01T00:00:00",
                1,
                "2000-01-01T00:00:00",
                settings.source_drive,
            ),
        )
        conn.execute(
            "INSERT INTO photo_metadata (file_id, thumbnail_path, indexed_at, phash) VALUES (?, ?, ?, ?)",
            (1, "old-thumb.jpg", "2000-01-01T00:00:00", "abc"),
        )
        conn.execute(
            "INSERT INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            (1, "old-visual", "siglip"),
        )

    result = scan_mod.incremental_scan(
        dry_run=False,
        prefer_everything=False,
        db=db,
        settings=settings,
    )

    assert result["changed"] == 1
    assert result["db_updated"] == 1
    with db.connect() as conn:
        meta = conn.execute("SELECT thumbnail_path, indexed_at, phash FROM photo_metadata WHERE file_id = 1").fetchone()
        tag_count = conn.execute("SELECT COUNT(*) FROM photo_tags WHERE file_id = 1 AND source = 'siglip'").fetchone()[0]
    assert meta["thumbnail_path"] is None
    assert meta["indexed_at"] is None
    assert meta["phash"] is None
    assert tag_count == 0


def test_incremental_scan_reports_paused_state(tmp_path, monkeypatch):
    scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
    (source_dir / "one.jpg").write_bytes(b"one")
    (source_dir / "two.jpg").write_bytes(b"two")
    calls = {"count": 0}

    def should_pause():
        calls["count"] += 1
        return calls["count"] > 1

    result = scan_mod.incremental_scan(
        dry_run=True,
        prefer_everything=False,
        db=db,
        settings=settings,
        should_pause=should_pause,
    )

    assert result["state"] == "paused"
    assert result["paused"] is True
    assert result["scanned"] == 1


def test_everything_query_is_limited_to_source_root(tmp_path, monkeypatch):
    scan_mod, _db, settings, source_dir = _configure(tmp_path, monkeypatch)

    query = scan_mod._build_everything_source_query(settings)

    assert str(source_dir) in query
    assert "-path" in query
    assert "ext:" in query


def test_everything_path_query_uses_path_option_and_normalizes_drive_alias(tmp_path, monkeypatch):
    scan_mod, _db, settings, _source_dir = _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(scan_mod, "_everything_source_search_paths", lambda settings=None: [r"Y:\\"])
    monkeypatch.setattr(scan_mod, "_match_source_dir", lambda filepath: settings.source_drive if filepath.startswith("Y:") else None)
    monkeypatch.setattr(scan_mod, "_normalize_filepath", lambda filepath, source_dir: filepath.replace("Y:", source_dir, 1))

    calls = []

    def fake_run_es(args, timeout=120):
        calls.append(args)
        return '"Y:\\\\NW\\\\file?.jpg"', 0

    monkeypatch.setattr(scan_mod, "_run_es", fake_run_es)

    files = scan_mod._query_everything_source_files(limit=10, timeout=5, settings=settings)

    assert calls[0][:2] == ["-path", r"Y:\\"]
    assert "ext:" in calls[0][-1]
    assert files == [settings.source_drive + r"\\NW\\file?.jpg"]


def test_parse_es_csv_keeps_literal_question_mark_paths(tmp_path, monkeypatch):
    scan_mod, _db, settings, _source_dir = _configure(tmp_path, monkeypatch)
    path = os.path.normpath(os.path.join(settings.source_drive, "NW", "file?.jpg"))

    files = scan_mod._parse_es_csv(f'"{path}"')

    assert files == [path]
