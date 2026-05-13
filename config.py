import os
from dotenv import load_dotenv, set_key, find_dotenv

ENV_FILE = find_dotenv() or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

load_dotenv(ENV_FILE)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

SOURCE_DRIVE = os.getenv("SOURCE_DRIVE", "D:\\测试")
DATA_DIR = os.getenv("PHOTO_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage"))
DB_PATH = os.path.join(DATA_DIR, "photos.db")
THUMBNAIL_DIR = os.path.join(DATA_DIR, "thumbnails")
CLASSIFICATION_HISTORY_FILE = os.path.join(DATA_DIR, "classification_history.txt")

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
        _OPENAI_CLIENT = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _OPENAI_CLIENT

def is_configured():
    return bool(DEEPSEEK_API_KEY and SOURCE_DRIVE and DATA_DIR)


def save_config(source_drive, data_dir, api_key, base_url="https://api.deepseek.com", model="deepseek-chat"):
    global SOURCE_DRIVE, DATA_DIR, DB_PATH, THUMBNAIL_DIR, CLASSIFICATION_HISTORY_FILE
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, _OPENAI_CLIENT

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

    SOURCE_DRIVE = source_drive
    DATA_DIR = data_dir
    DB_PATH = os.path.join(DATA_DIR, "photos.db")
    THUMBNAIL_DIR = os.path.join(DATA_DIR, "thumbnails")
    CLASSIFICATION_HISTORY_FILE = os.path.join(DATA_DIR, "classification_history.txt")
    DEEPSEEK_API_KEY = api_key
    DEEPSEEK_BASE_URL = base_url
    DEEPSEEK_MODEL = model
    _OPENAI_CLIENT = None

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def reload_config():
    global SOURCE_DRIVE, DATA_DIR, DB_PATH, THUMBNAIL_DIR, CLASSIFICATION_HISTORY_FILE
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, _OPENAI_CLIENT

    load_dotenv(ENV_FILE, override=True)

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    SOURCE_DRIVE = os.getenv("SOURCE_DRIVE", "D:\\测试")
    DATA_DIR = os.getenv("PHOTO_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage"))
    DB_PATH = os.path.join(DATA_DIR, "photos.db")
    THUMBNAIL_DIR = os.path.join(DATA_DIR, "thumbnails")
    CLASSIFICATION_HISTORY_FILE = os.path.join(DATA_DIR, "classification_history.txt")
    _OPENAI_CLIENT = None

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def init_all_tables():
    from db_manager import Database
    Database().init_tables()
