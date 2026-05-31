import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sqlite3
import sys
import threading
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from infra.image.thumbnail_cache import (  # noqa: E402
    THUMBNAIL_JPEG_QUALITY,
    build_thumbnail_cache_signature,
    build_thumbnail_path,
    create_thumbnail_file,
)
from services.startup_integrity import build_startup_integrity_report  # noqa: E402


class _CliSettings:
    def __init__(self, db_path: str):
        photo_data_dir = os.path.dirname(os.path.abspath(db_path))
        self.db_path = os.path.abspath(db_path)
        self.photo_data_dir = photo_data_dir
        self.thumbnail_dir = os.path.join(photo_data_dir, "thumbnails")
        self.thumbnail_size = (600, 600)


def _check_lookup(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {check["check_name"]: check for check in report.get("checks", [])}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_failed_rows(
    conn: sqlite3.Connection,
    settings: Any,
    limit: int,
    file_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    query = """
        SELECT pm.file_id, f.file_path
        FROM photo_metadata pm
        JOIN files f ON f.id = pm.file_id
        WHERE pm.thumbnail_path = '__FAILED__'
    """
    params: List[Any] = []
    if file_ids:
        placeholders = ",".join("?" * len(file_ids))
        query += f" AND pm.file_id IN ({placeholders})"
        params.extend(file_ids)
    query += " ORDER BY pm.file_id"
    rows = conn.execute(query, params).fetchall()
    selected = rows[: max(limit, 0)]
    return [
        {
            "file_id": row["file_id"],
            "file_path": row["file_path"],
            "target_thumbnail_path": build_thumbnail_path(settings.thumbnail_dir, row["file_id"]),
        }
        for row in selected
    ]


def _update_thumbnail_signature(conn: sqlite3.Connection, signature: str) -> int:
    if not _table_exists(conn, "thumbnail_params"):
        return 0
    row = conn.execute(
        "SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO thumbnail_params (key, value) VALUES (?, ?)",
            ("thumbnail_sig", signature),
        )
        return 1
    conn.execute(
        "UPDATE thumbnail_params SET value = ? WHERE key = ?",
        (signature, "thumbnail_sig"),
    )
    return 1


def _make_file_result(
    file_id: int,
    source_path: str,
    target_path: str,
    status: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        "file_id": file_id,
        "source_path": source_path,
        "target_path": target_path,
        "status": status,
    }
    if error:
        result["error"] = error
    return result


def _retry_failed_thumbnail_worker(item: Dict[str, Any], thumbnail_size: Any) -> Dict[str, Any]:
    file_result = _make_file_result(
        file_id=item["file_id"],
        source_path=item["file_path"],
        target_path=item["target_thumbnail_path"],
        status="planned",
    )
    if not os.path.isfile(item["file_path"]):
        file_result["status"] = "skipped"
        file_result["error"] = "source file missing"
        return file_result

    try:
        create_thumbnail_file(
            item["file_path"],
            item["target_thumbnail_path"],
            thumbnail_size=thumbnail_size,
            quality=THUMBNAIL_JPEG_QUALITY,
        )
    except Exception as exc:
        file_result["status"] = "failed"
        file_result["error"] = str(exc)
        return file_result

    file_result["status"] = "succeeded"
    return file_result


def run_thumbnail_maintenance(
    db_path: Optional[str] = None,
    limit: int = 20,
    file_ids: Optional[List[int]] = None,
    retry_failed: bool = False,
    migrate_signature: bool = False,
    apply: bool = False,
    workers: int = 2,
    batch_size: int = 10,
) -> Dict[str, Any]:
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)
    if not db_path:
        from config import get_settings

        settings = get_settings()
        db_path = settings.db_path
    else:
        settings = _CliSettings(db_path)

    integrity_report = build_startup_integrity_report(
        dry_run=True,
        db_path=db_path,
        settings=settings,
        with_repair_plan=True,
    )
    checks = _check_lookup(integrity_report)
    failed_count = checks.get("thumbnail_failed", {}).get("count", 0)
    missing_count = checks.get("thumbnail_file_missing", {}).get("count", 0)
    stale_signature = checks.get("thumbnail_cache_version_stale", {}).get("count", 0) > 0
    current_signature = integrity_report.get("thumbnail_cache_signature")
    stored_signature = integrity_report.get("stored_thumbnail_cache_signature")

    mode_parts: List[str] = []
    if retry_failed:
        mode_parts.append("retry_failed")
    if migrate_signature:
        mode_parts.append("migrate_signature")
    mode = "+".join(mode_parts) if mode_parts else "status"

    result: Dict[str, Any] = {
        "dry_run": not apply,
        "mode": mode,
        "db_path": os.path.abspath(db_path),
        "thumbnail_cache_signature": current_signature,
        "stored_thumbnail_cache_signature": stored_signature,
        "failed_thumbnail_count": failed_count,
        "missing_thumbnail_count": missing_count,
        "stale_signature": stale_signature,
        "suggested_action_summary": [step["action"] for step in integrity_report.get("repair_plan", [])[:5]],
        "integrity_report": integrity_report,
        "found": 0,
        "selected": 0,
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "db_updated": 0,
        "workers": workers,
        "batch_size": batch_size,
        "warnings": [],
        "file_results": [],
        "operations": {},
    }

    if not retry_failed and not migrate_signature:
        return result

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if retry_failed:
            retry_found_query = "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path = '__FAILED__'"
            retry_params: List[Any] = []
            if file_ids:
                placeholders = ",".join("?" * len(file_ids))
                retry_found_query += f" AND file_id IN ({placeholders})"
                retry_params.extend(file_ids)
            total_failed = conn.execute(retry_found_query, retry_params).fetchone()[0]
            selected_rows = _get_failed_rows(conn, settings, limit=limit, file_ids=file_ids)
            result["found"] += total_failed
            result["selected"] += len(selected_rows)
            planned_results = [
                _make_file_result(
                    file_id=row["file_id"],
                    source_path=row["file_path"],
                    target_path=row["target_thumbnail_path"],
                    status="planned",
                )
                for row in selected_rows
            ]
            result["file_results"].extend(planned_results)
            result["operations"]["retry_failed"] = {
                "found": total_failed,
                "selected": selected_rows,
                "results": planned_results,
            }
            if apply:
                result["file_results"] = []
                result["operations"]["retry_failed"]["results"] = result["file_results"]
                result["operations"]["retry_failed"]["workers"] = workers
                result["operations"]["retry_failed"]["batch_size"] = batch_size
                result["operations"]["retry_failed"]["db_write_thread_id"] = threading.get_ident()
                for start in range(0, len(selected_rows), batch_size):
                    batch_rows = selected_rows[start:start + batch_size]
                    worker_results_by_file_id: Dict[int, Dict[str, Any]] = {}
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        future_map = {
                            executor.submit(
                                _retry_failed_thumbnail_worker,
                                row,
                                settings.thumbnail_size,
                            ): row["file_id"]
                            for row in batch_rows
                        }
                        for future in as_completed(future_map):
                            worker_result = future.result()
                            worker_results_by_file_id[worker_result["file_id"]] = worker_result

                    for row in batch_rows:
                        file_id = row["file_id"]
                        target_path = row["target_thumbnail_path"]
                        file_result = worker_results_by_file_id[file_id]
                        result["attempted"] += 1

                        if file_result["status"] == "skipped":
                            result["skipped"] += 1
                            result["warnings"].append(
                                f"file_id={file_id} {file_result.get('error', 'skipped')}"
                            )
                            result["file_results"].append(file_result)
                            continue

                        if file_result["status"] == "failed":
                            result["failed"] += 1
                            result["warnings"].append(
                                f"file_id={file_id} retry failed: {file_result.get('error', 'unknown error')}"
                            )
                            result["file_results"].append(file_result)
                            continue

                        cursor = conn.execute(
                            "UPDATE photo_metadata SET thumbnail_path = ? WHERE file_id = ? AND thumbnail_path = '__FAILED__'",
                            (target_path, file_id),
                        )
                        if cursor.rowcount:
                            result["db_updated"] += cursor.rowcount
                            result["succeeded"] += 1
                            result["file_results"].append(file_result)
                            continue

                        file_result["status"] = "failed"
                        file_result["error"] = "database update skipped because record was no longer marked __FAILED__"
                        result["failed"] += 1
                        result["warnings"].append(f"file_id={file_id} {file_result['error']}")
                        result["file_results"].append(file_result)

        if migrate_signature:
            can_migrate = missing_count == 0
            migrate_op = {
                "current_signature": current_signature,
                "stored_signature": stored_signature,
                "can_apply": can_migrate,
            }
            needs_migration = stale_signature or stored_signature is None
            result["found"] += 1 if needs_migration else 0
            result["selected"] += 1 if needs_migration else 0
            if missing_count > 0:
                migrate_op["blocked_reason"] = "thumbnail_file_missing > 0"
                result["warnings"].append("signature migration blocked until missing thumbnail files are handled")
            elif not _table_exists(conn, "thumbnail_params"):
                migrate_op["blocked_reason"] = "thumbnail_params table missing"
                result["warnings"].append("signature migration blocked because thumbnail_params table is unavailable")
            result["operations"]["migrate_signature"] = migrate_op

            if apply and migrate_op.get("blocked_reason") is None and needs_migration:
                result["attempted"] += 1
                updated = _update_thumbnail_signature(conn, current_signature)
                result["db_updated"] += updated
                result["succeeded"] += 1 if updated else 0
            elif apply and migrate_op.get("blocked_reason") is not None:
                result["skipped"] += 1

        if apply:
            conn.commit()
    finally:
        conn.close()

    return result


def format_maintenance_text(result: Dict[str, Any]) -> str:
    lines = [
        "Thumbnail Maintenance Report",
        f"db_path: {result['db_path']}",
        f"dry_run: {result['dry_run']}",
        f"mode: {result['mode']}",
        f"thumbnail_cache_signature: {result['thumbnail_cache_signature']}",
        f"stored_thumbnail_cache_signature: {result['stored_thumbnail_cache_signature']}",
        f"failed thumbnails: {result['failed_thumbnail_count']}",
        f"missing thumbnail files: {result['missing_thumbnail_count']}",
        f"stale signature: {result['stale_signature']}",
        f"found: {result['found']}",
        f"selected: {result['selected']}",
        f"attempted: {result['attempted']}",
        f"succeeded: {result['succeeded']}",
        f"failed: {result['failed']}",
        f"skipped: {result['skipped']}",
        f"db_updated: {result['db_updated']}",
        f"workers: {result['workers']}",
        f"batch_size: {result['batch_size']}",
    ]
    if result.get("suggested_action_summary"):
        lines.append("suggested actions:")
        for action in result["suggested_action_summary"]:
            lines.append(f"- {action}")
    if result.get("operations", {}).get("retry_failed"):
        lines.append("retry_failed plan:")
        for item in result["operations"]["retry_failed"]["selected"]:
            lines.append(
                f"- file_id={item['file_id']} source={item['file_path']} target={item['target_thumbnail_path']}"
            )
    if result.get("file_results"):
        lines.append("per-file results:")
        for item in result["file_results"]:
            line = (
                f"- file_id={item['file_id']} status={item['status']} "
                f"source={item['source_path']} target={item['target_path']}"
            )
            if item.get("error"):
                line += f" error={item['error']}"
            lines.append(line)
    if result.get("operations", {}).get("migrate_signature"):
        op = result["operations"]["migrate_signature"]
        lines.append("migrate_signature plan:")
        lines.append(
            f"- stored={op.get('stored_signature')} current={op.get('current_signature')} can_apply={op.get('can_apply')}"
        )
        if op.get("blocked_reason"):
            lines.append(f"  blocked_reason: {op['blocked_reason']}")
    if result.get("warnings"):
        lines.append("warnings:")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Inspect and maintain thumbnail cache safely.")
    parser.add_argument("--db-path", help="Optional path to the SQLite database to inspect.")
    parser.add_argument("--limit", type=int, default=20, help="Limit selected rows for dry-run/apply operations.")
    parser.add_argument("--file-id", type=int, action="append", dest="file_ids", help="Restrict maintenance to specific file_id values.")
    parser.add_argument("--retry-failed", action="store_true", help="Plan or retry __FAILED__ thumbnail rows.")
    parser.add_argument("--migrate-signature", action="store_true", help="Plan or apply thumbnail_sig migration only.")
    parser.add_argument("--workers", type=int, default=2, help="Worker threads for small-batch retry-failed generation. Minimum 1.")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for retry-failed processing. Minimum 1.")
    parser.add_argument("--apply", action="store_true", help="Actually write DB updates / generate thumbnails. Omit for dry-run.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print structured JSON output only.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = run_thumbnail_maintenance(
        db_path=args.db_path,
        limit=max(args.limit, 0),
        file_ids=args.file_ids,
        retry_failed=args.retry_failed,
        migrate_signature=args.migrate_signature,
        apply=args.apply,
        workers=max(args.workers, 1),
        batch_size=max(args.batch_size, 1),
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_maintenance_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
