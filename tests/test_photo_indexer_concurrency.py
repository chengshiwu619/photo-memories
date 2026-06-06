import threading
from contextlib import contextmanager
import importlib.util
import sys
import types


def _install_fake_pil_modules():
    pil_module = types.ModuleType("PIL")

    class _FakeImageModule:
        LANCZOS = 1
        MAX_IMAGE_PIXELS = 500_000_000

        @staticmethod
        def open(*args, **kwargs):
            raise RuntimeError("fake PIL open should not be used in indexer concurrency tests")

    imageops_module = types.ModuleType("PIL.ImageOps")
    imageops_module.exif_transpose = lambda img: img
    imagefile_module = types.ModuleType("PIL.ImageFile")
    imagefile_module.LOAD_TRUNCATED_IMAGES = False

    pil_module.Image = _FakeImageModule
    pil_module.ImageOps = imageops_module
    pil_module.ImageFile = imagefile_module
    return pil_module, _FakeImageModule, imageops_module, imagefile_module


def _install_fake_dotenv_module():
    fake_module = types.ModuleType("dotenv")
    fake_module.find_dotenv = lambda: ""
    fake_module.load_dotenv = lambda *args, **kwargs: False
    fake_module.set_key = lambda path, key, value: (key, value)
    return fake_module


def _install_fake_pydantic_settings_module():
    fake_module = types.ModuleType("pydantic_settings")

    class BaseSettings:
        model_config = {}

        def __init__(self, **overrides):
            for field_name in getattr(self.__class__, "__annotations__", {}):
                default = getattr(self.__class__, field_name)
                setattr(self, field_name, overrides.get(field_name, default))

    class SettingsConfigDict(dict):
        pass

    fake_module.BaseSettings = BaseSettings
    fake_module.SettingsConfigDict = SettingsConfigDict
    return fake_module


def _install_fake_exifread_module():
    fake_module = types.ModuleType("exifread")
    fake_module.process_file = lambda *args, **kwargs: {}
    return fake_module


def _install_fake_imagehash_module():
    fake_module = types.ModuleType("imagehash")
    fake_module.phash = lambda img: "fake-phash"
    fake_module.hex_to_hash = lambda value: value
    return fake_module


def _install_fake_pillow_heif_module():
    fake_module = types.ModuleType("pillow_heif")
    fake_module.register_heif_opener = lambda: None
    return fake_module


if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = _install_fake_dotenv_module()

if "pydantic_settings" not in sys.modules:
    sys.modules["pydantic_settings"] = _install_fake_pydantic_settings_module()

if "exifread" not in sys.modules:
    sys.modules["exifread"] = _install_fake_exifread_module()

if "imagehash" not in sys.modules:
    sys.modules["imagehash"] = _install_fake_imagehash_module()

if "pillow_heif" not in sys.modules:
    sys.modules["pillow_heif"] = _install_fake_pillow_heif_module()

if "PIL" not in sys.modules and importlib.util.find_spec("PIL") is None:
    pil_module, image_module, imageops_module, imagefile_module = _install_fake_pil_modules()
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module
    sys.modules["PIL.ImageOps"] = imageops_module
    sys.modules["PIL.ImageFile"] = imagefile_module


def _make_row(
    file_id,
    thumbnail_path=None,
    phash_status="ok",
    phash_error=None,
    thumbnail_status="ok",
    thumbnail_error=None,
    source_file_size=None,
    source_file_mtime=None,
):
    return (
        file_id,
        "2024-01-01T00:00:00",
        "camera",
        None,
        None,
        100,
        80,
        thumbnail_path or f"thumb-{file_id}.jpg",
        None,
        "2024-01-01T00:00:00",
        f"phash-{file_id}",
        phash_status,
        phash_error,
        thumbnail_status,
        thumbnail_error,
        source_file_size,
        source_file_mtime,
    )


class _FakeConnection:
    def __init__(self, db):
        self.db = db

    def executemany(self, query, rows):
        self.db.executed_batches.append((threading.get_ident(), list(rows)))


class _FakeDb:
    def __init__(self):
        self.init_tables_called = 0
        self.executed_batches = []

    def init_tables(self):
        self.init_tables_called += 1

    @contextmanager
    def connect(self):
        yield _FakeConnection(self)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeCandidateConnection:
    def __init__(self, result_sets):
        self.result_sets = list(result_sets)

    def execute(self, *_args, **_kwargs):
        return _Rows(self.result_sets.pop(0))


class _FakeCandidateDb:
    def __init__(self, result_sets):
        self.result_sets = result_sets

    @contextmanager
    def connect(self):
        yield _FakeCandidateConnection(self.result_sets)


class _FakeCheckpoint:
    def __init__(self):
        self.saves = []
        self.cleared = 0
        self._pause_requested = False

    def load(self):
        return None

    def save(self, state, **kwargs):
        self.saves.append((state, kwargs))

    def clear(self):
        self.cleared += 1

    def is_pause_or_stop_requested(self):
        return self._pause_requested


def test_index_photos_workers_1_matches_serial_semantics(monkeypatch):
    from business.indexer import photo_indexer as mod

    fake_db = _FakeDb()
    fake_cp = _FakeCheckpoint()
    photos = [(1, "a.jpg", "new_changed_create"), (2, "b.jpg", "new_changed_create"), (3, "c.jpg", "new_changed_create")]

    monkeypatch.setattr(mod, "_db", fake_db)
    monkeypatch.setattr(mod, "_cp", fake_cp)
    monkeypatch.setattr(mod, "get_unindexed_photos", lambda force_retry=False, priority_filter=None: photos)
    monkeypatch.setattr(mod, "dedup_by_phash", lambda progress_callback=None: {"checked": 3, "duplicates": 0})
    monkeypatch.setattr(mod, "_index_single_photo", lambda file_id, file_path: _make_row(file_id))
    monkeypatch.setattr(mod, "INDEX_COMMIT_EVERY", 20)

    progress = []
    result = mod.index_photos(progress_callback=lambda cur, tot: progress.append((cur, tot)), workers=1, batch_size=2)

    assert result["total"] == 3
    assert result["indexed"] == 3
    assert result["processed"] == 3
    assert result["db_updated"] == 3
    assert fake_db.init_tables_called == 1
    assert len(fake_db.executed_batches) == 2
    assert fake_db.executed_batches[0][1] == [_make_row(1), _make_row(2)]
    assert fake_db.executed_batches[1][1] == [_make_row(3)]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert fake_cp.saves[0][1]["current_index"] == 0
    assert fake_cp.saves[1][1]["current_index"] == 2
    assert fake_cp.saves[2][1]["current_index"] == 3
    assert fake_cp.cleared == 1


def test_index_photos_workers_2_process_multiple_items_and_keep_db_writes_on_main_thread(monkeypatch):
    from business.indexer import photo_indexer as mod

    fake_db = _FakeDb()
    fake_cp = _FakeCheckpoint()
    photos = [(1, "a.jpg", "new_changed_create"), (2, "b.jpg", "new_changed_create"), (3, "c.jpg", "new_changed_create"), (4, "d.jpg", "new_changed_create")]
    worker_thread_ids = []
    barrier = threading.Barrier(2)
    main_thread_id = threading.get_ident()

    def _fake_index_single_photo(file_id, file_path):
        worker_thread_ids.append(threading.get_ident())
        if file_id in (1, 2):
            barrier.wait(timeout=2)
        return _make_row(file_id)

    monkeypatch.setattr(mod, "_db", fake_db)
    monkeypatch.setattr(mod, "_cp", fake_cp)
    monkeypatch.setattr(mod, "get_unindexed_photos", lambda force_retry=False, priority_filter=None: photos)
    monkeypatch.setattr(mod, "dedup_by_phash", lambda progress_callback=None: {"checked": 4, "duplicates": 0})
    monkeypatch.setattr(mod, "_index_single_photo", _fake_index_single_photo)
    monkeypatch.setattr(mod, "INDEX_COMMIT_EVERY", 2)

    result = mod.index_photos(workers=2, batch_size=2)

    assert result["total"] == 4
    assert result["indexed"] == 4
    assert result["processed"] == 4
    assert result["db_updated"] == 4
    assert len(set(worker_thread_ids)) >= 2
    assert len(fake_db.executed_batches) == 2
    assert all(thread_id == main_thread_id for thread_id, _rows in fake_db.executed_batches)
    assert fake_cp.saves[1][1]["current_index"] == 2
    assert fake_cp.saves[2][1]["current_index"] == 4


def test_index_photos_single_failure_does_not_block_other_rows_and_failed_marker_is_preserved(monkeypatch):
    from business.indexer import photo_indexer as mod

    fake_db = _FakeDb()
    fake_cp = _FakeCheckpoint()
    photos = [(1, "a.jpg", "new_changed_create"), (2, "b.jpg", "new_changed_create"), (3, "c.jpg", "new_changed_create")]

    def _fake_index_single_photo(file_id, file_path):
        if file_id == 2:
            raise RuntimeError("decode failed")
        if file_id == 3:
            return _make_row(file_id, thumbnail_path="__FAILED__")
        return _make_row(file_id)

    monkeypatch.setattr(mod, "_db", fake_db)
    monkeypatch.setattr(mod, "_cp", fake_cp)
    monkeypatch.setattr(mod, "get_unindexed_photos", lambda force_retry=False, priority_filter=None: photos)
    monkeypatch.setattr(mod, "dedup_by_phash", lambda progress_callback=None: {"checked": 2, "duplicates": 0})
    monkeypatch.setattr(mod, "_index_single_photo", _fake_index_single_photo)
    monkeypatch.setattr(mod, "INDEX_COMMIT_EVERY", 20)

    result = mod.index_photos(workers=2, batch_size=2)

    assert result["total"] == 3
    assert result["indexed"] == 2
    assert result["processed"] == 3
    assert result["thumbnail_failed"] >= 1
    written_rows = [row for _thread_id, rows in fake_db.executed_batches for row in rows]
    assert _make_row(1) in written_rows
    assert _make_row(3, thumbnail_path="__FAILED__") in written_rows
    assert all(row[0] != 2 for row in written_rows)


def test_index_photos_batch_limit_saves_checkpoint_after_batch(monkeypatch):
    from business.indexer import photo_indexer as mod

    fake_db = _FakeDb()
    fake_cp = _FakeCheckpoint()
    photos = [(1, "a.jpg", "new_changed_create"), (2, "b.jpg", "new_changed_create"), (3, "c.jpg", "new_changed_create"), (4, "d.jpg", "new_changed_create")]

    monkeypatch.setattr(mod, "_db", fake_db)
    monkeypatch.setattr(mod, "_cp", fake_cp)
    monkeypatch.setattr(mod, "get_unindexed_photos", lambda force_retry=False, priority_filter=None: photos)
    monkeypatch.setattr(mod, "dedup_by_phash", lambda progress_callback=None: {"checked": 0, "duplicates": 0})
    monkeypatch.setattr(mod, "_index_single_photo", lambda file_id, file_path: _make_row(file_id))
    monkeypatch.setattr(mod, "INDEX_COMMIT_EVERY", 20)

    result = mod.index_photos(workers=2, batch_size=2, batch_limit=2)

    assert result["paused"] is True
    assert result["batch_limit_reached"] is True
    assert result["indexed"] == 2
    assert fake_cp.saves[-1][1]["current_index"] == 2


def test_get_unindexed_requeues_ok_record_when_thumbnail_file_missing(monkeypatch):
    from business.indexer import photo_indexer as mod

    fake_db = _FakeCandidateDb([
        [],
        [(7, "photo.jpg", "missing-thumb.jpg")],
    ])
    monkeypatch.setattr(mod, "_db", fake_db)
    monkeypatch.setattr(mod.os.path, "exists", lambda path: path != "missing-thumb.jpg")

    rows = mod.get_unindexed_photos()

    assert rows == [(7, "photo.jpg", "historical_missing")]
