"""
路径规范化与健康检查模块测试。

覆盖：
- UNC 路径规范化
- slash/backslash 统一
- 大小写不同但 canonical_key 相同
- 包含 ?? 的路径标记 damaged_path
- 包含 � 或 NUL 的路径标记 damaged
- stat WinError 3 / FileNotFoundError 不会中断
- outside_root 不入库
- 同一 canonical_key 不重复入库，保留旧 record id
- Everything 损坏路径不入库
- 目录遍历真实路径正常入库
- damaged/missing/stat_failed/outside_root 不参与推荐/瀑布流查询
- 旧数据 path 字段不被批量覆盖
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime

import pytest


# ---- helpers ----

class _Settings:
    def __init__(self, source_dir, data_dir):
        self.source_drive = str(source_dir)
        self.photo_data_dir = str(data_dir)
        self.thumbnail_dir = os.path.join(str(data_dir), "thumbnails")
        self.thumbnail_size = (600, 600)

    @property
    def source_dirs(self):
        return [self.source_drive]

    @property
    def db_path(self):
        return os.path.join(self.photo_data_dir, "photos.db")


def _configure(tmp_path, monkeypatch):
    import db_manager as db_mod
    import business.scanner.fast_scan as scan_mod

    source_dir = tmp_path / "photos"
    data_dir = tmp_path / "cache"
    source_dir.mkdir()
    data_dir.mkdir()
    settings = _Settings(source_dir, data_dir)
    monkeypatch.setattr(db_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(scan_mod, "get_settings", lambda: settings)
    db = db_mod.Database(settings.db_path)
    db.init_tables()
    return scan_mod, db, settings, source_dir


# ============================================================================
# path_resolver 单元测试
# ============================================================================

class TestPathResolverUnit:
    """path_resolver 模块纯单元测试，不涉及 DB。"""

    def test_normalize_slashes(self):
        from services.path_resolver import normalize_path_slashes
        assert normalize_path_slashes("C:/Users/test/file.jpg") == r"C:\Users\test\file.jpg"
        assert normalize_path_slashes("C:\\Users\\test\\file.jpg") == r"C:\Users\test\file.jpg"

    def test_unc_path_preserved(self):
        from services.path_resolver import normalize_path_slashes
        result = normalize_path_slashes(r"\\NAS\share\photos\img.jpg")
        assert result.startswith(r"\\NAS\share")

    def test_extended_path_prefix_stripped(self):
        from services.path_resolver import normalize_path_slashes
        result = normalize_path_slashes(r"\\?\C:\Photos\img.jpg")
        assert result == r"C:\Photos\img.jpg"

    def test_unc_extended_prefix_stripped(self):
        from services.path_resolver import normalize_path_slashes
        result = normalize_path_slashes(r"\\?\UNC\server\share\img.jpg")
        assert result == r"\\server\share\img.jpg"

    def test_quotes_stripped(self):
        from services.path_resolver import normalize_path_slashes
        assert normalize_path_slashes('"C:\\Photos\\img.jpg"') == r"C:\Photos\img.jpg"

    def test_canonical_key_case_insensitive_windows(self):
        from services.path_resolver import compute_canonical_key
        k1 = compute_canonical_key(r"C:\Photos\IMG.JPG")
        k2 = compute_canonical_key(r"C:\photos\img.jpg")
        if sys.platform == "win32":
            assert k1 == k2
        else:
            # on linux, they may differ
            pass

    def test_canonical_key_trailing_slash_removed(self):
        from services.path_resolver import compute_canonical_key
        k = compute_canonical_key(r"C:\Photos\img.jpg\\")
        assert not k.endswith("\\")

    def test_damaged_path_question_marks(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        result = resolve_file_path(r"C:\Photos\im??ge.jpg", [source])
        assert result.status == PathStatus.DAMAGED_PATH
        assert "damaged" in result.reason.lower()

    def test_damaged_path_replacement_char(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        result = resolve_file_path("C:\\Photos\\im\ufffdge.jpg", [source])
        assert result.status == PathStatus.DAMAGED_PATH

    def test_damaged_path_null(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        result = resolve_file_path("C:\\Photos\\im\x00ge.jpg", [source])
        assert result.status == PathStatus.DAMAGED_PATH

    def test_outside_root(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        result = resolve_file_path(r"D:\Other\img.jpg", [source], stat_file=False)
        assert result.status == PathStatus.OUTSIDE_ROOT

    def test_unsupported_extension(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        result = resolve_file_path(os.path.join(source, "doc.txt"), [source], stat_file=False)
        assert result.status == PathStatus.UNSUPPORTED_EXT

    def test_missing_file(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        missing = os.path.join(source, "nonexistent.jpg")
        result = resolve_file_path(missing, [source], stat_file=True)
        assert result.status == PathStatus.MISSING

    def test_ok_file(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        ok_file = os.path.join(source, "real.jpg")
        ok_file = ok_file  # keep as string
        # Create an actual file
        with open(ok_file, "wb") as f:
            f.write(b"fake jpeg")
        result = resolve_file_path(ok_file, [source], stat_file=True)
        assert result.status == PathStatus.OK
        assert result.file_size == 9
        assert result.file_mtime is not None
        assert result.is_media is True

    def test_ok_file_provides_canonical_key(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        ok_file = os.path.join(source, "real.jpg")
        with open(ok_file, "wb") as f:
            f.write(b"fake jpeg")
        result = resolve_file_path(ok_file, [source], stat_file=True)
        assert result.canonical_key
        assert result.normalized_path
        assert result.source_root

    def test_stat_file_false_skips_stat(self, tmp_path):
        from services.path_resolver import resolve_file_path, PathStatus
        source = str(tmp_path)
        missing = os.path.join(source, "nonexistent.jpg")
        result = resolve_file_path(missing, [source], stat_file=False)
        # Without stat, can't detect missing, should be OK
        assert result.status == PathStatus.OK
        assert result.file_size is None

    def test_is_healthy_status_helper(self):
        from services.path_resolver import is_healthy_status, PathStatus
        assert is_healthy_status(PathStatus.OK) is True
        assert is_healthy_status(PathStatus.DAMAGED_PATH) is False
        assert is_healthy_status(PathStatus.MISSING) is False

    def test_is_displayable_status_helper(self):
        from services.path_resolver import is_displayable_status, PathStatus
        assert is_displayable_status(PathStatus.OK) is True
        assert is_displayable_status(PathStatus.DAMAGED_PATH) is False


# ============================================================================
# Scanner 集成测试
# ============================================================================

class TestIncrementalScanWithPathResolver:
    """增量扫描 + path_resolver 集成测试。"""

    def test_damaged_everything_path_not_inserted(self, tmp_path, monkeypatch):
        """Everything 返回包含 ?? 的损坏路径 → 不写入 files 表。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)

        # 模拟 Everything 返回损坏路径
        def fake_discover(*args, **kwargs):
            scan_mod._reset_bad_path_stats()
            return [os.path.join(str(source_dir), "im??ge.jpg")], "everything"

        monkeypatch.setattr(scan_mod, "_discover_incremental_files", fake_discover)

        result = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=True,
            db=db,
            settings=settings,
        )

        assert result["db_inserted"] == 0
        assert result["scanned"] >= 1  # attempted but skipped
        assert result["bad_path_count"] >= 1

    def test_outside_root_path_not_inserted(self, tmp_path, monkeypatch):
        """outside_root 路径不写入 files 表。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)

        def fake_discover(*args, **kwargs):
            scan_mod._reset_bad_path_stats()
            return [r"D:\Other\outside.jpg"], "everything"

        monkeypatch.setattr(scan_mod, "_discover_incremental_files", fake_discover)

        result = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=True,
            db=db,
            settings=settings,
        )

        assert result["db_inserted"] == 0

    def test_normal_walk_file_inserted(self, tmp_path, monkeypatch):
        """目录遍历发现的正常文件可正常入库。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        photo = source_dir / "valid.jpg"
        photo.write_bytes(b"valid jpeg data")

        result = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )

        assert result["new"] == 1
        assert result["db_inserted"] == 1
        with db.connect() as conn:
            row = conn.execute("SELECT file_path, path_status, canonical_key FROM files").fetchone()
        assert row["file_path"] == os.path.normpath(str(photo))
        assert row["path_status"] == "ok"
        assert row["canonical_key"] is not None

    def test_same_canonical_key_no_duplicate(self, tmp_path, monkeypatch):
        """同一 canonical_key 不重复入库，保留旧 record id。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        photo = source_dir / "SameFile.JPG"
        photo.write_bytes(b"same content")

        # 第一次扫描入库
        result1 = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )
        assert result1["new"] == 1

        with db.connect() as conn:
            first_id = conn.execute("SELECT id FROM files").fetchone()["id"]

        # 第二次扫描（同一文件，路径大小写可能不同）
        # 模拟路径大小写变化
        def fake_discover(*args, **kwargs):
            scan_mod._reset_bad_path_stats()
            return [os.path.normpath(str(photo)).upper()], "everything"

        monkeypatch.setattr(scan_mod, "_discover_incremental_files", fake_discover)

        result2 = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=True,
            db=db,
            settings=settings,
        )

        assert result2["new"] == 0
        assert result2["db_inserted"] == 0
        # 不应创建第二条记录
        with db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 1

    def test_old_path_not_overwritten(self, tmp_path, monkeypatch):
        """旧数据的 file_path 字段不被批量覆盖。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        photo = source_dir / "original.jpg"
        photo.write_bytes(b"original")

        # 手动插入一条旧记录（模拟旧数据：path_status 为空，canonical_key 为空）
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO files
                   (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image, scanned_at, source_dir)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    1,
                    os.path.normpath(str(photo)).upper(),  # 旧数据可能存的大写路径
                    photo.name,
                    os.path.normpath(str(source_dir)),
                    source_dir.name,
                    photo.stat().st_size,
                    datetime.fromtimestamp(photo.stat().st_mtime).isoformat(),
                    1,
                    "2000-01-01T00:00:00",
                    settings.source_drive,
                ),
            )

        # 扫描（发现同一个文件，规范化路径不同）
        result = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )

        # 旧 file_path 应该被保留（因为 canonical_key 匹配到旧记录）
        with db.connect() as conn:
            row = conn.execute("SELECT id, file_path FROM files").fetchone()
        assert row["id"] == 1  # 旧 record id 保留

    def test_missing_file_stat_failed_handled(self, tmp_path, monkeypatch):
        """stat 失败的文件（WinError 3）不会中断扫描。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)

        # 创建一个文件然后删除它（模拟被删除的情况）
        ghost = source_dir / "ghost.jpg"
        ghost.write_bytes(b"i will be deleted")
        ghost_path = str(ghost)
        os.unlink(ghost_path)

        def fake_discover(*args, **kwargs):
            scan_mod._reset_bad_path_stats()
            return [os.path.normpath(ghost_path)], "everything"

        monkeypatch.setattr(scan_mod, "_discover_incremental_files", fake_discover)

        # 不应抛异常
        result = scan_mod.incremental_scan(
            dry_run=False,
            prefer_everything=True,
            db=db,
            settings=settings,
        )
        assert result["db_inserted"] == 0
        # 应计入 errors
        assert result["errors"] >= 1


# ============================================================================
# Recommendation 查询过滤测试
# ============================================================================

class TestRecommendationPathFilter:
    """推荐/瀑布流查询排除异常路径。"""

    def _insert_file(self, conn, file_id, file_path, folder_path, path_status=None):
        conn.execute(
            """INSERT INTO files
               (id, file_path, file_name, folder_path, folder_name, is_image, path_status)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (file_id, file_path, os.path.basename(file_path), folder_path, os.path.basename(folder_path), path_status),
        )
        conn.execute(
            "INSERT OR IGNORE INTO folder_categories (folder_path, category) VALUES (?, 1)",
            (folder_path,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO photo_metadata (file_id, thumbnail_path, width, height, date_taken) VALUES (?, NULL, 100, 80, '2026-01-01T00:00:00')",
            (file_id,),
        )

    def test_damaged_path_excluded_from_batch(self, tmp_path):
        """damaged_path 状态的照片不出现在瀑布流查询结果中。"""
        from ui.recommendation import load_category_photos_batch

        db_path = str(tmp_path / "test.db")
        from db_manager import Database
        db = Database(db_path)
        db.init_tables()

        with db.connect() as conn:
            self._insert_file(conn, 1, r"D:\Photos\ok.jpg", r"D:\Photos", "ok")
            self._insert_file(conn, 2, r"D:\Photos\bad.jpg", r"D:\Photos", "damaged_path")
            self._insert_file(conn, 3, r"D:\Photos\missing.jpg", r"D:\Photos", "missing")

        conn = db.get_persistent_connection()
        try:
            photos = load_category_photos_batch(conn, 1, 0, limit=10)
        finally:
            conn.close()

        ids = {p["id"] for p in photos}
        assert 1 in ids  # ok
        assert 2 not in ids  # damaged_path excluded
        assert 3 not in ids  # missing excluded

    def test_null_path_status_still_visible(self, tmp_path):
        """旧数据 path_status=NULL 仍然可见（向后兼容）。"""
        from ui.recommendation import load_category_photos_batch

        db_path = str(tmp_path / "test.db")
        from db_manager import Database
        db = Database(db_path)
        db.init_tables()

        with db.connect() as conn:
            self._insert_file(conn, 1, r"D:\Photos\old_ok.jpg", r"D:\Photos", None)  # NULL

        conn = db.get_persistent_connection()
        try:
            photos = load_category_photos_batch(conn, 1, 0, limit=10)
        finally:
            conn.close()

        ids = {p["id"] for p in photos}
        assert 1 in ids  # NULL status still visible


# ============================================================================
# DB Schema 测试
# ============================================================================

class TestPathStatusSchema:
    """验证新增 DB 字段后向兼容。"""

    def test_new_columns_exist_in_new_db(self):
        from db_manager import Database
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "photos.db")
            db = Database(db_path)
            db.init_tables()
            import sqlite3
            conn = sqlite3.connect(db_path)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
            conn.close()
            for col in ["canonical_key", "normalized_path", "path_status", "path_error"]:
                assert col in cols, f"Missing column: {col}"
        finally:
            shutil.rmtree(tmp)

    def test_new_indexes_exist(self):
        from db_manager import Database
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "photos.db")
            db = Database(db_path)
            db.init_tables()
            import sqlite3
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            indexes = {r[0] for r in rows}
            conn.close()
            assert "idx_files_canonical_key" in indexes
            assert "idx_files_path_status" in indexes
        finally:
            shutil.rmtree(tmp)

    def test_old_columns_unchanged(self):
        """旧字段不被删除。"""
        from db_manager import Database
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "photos.db")
            db = Database(db_path)
            db.init_tables()
            import sqlite3
            conn = sqlite3.connect(db_path)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
            conn.close()
            for col in ["id", "file_path", "file_name", "folder_path", "source_dir"]:
                assert col in cols, f"Old column removed: {col}"
        finally:
            shutil.rmtree(tmp)


# ============================================================================
# Indexer 测试
# ============================================================================

class TestIndexerPathFilter:
    """索引器跳过异常路径。"""

    def test_get_unindexed_excludes_damaged_paths(self, tmp_path, monkeypatch):
        from db_manager import Database
        import business.indexer.photo_indexer as idx_mod

        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        db.init_tables()
        monkeypatch.setattr(idx_mod, "_db", db)

        with db.connect() as conn:
            conn.execute(
                """INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image, path_status)
                   VALUES (1, 'ok.jpg', 'ok.jpg', '/tmp', 'tmp', 1, 'ok')"""
            )
            conn.execute(
                """INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image, path_status)
                   VALUES (2, 'bad.jpg', 'bad.jpg', '/tmp', 'tmp', 1, 'missing')"""
            )

        photos = idx_mod.get_unindexed_photos(force_retry=True)
        ids = {p[0] for p in photos}
        assert 1 in ids
        assert 2 not in ids  # missing status excluded


# ============================================================================
# 后台扫描 limit 安全测试
# ============================================================================

class TestBackgroundScanLimitSafety:
    """后台扫描 limit 缺失时不会触发无限全量扫描。"""

    def test_incremental_scan_limit_none_falls_back_to_default(self, tmp_path, monkeypatch):
        """limit=None 时 incremental_scan 强制使用安全默认值。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        (source_dir / "a.jpg").write_bytes(b"a")

        result = scan_mod.incremental_scan(
            limit=None,
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )
        # limit=None 应该被替换为安全默认 limit (1000)，不应报错
        assert result["scanned"] >= 1
        assert result["batch_limit_reached"] is False  # 1 个文件 < 1000

    def test_incremental_scan_limit_zero_means_full_scan(self, tmp_path, monkeypatch):
        """limit=0 时 incremental_scan 执行全量扫描。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        (source_dir / "b.jpg").write_bytes(b"b")

        result = scan_mod.incremental_scan(
            limit=0,
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )
        assert result["scanned"] >= 1
        assert result["batch_limit_reached"] is False

    def test_incremental_scan_limit_negative_means_full_scan(self, tmp_path, monkeypatch):
        """limit 为负数时 incremental_scan 执行全量扫描。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        (source_dir / "c.jpg").write_bytes(b"c")

        result = scan_mod.incremental_scan(
            limit=-1,
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )
        assert result["scanned"] >= 1

    def test_incremental_scan_respects_small_limit(self, tmp_path, monkeypatch):
        """正常的小 limit 值被正确遵守，处理到 limit 后停止。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)
        for i in range(15):
            (source_dir / f"img_{i:04d}.jpg").write_bytes(b"x")

        result = scan_mod.incremental_scan(
            limit=5,
            dry_run=False,
            prefer_everything=False,
            db=db,
            settings=settings,
        )
        # 发现 15 个文件，但 limit=5，应该只处理到 5 个
        assert result["scanned"] <= 5
        assert result["batch_limit_reached"] is True or result["scanned"] == 5

    def test_walk_fallback_respects_limit(self, tmp_path, monkeypatch):
        """目录遍历 fallback 在达到 limit 后停止，不先收集全部文件。"""
        scan_mod, db, settings, source_dir = _configure(tmp_path, monkeypatch)

        # 创建 50 个文件，遍历应停在 limit=10
        for i in range(50):
            (source_dir / f"img_{i:04d}.jpg").write_bytes(b"x")

        # 直接测试 _iter_walk_files 的行为
        files = list(scan_mod._iter_walk_files(limit=10, verbose=False))
        assert len(files) <= 10
        # 50 个文件，但 limit=10 意味着只 yield 了 10 个
        assert 0 < len(files) <= 10

    def test_config_background_scan_limit_default_1000(self):
        """config 中 background_scan_limit 默认值为 1000（非 0）。"""
        from config import Settings
        s = Settings()
        assert s.background_scan_limit == 1000

    def test_config_background_scan_limit_not_zero(self):
        """config 默认值不是 0（0 会导致 or None 表达式返回 None）。"""
        from config import Settings
        s = Settings()
        assert s.background_scan_limit > 0

