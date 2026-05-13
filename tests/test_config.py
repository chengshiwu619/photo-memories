import os
import importlib


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
    import config
    original = config.DEEPSEEK_API_KEY
    try:
        config.DEEPSEEK_API_KEY = ""
        assert config.is_configured() is False
    finally:
        config.DEEPSEEK_API_KEY = original


def test_is_configured_with_all():
    import config
    original_key = config.DEEPSEEK_API_KEY
    original_src = config.SOURCE_DRIVE
    original_data = config.DATA_DIR
    try:
        config.DEEPSEEK_API_KEY = "sk-test"
        config.SOURCE_DRIVE = "D:\\test"
        config.DATA_DIR = "D:\\testdata"
        assert config.is_configured() is True
    finally:
        config.DEEPSEEK_API_KEY = original_key
        config.SOURCE_DRIVE = original_src
        config.DATA_DIR = original_data


def test_get_openai_client_returns_same_instance():
    import config
    config._OPENAI_CLIENT = None
    original_key = config.DEEPSEEK_API_KEY
    try:
        config.DEEPSEEK_API_KEY = "sk-test-dummy"
        c1 = config.get_openai_client()
        c2 = config.get_openai_client()
        assert c1 is c2
    finally:
        config.DEEPSEEK_API_KEY = original_key
        config._OPENAI_CLIENT = None
