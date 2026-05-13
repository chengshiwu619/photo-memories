import os
import sqlite3
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
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            file_size INTEGER,
            file_mtime TEXT,
            file_hash TEXT,
            is_image INTEGER DEFAULT 1,
            scanned_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_path);
        CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash);

        CREATE TABLE IF NOT EXISTS folder_categories (
            folder_path TEXT PRIMARY KEY,
            category INTEGER NOT NULL,
            confidence TEXT,
            classified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS photo_metadata (
            file_id INTEGER PRIMARY KEY,
            date_taken TEXT,
            camera_model TEXT,
            gps_lat REAL,
            gps_lon REAL,
            width INTEGER,
            height INTEGER,
            thumbnail_path TEXT,
            exif_json TEXT,
            indexed_at TEXT,
            is_starred INTEGER DEFAULT 0,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );
        CREATE INDEX IF NOT EXISTS idx_meta_date ON photo_metadata(date_taken);

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category INTEGER NOT NULL,
            memory_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            photo_ids TEXT NOT NULL,
            cover_file_id INTEGER,
            created_at TEXT,
            is_starred INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        CREATE INDEX IF NOT EXISTS idx_memories_starred ON memories(is_starred);

        CREATE TABLE IF NOT EXISTS click_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            folder_path TEXT NOT NULL,
            category INTEGER,
            clicked_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (file_id) REFERENCES files(id)
        );
        CREATE INDEX IF NOT EXISTS idx_click_folder ON click_history(folder_path);
        CREATE INDEX IF NOT EXISTS idx_click_category ON click_history(category);

        CREATE TABLE IF NOT EXISTS photo_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (file_id) REFERENCES files(id),
            UNIQUE(file_id, tag)
        );
        CREATE INDEX IF NOT EXISTS idx_tags_file ON photo_tags(file_id);
    """)
    conn.commit()
    conn.close()
