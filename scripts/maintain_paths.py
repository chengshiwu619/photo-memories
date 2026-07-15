"""
路径状态维护脚本。

用于分批给旧数据补充 canonical_key / path_status / normalized_path。
- 不覆盖旧 path 字段
- 默认 dry-run，使用 --apply 才写库
- 支持 --limit 分批处理
- 默认仅处理 path_status IS NULL 或 path_status = 'pending' 的记录
- 使用 --recheck-existing 时复查全部记录，用于发现原图已删除但缩略图仍在的旧数据
"""

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db_manager import Database  # noqa: E402
from config import get_settings  # noqa: E402
from services.path_resolver import (  # noqa: E402
    resolve_file_path,
    compute_canonical_key,
    PathStatus,
)
from logger_setup import logger  # noqa: E402


def backfill_paths(dry_run=True, limit=None, verbose=False, recheck_existing=False):
    """分批补充旧数据的路径状态信息。

    Args:
        dry_run: True 时只打印不写库
        limit: 最大处理条数
        verbose: 是否打印详细信息

    Returns:
        dict: 统计信息
    """
    settings = get_settings()
    db = Database(settings.db_path)
    db.init_tables()

    source_dirs = settings.source_dirs

    with db.connect() as conn:
        if recheck_existing:
            rows = conn.execute(
                """SELECT id, file_path FROM files
                   ORDER BY id"""
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, file_path FROM files
                   WHERE path_status IS NULL OR path_status = 'pending'
                   ORDER BY id"""
            ).fetchall()

    total = len(rows)
    if limit and limit < total:
        rows = rows[:limit]
        logger.info(f"待处理 {total} 条记录，限制处理前 {len(rows)} 条")
    else:
        logger.info(f"待处理 {total} 条记录")

    stats = {
        "dry_run": dry_run,
        "recheck_existing": recheck_existing,
        "total_pending": total,
        "processed": 0,
        "ok": 0,
        "damaged_path": 0,
        "missing": 0,
        "stat_failed": 0,
        "outside_root": 0,
        "unsupported_ext": 0,
        "errors": 0,
        "samples": {
            "ok": [],
            "damaged_path": [],
            "missing": [],
            "stat_failed": [],
            "outside_root": [],
        },
    }
    pending_updates = []

    for row in rows:
        file_id = row["id"]
        file_path = row["file_path"]

        result = resolve_file_path(file_path, source_dirs, stat_file=True)
        stats["processed"] += 1

        if result.status == PathStatus.OK:
            stats["ok"] += 1
            if verbose and len(stats["samples"]["ok"]) < 10:
                stats["samples"]["ok"].append(file_path)
        elif result.status == PathStatus.DAMAGED_PATH:
            stats["damaged_path"] += 1
            if len(stats["samples"]["damaged_path"]) < 10:
                stats["samples"]["damaged_path"].append({"path": file_path, "reason": result.reason})
        elif result.status == PathStatus.MISSING:
            stats["missing"] += 1
            if len(stats["samples"]["missing"]) < 10:
                stats["samples"]["missing"].append({"path": file_path, "reason": result.reason})
        elif result.status == PathStatus.STAT_FAILED:
            stats["stat_failed"] += 1
            if len(stats["samples"]["stat_failed"]) < 10:
                stats["samples"]["stat_failed"].append({"path": file_path, "reason": result.reason})
        elif result.status == PathStatus.OUTSIDE_ROOT:
            stats["outside_root"] += 1
            if len(stats["samples"]["outside_root"]) < 10:
                stats["samples"]["outside_root"].append({"path": file_path, "reason": result.reason})
        elif result.status == PathStatus.UNSUPPORTED_EXT:
            stats["unsupported_ext"] += 1
        else:
            stats["errors"] += 1

        if not dry_run:
            pending_updates.append((
                result.canonical_key,
                result.normalized_path if result.status == PathStatus.OK else None,
                result.status.value,
                result.reason or None,
                file_id,
            ))

        # 每 10 条 flush 一次
        if not dry_run and len(pending_updates) >= 10:
            _flush_updates(db, pending_updates)
            pending_updates = []

        if stats["processed"] % 100 == 0:
            logger.info(f"  已处理 {stats['processed']}/{len(rows)}")

    if not dry_run and pending_updates:
        _flush_updates(db, pending_updates)

    logger.info(f"路径状态维护完成: {stats}")
    return stats


def _flush_updates(db, pending_updates):
    with db.connect() as conn:
        conn.executemany(
            """UPDATE files
               SET canonical_key = ?, normalized_path = ?, path_status = ?, path_error = ?
               WHERE id = ?""",
            pending_updates,
        )


def format_backfill_text(stats):
    lines = [
        "Path Backfill Report",
        f"dry_run: {stats['dry_run']}",
        f"total_pending: {stats['total_pending']}",
        f"processed: {stats['processed']}",
        f"ok: {stats['ok']}",
        f"damaged_path: {stats['damaged_path']}",
        f"missing: {stats['missing']}",
        f"stat_failed: {stats['stat_failed']}",
        f"outside_root: {stats['outside_root']}",
        f"unsupported_ext: {stats['unsupported_ext']}",
        f"errors: {stats['errors']}",
    ]
    for key in ["ok", "damaged_path", "missing", "stat_failed", "outside_root"]:
        samples = stats.get("samples", {}).get(key, [])
        if not samples:
            continue
        lines.append(f"{key}_samples:")
        for s in samples[:5]:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="补充旧数据的路径状态信息（canonical_key / path_status / normalized_path）"
    )
    parser.add_argument("--backfill-paths", action="store_true", default=True,
                        help="执行路径状态补充")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库（默认 dry-run）")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="仅分析不写入（默认）")
    parser.add_argument("--limit", type=int, help="最多处理 N 条记录")
    parser.add_argument("--verbose", action="store_true", help="打印详细信息")
    parser.add_argument("--recheck-existing", action="store_true",
                        help="复查所有 files 记录，包括已标记 ok 的记录；用于发现原图已删除但缩略图仍在的旧数据")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="以 JSON 格式输出")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # --apply 覆盖 --dry-run
    dry_run = not args.apply

    stats = backfill_paths(
        dry_run=dry_run,
        limit=args.limit,
        verbose=args.verbose,
        recheck_existing=args.recheck_existing,
    )

    if args.json_output:
        # 清理不可序列化的对象
        clean_stats = {k: v for k, v in stats.items() if k != "samples"}
        clean_stats["samples"] = {k: [str(s) for s in v] for k, v in stats.get("samples", {}).items()}
        print(json.dumps(clean_stats, ensure_ascii=False, indent=2))
    else:
        print(format_backfill_text(stats))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
