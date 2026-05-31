import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


DEFAULT_LIMIT = 10
SIGLIP_SOURCE = "siglip"


class _CliSettings:
    def __init__(self, db_path: str):
        photo_data_dir = os.path.dirname(os.path.abspath(db_path))
        self.db_path = os.path.abspath(db_path)
        self.photo_data_dir = photo_data_dir
        self.thumbnail_dir = os.path.join(photo_data_dir, "thumbnails")


def _resolve_settings(db_path: Optional[str]) -> Any:
    if db_path:
        return _CliSettings(db_path)

    from config import get_settings

    return get_settings()


def _siglip_dependency_available() -> bool:
    try:
        from infra.image.clip_encoder import is_available

        return bool(is_available())
    except Exception:
        return False


def _generate_siglip_tags(file_ids: List[int]) -> Dict[int, List[str]]:
    from business.image_recognition.tag_generator import generate_tags_batch

    return generate_tags_batch(file_ids)


def _select_siglip_candidates(conn: sqlite3.Connection, limit: int) -> tuple[list[Dict[str, Any]], int]:
    rows = conn.execute(
        """
        SELECT
            f.id AS file_id,
            f.file_path AS source_path,
            pm.thumbnail_path AS thumbnail_path,
            CASE WHEN EXISTS (
                SELECT 1
                FROM photo_tags pt
                WHERE pt.file_id = f.id AND pt.source = ?
            ) THEN 1 ELSE 0 END AS has_siglip_tags
        FROM files f
        JOIN photo_metadata pm ON pm.file_id = f.id
        WHERE f.is_image = 1
          AND pm.thumbnail_path IS NOT NULL
          AND pm.thumbnail_path != '__FAILED__'
          AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
        ORDER BY f.id
        """,
        (SIGLIP_SOURCE,),
    ).fetchall()

    selected: List[Dict[str, Any]] = []
    skipped = 0
    for row in rows:
        if row["has_siglip_tags"]:
            skipped += 1
            continue
        thumb_path = row["thumbnail_path"]
        if not thumb_path or not os.path.exists(thumb_path):
            skipped += 1
            continue
        selected.append(
            {
                "file_id": row["file_id"],
                "source_path": row["source_path"],
                "thumbnail_path": thumb_path,
                "current_status": "ready_for_siglip",
            }
        )
        if len(selected) >= limit:
            break

    return selected, skipped


def _build_file_result(
    item: Dict[str, Any],
    status: str,
    reason: Optional[str] = None,
    error: Optional[str] = None,
    labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    result = {
        "file_id": item["file_id"],
        "source_path": item["source_path"],
        "thumbnail_path": item["thumbnail_path"],
        "current_status": item["current_status"],
        "status": status,
    }
    if reason is not None:
        result["reason"] = reason
    if error is not None:
        result["error"] = error
    if labels is not None:
        result["labels"] = labels
    return result


def run_ai_recognition_validation(
    db_path: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = True,
) -> Dict[str, Any]:
    settings = _resolve_settings(db_path)
    db_path = os.path.abspath(settings.db_path)
    dependency_available = _siglip_dependency_available()

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        selected, skipped = _select_siglip_candidates(conn, max(int(limit), 0))
        result: Dict[str, Any] = {
            "dry_run": dry_run,
            "mode": "siglip_tag_validation",
            "db_path": db_path,
            "limit": max(int(limit), 0),
            "selected": len(selected),
            "skipped": skipped,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "model_loaded": False,
            "db_updated": 0,
            "dependency_available": dependency_available,
            "warnings": [],
            "file_results": [],
        }

        if not selected:
            result["warnings"].append("No eligible photos were selected for SigLIP validation.")
            return result

        if dry_run:
            result["file_results"] = [
                _build_file_result(item, status="planned", reason="dry-run only") for item in selected
            ]
            if not dependency_available:
                result["warnings"].append(
                    "SigLIP dependency is not currently importable; dry-run stayed read-only and skipped model loading."
                )
            return result

        if not dependency_available:
            result["warnings"].append(
                "SigLIP dependency is not currently importable; aborting apply without loading a model or writing the database."
            )
            return result

        try:
            tags_by_file = _generate_siglip_tags([item["file_id"] for item in selected])
            result["model_loaded"] = True
        except Exception as exc:
            result["failed"] = len(selected)
            result["processed"] = len(selected)
            for item in selected:
                result["file_results"].append(
                    _build_file_result(item, status="failed", error=str(exc), reason="tag generation crashed")
                )
            result["warnings"].append(f"SigLIP batch generation failed before any DB write: {exc}")
            return result

        pending_rows: List[tuple[int, str, str]] = []
        for item in selected:
            result["processed"] += 1
            labels = tags_by_file.get(item["file_id"])
            if labels is None:
                result["failed"] += 1
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="failed",
                        reason="no_result",
                        error="generate_tags_batch returned no result for this file_id",
                    )
                )
                continue

            result["succeeded"] += 1
            for label in labels:
                pending_rows.append((item["file_id"], label, SIGLIP_SOURCE))
            result["file_results"].append(
                _build_file_result(
                    item,
                    status="succeeded",
                    reason="tags_generated",
                    labels=labels,
                )
            )

        if pending_rows:
            conn.executemany(
                "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
                pending_rows,
            )
            conn.commit()
            result["db_updated"] = len(pending_rows)

        return result
    finally:
        conn.close()


def format_ai_recognition_text(result: Dict[str, Any]) -> str:
    lines = [
        "AI Recognition Validation Report",
        f"db_path: {result['db_path']}",
        f"dry_run: {result['dry_run']}",
        f"mode: {result['mode']}",
        f"limit: {result['limit']}",
        f"selected: {result['selected']}",
        f"skipped: {result['skipped']}",
        f"processed: {result['processed']}",
        f"succeeded: {result['succeeded']}",
        f"failed: {result['failed']}",
        f"model_loaded: {result['model_loaded']}",
        f"db_updated: {result['db_updated']}",
        f"dependency_available: {result['dependency_available']}",
    ]
    if result.get("warnings"):
        lines.append("warnings:")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
    if result.get("file_results"):
        lines.append("per-file results:")
        for item in result["file_results"]:
            lines.append(
                f"- file_id={item['file_id']} status={item['status']} current_status={item['current_status']}"
            )
            lines.append(f"  source_path: {item['source_path']}")
            lines.append(f"  thumbnail_path: {item['thumbnail_path']}")
            if item.get("reason"):
                lines.append(f"  reason: {item['reason']}")
            if item.get("labels") is not None:
                lines.append(f"  labels: {item['labels']}")
            if item.get("error"):
                lines.append(f"  error: {item['error']}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Validate the local AI recognition path in small batches.")
    parser.add_argument("--db-path", help="Optional path to the SQLite database to inspect.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum number of eligible photos to process.")
    parser.add_argument("--dry-run", action="store_true", help="Preview selected file_ids only. No model load, DB write, or network access.")
    parser.add_argument("--apply", action="store_true", help="Actually run a small local SigLIP tagging batch and write photo_tags rows.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print structured JSON output only.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    dry_run = True if not args.apply else False
    if args.dry_run:
        dry_run = True

    result = run_ai_recognition_validation(
        db_path=args.db_path,
        limit=max(args.limit, 0),
        dry_run=dry_run,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_ai_recognition_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
