import os
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Optional

from infra.image.thumbnail_cache import (
    THUMBNAIL_CACHE_VERSION,
    build_thumbnail_cache_signature,
    classify_thumbnail_cache_signature,
)
from logger_setup import logger


IntegrityCheck = Dict[str, Any]
IntegrityReport = Dict[str, Any]
DEFAULT_MAX_SAMPLES = 5


def _make_check(
    check_name: str,
    severity: str,
    count: int,
    sample_ids: Optional[List[Any]] = None,
    sample_paths: Optional[List[str]] = None,
    suggested_action: str = "",
) -> IntegrityCheck:
    return {
        "check_name": check_name,
        "severity": severity,
        "count": count,
        "sample_ids": sample_ids or [],
        "sample_paths": sample_paths or [],
        "suggested_action": suggested_action,
    }


def _limit_list(values: Optional[List[Any]], max_samples: int) -> List[Any]:
    if not values:
        return []
    if max_samples < 0:
        return list(values)
    return list(values[:max_samples])


def _sample_check(
    check_name: str,
    severity: str,
    count: int,
    sample_ids: Optional[List[Any]] = None,
    sample_paths: Optional[List[str]] = None,
    suggested_action: str = "",
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> IntegrityCheck:
    return _make_check(
        check_name=check_name,
        severity=severity,
        count=count,
        sample_ids=_limit_list(sample_ids, max_samples),
        sample_paths=_limit_list(sample_paths, max_samples),
        suggested_action=suggested_action,
    )


def _resolve_settings(settings: Any = None) -> Any:
    if settings is not None:
        return settings
    from config import get_settings

    return get_settings()


def _resolve_db_path(db_path: Optional[str], settings: Any) -> str:
    if db_path:
        return db_path
    if hasattr(settings, "db_path"):
        return settings.db_path
    raise ValueError("db_path is required when settings has no db_path")


def _query_memory_reference_issues(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        WITH valid_memories AS (
            SELECT id, photo_ids
            FROM memories
            WHERE dismissed_at IS NULL
              AND photo_ids IS NOT NULL
              AND json_valid(photo_ids) = 1
        )
        SELECT vm.id AS memory_id,
               CAST(j.value AS INTEGER) AS file_id,
               f.id AS existing_file_id
        FROM valid_memories vm, json_each(vm.photo_ids) j
        LEFT JOIN files f ON f.id = CAST(j.value AS INTEGER)
        WHERE f.id IS NULL
        """
    ).fetchall()


def _is_memory_hidden(conn: sqlite3.Connection, memory_id: int) -> bool:
    """检查 memory 是否已被标记为 hidden（is_hidden=1 或已 dismissed）。"""
    try:
        row = conn.execute(
            "SELECT is_hidden, dismissed_at FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            return True
        if row["dismissed_at"] is not None:
            return True
        if row["is_hidden"] == 1:
            return True
        return False
    except Exception:
        # is_hidden 列可能不存在（旧 schema）
        return False


def _query_memory_visibility(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """查询 memory 可见性。兼容旧 schema 无 is_hidden 列的情况。"""
    query_with_hidden = """
        WITH valid_memories AS (
            SELECT id, memory_type, cover_file_id, photo_ids
            FROM memories
            WHERE dismissed_at IS NULL
              AND (is_hidden IS NULL OR is_hidden = 0)
              AND photo_ids IS NOT NULL
              AND json_valid(photo_ids) = 1
        )
        SELECT vm.id AS memory_id,
               vm.memory_type AS memory_type,
               vm.cover_file_id AS cover_file_id,
               COUNT(*) AS total_refs,
               SUM(
                   CASE
                       WHEN f.id IS NOT NULL
                        AND pm.thumbnail_path IS NOT NULL
                        AND pm.thumbnail_path != ''
                        AND pm.thumbnail_path != '__FAILED__'
                        AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                       THEN 1
                       ELSE 0
                   END
               ) AS visible_refs
        FROM valid_memories vm, json_each(vm.photo_ids) j
        LEFT JOIN files f ON f.id = CAST(j.value AS INTEGER)
        LEFT JOIN photo_metadata pm ON pm.file_id = CAST(j.value AS INTEGER)
        GROUP BY vm.id, vm.memory_type, vm.cover_file_id
    """
    query_without_hidden = """
        WITH valid_memories AS (
            SELECT id, memory_type, cover_file_id, photo_ids
            FROM memories
            WHERE dismissed_at IS NULL
              AND photo_ids IS NOT NULL
              AND json_valid(photo_ids) = 1
        )
        SELECT vm.id AS memory_id,
               vm.memory_type AS memory_type,
               vm.cover_file_id AS cover_file_id,
               COUNT(*) AS total_refs,
               SUM(
                   CASE
                       WHEN f.id IS NOT NULL
                        AND pm.thumbnail_path IS NOT NULL
                        AND pm.thumbnail_path != ''
                        AND pm.thumbnail_path != '__FAILED__'
                        AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                       THEN 1
                       ELSE 0
                   END
               ) AS visible_refs
        FROM valid_memories vm, json_each(vm.photo_ids) j
        LEFT JOIN files f ON f.id = CAST(j.value AS INTEGER)
        LEFT JOIN photo_metadata pm ON pm.file_id = CAST(j.value AS INTEGER)
        GROUP BY vm.id, vm.memory_type, vm.cover_file_id
    """
    try:
        return conn.execute(query_with_hidden).fetchall()
    except sqlite3.OperationalError:
        # 旧 schema 没有 is_hidden 列
        return conn.execute(query_without_hidden).fetchall()


def _query_invalid_cover_refs(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT m.id AS memory_id, m.cover_file_id
        FROM memories m
        LEFT JOIN files f ON f.id = m.cover_file_id
        WHERE m.dismissed_at IS NULL
          AND m.cover_file_id IS NOT NULL
          AND f.id IS NULL
        """
    ).fetchall()


def _query_missing_thumbnail_refs(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT pm.file_id, pm.thumbnail_path
        FROM photo_metadata pm
        JOIN files f ON f.id = pm.file_id
        WHERE f.is_image = 1
          AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path = '')
        """
    ).fetchall()


def _query_failed_thumbnail_refs(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT pm.file_id, pm.thumbnail_path
        FROM photo_metadata pm
        JOIN files f ON f.id = pm.file_id
        WHERE f.is_image = 1
          AND pm.thumbnail_path = '__FAILED__'
        """
    ).fetchall()


def _query_broken_thumbnail_files(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT pm.file_id, pm.thumbnail_path
        FROM photo_metadata pm
        JOIN files f ON f.id = pm.file_id
        WHERE f.is_image = 1
          AND pm.thumbnail_path IS NOT NULL
          AND pm.thumbnail_path != ''
          AND pm.thumbnail_path != '__FAILED__'
        """
    ).fetchall()
    return [row for row in rows if not os.path.exists(row["thumbnail_path"])]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_thumbnail_signature_value(conn: sqlite3.Connection) -> Optional[str]:
    if not _table_exists(conn, "thumbnail_params"):
        return None
    row = conn.execute(
        "SELECT value FROM thumbnail_params WHERE key = 'thumbnail_sig'"
    ).fetchone()
    return row[0] if row else None


def summarize_integrity_report(report: IntegrityReport) -> Dict[str, int]:
    checks = report.get("checks", [])
    error_count = sum(check["count"] for check in checks if check["severity"] == "error")
    warning_count = sum(check["count"] for check in checks if check["severity"] == "warning")
    info_count = sum(check["count"] for check in checks if check["severity"] == "info")
    error_checks = sum(1 for check in checks if check["severity"] == "error" and check["count"] > 0)
    warning_checks = sum(1 for check in checks if check["severity"] == "warning" and check["count"] > 0)
    info_checks = sum(1 for check in checks if check["severity"] == "info" and check["count"] > 0)
    return {
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "error_checks": error_checks,
        "warning_checks": warning_checks,
        "info_checks": info_checks,
        "total_checks": len(checks),
    }


def finalize_integrity_report(report: IntegrityReport) -> IntegrityReport:
    summary = summarize_integrity_report(report)
    report["summary"] = summary
    report["has_errors"] = summary["error_count"] > 0
    report["has_warnings"] = summary["warning_count"] > 0
    return report


def limit_integrity_report_samples(report: IntegrityReport, max_samples: int = DEFAULT_MAX_SAMPLES) -> IntegrityReport:
    trimmed = deepcopy(report)
    for check in trimmed.get("checks", []):
        check["sample_ids"] = _limit_list(check.get("sample_ids"), max_samples)
        check["sample_paths"] = _limit_list(check.get("sample_paths"), max_samples)
    return finalize_integrity_report(trimmed)


def format_integrity_report_text(report: IntegrityReport, show_zero: bool = False) -> str:
    report = finalize_integrity_report(deepcopy(report))
    summary = report["summary"]
    lines = [
        "Startup Integrity Report",
        f"db_path: {report.get('db_path', '')}",
        f"dry_run: {report.get('dry_run', True)}",
        f"thumbnail_cache_version: {report.get('thumbnail_cache_version', '')}",
        f"thumbnail_cache_signature: {report.get('thumbnail_cache_signature', '')}",
        f"errors: {summary['error_count']}",
        f"warnings: {summary['warning_count']}",
        f"info: {summary['info_count']}",
    ]
    for check in report.get("checks", []):
        if not show_zero and check["severity"] == "info" and check["count"] == 0:
            continue
        lines.append(
            f"- {check['check_name']} | severity={check['severity']} | count={check['count']}"
        )
        if check.get("sample_ids"):
            lines.append(f"  sample_ids: {check['sample_ids']}")
        if check.get("sample_paths"):
            lines.append(f"  sample_paths: {check['sample_paths']}")
        if check.get("suggested_action"):
            lines.append(f"  suggested_action: {check['suggested_action']}")
    repair_plan = report.get("repair_plan") or []
    if repair_plan:
        lines.append("Suggested Repair Plan")
        for step in repair_plan:
            lines.append(
                f"- {step['check_name']} | priority={step['priority']} | affected_count={step['affected_count']}"
            )
            lines.append(f"  action: {step['action']}")
            if step.get("sample_ids"):
                lines.append(f"  sample_ids: {step['sample_ids']}")
            if step.get("sample_paths"):
                lines.append(f"  sample_paths: {step['sample_paths']}")
    return "\n".join(lines)


def _check_lookup(report: IntegrityReport) -> Dict[str, IntegrityCheck]:
    return {check["check_name"]: check for check in report.get("checks", [])}


def _append_repair_step(
    plan: List[Dict[str, Any]],
    plan_type: str,
    check_name: str,
    priority: str,
    affected_count: int,
    action: str,
    sample_ids: Optional[List[Any]] = None,
    sample_paths: Optional[List[str]] = None,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> None:
    plan.append(
        {
            "plan_type": plan_type,
            "check_name": check_name,
            "priority": priority,
            "affected_count": affected_count,
            "action": action,
            "sample_ids": _limit_list(sample_ids, max_samples),
            "sample_paths": _limit_list(sample_paths, max_samples),
        }
    )


def build_repair_plan(report: IntegrityReport, max_samples: int = DEFAULT_MAX_SAMPLES) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    checks = _check_lookup(report)

    for simple_check_name, plan_type, action in [
        ("photo_data_dir_exists", "config_dir_create", "Create the configured photo_data_dir or correct the cache directory setting before startup tasks run."),
        ("thumbnail_dir_exists", "config_dir_create", "Create the configured thumbnail_dir or fix the thumbnail cache path in settings before indexing."),
        ("database_file_exists", "database_restore", "Initialize or restore the SQLite database file before relying on memory and thumbnail integrity checks."),
        ("memories_missing_file_refs", "memory_rebuild", "Rebuild the affected memory rows from discovery logic or manually inspect stale file_id references before displaying them."),
        ("memories_unrenderable_in_ui", "memory_rebuild", "Rebuild these memories so every displayed memory has at least one currently renderable photo reference."),
        ("memories_partially_unrenderable", "memory_review", "Review these memories and rebuild or trim stale photo references so visible content matches stored references."),
        ("memories_invalid_cover_file", "memory_cover_reselect", "Choose a new cover_file_id from a valid referenced photo when the stored cover file is missing."),
        ("thumbnail_path_empty", "thumbnail_regenerate", "Regenerate thumbnails for these file_ids in small batches so UI and memory views regain a usable thumbnail reference."),
        ("thumbnail_file_missing", "thumbnail_regenerate", "Rebuild missing thumbnail files in small batches by file_id/path while keeping existing valid cache files untouched."),
    ]:
        check = checks.get(simple_check_name)
        if not check or check.get("count", 0) <= 0:
            continue
        priority = "high" if check["severity"] == "error" else "medium" if check["severity"] == "warning" else "low"
        _append_repair_step(
            plan,
            plan_type=plan_type,
            check_name=simple_check_name,
            priority=priority,
            affected_count=check["count"],
            action=action,
            sample_ids=check.get("sample_ids"),
            sample_paths=check.get("sample_paths"),
            max_samples=max_samples,
        )

    stale_check = checks.get("thumbnail_cache_version_stale")
    missing_thumb_files = checks.get("thumbnail_file_missing", {})
    if stale_check and stale_check.get("count", 0) > 0:
        action = (
            "The stored thumbnail cache signature is older than the current format, but cached files still appear present. "
            "Plan a signature migration and, if desired, a staged thumbnail refresh in small batches by file_id/path."
            if missing_thumb_files.get("count", 0) == 0
            else
            "The stored thumbnail cache signature is older than the current format and some thumbnail files are missing. "
            "Migrate the cache signature and prioritize rebuilding only the missing thumbnails before any broader batch refresh."
        )
        _append_repair_step(
            plan,
            plan_type="cache_signature_migration",
            check_name="thumbnail_cache_version_stale",
            priority="medium",
            affected_count=stale_check["count"],
            action=action,
            sample_ids=stale_check.get("sample_ids"),
            sample_paths=stale_check.get("sample_paths"),
            max_samples=max_samples,
        )

    missing_sig_check = checks.get("thumbnail_cache_version_missing")
    if missing_sig_check and missing_sig_check.get("count", 0) > 0:
        _append_repair_step(
            plan,
            plan_type="cache_signature_migration",
            check_name="thumbnail_cache_version_missing",
            priority="medium",
            affected_count=missing_sig_check["count"],
            action=(
                "Thumbnail cache metadata is missing. Record the current cache signature after validating settings, "
                "then schedule thumbnail regeneration in small batches by file_id/path only where needed."
            ),
            sample_ids=missing_sig_check.get("sample_ids"),
            sample_paths=missing_sig_check.get("sample_paths"),
            max_samples=max_samples,
        )

    failed_check = checks.get("thumbnail_failed")
    if failed_check and failed_check.get("count", 0) > 0:
        _append_repair_step(
            plan,
            plan_type="thumbnail_failed_retry",
            check_name="thumbnail_failed",
            priority="medium",
            affected_count=failed_check["count"],
            action=(
                "Retry thumbnail generation only for __FAILED__ file_ids after first confirming the source files are still readable "
                "and that the image decoder can open them."
            ),
            sample_ids=failed_check.get("sample_ids"),
            sample_paths=failed_check.get("sample_paths"),
            max_samples=max_samples,
        )
    return plan


def build_startup_integrity_report(
    dry_run: bool = True,
    db_path: Optional[str] = None,
    settings: Any = None,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    with_repair_plan: bool = False,
) -> IntegrityReport:
    settings = _resolve_settings(settings)
    resolved_db_path = _resolve_db_path(db_path, settings)
    report: IntegrityReport = {
        "dry_run": dry_run,
        "db_path": resolved_db_path,
        "thumbnail_cache_version": THUMBNAIL_CACHE_VERSION,
        "thumbnail_cache_signature": build_thumbnail_cache_signature(settings),
        "checks": [],
    }

    photo_data_dir = getattr(settings, "photo_data_dir", "")
    thumbnail_dir = getattr(settings, "thumbnail_dir", "")

    report["checks"].append(
        _sample_check(
            "photo_data_dir_exists",
            "info" if photo_data_dir and os.path.isdir(photo_data_dir) else "warning",
            0 if photo_data_dir and os.path.isdir(photo_data_dir) else 1,
            sample_paths=[photo_data_dir] if photo_data_dir else [],
            suggested_action="Confirm the configured cache directory exists before startup tasks write caches.",
            max_samples=max_samples,
        )
    )
    report["checks"].append(
        _sample_check(
            "thumbnail_dir_exists",
            "info" if thumbnail_dir and os.path.isdir(thumbnail_dir) else "warning",
            0 if thumbnail_dir and os.path.isdir(thumbnail_dir) else 1,
            sample_paths=[thumbnail_dir] if thumbnail_dir else [],
            suggested_action="Create the thumbnail cache directory explicitly through config/setup flow before indexing.",
            max_samples=max_samples,
        )
    )

    if not os.path.isfile(resolved_db_path):
        report["checks"].append(
            _sample_check(
                "database_file_exists",
                "warning",
                1,
                sample_paths=[resolved_db_path],
                suggested_action="Initialize the local database before relying on startup integrity checks.",
                max_samples=max_samples,
            )
        )
        report = finalize_integrity_report(report)
        if with_repair_plan:
            report["repair_plan"] = build_repair_plan(report, max_samples=max_samples)
        return report

    conn = sqlite3.connect(resolved_db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        stored_thumbnail_signature = _get_thumbnail_signature_value(conn)
        signature_status = classify_thumbnail_cache_signature(
            stored_thumbnail_signature,
            settings,
        )
        report["stored_thumbnail_cache_signature"] = stored_thumbnail_signature

        report["checks"].append(
            _sample_check(
                "thumbnail_cache_version_missing",
                "warning" if signature_status == "missing" else "info",
                1 if signature_status == "missing" else 0,
                sample_ids=(
                    [{"current_signature": report["thumbnail_cache_signature"]}]
                    if signature_status == "missing"
                    else []
                ),
                suggested_action="Thumbnail cache metadata is missing; review cache provenance before trusting existing thumbnails.",
                max_samples=max_samples,
            )
        )
        report["checks"].append(
            _sample_check(
                "thumbnail_cache_version_stale",
                "warning" if signature_status in {"legacy", "stale"} else "info",
                1 if signature_status in {"legacy", "stale"} else 0,
                sample_ids=(
                    [{
                        "stored_signature": stored_thumbnail_signature,
                        "current_signature": report["thumbnail_cache_signature"],
                        "signature_status": signature_status,
                    }]
                    if signature_status in {"legacy", "stale"}
                    else []
                ),
                suggested_action=(
                    "Existing thumbnails appear to come from an older cache signature. "
                    "If files are still present, plan a signature migration or staged refresh rather than treating the cache as broken."
                ),
                max_samples=max_samples,
            )
        )

        missing_file_refs = _query_memory_reference_issues(conn)
        report["checks"].append(
            _sample_check(
                "memories_missing_file_refs",
                "error" if missing_file_refs else "info",
                len(missing_file_refs),
                sample_ids=[
                    {"memory_id": row["memory_id"], "file_id": row["file_id"]}
                    for row in missing_file_refs
                ],
                suggested_action="Rebuild or manually review memories that reference missing file IDs before showing them.",
                max_samples=max_samples,
            )
        )

        visibility_rows = _query_memory_visibility(conn)
        fully_hidden = [row for row in visibility_rows if row["total_refs"] > 0 and row["visible_refs"] == 0]
        partially_hidden = [
            row for row in visibility_rows
            if row["total_refs"] > 0 and 0 < row["visible_refs"] < row["total_refs"]
        ]
        # 同时排除 is_hidden=1 的 memory（已被维护命令标记隐藏，不重复报）
        fully_hidden = [
            row for row in fully_hidden
            if not _is_memory_hidden(conn, row["memory_id"])
        ]
        partially_hidden = [
            row for row in partially_hidden
            if not _is_memory_hidden(conn, row["memory_id"])
        ]
        report["checks"].append(
            _sample_check(
                "memories_unrenderable_in_ui",
                "warning" if fully_hidden else "info",
                len(fully_hidden),
                sample_ids=[
                    {
                        "memory_id": row["memory_id"],
                        "memory_type": row["memory_type"],
                        "cover_file_id": row["cover_file_id"],
                    }
                    for row in fully_hidden
                ],
                suggested_action="Rebuild these memories because current thumbnail/duplicate filters leave them with no displayable photos.",
                max_samples=max_samples,
            )
        )
        report["checks"].append(
            _sample_check(
                "memories_partially_unrenderable",
                "warning" if partially_hidden else "info",
                len(partially_hidden),
                sample_ids=[
                    {
                        "memory_id": row["memory_id"],
                        "visible_refs": row["visible_refs"],
                        "total_refs": row["total_refs"],
                    }
                    for row in partially_hidden
                ],
                suggested_action="Review or rebuild memories that contain a mix of valid and stale photo references.",
                max_samples=max_samples,
            )
        )

        invalid_cover_refs = _query_invalid_cover_refs(conn)
        report["checks"].append(
            _sample_check(
                "memories_invalid_cover_file",
                "warning" if invalid_cover_refs else "info",
                len(invalid_cover_refs),
                sample_ids=[
                    {"memory_id": row["memory_id"], "cover_file_id": row["cover_file_id"]}
                    for row in invalid_cover_refs
                ],
                suggested_action="Refresh cover_file_id when the referenced file no longer exists.",
                max_samples=max_samples,
            )
        )

        missing_thumbs = _query_missing_thumbnail_refs(conn)
        report["checks"].append(
            _sample_check(
                "thumbnail_path_empty",
                "warning" if missing_thumbs else "info",
                len(missing_thumbs),
                sample_ids=[row["file_id"] for row in missing_thumbs],
                suggested_action="These photos have no thumbnail path yet and may not appear in memory/timeline views until re-indexed.",
                max_samples=max_samples,
            )
        )

        failed_thumbs = _query_failed_thumbnail_refs(conn)
        report["checks"].append(
            _sample_check(
                "thumbnail_failed",
                "warning" if failed_thumbs else "info",
                len(failed_thumbs),
                sample_ids=[row["file_id"] for row in failed_thumbs],
                suggested_action="Review failed thumbnail entries and regenerate thumbnails if the source files are still valid.",
                max_samples=max_samples,
            )
        )

        broken_thumb_files = _query_broken_thumbnail_files(conn)
        report["checks"].append(
            _sample_check(
                "thumbnail_file_missing",
                "warning" if broken_thumb_files else "info",
                len(broken_thumb_files),
                sample_ids=[row["file_id"] for row in broken_thumb_files],
                sample_paths=[row["thumbnail_path"] for row in broken_thumb_files],
                suggested_action="Reset or rebuild broken thumbnail file references so UI loaders do not point at missing cache files.",
                max_samples=max_samples,
            )
        )
    finally:
        conn.close()

    report = finalize_integrity_report(report)
    if with_repair_plan:
        report["repair_plan"] = build_repair_plan(report, max_samples=max_samples)
    return report


def run_startup_integrity_check(
    dry_run: bool = True,
    db_path: Optional[str] = None,
    settings: Any = None,
) -> IntegrityReport:
    return build_startup_integrity_report(
        dry_run=dry_run,
        db_path=db_path,
        settings=settings,
        max_samples=DEFAULT_MAX_SAMPLES,
        with_repair_plan=False,
    )


def log_startup_integrity_report(report: IntegrityReport) -> None:
    report = finalize_integrity_report(deepcopy(report))
    summary = report["summary"]
    logger.info(
        "Startup integrity summary: db_path=%s dry_run=%s errors=%s warnings=%s",
        report.get("db_path", ""),
        report.get("dry_run", True),
        summary["error_count"],
        summary["warning_count"],
    )
    for check in report.get("checks", []):
        if check["count"] <= 0:
            continue
        sample_ids = check.get("sample_ids") or []
        sample_paths = check.get("sample_paths") or []
        logger_method = logger.warning if check["severity"] in {"warning", "error"} else logger.info
        logger_method(
            "Startup integrity check: %s severity=%s count=%s sample_ids=%s sample_paths=%s action=%s",
            check["check_name"],
            check["severity"],
            check["count"],
            sample_ids,
            sample_paths,
            check["suggested_action"],
        )
