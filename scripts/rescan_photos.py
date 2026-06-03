import argparse
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from business.indexer.photo_indexer import index_photos  # noqa: E402
from business.scanner.fast_scan import incremental_scan  # noqa: E402
from scripts.maintain_paths import backfill_paths  # noqa: E402


def print_db_stats():
    """打印 DB 统计信息。"""
    from db_manager import Database
    from config import get_settings
    s = get_settings()
    db = Database()
    db.init_tables()
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        imgs = conn.execute("SELECT COUNT(*) FROM files WHERE is_image=1").fetchone()[0]
        meta = conn.execute("SELECT COUNT(*) FROM photo_metadata").fetchone()[0]
        thumb_ok = conn.execute(
            "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NOT NULL AND thumbnail_path!='' AND thumbnail_path!='__FAILED__'"
        ).fetchone()[0]
        thumb_fail = conn.execute(
            "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path='__FAILED__'"
        ).fetchone()[0]
        pending_sql = """
            SELECT COUNT(*) FROM files f LEFT JOIN photo_metadata pm ON f.id=pm.file_id
            WHERE f.is_image=1 AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL OR pm.thumbnail_path='' OR pm.thumbnail_path='__FAILED__')
        """
        pending = conn.execute(pending_sql).fetchone()[0]
        path_stats = conn.execute("SELECT path_status, COUNT(*) FROM files GROUP BY path_status").fetchall()

    print("DB Statistics")
    print(f"  db_path: {s.db_path}")
    print(f"  scan_root: {s.source_drive}")
    print(f"  files.total: {total}")
    print(f"  files.images: {imgs}")
    print(f"  photo_metadata.total: {meta}")
    print(f"  thumbnails.ok: {thumb_ok}")
    print(f"  thumbnails.failed: {thumb_fail}")
    print(f"  thumbnail_pending: {pending}")
    print(f"  thumbnail_dir: {s.thumbnail_dir}")
    print(f"  path_status: {[(r[0], r[1]) for r in path_stats]}")


def format_scan_text(result):
    lines = [
        "Incremental Photo Scan Report",
        f"dry_run: {result['dry_run']}",
        f"discovery_source: {result['discovery_source']}",
        f"scanned: {result['scanned']}",
        f"new: {result['new']}",
        f"existing: {result['existing']}",
        f"changed: {result['changed']}",
        f"skipped: {result['skipped']}",
        f"errors: {result['errors']}",
        f"db_inserted: {result['db_inserted']}",
        f"db_updated: {result['db_updated']}",
        f"thumbnail_pending: {result['thumbnail_pending']}",
        f"tag_pending: {result['tag_pending']}",
        f"batch_limit_reached: {result['batch_limit_reached']}",
    ]
    samples = result.get("samples") or {}
    for key in ["new", "changed", "skipped", "errors"]:
        values = samples.get(key) or []
        if not values:
            continue
        lines.append(f"{key}_samples:")
        for value in values:
            lines.append(f"- {value}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Safely rescan configured photo roots for new or changed files.")
    parser.add_argument("--scan", action="store_true", help="Run incremental scan (same as default).")
    parser.add_argument("--limit", type=int, help="Only process the first N discovered files.")
    parser.add_argument("--apply", action="store_true", help="Write new/changed file rows. Omit for dry-run.")
    parser.add_argument("--verbose", action="store_true", help="Log skip reasons and include skip samples.")
    parser.add_argument("--no-everything", action="store_true", help="Skip Everything and scan directories directly.")
    parser.add_argument("--index", action="store_true", help="After --apply, run thumbnail indexing for pending photos.")
    parser.add_argument("--index-limit", type=int, help="Limit thumbnail indexing after apply.")
    parser.add_argument("--retry-failed", action="store_true", help="With --index, retry previously failed/skipped thumbnails.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print structured JSON output.")
    parser.add_argument("--backfill-paths", action="store_true", help="Backfill canonical_key/path_status for existing records (dry-run unless --apply).")
    parser.add_argument("--stats", action="store_true", help="Print DB statistics only (no scan/index).")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # --stats: 只打印 DB 统计
    if args.stats:
        print_db_stats()
        return 0

    # 如果指定了 --backfill-paths，执行路径状态补充（独立于扫描）
    if args.backfill_paths:
        result = backfill_paths(
            dry_run=not args.apply,
            limit=args.limit,
            verbose=args.verbose,
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            from scripts.maintain_paths import format_backfill_text
            print(format_backfill_text(result))
        return 0

    result = incremental_scan(
        limit=args.limit,
        dry_run=not args.apply,
        verbose=args.verbose,
        prefer_everything=not args.no_everything,
    )
    if args.apply and args.index:
        result["index_result"] = index_photos(batch_limit=args.index_limit, force_retry=args.retry_failed)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_scan_text(result))
        if result.get("index_result"):
            idx = result["index_result"]
            print("Index Result")
            print(f"total: {idx.get('total', 0)}")
            print(f"indexed: {idx.get('indexed', 0)}")
            print(f"paused: {idx.get('paused', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
