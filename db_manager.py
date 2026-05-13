import sqlite3
from contextlib import contextmanager

from logger_setup import logger
from config import DB_PATH
from infra.db.repositories.files_repo import FilesRepository
from infra.db.repositories.folder_categories_repo import FolderCategoriesRepository
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from infra.db.repositories.memories_repo import MemoriesRepository
from infra.db.repositories.click_history_repo import ClickHistoryRepository
from infra.db.repositories.photo_tags_repo import PhotoTagsRepository


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH

    @property
    def files(self):
        return FilesRepository(self)

    @property
    def folder_categories(self):
        return FolderCategoriesRepository(self)

    @property
    def photo_metadata(self):
        return PhotoMetadataRepository(self)

    @property
    def memories(self):
        return MemoriesRepository(self)

    @property
    def click_history(self):
        return ClickHistoryRepository(self)

    @property
    def photo_tags(self):
        return PhotoTagsRepository(self)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_persistent_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def init_tables(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
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


def get_database():
    return Database()
