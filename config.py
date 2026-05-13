import os
from dotenv import load_dotenv, set_key, find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = find_dotenv() or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    source_drive: str = "D:\\测试"
    photo_data_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage")

    thumbnail_size: tuple[int, int] = (400, 400)

    @property
    def db_path(self) -> str:
        return os.path.join(self.photo_data_dir, "photos.db")

    @property
    def thumbnail_dir(self) -> str:
        return os.path.join(self.photo_data_dir, "thumbnails")

    @property
    def classification_history_file(self) -> str:
        return os.path.join(self.photo_data_dir, "classification_history.txt")

    def is_configured(self) -> bool:
        return bool(self.deepseek_api_key and self.source_drive and self.photo_data_dir)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _sync_module_vars_from_settings():
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    global SOURCE_DRIVE, DATA_DIR, DB_PATH, THUMBNAIL_DIR, CLASSIFICATION_HISTORY_FILE
    s = get_settings()
    DEEPSEEK_API_KEY = s.deepseek_api_key
    DEEPSEEK_BASE_URL = s.deepseek_base_url
    DEEPSEEK_MODEL = s.deepseek_model
    SOURCE_DRIVE = s.source_drive
    DATA_DIR = s.photo_data_dir
    DB_PATH = s.db_path
    THUMBNAIL_DIR = s.thumbnail_dir
    CLASSIFICATION_HISTORY_FILE = s.classification_history_file


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"}
THUMBNAIL_SIZE = (400, 400)

CATEGORY_LIFE = 1
CATEGORY_SAMPLE = 2
CATEGORY_PHOTOGRAPHY = 3
CATEGORY_ADULT = 4

CATEGORY_NAMES = {
    CATEGORY_LIFE: "生活照片",
    CATEGORY_SAMPLE: "拍摄样片",
    CATEGORY_PHOTOGRAPHY: "摄影照片",
    CATEGORY_ADULT: "色情照片",
}

_OPENAI_CLIENT = None


def get_openai_client():
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        from openai import OpenAI
        s = get_settings()
        _OPENAI_CLIENT = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
    return _OPENAI_CLIENT


def is_configured():
    return get_settings().is_configured()


def save_config(source_drive, data_dir, api_key, base_url="https://api.deepseek.com", model="deepseek-chat"):
    global _OPENAI_CLIENT

    set_key(ENV_FILE, "SOURCE_DRIVE", source_drive)
    set_key(ENV_FILE, "PHOTO_DATA_DIR", data_dir)
    set_key(ENV_FILE, "DEEPSEEK_API_KEY", api_key)
    set_key(ENV_FILE, "DEEPSEEK_BASE_URL", base_url)
    set_key(ENV_FILE, "DEEPSEEK_MODEL", model)

    os.environ["SOURCE_DRIVE"] = source_drive
    os.environ["PHOTO_DATA_DIR"] = data_dir
    os.environ["DEEPSEEK_API_KEY"] = api_key
    os.environ["DEEPSEEK_BASE_URL"] = base_url
    os.environ["DEEPSEEK_MODEL"] = model

    global _settings
    _settings = Settings()
    _sync_module_vars_from_settings()
    _OPENAI_CLIENT = None

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def reload_config():
    global _OPENAI_CLIENT, _settings

    load_dotenv(ENV_FILE, override=True)
    _settings = Settings()
    _sync_module_vars_from_settings()
    _OPENAI_CLIENT = None

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)


_sync_module_vars_from_settings()
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)
