"""
Memory 维护脚本。

用于处理不可渲染 memory：
- --disable-unrenderable：将完全没有可显示照片引用的 memory 标记为 is_hidden=1
- --rebuild-unrenderable：尝试用同日期/同文件夹照片重建 refs

默认 dry-run，使用 --apply 才写库。
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
from logger_setup import logger  # noqa: E402
from services.startup_integrity import _query_memory_visibility  # noqa: E402

MIN_VISIBLE_REFS = 4  # 与 recommendation 中 MIN_MEMORY_VISIBLE_REFS 一致


def disable_unrenderable_memories(dry_run=True, limit=None, verbose=False):
    """将完全没有可见照片引用的 memory 标记为 is_hidden=1。

    不删除任何记录，不修改 photo_ids。
    """
    settings = get_settings()
    db = Database(settings.db_path)
    db.init_tables()

    with db.connect() as conn:
        visibility_rows = _query_memory_visibility(conn)

    fully_hidden = [row for row in visibility_rows if row["total_refs"] > 0 and row["visible_refs"] == 0]
    total = len(fully_hidden)
    if limit and limit < total:
        fully_hidden = fully_hidden[:limit]
        logger.info(f"完全不可渲染 memory: {total} 个，限制处理前 {len(fully_hidden)} 个")
    else:
        logger.info(f"完全不可渲染 memory: {total} 个")

    stats = {
        "dry_run": dry_run,
        "total_unrenderable": total,
        "processed": 0,
        "hidden": 0,
        "errors": 0,
        "samples": [],
    }

    pending = []
    for row in fully_hidden:
        mid = row["memory_id"]
        stats["processed"] += 1
        stats["samples"].append({
            "memory_id": mid,
            "memory_type": row["memory_type"],
            "cover_file_id": row["cover_file_id"],
            "visible_refs": row["visible_refs"],
            "total_refs": row["total_refs"],
        })
        stats["hidden"] += 1

        if not dry_run:
            pending.append((mid,))

        if not dry_run and len(pending) >= 10:
            _flush_disable(db, pending)
            pending = []

        if verbose and stats["processed"] <= 10:
            logger.info(f"  memory_id={mid} type={row['memory_type']} visible_refs=0")

    if not dry_run and pending:
        _flush_disable(db, pending)

    logger.info(f"Memory disable 完成: {stats}")
    return stats


def _flush_disable(db, pending):
    with db.connect() as conn:
        conn.executemany(
            "UPDATE memories SET is_hidden = 1 WHERE id = ?",
            pending,
        )


def rebuild_unrenderable_memories(dry_run=True, limit=None, verbose=False):
    """尝试用同文件夹/同日期可显示照片重建不可渲染 memory 的 photo_ids。

    策略：
    1. 发现有可见照片的 partially_unrenderable memory，尝试从同文件夹补位
    2. 完全不可渲染的 memory，尝试从原 refs 的文件夹/日期找可显示照片
    3. 补不到足够 refs（< MIN_VISIBLE_REFS）则标记为 hidden
    """
    settings = get_settings()
    db = Database(settings.db_path)
    db.init_tables()

    with db.connect() as conn:
        visibility_rows = _query_memory_visibility(conn)

    fully_hidden = [row for row in visibility_rows if row["total_refs"] > 0 and row["visible_refs"] == 0]
    partially_hidden = [
        row for row in visibility_rows
        if row["total_refs"] > 0 and 0 < row["visible_refs"] < row["total_refs"]
    ]

    stats = {
        "dry_run": dry_run,
        "fully_unrenderable": len(fully_hidden),
        "partially_unrenderable": len(partially_hidden),
        "rebuilt": 0,
        "hidden": 0,
        "skipped": 0,
        "errors": 0,
        "samples": [],
    }

    targets = list(partially_hidden) + list(fully_hidden)
    if limit and len(targets) > limit:
        targets = targets[:limit]

    for row in targets:
        mid = row["memory_id"]
        try:
            result = _try_rebuild_memory(db, mid, row, dry_run, verbose)
            if result == "rebuilt":
                stats["rebuilt"] += 1
            elif result == "hidden":
                stats["hidden"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.warning(f"Rebuild memory {mid} 失败: {e}")

        if len(stats["samples"]) < 10:
            stats["samples"].append({
                "memory_id": mid,
                "memory_type": row["memory_type"],
                "visible_refs": row["visible_refs"],
                "total_refs": row["total_refs"],
            })

    logger.info(f"Memory rebuild 完成: {stats}")
    return stats


def _try_rebuild_memory(db, memory_id, visibility_row, dry_run, verbose):
    """尝试为单个 memory 补位可显示照片。"""
    with db.connect() as conn:
        mem = conn.execute(
            "SELECT id, photo_ids, category FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if not mem:
            return "skipped"

        try:
            photo_ids = json.loads(mem["photo_ids"])
        except Exception:
            return "skipped"

        # 获取原 refs 中照片的文件夹和日期
        if not photo_ids:
            return "skipped"

        placeholders = ",".join("?" * len(photo_ids))
        ref_rows = conn.execute(
            f"""SELECT f.folder_path, pm.date_taken
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.id IN ({placeholders})""",
            photo_ids,
        ).fetchall()

        folders = list({r["folder_path"] for r in ref_rows if r["folder_path"]})
        dates = []
        for r in ref_rows:
            dt = r["date_taken"]
            if dt and len(dt) >= 10:
                dates.append(dt[:10])

        # 从同文件夹/同日期找可显示照片
        cat_id = mem["category"]
        need = MIN_VISIBLE_REFS - visibility_row["visible_refs"]
        if need <= 0:
            return "skipped"

        # 查找可显示照片（有缩略图、非重复、路径正常）
        new_ids = _find_displayable_photos(conn, cat_id, folders, dates, photo_ids, need)
        if not new_ids:
            if visibility_row["visible_refs"] == 0:
                if verbose:
                    logger.info(f"  memory_id={memory_id}: 无可见照片可补，标记 hidden")
                if not dry_run:
                    conn.execute("UPDATE memories SET is_hidden = 1 WHERE id = ?", (memory_id,))
                return "hidden"
            return "skipped"

        # 合并新旧 refs
        existing_visible = _get_visible_ref_ids(conn, photo_ids)
        new_refs = list(set(existing_visible + new_ids))[:20]  # 最多 20 个 refs
        new_photo_ids = json.dumps(new_refs)

        if verbose:
            logger.info(f"  memory_id={memory_id}: visible_refs {visibility_row['visible_refs']}→{len(new_refs)}")

        if not dry_run:
            # 选择新的 cover_file_id
            new_cover = new_refs[0] if new_refs else None
            conn.execute(
                """UPDATE memories
                   SET photo_ids = ?, cover_file_id = COALESCE(?, cover_file_id)
                   WHERE id = ?""",
                (new_photo_ids, new_cover, memory_id),
            )
        return "rebuilt"


def _find_displayable_photos(conn, cat_id, folders, dates, exclude_ids, limit):
    """查找可显示的照片（排除已引用的）。"""
    exclude = set(exclude_ids)
    found = []

    base_sql = """SELECT f.id FROM files f
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE f.is_image = 1
          AND fc.category = ?
          AND pm.thumbnail_path IS NOT NULL
          AND pm.thumbnail_path != '__FAILED__'
          AND pm.thumbnail_path != ''
          AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
          AND (f.path_status IS NULL OR f.path_status NOT IN ('damaged_path','missing','stat_failed','outside_root'))
    """

    # 同文件夹
    for folder in folders[:5]:
        if len(found) >= limit:
            break
        placeholders = ",".join("?" * len(exclude))
        rows = conn.execute(
            base_sql + f" AND f.folder_path = ? AND f.id NOT IN ({placeholders}) ORDER BY pm.date_taken DESC LIMIT ?",
            [cat_id, folder] + list(exclude) + [limit - len(found)],
        ).fetchall()
        for r in rows:
            if r[0] not in exclude:
                found.append(r[0])
                exclude.add(r[0])

    # 同日期
    for day in dates[:5]:
        if len(found) >= limit:
            break
        placeholders = ",".join("?" * len(exclude))
        rows = conn.execute(
            base_sql + f" AND COALESCE(pm.date_taken, f.file_mtime) LIKE ? AND f.id NOT IN ({placeholders}) ORDER BY pm.date_taken DESC LIMIT ?",
            [cat_id, f"{day}%"] + list(exclude) + [limit - len(found)],
        ).fetchall()
        for r in rows:
            if r[0] not in exclude:
                found.append(r[0])
                exclude.add(r[0])

    return found[:limit]


def _get_visible_ref_ids(conn, photo_ids):
    """返回 photo_ids 中当前有可显示缩略图的 ID 列表。"""
    if not photo_ids:
        return []
    placeholders = ",".join("?" * len(photo_ids))
    rows = conn.execute(
        f"""SELECT f.id FROM files f
            JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.id IN ({placeholders})
              AND pm.thumbnail_path IS NOT NULL
              AND pm.thumbnail_path != '__FAILED__'
              AND pm.thumbnail_path != ''
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)""",
        photo_ids,
    ).fetchall()
    return [r[0] for r in rows]


# ---- CLI ----

def format_stats_text(stats):
    lines = [
        "Memory Maintenance Report",
        f"dry_run: {stats.get('dry_run', True)}",
    ]
    for k, v in stats.items():
        if k in ("dry_run", "samples"):
            continue
        lines.append(f"{k}: {v}")
    samples = stats.get("samples", [])
    if samples:
        lines.append("samples:")
        for s in samples[:5]:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="维护不可渲染 memory")
    parser.add_argument("--disable-unrenderable", action="store_true",
                        help="将完全不可渲染 memory 标记为 hidden")
    parser.add_argument("--rebuild-unrenderable", action="store_true",
                        help="尝试重建不可渲染 memory 的照片引用")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库（默认 dry-run）")
    parser.add_argument("--limit", type=int, help="最多处理 N 条记录")
    parser.add_argument("--verbose", action="store_true", help="打印详细信息")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="以 JSON 格式输出")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    dry_run = not args.apply

    if args.rebuild_unrenderable:
        stats = rebuild_unrenderable_memories(
            dry_run=dry_run,
            limit=args.limit,
            verbose=args.verbose,
        )
    elif args.disable_unrenderable:
        stats = disable_unrenderable_memories(
            dry_run=dry_run,
            limit=args.limit,
            verbose=args.verbose,
        )
    else:
        # 默认执行 disable（dry-run）
        logger.info("未指定操作，默认执行 --disable-unrenderable (dry-run)")
        stats = disable_unrenderable_memories(
            dry_run=True,
            limit=args.limit,
            verbose=args.verbose,
        )

    if args.json_output:
        clean = {k: v for k, v in stats.items() if k != "samples"}
        clean["samples"] = [str(s) for s in stats.get("samples", [])]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        print(format_stats_text(stats))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
