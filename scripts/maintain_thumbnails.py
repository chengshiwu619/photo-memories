import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sqlite3
import sys
import threading
from collections import Counter
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
from services.startup_integrity import (  # noqa: E402
    build_repair_plan,
    build_startup_integrity_report,
    finalize_integrity_report,
)


DEFAULT_SELECTION_LIMIT = 20
DEFAULT_WORKERS = 2
DEFAULT_BATCH_SIZE = 10
LONG_PATH_WARNING_THRESHOLD = 240
SPECIAL_CHAR_PATTERN = re.compile(r"[^\w\s\\/:\.\-\(\)\[\]]", re.UNICODE)
DECODE_RISK_EXTENSIONS = {".heic", ".heif", ".avif"}


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


def _get_supported_image_extensions() -> set[str]:
    try:
        from config import IMAGE_EXTENSIONS

        return {ext.lower() for ext in IMAGE_EXTENSIONS}
    except Exception:
        return {
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".gif",
            ".webp",
            ".tif",
            ".tiff",
            ".heic",
            ".heif",
            ".avif",
        }


def _get_failed_rows(
    conn: sqlite3.Connection,
    settings: Any,
    limit: Optional[int],
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
    if limit is not None:
        rows = rows[: max(limit, 0)]
    return [
        {
            "file_id": row["file_id"],
            "file_path": row["file_path"],
            "target_thumbnail_path": build_thumbnail_path(settings.thumbnail_dir, row["file_id"]),
        }
        for row in rows
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


def _safe_read_probe(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            fh.read(1)
        return True
    except Exception:
        return False


def _make_file_result(
    file_id: int,
    source_path: str,
    target_path: str,
    status: str,
    source_exists: bool,
    source_is_file: bool,
    source_readable: bool,
    file_ext: str,
    path_length: int,
    has_non_ascii: bool,
    has_special_chars: bool,
    likely_reason: str,
    retry_recommended: bool,
    recommended_action: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        "file_id": file_id,
        "source_path": source_path,
        "target_path": target_path,
        "status": status,
        "source_exists": source_exists,
        "source_is_file": source_is_file,
        "source_readable": source_readable,
        "file_ext": file_ext,
        "path_length": path_length,
        "has_non_ascii": has_non_ascii,
        "has_special_chars": has_special_chars,
        "likely_reason": likely_reason,
        "retry_recommended": retry_recommended,
        "recommended_action": recommended_action,
    }
    if error:
        result["error"] = error
    return result


def diagnose_failed_thumbnail_item(
    item: Dict[str, Any],
    supported_extensions: Optional[set[str]] = None,
) -> Dict[str, Any]:
    supported_extensions = supported_extensions or _get_supported_image_extensions()
    source_path = item["file_path"]
    target_path = item["target_thumbnail_path"]
    file_ext = os.path.splitext(source_path)[1].lower()
    source_exists = os.path.exists(source_path)
    source_is_file = os.path.isfile(source_path)
    source_readable = source_exists and source_is_file and _safe_read_probe(source_path)
    path_length = len(source_path)
    has_non_ascii = any(ord(ch) > 127 for ch in source_path)
    has_special_chars = bool(SPECIAL_CHAR_PATTERN.search(source_path))

    if not source_exists:
        likely_reason = "missing_source"
        retry_recommended = False
        recommended_action = "Check whether the NAS mount/path moved or is currently unavailable before retrying."
    elif not source_is_file:
        likely_reason = "not_file"
        retry_recommended = False
        recommended_action = "The source path is not a regular file; fix the path or re-index before retrying."
    elif file_ext not in supported_extensions:
        likely_reason = "unsupported_extension"
        retry_recommended = False
        recommended_action = "This extension is outside the supported thumbnail formats; review indexing rules before retrying."
    elif not source_readable:
        likely_reason = "inaccessible_source"
        retry_recommended = False
        recommended_action = "The file exists but is not readable right now; check NAS permissions, locks, or network access before retrying."
    elif path_length >= LONG_PATH_WARNING_THRESHOLD:
        likely_reason = "long_path_risk"
        retry_recommended = True
        recommended_action = "Retry a single file_id first; long Windows/NAS paths are a risk hint but do not automatically block regeneration."
    elif file_ext in DECODE_RISK_EXTENSIONS:
        likely_reason = "decode_maybe_failed"
        retry_recommended = True
        recommended_action = "The source looks reachable, but this format may have decoder issues; retry one file_id first and review the exact error if it fails again."
    elif has_special_chars:
        likely_reason = "special_char_path"
        retry_recommended = True
        recommended_action = "Retry one file_id first; special characters are only a risk hint, not a hard blocker."
    elif has_non_ascii:
        likely_reason = "non_ascii_path"
        retry_recommended = True
        recommended_action = "Retry one file_id first; non-ASCII paths are only a risk hint, not a hard blocker."
    elif source_exists and source_is_file and source_readable and file_ext in supported_extensions:
        likely_reason = "source_ok_retry_possible"
        retry_recommended = True
        recommended_action = "This file is a good candidate for a single-file retry, then a small-batch apply if it succeeds."
    else:
        likely_reason = "unknown"
        retry_recommended = False
        recommended_action = "Review the path manually before retrying because the failure reason could not be classified confidently."

    return _make_file_result(
        file_id=item["file_id"],
        source_path=source_path,
        target_path=target_path,
        status="planned",
        source_exists=source_exists,
        source_is_file=source_is_file,
        source_readable=source_readable,
        file_ext=file_ext,
        path_length=path_length,
        has_non_ascii=has_non_ascii,
        has_special_chars=has_special_chars,
        likely_reason=likely_reason,
        retry_recommended=retry_recommended,
        recommended_action=recommended_action,
    )


def build_failed_thumbnail_diagnosis(
    db_path: str,
    settings: Any,
    limit: Optional[int] = DEFAULT_SELECTION_LIMIT,
    file_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        found_query = "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path = '__FAILED__'"
        params: List[Any] = []
        if file_ids:
            placeholders = ",".join("?" * len(file_ids))
            found_query += f" AND file_id IN ({placeholders})"
            params.extend(file_ids)
        found = conn.execute(found_query, params).fetchone()[0]
        selected_rows = _get_failed_rows(conn, settings, limit=limit, file_ids=file_ids)
    finally:
        conn.close()

    diagnoses = [diagnose_failed_thumbnail_item(item) for item in selected_rows]
    retry_recommended_count = sum(1 for item in diagnoses if item["retry_recommended"])
    blocked_count = len(diagnoses) - retry_recommended_count
    reason_counts = Counter(item["likely_reason"] for item in diagnoses)

    return {
        "found": found,
        "selected_rows": selected_rows,
        "diagnoses": diagnoses,
        "retry_recommended_count": retry_recommended_count,
        "blocked_count": blocked_count,
        "reason_counts": dict(reason_counts),
    }


def build_failed_thumbnail_next_steps(
    retry_recommended_count: int,
    blocked_count: int,
    reason_counts: Dict[str, int],
    selected_count: int,
) -> List[str]:
    next_steps: List[str] = []
    if blocked_count > 0:
        if reason_counts.get("missing_source", 0) >= max(1, retry_recommended_count):
            next_steps.append("先检查 missing_source 的 NAS 挂载、路径是否移动，未恢复前不要执行 --apply。")
        elif reason_counts.get("inaccessible_source", 0) > 0 or reason_counts.get("not_file", 0) > 0:
            next_steps.append("先修复不可访问路径、权限或非文件路径问题，再考虑重试 failed 缩略图。")
        elif reason_counts.get("unsupported_extension", 0) > 0:
            next_steps.append("先确认不受支持扩展是否应该被索引，而不是直接对这些项执行 --apply。")

    if retry_recommended_count > 0:
        next_steps.append("先对 retry_recommended=true 的单个 file_id 执行 --apply。")
        if selected_count > 1:
            next_steps.append("单个成功后再使用 --limit 5 --apply 做小批量推进。")

    next_steps.append("全部 failed 处理后再运行 check_integrity 复查 thumbnail_failed 是否清零。")
    next_steps.append("确认 thumbnail_failed=0 后再考虑 migrate-signature --apply。")
    return next_steps


def refine_integrity_report_with_failed_diagnosis(
    report: Dict[str, Any],
    diagnosis_summary: Dict[str, Any],
    max_samples: int = 5,
) -> Dict[str, Any]:
    report = finalize_integrity_report(report)
    report["thumbnail_failed_diagnosis_summary"] = {
        "found": diagnosis_summary["found"],
        "selected": len(diagnosis_summary["diagnoses"]),
        "retry_recommended_count": diagnosis_summary["retry_recommended_count"],
        "blocked_count": diagnosis_summary["blocked_count"],
        "reason_counts": diagnosis_summary["reason_counts"],
    }

    if "repair_plan" not in report:
        report["repair_plan"] = build_repair_plan(report, max_samples=max_samples)

    reason_counts = diagnosis_summary["reason_counts"]
    retry_recommended_count = diagnosis_summary["retry_recommended_count"]
    blocked_count = diagnosis_summary["blocked_count"]
    for step in report.get("repair_plan", []):
        if step.get("check_name") != "thumbnail_failed":
            continue
        if blocked_count > retry_recommended_count and reason_counts.get("missing_source", 0) > 0:
            step["action"] = (
                "Most failed thumbnails currently look like missing or inaccessible source paths. "
                "Check the NAS mount, path moves, or file availability before running any retry apply."
            )
        elif retry_recommended_count > 0:
            step["action"] = (
                "Most failed thumbnails still look retryable. Backup photos.db, retry a single file_id first, "
                "then continue with --limit 5 --apply if that succeeds."
            )
        else:
            step["action"] = (
                "Review the failed thumbnail paths manually before retrying because the current diagnostics do not "
                "show a clear safe-retry majority."
            )
        break
    return report


def _retry_failed_thumbnail_worker(item: Dict[str, Any], thumbnail_size: Any) -> Dict[str, Any]:
    diagnosis = diagnose_failed_thumbnail_item(item)
    if not diagnosis["retry_recommended"]:
        diagnosis["status"] = "skipped"
        diagnosis["error"] = f"retry not recommended: {diagnosis['likely_reason']}"
        return diagnosis

    try:
        create_thumbnail_file(
            item["file_path"],
            item["target_thumbnail_path"],
            thumbnail_size=thumbnail_size,
            quality=THUMBNAIL_JPEG_QUALITY,
        )
    except Exception as exc:
        diagnosis["status"] = "failed"
        diagnosis["error"] = str(exc)
        return diagnosis

    diagnosis["status"] = "succeeded"
    return diagnosis


def run_thumbnail_maintenance(
    db_path: Optional[str] = None,
    limit: int = DEFAULT_SELECTION_LIMIT,
    file_ids: Optional[List[int]] = None,
    retry_failed: bool = False,
    migrate_signature: bool = False,
    apply: bool = False,
    workers: int = DEFAULT_WORKERS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    scope_limited: bool = False,
) -> Dict[str, Any]:
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)
    explicit_scope = scope_limited or bool(file_ids) or limit != DEFAULT_SELECTION_LIMIT

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
        "retry_recommended_count": 0,
        "blocked_count": 0,
        "planned_apply_count": 0,
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "db_updated": 0,
        "workers": workers,
        "batch_size": batch_size,
        "warnings": [],
        "next_steps": [],
        "file_results": [],
        "operations": {},
    }

    if not retry_failed and not migrate_signature:
        return result

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if retry_failed:
            diagnosis_summary = build_failed_thumbnail_diagnosis(
                db_path=db_path,
                settings=settings,
                limit=limit,
                file_ids=file_ids,
            )
            selected_rows = diagnosis_summary["selected_rows"]
            file_results = diagnosis_summary["diagnoses"]
            result["found"] += diagnosis_summary["found"]
            result["selected"] += len(selected_rows)
            result["retry_recommended_count"] = diagnosis_summary["retry_recommended_count"]
            result["blocked_count"] = diagnosis_summary["blocked_count"]
            result["planned_apply_count"] = diagnosis_summary["retry_recommended_count"]
            result["file_results"] = file_results
            result["next_steps"] = build_failed_thumbnail_next_steps(
                retry_recommended_count=result["retry_recommended_count"],
                blocked_count=result["blocked_count"],
                reason_counts=diagnosis_summary["reason_counts"],
                selected_count=result["selected"],
            )
            result["operations"]["retry_failed"] = {
                "found": diagnosis_summary["found"],
                "selected": selected_rows,
                "results": file_results,
                "workers": workers,
                "batch_size": batch_size,
                "reason_counts": diagnosis_summary["reason_counts"],
            }

            if apply and not explicit_scope:
                result["warnings"].append(
                    "retry-failed apply refused: specify at least one --file-id or an explicit --limit before modifying the database."
                )
                result["planned_apply_count"] = 0
                result["next_steps"].insert(0, "先用 --file-id 或显式 --limit 缩小范围，再执行 --apply。")
            elif apply:
                retryable_items = [
                    row for row, diagnosis in zip(selected_rows, file_results)
                    if diagnosis["retry_recommended"]
                ]
                if result["selected"] > batch_size:
                    result["warnings"].append(
                        f"selected items ({result['selected']}) exceed batch_size ({batch_size}); apply will run in multiple batches."
                    )

                result["operations"]["retry_failed"]["db_write_thread_id"] = threading.get_ident()
                result["file_results"] = []
                result["operations"]["retry_failed"]["results"] = result["file_results"]

                diagnosis_by_file_id = {item["file_id"]: item for item in file_results}
                for item in file_results:
                    if not item["retry_recommended"]:
                        skipped_item = dict(item)
                        skipped_item["status"] = "skipped"
                        skipped_item["error"] = f"retry not recommended: {item['likely_reason']}"
                        result["skipped"] += 1
                        result["warnings"].append(
                            f"file_id={item['file_id']} skipped before worker execution because {item['likely_reason']}"
                        )
                        result["file_results"].append(skipped_item)

                for start in range(0, len(retryable_items), batch_size):
                    batch_rows = retryable_items[start:start + batch_size]
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

                        failed_update = dict(file_result)
                        failed_update["status"] = "failed"
                        failed_update["error"] = "database update skipped because record was no longer marked __FAILED__"
                        result["failed"] += 1
                        result["warnings"].append(f"file_id={file_id} {failed_update['error']}")
                        result["file_results"].append(failed_update)

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
        f"retry_recommended_count: {result['retry_recommended_count']}",
        f"blocked_count: {result['blocked_count']}",
        f"planned_apply_count: {result['planned_apply_count']}",
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
            lines.append(f"- file_id={item['file_id']} status={item['status']} likely_reason={item['likely_reason']}")
            lines.append(f"  source_path: {item['source_path']}")
            lines.append(f"  target_path: {item['target_path']}")
            lines.append(
                "  source_exists: {source_exists} source_is_file: {source_is_file} source_readable: {source_readable}".format(
                    source_exists=item["source_exists"],
                    source_is_file=item["source_is_file"],
                    source_readable=item["source_readable"],
                )
            )
            lines.append(
                "  file_ext: {file_ext} path_length: {path_length} has_non_ascii: {has_non_ascii} has_special_chars: {has_special_chars}".format(
                    file_ext=item["file_ext"],
                    path_length=item["path_length"],
                    has_non_ascii=item["has_non_ascii"],
                    has_special_chars=item["has_special_chars"],
                )
            )
            lines.append(f"  retry_recommended: {item['retry_recommended']}")
            lines.append(f"  recommended_action: {item['recommended_action']}")
            if item.get("error"):
                lines.append(f"  error: {item['error']}")
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
    if result.get("next_steps"):
        lines.append("next_steps:")
        for step in result["next_steps"]:
            lines.append(f"- {step}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Inspect and maintain thumbnail cache safely.")
    parser.add_argument("--db-path", help="Optional path to the SQLite database to inspect.")
    parser.add_argument("--limit", type=int, default=DEFAULT_SELECTION_LIMIT, help="Limit selected rows for dry-run/apply operations.")
    parser.add_argument("--file-id", type=int, action="append", dest="file_ids", help="Restrict maintenance to specific file_id values.")
    parser.add_argument("--retry-failed", action="store_true", help="Diagnose, plan, or retry __FAILED__ thumbnail rows.")
    parser.add_argument("--migrate-signature", action="store_true", help="Plan or apply thumbnail_sig migration only.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Worker threads for small-batch retry-failed generation. Minimum 1.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for retry-failed processing. Minimum 1.")
    parser.add_argument("--apply", action="store_true", help="Actually write DB updates / generate thumbnails. Omit for dry-run.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print structured JSON output only.")
    return parser.parse_args(argv)


def main(argv=None):
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parse_args(raw_argv)
    scope_limited = "--limit" in raw_argv or "--file-id" in raw_argv
    result = run_thumbnail_maintenance(
        db_path=args.db_path,
        limit=max(args.limit, 0),
        file_ids=args.file_ids,
        retry_failed=args.retry_failed,
        migrate_signature=args.migrate_signature,
        apply=args.apply,
        workers=max(args.workers, 1),
        batch_size=max(args.batch_size, 1),
        scope_limited=scope_limited,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_maintenance_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
