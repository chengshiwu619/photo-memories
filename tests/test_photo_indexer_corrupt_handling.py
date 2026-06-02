import os
from types import SimpleNamespace

from db_manager import Database


class _BrokenOpenImage:
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def load(self):
        raise self.exc


def _settings(thumb_dir):
    return SimpleNamespace(thumbnail_dir=str(thumb_dir), thumbnail_size=(320, 320))


def _create_file(path, content=b"partial image bytes"):
    path.write_bytes(content)
    stat = path.stat()
    return stat.st_size


def _install_test_db(monkeypatch, tmp_path):
    from business.indexer import photo_indexer as mod

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    monkeypatch.setattr(mod, "_db", db)
    return mod, db


def test_truncated_image_uses_tolerant_thumbnail_retry(monkeypatch, tmp_path):
    mod, _db = _install_test_db(monkeypatch, tmp_path)
    src = tmp_path / "截断照片.JPG"
    size = _create_file(src)
    calls = []

    monkeypatch.setattr(mod, "get_settings", lambda: _settings(tmp_path / "thumbs"))
    monkeypatch.setattr(mod, "extract_exif", lambda filepath: {
        "date_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "raw": {},
    })
    monkeypatch.setattr(mod, "compute_phash_result", lambda filepath: ("hash-ok", "ok", None))
    monkeypatch.setattr(mod.Image, "open", lambda filepath: _BrokenOpenImage(OSError("image file is truncated")))

    def fake_create_thumbnail_file(filepath, thumb_path, thumbnail_size, quality):
        calls.append(mod.ImageFile.LOAD_TRUNCATED_IMAGES)
        if len(calls) == 1:
            raise OSError("image file is truncated")
        assert mod.ImageFile.LOAD_TRUNCATED_IMAGES is True
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"thumb")
        return 100, 80

    monkeypatch.setattr(mod, "create_thumbnail_file", fake_create_thumbnail_file)

    row = mod._index_single_photo(1, str(src))

    assert calls == [False, True]
    assert row[7] != "__FAILED__"
    assert row[13] == "recovered"
    assert row[14] is None
    assert row[15] == size
    assert row[16] is not None


def test_tolerant_retry_failure_records_source_state(monkeypatch, tmp_path):
    mod, _db = _install_test_db(monkeypatch, tmp_path)
    src = tmp_path / "broken-stream.jpg"
    size = _create_file(src)

    monkeypatch.setattr(mod, "get_settings", lambda: _settings(tmp_path / "thumbs"))
    monkeypatch.setattr(mod, "extract_exif", lambda filepath: {
        "date_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "raw": {},
    })
    monkeypatch.setattr(mod.Image, "open", lambda filepath: _BrokenOpenImage(OSError("broken data stream when reading image file")))
    monkeypatch.setattr(
        mod,
        "create_thumbnail_file",
        lambda filepath, thumb_path, thumbnail_size, quality: (_ for _ in ()).throw(
            OSError("broken data stream when reading image file")
        ),
    )

    row = mod._index_single_photo(2, str(src))

    assert row[7] == "__FAILED__"
    assert row[11] == "skipped"
    assert row[12] == "thumbnail_failed"
    assert row[13] == "failed"
    assert "truncated_or_broken_stream" in row[14]
    assert row[15] == size
    assert row[16] is not None


def test_unreadable_image_is_marked_skipped_without_thumbnail_retry(monkeypatch, tmp_path):
    mod, _db = _install_test_db(monkeypatch, tmp_path)
    src = tmp_path / "unreadable.jpg"
    _create_file(src)
    thumbnail_calls = []

    monkeypatch.setattr(mod.Image, "open", lambda filepath: _BrokenOpenImage(OSError("cannot identify image file")))
    monkeypatch.setattr(mod, "create_thumbnail_file", lambda *args, **kwargs: thumbnail_calls.append(args))

    row = mod._index_single_photo(3, str(src))

    assert row[7] == "__FAILED__"
    assert row[11] == "skipped"
    assert row[12] == "thumbnail_failed"
    assert row[13] == "skipped"
    assert "corrupted_or_unreadable" in row[14]
    assert thumbnail_calls == []


def test_failed_thumbnail_is_not_requeued_until_file_changes_or_force_retry(monkeypatch, tmp_path):
    mod, db = _install_test_db(monkeypatch, tmp_path)
    src = tmp_path / "same-size-mtime.jpg"
    _create_file(src)
    mtime = "2026-06-02T12:00:00"

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO files
                (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (10, str(src), src.name, str(tmp_path), tmp_path.name, 19, mtime),
        )
        conn.execute(
            """
            INSERT INTO photo_metadata
                (file_id, thumbnail_path, thumbnail_status, thumbnail_error, source_file_size, source_file_mtime)
            VALUES (?, '__FAILED__', 'failed', 'broken data stream', ?, ?)
            """,
            (10, 19, mtime),
        )

    assert [tuple(row) for row in mod.get_unindexed_photos()] == []
    assert [tuple(row) for row in mod.get_unindexed_photos(force_retry=True)] == [(10, str(src))]

    with db.connect() as conn:
        conn.execute("UPDATE files SET file_size = ? WHERE id = ?", (20, 10))

    assert [tuple(row) for row in mod.get_unindexed_photos()] == [(10, str(src))]


def test_phash_truncated_image_uses_tolerant_retry(monkeypatch):
    from business.indexer import photo_indexer as mod

    calls = []

    def fake_compute(filepath):
        calls.append(mod.ImageFile.LOAD_TRUNCATED_IMAGES)
        if len(calls) == 1:
            raise OSError("image file is truncated")
        assert mod.ImageFile.LOAD_TRUNCATED_IMAGES is True
        return "phash-recovered"

    monkeypatch.setattr(mod, "_compute_phash_once", fake_compute)

    phash, status, error = mod.compute_phash_result("truncated.jpg")

    assert calls == [False, True]
    assert phash == "phash-recovered"
    assert status == "recovered"
    assert error is None


def test_phash_failure_does_not_hide_recovered_thumbnail(monkeypatch, tmp_path):
    mod, _db = _install_test_db(monkeypatch, tmp_path)
    src = tmp_path / "thumb-recovered-phash-failed.jpg"
    _create_file(src)
    calls = []

    monkeypatch.setattr(mod, "get_settings", lambda: _settings(tmp_path / "thumbs"))
    monkeypatch.setattr(mod, "extract_exif", lambda filepath: {
        "date_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "raw": {},
    })
    monkeypatch.setattr(mod.Image, "open", lambda filepath: _BrokenOpenImage(OSError("image file is truncated")))
    monkeypatch.setattr(
        mod,
        "compute_phash_result",
        lambda filepath: (None, "failed", "truncated_or_broken_stream: image file is truncated"),
    )

    def fake_create_thumbnail_file(filepath, thumb_path, thumbnail_size, quality):
        calls.append(mod.ImageFile.LOAD_TRUNCATED_IMAGES)
        if len(calls) == 1:
            raise OSError("image file is truncated")
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"thumb")
        return 100, 80

    monkeypatch.setattr(mod, "create_thumbnail_file", fake_create_thumbnail_file)

    row = mod._index_single_photo(11, str(src))

    assert row[7] != "__FAILED__"
    assert row[10] is None
    assert row[11] == "failed"
    assert "truncated_or_broken_stream" in row[12]
    assert row[13] == "recovered"
