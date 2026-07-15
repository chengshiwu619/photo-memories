import os
import sqlite3
import shutil
from datetime import datetime
from contextlib import contextmanager

from logger_setup import logger
from config import get_settings

SCHEMA_VERSION = "0.3"


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or get_settings().db_path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
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

    def _table_exists(self, conn, table_name):
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def _column_exists(self, conn, table_name, column_name):
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return any(row[1] == column_name for row in cursor.fetchall())

    def validate_schema(self) -> tuple[bool, list[str]]:
        """验证数据库 schema 完整性，返回 (是否通过, 错误列表)"""
        errors = []
        try:
            with self.connect() as conn:
                required_tables = [
                    "files", "folder_categories", "photo_metadata", "memories",
                    "click_history", "photo_tags", "photo_tag_status", "sample_keywords", "life_keywords",
                    "photo_shown_history", "face_clusters", "face_embeddings",
                    "events", "memory_reasoning", "migration_log", "task_checkpoints"
                ]

                for table in required_tables:
                    if not self._table_exists(conn, table):
                        errors.append(f"Missing table: {table}")

                if not errors:
                    # 检查文件表必需字段
                    required_file_cols = ["id", "file_path", "file_name", "folder_path", "source_dir"]
                    for col in required_file_cols:
                        if not self._column_exists(conn, "files", col):
                            errors.append(f"Missing column: files.{col}")

                    # 检查 photo_metadata 必需字段
                    required_meta_cols = ["file_id", "date_taken", "phash", "is_duplicate_of"]
                    for col in required_meta_cols:
                        if not self._column_exists(conn, "photo_metadata", col):
                            errors.append(f"Missing column: photo_metadata.{col}")

                    # 检查 memories 必需字段
                    required_mem_cols = ["id", "category", "memory_type", "title", "photo_ids", "dismissed_at", "payload"]
                    for col in required_mem_cols:
                        if not self._column_exists(conn, "memories", col):
                            errors.append(f"Missing column: memories.{col}")

            return len(errors) == 0, errors
        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")
            return False, errors

    def _get_current_version(self, conn):
        if self._table_exists(conn, "migration_log"):
            cursor = conn.execute(
                "SELECT version_to FROM migration_log ORDER BY migrated_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return row[0]

        if not self._table_exists(conn, "files"):
            return None

        return "0.2"

    def _backup_database(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.db_path}.bak.{timestamp}"
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to {backup_path}")
        return backup_path

    def _create_v03_new_tables(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS face_clusters (
                cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT DEFAULT '',
                user_corrected INTEGER DEFAULT 0,
                representative_face INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS face_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                cluster_id INTEGER,
                FOREIGN KEY (file_id) REFERENCES files(id),
                FOREIGN KEY (cluster_id) REFERENCES face_clusters(cluster_id)
            );
            CREATE INDEX IF NOT EXISTS idx_fe_file ON face_embeddings(file_id);
            CREATE INDEX IF NOT EXISTS idx_fe_cluster ON face_embeddings(cluster_id);

            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                gps_cluster TEXT,
                location_name TEXT,
                photo_ids TEXT NOT NULL,
                event_type TEXT DEFAULT 'event'
            );

            CREATE TABLE IF NOT EXISTS memory_reasoning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                reasoning TEXT,
                feedback_type TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            );

            CREATE TABLE IF NOT EXISTS migration_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_from TEXT NOT NULL,
                version_to TEXT NOT NULL,
                migrated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS task_checkpoints (
                task_type TEXT NOT NULL,
                task_key TEXT NOT NULL,
                status_json TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (task_type, task_key)
            );
        """)

    def _create_all_tables(self, conn):
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
                scanned_at TEXT,
                source_dir TEXT,
                canonical_key TEXT,
                normalized_path TEXT,
                path_status TEXT DEFAULT 'pending',
                path_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_path);
            CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash);
            CREATE INDEX IF NOT EXISTS idx_files_source_dir ON files(source_dir);
            CREATE INDEX IF NOT EXISTS idx_files_canonical_key ON files(canonical_key);
            CREATE INDEX IF NOT EXISTS idx_files_path_status ON files(path_status);

            CREATE TABLE IF NOT EXISTS folder_categories (
                folder_path TEXT PRIMARY KEY,
                category INTEGER NOT NULL,
                confidence TEXT,
                classified_at TEXT,
                fingerprint TEXT,
                classifier_version TEXT,
                prompt_version TEXT,
                status TEXT DEFAULT 'ok',
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS photo_metadata (
                file_id INTEGER PRIMARY KEY,
                category INTEGER,
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
                phash TEXT,
                is_duplicate_of INTEGER,
                phash_status TEXT DEFAULT 'ok',
                phash_error TEXT,
                thumbnail_status TEXT DEFAULT 'ok',
                thumbnail_error TEXT,
                source_file_size INTEGER,
                source_file_mtime TEXT,
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE INDEX IF NOT EXISTS idx_meta_date ON photo_metadata(date_taken);
            CREATE INDEX IF NOT EXISTS idx_meta_phash ON photo_metadata(phash);
            CREATE INDEX IF NOT EXISTS idx_meta_duplicate ON photo_metadata(is_duplicate_of);
            CREATE INDEX IF NOT EXISTS idx_meta_category ON photo_metadata(category);

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category INTEGER NOT NULL,
                memory_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                photo_ids TEXT NOT NULL,
                cover_file_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                is_starred INTEGER DEFAULT 0,
                last_shown_at TEXT,
                click_count INTEGER DEFAULT 0,
                dismissed_at TEXT,
                payload TEXT,
                is_hidden INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_memories_starred ON memories(is_starred);
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
            CREATE INDEX IF NOT EXISTS idx_memories_dismissed ON memories(dismissed_at);

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
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (file_id) REFERENCES files(id),
                UNIQUE(file_id, tag, source)
            );
            CREATE INDEX IF NOT EXISTS idx_tags_file ON photo_tags(file_id);
            CREATE INDEX IF NOT EXISTS idx_tags_source ON photo_tags(source);

            CREATE TABLE IF NOT EXISTS photo_tag_status (
                file_id INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'siglip',
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                source_file_size INTEGER,
                source_file_mtime TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (file_id, source),
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tag_status_source_status ON photo_tag_status(source, status);

            CREATE TABLE IF NOT EXISTS sample_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS life_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS photo_shown_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                category INTEGER,
                shown_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE INDEX IF NOT EXISTS idx_shown_file ON photo_shown_history(file_id);
            CREATE INDEX IF NOT EXISTS idx_shown_at ON photo_shown_history(shown_at);
            CREATE INDEX IF NOT EXISTS idx_shown_category_file_at
                ON photo_shown_history(category, file_id, shown_at);
        """)

        self._create_v03_new_tables(conn)

        conn.execute(
            "INSERT INTO migration_log (version_from, version_to) VALUES (?, ?)",
            ("init", SCHEMA_VERSION)
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS thumbnail_params (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

    def _migrate_v02_to_v03(self, conn):
        from config import get_settings

        logger.info("Starting v0.2 -> v0.3 migration...")

        self._backup_database()

        if not self._column_exists(conn, "files", "source_dir"):
            conn.execute("ALTER TABLE files ADD COLUMN source_dir TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_source_dir ON files(source_dir)")
            s = get_settings()
            source_dirs = [p.strip() for p in s.source_drive.split(";") if p.strip()]
            if len(source_dirs) == 1:
                conn.execute("UPDATE files SET source_dir = ? WHERE source_dir IS NULL", (source_dirs[0],))
            logger.info("Added source_dir to files table")

        if not self._column_exists(conn, "photo_metadata", "phash"):
            conn.execute("ALTER TABLE photo_metadata ADD COLUMN phash TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_phash ON photo_metadata(phash)")
        if not self._column_exists(conn, "photo_metadata", "is_duplicate_of"):
            conn.execute("ALTER TABLE photo_metadata ADD COLUMN is_duplicate_of INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_duplicate ON photo_metadata(is_duplicate_of)")

        if not self._column_exists(conn, "memories", "last_shown_at"):
            conn.execute("ALTER TABLE memories ADD COLUMN last_shown_at TEXT")
        if not self._column_exists(conn, "memories", "click_count"):
            conn.execute("ALTER TABLE memories ADD COLUMN click_count INTEGER DEFAULT 0")
        if not self._column_exists(conn, "memories", "dismissed_at"):
            conn.execute("ALTER TABLE memories ADD COLUMN dismissed_at TEXT")
        if not self._column_exists(conn, "memories", "payload"):
            conn.execute("ALTER TABLE memories ADD COLUMN payload TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_dismissed ON memories(dismissed_at)")

        if not self._column_exists(conn, "photo_tags", "source"):
            conn.execute(
                "CREATE TABLE photo_tags_new ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "file_id INTEGER NOT NULL, "
                "tag TEXT NOT NULL, "
                "source TEXT NOT NULL DEFAULT 'manual', "
                "created_at TEXT DEFAULT (datetime('now')), "
                "FOREIGN KEY (file_id) REFERENCES files(id), "
                "UNIQUE(file_id, tag, source))"
            )
            conn.execute(
                "INSERT INTO photo_tags_new (id, file_id, tag, source, created_at) "
                "SELECT id, file_id, tag, 'manual', created_at FROM photo_tags"
            )
            conn.execute("DROP TABLE photo_tags")
            conn.execute("ALTER TABLE photo_tags_new RENAME TO photo_tags")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_file ON photo_tags(file_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_source ON photo_tags(source)")

        self._create_v03_new_tables(conn)

        conn.execute(
            "INSERT INTO migration_log (version_from, version_to) VALUES (?, ?)",
            ("0.2", "0.3")
        )

        logger.info("v0.2 -> v0.3 migration completed")

    def init_tables(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")

        current_version = self._get_current_version(conn)

        if current_version is None:
            self._create_all_tables(conn)
            conn.commit()
        elif current_version == "0.2":
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._migrate_v02_to_v03(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                conn.close()
                raise

        self._ensure_missing_tables(conn)
        self._check_and_clear_thumbnails(conn)

        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

        is_valid, errors = self.validate_schema()
        if not is_valid:
            logger.warning(f"Schema validation issues found: {errors}")
        else:
            logger.info("Schema validation passed")

    def _ensure_missing_tables(self, conn):
        missing = [
            ("photo_shown_history", """
                CREATE TABLE IF NOT EXISTS photo_shown_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    category INTEGER,
                    shown_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id)
                )
            """, [
                "CREATE INDEX IF NOT EXISTS idx_shown_file ON photo_shown_history(file_id)",
                "CREATE INDEX IF NOT EXISTS idx_shown_at ON photo_shown_history(shown_at)",
                "CREATE INDEX IF NOT EXISTS idx_shown_category_file_at ON photo_shown_history(category, file_id, shown_at)",
            ]),
            ("sample_keywords", """
                CREATE TABLE IF NOT EXISTS sample_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """, []),
            ("life_keywords", """
                CREATE TABLE IF NOT EXISTS life_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """, []),
            ("thumbnail_params", """
                CREATE TABLE IF NOT EXISTS thumbnail_params (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """, []),
            ("photo_tag_status", """
                CREATE TABLE IF NOT EXISTS photo_tag_status (
                    file_id INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'siglip',
                    status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT,
                    source_file_size INTEGER,
                    source_file_mtime TEXT,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (file_id, source),
                    FOREIGN KEY (file_id) REFERENCES files(id)
                )
            """, [
                "CREATE INDEX IF NOT EXISTS idx_tag_status_source_status ON photo_tag_status(source, status)",
            ]),
        ]
        for table_name, create_sql, indexes in missing:
            if not self._table_exists(conn, table_name):
                conn.execute(create_sql)
                for idx_sql in indexes:
                    conn.execute(idx_sql)
                logger.info(f"补建缺失表: {table_name}")
        if self._table_exists(conn, "photo_shown_history"):
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_shown_file ON photo_shown_history(file_id)",
                "CREATE INDEX IF NOT EXISTS idx_shown_at ON photo_shown_history(shown_at)",
                "CREATE INDEX IF NOT EXISTS idx_shown_category_file_at ON photo_shown_history(category, file_id, shown_at)",
            ]:
                conn.execute(idx_sql)
        folder_category_columns = [
            ("fingerprint", "TEXT"),
            ("classifier_version", "TEXT"),
            ("prompt_version", "TEXT"),
            ("status", "TEXT DEFAULT 'ok'"),
            ("error", "TEXT"),
        ]
        if self._table_exists(conn, "folder_categories"):
            for col, ddl in folder_category_columns:
                if not self._column_exists(conn, "folder_categories", col):
                    conn.execute(f"ALTER TABLE folder_categories ADD COLUMN {col} {ddl}")
                    logger.info(f"补建缺失字段: folder_categories.{col}")
        photo_metadata_columns = [
            ("category", "INTEGER"),
            ("phash_status", "TEXT DEFAULT 'ok'"),
            ("phash_error", "TEXT"),
            ("thumbnail_status", "TEXT DEFAULT 'ok'"),
            ("thumbnail_error", "TEXT"),
            ("source_file_size", "INTEGER"),
            ("source_file_mtime", "TEXT"),
        ]
        if self._table_exists(conn, "photo_metadata"):
            for col, ddl in photo_metadata_columns:
                if not self._column_exists(conn, "photo_metadata", col):
                    conn.execute(f"ALTER TABLE photo_metadata ADD COLUMN {col} {ddl}")
                    logger.info(f"补建缺失字段: photo_metadata.{col}")
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_category ON photo_metadata(category)")
            except Exception:
                pass
        memories_columns = [
            ("is_hidden", "INTEGER DEFAULT 0"),
        ]
        if self._table_exists(conn, "memories"):
            for col, ddl in memories_columns:
                if not self._column_exists(conn, "memories", col):
                    conn.execute(f"ALTER TABLE memories ADD COLUMN {col} {ddl}")
                    logger.info(f"补建缺失字段: memories.{col}")
        files_columns = [
            ("canonical_key", "TEXT"),
            ("normalized_path", "TEXT"),
            ("path_status", "TEXT DEFAULT 'pending'"),
            ("path_error", "TEXT"),
        ]
        if self._table_exists(conn, "files"):
            for col, ddl in files_columns:
                if not self._column_exists(conn, "files", col):
                    conn.execute(f"ALTER TABLE files ADD COLUMN {col} {ddl}")
                    logger.info(f"补建缺失字段: files.{col}")
            for idx_name, idx_sql in [
                ("idx_files_canonical_key", "CREATE INDEX IF NOT EXISTS idx_files_canonical_key ON files(canonical_key)"),
                ("idx_files_path_status", "CREATE INDEX IF NOT EXISTS idx_files_path_status ON files(path_status)"),
            ]:
                try:
                    conn.execute(idx_sql)
                except Exception:
                    pass
        conn.commit()

    def _check_and_clear_thumbnails(self, conn):
        """Check thumbnail signature drift without deleting cache files on startup."""
        from config import get_settings
        from infra.image.thumbnail_cache import (
            build_thumbnail_cache_signature,
            classify_thumbnail_cache_signature,
        )

        settings = get_settings()
        current_sig = build_thumbnail_cache_signature(settings)

        row = conn.execute("SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'").fetchone()
        if row is None:
            conn.execute("INSERT INTO thumbnail_params (key, value) VALUES (?, ?)", ("thumbnail_sig", current_sig))
            conn.commit()
            return

        stored_sig = row[0]
        signature_status = classify_thumbnail_cache_signature(stored_sig, settings)
        if signature_status == "current":
            return

        rows = conn.execute(
            """
            SELECT thumbnail_path FROM photo_metadata
            WHERE thumbnail_path IS NOT NULL
              AND thumbnail_path != ''
              AND thumbnail_path != '__FAILED__'
            """
        ).fetchall()
        missing_count = 0
        for row in rows:
            thumb_path = row[0]
            if thumb_path and not os.path.exists(thumb_path):
                missing_count += 1

        logger.warning(
            "Thumbnail cache signature is not current on startup: stored=%s current=%s status=%s missing_thumbnail_files=%s. "
            "Startup will not delete cache files or clear photo_metadata.thumbnail_path automatically; use integrity or maintenance tools to review or migrate.",
            stored_sig,
            current_sig,
            signature_status,
            missing_count,
        )


def get_database():
    return Database()
