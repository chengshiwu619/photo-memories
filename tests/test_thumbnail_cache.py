import os
import sqlite3
import sys
import types

from infra.image.thumbnail_cache import (
    build_legacy_thumbnail_cache_signature,
    build_thumbnail_cache_signature,
    classify_thumbnail_cache_signature,
)


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
                env_value = overrides.get(field_name, os.environ.get(field_name.upper(), default))
                setattr(self, field_name, env_value)

    class SettingsConfigDict(dict):
        pass

    fake_module.BaseSettings = BaseSettings
    fake_module.SettingsConfigDict = SettingsConfigDict
    return fake_module


if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = _install_fake_dotenv_module()

if "pydantic_settings" not in sys.modules:
    sys.modules["pydantic_settings"] = _install_fake_pydantic_settings_module()


class _FakeSettings:
    def __init__(self, thumbnail_size=(600, 600)):
        self.thumbnail_size = thumbnail_size


def test_thumbnail_cache_signature_helpers_classify_current_legacy_and_stale():
    settings = _FakeSettings()

    current_sig = build_thumbnail_cache_signature(settings)
    legacy_sig = build_legacy_thumbnail_cache_signature(settings)

    assert current_sig == "v2:600x600:q90"
    assert legacy_sig == "600x600_q90"
    assert classify_thumbnail_cache_signature(current_sig, settings) == "current"
    assert classify_thumbnail_cache_signature(legacy_sig, settings) == "legacy"
    assert classify_thumbnail_cache_signature("legacy:400x400:q80", settings) == "stale"
    assert classify_thumbnail_cache_signature(None, settings) == "missing"


def test_db_manager_keeps_existing_thumbnails_when_legacy_signature_is_detected(tmp_path, monkeypatch):
    from db_manager import Database
    import config

    settings = _FakeSettings()
    db_path = tmp_path / "photos.db"
    thumb_path = tmp_path / "thumbs" / "1.jpg"
    thumb_path.parent.mkdir(parents=True)
    thumb_path.write_bytes(b"ok")

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE photo_metadata (
                file_id INTEGER PRIMARY KEY,
                thumbnail_path TEXT
            );
            CREATE TABLE thumbnail_params (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO photo_metadata (file_id, thumbnail_path) VALUES (?, ?)",
            (1, str(thumb_path)),
        )
        conn.execute(
            "INSERT INTO thumbnail_params (key, value) VALUES (?, ?)",
            ("thumbnail_sig", build_legacy_thumbnail_cache_signature(settings)),
        )
        conn.commit()

        monkeypatch.setattr(config, "get_settings", lambda: settings)
        db = Database(str(db_path))
        db._check_and_clear_thumbnails(conn)

        stored_sig = conn.execute(
            "SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'"
        ).fetchone()[0]
        stored_thumb_path = conn.execute(
            "SELECT thumbnail_path FROM photo_metadata WHERE file_id = 1"
        ).fetchone()[0]
    finally:
        conn.close()

    assert stored_sig == "600x600_q90"
    assert stored_thumb_path == str(thumb_path)
    assert thumb_path.exists()


def test_db_manager_initializes_missing_signature_with_current_helper(tmp_path, monkeypatch):
    from db_manager import Database
    import config

    settings = _FakeSettings()
    db_path = tmp_path / "photos.db"

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE photo_metadata (
                file_id INTEGER PRIMARY KEY,
                thumbnail_path TEXT
            );
            CREATE TABLE thumbnail_params (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()

        monkeypatch.setattr(config, "get_settings", lambda: settings)
        db = Database(str(db_path))
        db._check_and_clear_thumbnails(conn)

        stored_sig = conn.execute(
            "SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert stored_sig == build_thumbnail_cache_signature(settings)
