import os
import tempfile
import shutil


def test_config_imports():
    import config
    assert hasattr(config, "DEEPSEEK_API_KEY")
    assert hasattr(config, "SOURCE_DRIVE")
    assert hasattr(config, "DATA_DIR")
    assert hasattr(config, "DB_PATH")
    assert hasattr(config, "THUMBNAIL_DIR")
    assert hasattr(config, "IMAGE_EXTENSIONS")
    assert hasattr(config, "VIDEO_EXTENSIONS")


def test_category_constants():
    import config
    assert config.CATEGORY_LIFE == 1
    assert config.CATEGORY_SAMPLE == 2
    assert config.CATEGORY_PHOTOGRAPHY == 3
    assert config.CATEGORY_ADULT == 4
    assert len(config.CATEGORY_NAMES) == 4
    assert config.CATEGORY_NAMES[1] == "生活照片"


def test_extensions_sets():
    import config
    assert ".jpg" in config.IMAGE_EXTENSIONS
    assert ".png" in config.IMAGE_EXTENSIONS
    assert ".heic" in config.IMAGE_EXTENSIONS
    assert ".mp4" in config.VIDEO_EXTENSIONS
    assert config.IMAGE_EXTENSIONS.isdisjoint(config.VIDEO_EXTENSIONS)


def test_is_configured_without_api_key():
    import config, os
    orig_env = config.ENV_FILE
    try:
        config.ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_nonexistent_.env")
        assert config.is_configured() is False
    finally:
        config.ENV_FILE = orig_env


def test_is_configured_with_all():
    import config, os
    orig_key = os.environ.get("DEEPSEEK_API_KEY", "")
    orig_src = os.environ.get("SOURCE_DRIVE", "")
    orig_data = os.environ.get("PHOTO_DATA_DIR", "")
    try:
        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        os.environ["SOURCE_DRIVE"] = "D:\\test"
        os.environ["PHOTO_DATA_DIR"] = "D:\\testdata"
        config._settings = None
        config.reload_config()
        assert config.is_configured() is True
    finally:
        if orig_key:
            os.environ["DEEPSEEK_API_KEY"] = orig_key
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        if orig_src:
            os.environ["SOURCE_DRIVE"] = orig_src
        else:
            os.environ.pop("SOURCE_DRIVE", None)
        if orig_data:
            os.environ["PHOTO_DATA_DIR"] = orig_data
        else:
            os.environ.pop("PHOTO_DATA_DIR", None)
        config._settings = None
        config.reload_config()


def test_get_openai_client_returns_same_instance():
    import config, os
    config._OPENAI_CLIENT = None
    orig_key = os.environ.get("DEEPSEEK_API_KEY", "")
    try:
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-dummy"
        config._settings = None
        config.reload_config()
        c1 = config.get_openai_client()
        c2 = config.get_openai_client()
        assert c1 is c2
    finally:
        if orig_key:
            os.environ["DEEPSEEK_API_KEY"] = orig_key
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        config._OPENAI_CLIENT = None
        config._settings = None


def test_settings_class_exists():
    import config
    assert hasattr(config, "Settings")


def test_settings_defaults():
    import config
    s = config.Settings()
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.deepseek_model == "deepseek-chat"
    assert s.thumbnail_size == (400, 400)


def test_settings_computed_properties():
    import config
    s = config.Settings()
    assert s.db_path.endswith("photos.db")
    assert s.thumbnail_dir.endswith("thumbnails")
    assert s.classification_history_file.endswith("classification_history.txt")


def test_get_settings_returns_same_instance():
    import config
    config._settings = None
    s1 = config.get_settings()
    s2 = config.get_settings()
    assert s1 is s2
    config._settings = None


def test_save_config_updates_settings():
    import config
    tmp = tempfile.mkdtemp()
    try:
        orig_env_file = config.ENV_FILE
        fake_env = os.path.join(tmp, ".env")
        with open(fake_env, "w") as f:
            f.write("DEEPSEEK_API_KEY=sk-old\n")
            f.write("SOURCE_DRIVE=D:\\old\n")
            f.write("PHOTO_DATA_DIR=D:\\olddata\n")
        config.ENV_FILE = fake_env
        config._settings = None
        config.reload_config()
        assert config.SOURCE_DRIVE == "D:\\old"
        assert config.DATA_DIR == "D:\\olddata"

        config.save_config("D:\\new", "D:\\newdata", "sk-new")
        assert config.SOURCE_DRIVE == "D:\\new"
        assert config.DATA_DIR == "D:\\newdata"
        assert config.DEEPSEEK_API_KEY == "sk-new"

        s = config.get_settings()
        assert s.source_drive == "D:\\new"
        assert s.photo_data_dir == "D:\\newdata"
        assert s.deepseek_api_key == "sk-new"

    finally:
        shutil.rmtree(tmp)
        config.ENV_FILE = orig_env_file
        config.reload_config()
