import os
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Optional

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


def _query_memory_visibility(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
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
    ).fetchall()


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


def format_integrity_report_text(report: IntegrityReport) -> str:
    report = finalize_integrity_report(deepcopy(report))
    summary = report["summary"]
    lines = [
        "Startup Integrity Report",
        f"db_path: {report.get('db_path', '')}",
        f"dry_run: {report.get('dry_run', True)}",
        f"errors: {summary['error_count']}",
        f"warnings: {summary['warning_count']}",
        f"info: {summary['info_count']}",
    ]
    for check in report.get("checks", []):
        lines.append(
            f"- {check['check_name']} | severity={check['severity']} | count={check['count']}"
        )
        if check.get("sample_ids"):
            lines.append(f"  sample_ids: {check['sample_ids']}")
        if check.get("sample_paths"):
            lines.append(f"  sample_paths: {check['sample_paths']}")
        if check.get("suggested_action"):
            lines.append(f"  suggested_action: {check['suggested_action']}")
    return "\n".join(lines)


def build_startup_integrity_report(
    dry_run: bool = True,
    db_path: Optional[str] = None,
    settings: Any = None,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> IntegrityReport:
    settings = _resolve_settings(settings)
    resolved_db_path = _resolve_db_path(db_path, settings)
    report: IntegrityReport = {
        "dry_run": dry_run,
        "db_path": resolved_db_path,
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
        return finalize_integrity_report(report)

    conn = sqlite3.connect(resolved_db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
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
        report["checks"].append(
            _sample_check(
                "memories_unrenderable_in_ui",
                "error" if fully_hidden else "info",
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
                "photo_metadata_missing_thumbnail_ref",
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
                "photo_metadata_failed_thumbnail_ref",
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
                "photo_metadata_broken_thumbnail_files",
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

    return finalize_integrity_report(report)


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
