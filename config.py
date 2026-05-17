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
    deepseek_classify_model: str = "deepseek-v4-flash"

    source_drive: str = "D:\\测试"
    photo_data_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage")

    thumbnail_size: tuple[int, int] = (400, 400)

    @property
    def source_dirs(self) -> list[str]:
        return [p.strip() for p in self.source_drive.split(";") if p.strip()]

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


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"}
THUMBNAIL_SIZE = (400, 400)
PHASH_THRESHOLD = 8
MEMORY_HIGH_FREQ_DAYS = 3

CATEGORY_LIFE = 1
CATEGORY_SAMPLE = 2

CATEGORY_NAMES = {
    CATEGORY_LIFE: "生活照片",
    CATEGORY_SAMPLE: "拍摄样片",
}

def is_configured():
    if not os.path.isfile(ENV_FILE):
        return False
    return get_settings().is_configured()


def save_config(source_drive, data_dir, api_key, base_url="https://api.deepseek.com", model="deepseek-chat"):
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

    s = get_settings()
    os.makedirs(s.photo_data_dir, exist_ok=True)
    os.makedirs(s.thumbnail_dir, exist_ok=True)

    from infra.llm.client import LLMClient
    LLMClient.reset()


def reload_config():
    global _settings

    load_dotenv(ENV_FILE, override=True)
    _settings = Settings()

    s = get_settings()
    os.makedirs(s.photo_data_dir, exist_ok=True)
    os.makedirs(s.thumbnail_dir, exist_ok=True)

    from infra.llm.client import LLMClient
    LLMClient.reset()


_s = get_settings()
os.makedirs(_s.photo_data_dir, exist_ok=True)
os.makedirs(_s.thumbnail_dir, exist_ok=True)
