"""
缩略图链路完整诊断脚本。

运行: python scripts/diag_thumbnail_pipeline.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import get_settings, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from db_manager import Database
from logger_setup import logger

ALL_EXT = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def main():
    s = get_settings()
    db = Database()
    db.init_tables()

    print("=" * 60)
    print("缩略图链路诊断报告")
    print("=" * 60)

    # ---- 配置 ----
    print("\n--- 1. 扫描根目录 ---")
    for i, sd in enumerate(s.source_dirs):
        exists = os.path.isdir(sd)
        print(f"  source_dirs[{i}]: {sd}")
        print(f"  exists: {exists}")
        if exists:
            try:
                items = os.listdir(sd)
                print(f"  readable: True, top-level items: {len(items)}")
                samples = [os.path.join(sd, x) for x in items[:5] if not x.startswith('.')]
                print(f"  sample paths: {samples}")
            except Exception as e:
                print(f"  readable: False, error: {e}")

    # ---- Everything ----
    print("\n--- 2. Everything 状态 ---")
    from business.scanner.fast_scan import es_available, _get_es_path, _detect_instance
    es_exe = _get_es_path()
    print(f"  es.exe path: {es_exe}")
    print(f"  es_available(): {es_available()}")
    inst = _detect_instance()
    print(f"  detected instance: {inst!r}")

    # ---- DB 状态 ----
    print("\n--- 3. DB 状态 ---")
    print(f"  db_path: {s.db_path}")
    print(f"  db_exists: {os.path.isfile(s.db_path)}")
    if os.path.isfile(s.db_path):
        size_mb = os.path.getsize(s.db_path) / (1024 * 1024)
        print(f"  db_size: {size_mb:.1f} MB")

    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        imgs = conn.execute("SELECT COUNT(*) FROM files WHERE is_image = 1").fetchone()[0]
        vids = conn.execute("SELECT COUNT(*) FROM files WHERE is_image = 0").fetchone()[0]
        print(f"  files.total: {total}")
        print(f"  files.is_image=1: {imgs}")
        print(f"  files.is_image=0: {vids}")

        meta_total = conn.execute("SELECT COUNT(*) FROM photo_metadata").fetchone()[0]
        thumb_ok = conn.execute(
            "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NOT NULL AND thumbnail_path != '' AND thumbnail_path != '__FAILED__'"
        ).fetchone()[0]
        thumb_empty = conn.execute(
            "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NULL OR thumbnail_path = ''"
        ).fetchone()[0]
        thumb_failed = conn.execute(
            "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path = '__FAILED__'"
        ).fetchone()[0]
        print(f"  photo_metadata.total: {meta_total}")
        print(f"  photo_metadata.thumb_ok: {thumb_ok}")
        print(f"  photo_metadata.thumb_empty: {thumb_empty}")
        print(f"  photo_metadata.thumb_failed: {thumb_failed}")

        # thumbnail pending (无 photo_metadata 或 无缩略图)
        pending = conn.execute("""
            SELECT COUNT(*) FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.is_image = 1
              AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL OR pm.thumbnail_path = '' OR pm.thumbnail_path = '__FAILED__')
        """).fetchone()[0]
        print(f"  thumbnail_pending (broad): {pending}")

        # path_status 分布
        path_stats = conn.execute(
            "SELECT path_status, COUNT(*) FROM files GROUP BY path_status"
        ).fetchall()
        print(f"  path_status distribution: {[(r[0], r[1]) for r in path_stats]}")

        # 随机抽样 20 条
        samples = conn.execute(
            "SELECT id, file_path, file_name FROM files WHERE is_image=1 ORDER BY RANDOM() LIMIT 20"
        ).fetchall()
        print(f"  sample files (20):")
        for r in samples[:5]:
            fp = r["file_path"]
            exists = os.path.exists(fp) if fp else False
            print(f"    id={r['id']} path={fp[:100]} exists={exists}")

        # 缩略图缓存目录
        print(f"\n--- 4. 缩略图缓存 ---")
        thumb_dir = s.thumbnail_dir
        print(f"  thumbnail_dir: {thumb_dir}")
        print(f"  exists: {os.path.isdir(thumb_dir)}")
        if os.path.isdir(thumb_dir):
            files = os.listdir(thumb_dir)
            print(f"  file count: {len(files)}")
            jpg_count = sum(1 for f in files if f.endswith('.jpg'))
            print(f"  .jpg files: {jpg_count}")
            samples = [f for f in files if f.endswith('.jpg')][:5]
            print(f"  sample .jpg: {samples}")

    # ---- pending 查询逻辑检查 ----
    print("\n--- 5. pending 查询条件 ---")
    from business.indexer.photo_indexer import get_unindexed_photos
    unindexed = get_unindexed_photos(force_retry=False)
    unindexed_force = get_unindexed_photos(force_retry=True)
    print(f"  get_unindexed_photos(): {len(unindexed)}")
    print(f"  get_unindexed_photos(force_retry=True): {len(unindexed_force)}")

    # ---- AI 门控状态 ----
    print("\n--- 6. AI 门控状态 ---")
    pending_count = conn.execute("""
        SELECT COUNT(*) FROM files f
        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE f.is_image = 1
          AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL OR pm.thumbnail_path = '' OR pm.thumbnail_path = '__FAILED__')
    """).fetchone()[0]
    print(f"  thumbnail pending: {pending_count}")
    print(f"  THUMBNAIL_P0_THRESHOLD: 0")
    print(f"  AI tasks deferred: {pending_count > 0}")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
