import argparse
from collections import Counter, defaultdict
import json
import os
import random
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


DEFAULT_LIMIT = 50
DEFAULT_SAMPLE_MODE = "sequential"
VALID_SOURCES = {"path", "siglip", "all"}
DATE_PATTERN = re.compile(r"(20\d{2})[._-]?([01]\d)[._-]?([0-3]\d)")
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9._+-]*")
ASCII_NOISE = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "bmp",
    "webp",
    "mov",
    "mp4",
    "avi",
    "no",
    "gb",
    "mb",
    "kb",
    "tb",
    "p",
    "v",
    "photos",
    "waxzml",
    "dcim",
    "mobile",
    "mobilebackup",
    "moments",
    "sm-n9600",
    "vol",
}
PATH_NOISE_TAGS = {
    "no",
    "gb",
    "mb",
    "kb",
    "tb",
    "p",
    "v",
    "photos",
    "waxzml",
    "dcim",
    "mobile",
    "mobilebackup",
    "moments",
    "sm-n9600",
    "vol",
    "p-3",
    "p-4",
    "p-7",
    "p+28v",
}
CAPACITY_TOKEN_PATTERN = re.compile(r"^\d+(?:\.\d+)?(?:gb|mb|kb|tb)$", re.IGNORECASE)
COUNT_TOKEN_PATTERN = re.compile(r"^\d+[pv](?:\+\d+[pv])*$", re.IGNORECASE)
BROKEN_COUNT_FRAGMENT_PATTERN = re.compile(r"^p[-+]?\d+[a-z0-9]*$", re.IGNORECASE)
PURE_NUMBER_PATTERN = re.compile(r"^\d+$")
NO_INDEX_PATTERN = re.compile(r"^no[._-]?\d+[a-z0-9]*$", re.IGNORECASE)
COUNT_SIZE_FRAGMENT_PATTERN = re.compile(
    r"^\d+(?:p|v)(?:\d*(?:p|v))?(?:[-+]\d+(?:\.\d+)?[a-z]*)+$",
    re.IGNORECASE,
)


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


def _generate_siglip_tags(file_ids: List[int], settings: Any) -> Dict[str, Any]:
    from business.image_recognition.tag_generator import generate_tags_batch

    return generate_tags_batch(file_ids, settings=settings, return_diagnostics=True)


def _pick_candidates(
    candidates: List[Dict[str, Any]],
    limit: int,
    sample_mode: str,
    seed: Optional[int],
) -> List[Dict[str, Any]]:
    limit = max(int(limit), 0)
    if limit == 0 or not candidates:
        return []

    if sample_mode == "sequential":
        return candidates[:limit]

    rng = random.Random(seed)
    if sample_mode == "random":
        picked = list(candidates)
        rng.shuffle(picked)
        return picked[:limit]

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        grouped[item["source_folder"]].append(item)

    folder_keys = list(grouped.keys())
    rng.shuffle(folder_keys)
    for folder in folder_keys:
        rng.shuffle(grouped[folder])

    selected: List[Dict[str, Any]] = []
    while folder_keys and len(selected) < limit:
        next_round: List[str] = []
        for folder in folder_keys:
            bucket = grouped[folder]
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))
            if bucket:
                next_round.append(folder)
        folder_keys = next_round
    return selected


def _select_candidates(
    conn: sqlite3.Connection,
    limit: int,
    source: str,
    sample_mode: str,
    seed: Optional[int],
) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT
            f.id AS file_id,
            f.file_path AS source_path,
            pm.thumbnail_path AS thumbnail_path,
            pm.is_duplicate_of AS is_duplicate_of,
            fc.category AS folder_category,
            CASE WHEN EXISTS (
                SELECT 1 FROM photo_tags pt WHERE pt.file_id = f.id AND pt.source = 'path'
            ) THEN 1 ELSE 0 END AS has_path_tags,
            CASE WHEN EXISTS (
                SELECT 1 FROM photo_tags pt WHERE pt.file_id = f.id AND pt.source = 'siglip'
            ) THEN 1 ELSE 0 END AS has_siglip_tags
        FROM files f
        JOIN photo_metadata pm ON pm.file_id = f.id
        LEFT JOIN folder_categories fc ON fc.folder_path = f.folder_path
        WHERE f.is_image = 1
          AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
        ORDER BY f.id
        """
    ).fetchall()

    candidate_rows: List[Dict[str, Any]] = []
    invalid_thumbnail_skipped = 0
    already_tagged_skipped = 0

    for row in rows:
        thumb_path = row["thumbnail_path"]
        if not thumb_path or thumb_path == "__FAILED__" or not os.path.exists(thumb_path):
            invalid_thumbnail_skipped += 1
            continue

        item = {
            "file_id": row["file_id"],
            "source_path": row["source_path"],
            "thumbnail_path": thumb_path,
            "source_folder": os.path.dirname(row["source_path"]) or "",
            "folder_category": row["folder_category"],
            "has_path_tags": bool(row["has_path_tags"]),
            "has_siglip_tags": bool(row["has_siglip_tags"]),
        }

        if source == "path" and item["has_path_tags"]:
            already_tagged_skipped += 1
            continue
        if source == "siglip" and item["has_siglip_tags"]:
            already_tagged_skipped += 1
            continue
        if source == "all" and item["has_path_tags"] and item["has_siglip_tags"]:
            already_tagged_skipped += 1
            continue

        candidate_rows.append(item)

    selected = _pick_candidates(candidate_rows, limit=limit, sample_mode=sample_mode, seed=seed)
    return {
        "candidate_count": len(candidate_rows),
        "selected": selected,
        "already_tagged_skipped": already_tagged_skipped,
        "invalid_thumbnail_skipped": invalid_thumbnail_skipped,
    }


def _clean_path_token(token: str) -> Optional[str]:
    normalized = token.strip()
    if not normalized:
        return None
    if normalized.startswith("category:"):
        return normalized
    if PURE_NUMBER_PATTERN.match(normalized):
        return None
    if normalized.isascii():
        lowered = normalized.lower()
        if lowered in ASCII_NOISE:
            return None
        if CAPACITY_TOKEN_PATTERN.match(lowered):
            return None
        if COUNT_TOKEN_PATTERN.match(lowered):
            return None
        if BROKEN_COUNT_FRAGMENT_PATTERN.match(lowered):
            return None
        if NO_INDEX_PATTERN.match(lowered):
            return None
        if COUNT_SIZE_FRAGMENT_PATTERN.match(lowered):
            return None
        return lowered
    return normalized


def _extract_path_tags(item: Dict[str, Any]) -> Dict[str, List[str]]:
    source_path = item["source_path"]
    raw_tags: List[str] = []
    cleaned_tags: List[str] = []
    filtered_tags: List[str] = []
    raw_seen: set[str] = set()
    cleaned_seen: set[str] = set()

    def add_raw(value: Optional[str]) -> None:
        if not value:
            return
        normalized = value.strip()
        if not normalized or normalized in raw_seen:
            return
        raw_seen.add(normalized)
        raw_tags.append(normalized)

    if item.get("folder_category") == 1:
        add_raw("category:life")
    elif item.get("folder_category") == 2:
        add_raw("category:sample")

    date_match = DATE_PATTERN.search(source_path)
    if date_match:
        year, month, day = date_match.groups()
        add_raw(f"date:{year}-{month}-{day}")
        add_raw(f"year:{year}")

    folder_parts: List[str] = []
    current = os.path.dirname(source_path)
    for _ in range(7):
        if not current:
            break
        folder_parts.append(os.path.basename(current))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    for segment in folder_parts:
        for token in TOKEN_PATTERN.findall(segment):
            add_raw(token)

    for token in raw_tags:
        cleaned = _clean_path_token(token)
        if cleaned is None:
            filtered_tags.append(token)
            continue
        if cleaned not in cleaned_seen:
            cleaned_seen.add(cleaned)
            cleaned_tags.append(cleaned)

    return {
        "raw_tags": raw_tags[:20],
        "cleaned_tags": cleaned_tags[:12],
        "filtered_tags": filtered_tags[:20],
    }


def _build_file_result(
    item: Dict[str, Any],
    source: str,
    status: str,
    reason: Optional[str] = None,
    tags: Optional[List[str]] = None,
    error: Optional[str] = None,
    raw_tags: Optional[List[str]] = None,
    cleaned_tags: Optional[List[str]] = None,
    filtered_tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    payload = {
        "file_id": item["file_id"],
        "source_path": item["source_path"],
        "thumbnail_path": item["thumbnail_path"],
        "source_folder": item["source_folder"],
        "source": source,
        "status": status,
    }
    if reason is not None:
        payload["reason"] = reason
    if tags is not None:
        payload["tags"] = tags
    if error is not None:
        payload["error"] = error
    if raw_tags is not None:
        payload["raw_tags"] = raw_tags
    if cleaned_tags is not None:
        payload["cleaned_tags"] = cleaned_tags
    if filtered_tags is not None:
        payload["filtered_tags"] = filtered_tags
    return payload


def _apply_path_labels(
    conn: sqlite3.Connection,
    selected: List[Dict[str, Any]],
    dry_run: bool,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    pending_rows: List[tuple[int, str, str]] = []
    tag_counter: Counter[str] = Counter()
    processed = succeeded = failed = db_updated = 0
    files_with_tags = files_without_tags = no_tags_count = 0

    for item in selected:
        processed += 1
        tag_payload = _extract_path_tags(item)
        tags = tag_payload["cleaned_tags"]
        if not tags:
            succeeded += 1
            files_without_tags += 1
            no_tags_count += 1
            results.append(
                _build_file_result(
                    item,
                    "path",
                    "succeeded_no_tags",
                    reason="no_path_tags",
                    tags=[],
                    raw_tags=tag_payload["raw_tags"],
                    cleaned_tags=tag_payload["cleaned_tags"],
                    filtered_tags=tag_payload["filtered_tags"],
                )
            )
            continue

        succeeded += 1
        files_with_tags += 1
        results.append(
            _build_file_result(
                item,
                "path",
                "succeeded_with_tags",
                reason="path_tags_generated",
                tags=tags,
                raw_tags=tag_payload["raw_tags"],
                cleaned_tags=tag_payload["cleaned_tags"],
                filtered_tags=tag_payload["filtered_tags"],
            )
        )
        for tag in tags:
            pending_rows.append((item["file_id"], tag, "path"))
            tag_counter[tag] += 1

    if pending_rows and not dry_run:
        before_changes = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            pending_rows,
        )
        conn.commit()
        db_updated = conn.total_changes - before_changes

    return {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "db_updated": db_updated,
        "tags_inserted": db_updated,
        "files_with_tags": files_with_tags,
        "files_without_tags": files_without_tags,
        "no_tags_count": no_tags_count,
        "top_tags": tag_counter,
        "file_results": results,
        "warnings": [],
    }


def _apply_siglip_labels(
    conn: sqlite3.Connection,
    selected: List[Dict[str, Any]],
    settings: Any,
    dry_run: bool,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    warnings: List[str] = []
    processed = succeeded = failed = db_updated = 0
    files_with_tags = files_without_tags = no_tags_count = 0
    tag_counter: Counter[str] = Counter()
    pending_rows: List[tuple[int, str, str]] = []
    encoded_count = 0
    encode_failed_count = 0
    encode_error_sample: List[Dict[str, Any]] = []

    if not _siglip_dependency_available():
        warnings.append("SigLIP dependency unavailable; source=siglip did not run.")
        for item in selected:
            processed += 1
            failed += 1
            results.append(_build_file_result(item, "siglip", "failed_dependency", reason="dependency_unavailable"))
        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "db_updated": 0,
            "tags_inserted": 0,
            "files_with_tags": 0,
            "files_without_tags": 0,
            "no_tags_count": 0,
            "top_tags": tag_counter,
            "file_results": results,
            "warnings": warnings,
            "encoded_count": 0,
            "encode_failed_count": len(selected),
            "encode_error_sample": [],
        }

    try:
        generation = _generate_siglip_tags([item["file_id"] for item in selected], settings=settings)
    except Exception as exc:
        warnings.append(f"SigLIP generation failed: {exc}")
        for item in selected:
            processed += 1
            failed += 1
            results.append(_build_file_result(item, "siglip", "failed_model", reason="model_load_failed", error=str(exc)))
        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "db_updated": 0,
            "tags_inserted": 0,
            "files_with_tags": 0,
            "files_without_tags": 0,
            "no_tags_count": 0,
            "top_tags": tag_counter,
            "file_results": results,
            "warnings": warnings,
            "encoded_count": 0,
            "encode_failed_count": len(selected),
            "encode_error_sample": [],
        }

    tags_by_file = generation.get("tags_by_file", {})
    encoded_count = generation.get("encoded_count", 0)
    encode_failed_count = generation.get("encode_failed_count", 0)
    encode_errors = generation.get("encode_errors", [])
    encode_error_sample = encode_errors[:5]
    error_by_file = {entry.get("file_id"): entry for entry in encode_errors}

    for item in selected:
        processed += 1
        file_id = item["file_id"]
        if file_id in tags_by_file:
            tags = tags_by_file[file_id]
            if not tags:
                succeeded += 1
                files_without_tags += 1
                no_tags_count += 1
                results.append(_build_file_result(item, "siglip", "succeeded_no_tags", reason="no_tags_above_threshold", tags=[]))
                continue

            succeeded += 1
            files_with_tags += 1
            results.append(_build_file_result(item, "siglip", "succeeded_with_tags", reason="siglip_tags_generated", tags=tags))
            for tag in tags:
                pending_rows.append((file_id, tag, "siglip"))
                tag_counter[tag] += 1
            continue

        failed += 1
        error_entry = error_by_file.get(file_id)
        if error_entry:
            reason = error_entry.get("reason", "thumbnail_load_failed")
            status = "failed_thumbnail" if reason in {"thumbnail_not_found", "image_open_failed", "preprocess_failed"} else "failed_model"
            results.append(_build_file_result(item, "siglip", status, reason=reason, error=error_entry.get("error")))
        else:
            results.append(_build_file_result(item, "siglip", "failed_unknown", reason="failed_unknown"))

    if pending_rows and not dry_run:
        before_changes = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            pending_rows,
        )
        conn.commit()
        db_updated = conn.total_changes - before_changes

    return {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "db_updated": db_updated,
        "tags_inserted": db_updated,
        "files_with_tags": files_with_tags,
        "files_without_tags": files_without_tags,
        "no_tags_count": no_tags_count,
        "top_tags": tag_counter,
        "file_results": results,
        "warnings": warnings,
        "encoded_count": encoded_count,
        "encode_failed_count": encode_failed_count,
        "encode_error_sample": encode_error_sample,
    }


def _merge_counters(base: Counter[str], extra: Counter[str]) -> Counter[str]:
    merged = Counter(base)
    merged.update(extra)
    return merged


def _fetch_current_top_path_tags(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tag, COUNT(*) AS tag_count
        FROM photo_tags
        WHERE source = 'path'
        GROUP BY tag
        ORDER BY tag_count DESC, tag ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{"tag": row["tag"], "count": row["tag_count"]} for row in rows]


def run_path_noise_cleanup(
    db_path: Optional[str] = None,
    dry_run: bool = True,
    sample_limit: int = 5,
) -> Dict[str, Any]:
    settings = _resolve_settings(db_path)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in PATH_NOISE_TAGS)
        rows = conn.execute(
            f"""
            SELECT tag, COUNT(*) AS tag_count
            FROM photo_tags
            WHERE source = 'path'
              AND LOWER(tag) IN ({placeholders})
            GROUP BY tag
            ORDER BY tag_count DESC, tag ASC
            """,
            tuple(sorted(PATH_NOISE_TAGS)),
        ).fetchall()

        cleanup_items: List[Dict[str, Any]] = []
        total_matches = 0
        for row in rows:
            tag = row["tag"]
            sample_rows = conn.execute(
                """
                SELECT file_id
                FROM photo_tags
                WHERE source = 'path' AND tag = ?
                ORDER BY file_id
                LIMIT ?
                """,
                (tag, max(int(sample_limit), 1)),
            ).fetchall()
            count = row["tag_count"]
            total_matches += count
            cleanup_items.append(
                {
                    "tag": tag,
                    "count": count,
                    "sample_file_ids": [sample["file_id"] for sample in sample_rows],
                }
            )

        deleted_rows = 0
        if cleanup_items and not dry_run:
            before_changes = conn.total_changes
            conn.execute(
                f"""
                DELETE FROM photo_tags
                WHERE source = 'path'
                  AND LOWER(tag) IN ({placeholders})
                """,
                tuple(sorted(PATH_NOISE_TAGS)),
            )
            conn.commit()
            deleted_rows = conn.total_changes - before_changes

        return {
            "mode": "cleanup_noise",
            "source": "path",
            "dry_run": dry_run,
            "db_path": os.path.abspath(settings.db_path),
            "noise_tags": sorted(PATH_NOISE_TAGS),
            "matched_tag_count": len(cleanup_items),
            "matched_row_count": total_matches,
            "deleted_rows": deleted_rows,
            "cleanup_items": cleanup_items,
            "top_tags_after_cleanup": _fetch_current_top_path_tags(conn),
            "warnings": [],
        }
    finally:
        conn.close()


def run_ai_labeling(
    db_path: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = True,
    source: str = "path",
    sample_mode: str = DEFAULT_SAMPLE_MODE,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    if source not in VALID_SOURCES:
        raise ValueError(f"Unsupported source: {source}")

    settings = _resolve_settings(db_path)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        selection = _select_candidates(
            conn,
            max(int(limit), 0),
            source=source,
            sample_mode=sample_mode,
            seed=seed,
        )
        selected = selection["selected"]
        folder_samples = sorted({item["source_folder"] for item in selected if item["source_folder"]})[:10]
        summary: Dict[str, Any] = {
            "source": source,
            "dry_run": dry_run,
            "db_path": os.path.abspath(settings.db_path),
            "limit": max(int(limit), 0),
            "sample_mode": sample_mode,
            "seed": seed,
            "candidate_count": selection["candidate_count"],
            "selected": len(selected),
            "selected_folder_count": len({item["source_folder"] for item in selected if item["source_folder"]}),
            "selected_source_folder_samples": folder_samples,
            "already_tagged_skipped": selection["already_tagged_skipped"],
            "invalid_thumbnail_skipped": selection["invalid_thumbnail_skipped"],
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "tags_inserted": 0,
            "files_with_tags": 0,
            "files_without_tags": 0,
            "top_tags": [],
            "db_updated": 0,
            "warnings": [],
            "file_results": [],
        }

        if not selected:
            summary["warnings"].append("No eligible photos were selected for labeling.")
            return summary

        top_tags_counter: Counter[str] = Counter()

        if source in {"path", "all"}:
            path_result = _apply_path_labels(conn, selected, dry_run=dry_run)
            summary["processed"] += path_result["processed"]
            summary["succeeded"] += path_result["succeeded"]
            summary["failed"] += path_result["failed"]
            summary["tags_inserted"] += path_result["tags_inserted"]
            summary["files_with_tags"] += path_result["files_with_tags"]
            summary["files_without_tags"] += path_result["files_without_tags"]
            summary["db_updated"] += path_result["db_updated"]
            summary["warnings"].extend(path_result["warnings"])
            summary["file_results"].extend(path_result["file_results"])
            top_tags_counter = _merge_counters(top_tags_counter, path_result["top_tags"])

        if source in {"siglip", "all"}:
            siglip_result = _apply_siglip_labels(conn, selected, settings=settings, dry_run=dry_run)
            summary["processed"] += siglip_result["processed"]
            summary["succeeded"] += siglip_result["succeeded"]
            summary["failed"] += siglip_result["failed"]
            summary["tags_inserted"] += siglip_result["tags_inserted"]
            summary["files_with_tags"] += siglip_result["files_with_tags"]
            summary["files_without_tags"] += siglip_result["files_without_tags"]
            summary["db_updated"] += siglip_result["db_updated"]
            summary["warnings"].extend(siglip_result["warnings"])
            summary["file_results"].extend(siglip_result["file_results"])
            top_tags_counter = _merge_counters(top_tags_counter, siglip_result["top_tags"])
            summary["encoded_count"] = siglip_result["encoded_count"]
            summary["encode_failed_count"] = siglip_result["encode_failed_count"]
            summary["encode_error_sample"] = siglip_result["encode_error_sample"]

        summary["top_tags"] = [
            {"tag": tag, "count": count}
            for tag, count in top_tags_counter.most_common(10)
        ]
        return summary
    finally:
        conn.close()


def format_ai_labeling_text(result: Dict[str, Any]) -> str:
    if result.get("mode") == "cleanup_noise":
        lines = [
            "Path Tag Cleanup Report",
            f"db_path: {result['db_path']}",
            f"source: {result['source']}",
            f"dry_run: {result['dry_run']}",
            f"matched_tag_count: {result['matched_tag_count']}",
            f"matched_row_count: {result['matched_row_count']}",
            f"deleted_rows: {result['deleted_rows']}",
            f"top_tags_after_cleanup: {result['top_tags_after_cleanup']}",
        ]
        if result.get("cleanup_items"):
            lines.append("cleanup items:")
            for item in result["cleanup_items"]:
                lines.append(f"- tag={item['tag']} count={item['count']} sample_file_ids={item['sample_file_ids']}")
        if result.get("warnings"):
            lines.append("warnings:")
            for warning in result["warnings"]:
                lines.append(f"- {warning}")
        return "\n".join(lines)

    lines = [
        "AI Labeling Report",
        f"db_path: {result['db_path']}",
        f"source: {result['source']}",
        f"dry_run: {result['dry_run']}",
        f"limit: {result['limit']}",
        f"sample_mode: {result['sample_mode']}",
        f"seed: {result['seed']}",
        f"candidate_count: {result['candidate_count']}",
        f"selected: {result['selected']}",
        f"selected_folder_count: {result['selected_folder_count']}",
        f"selected_source_folder_samples: {result['selected_source_folder_samples']}",
        f"already_tagged_skipped: {result['already_tagged_skipped']}",
        f"invalid_thumbnail_skipped: {result['invalid_thumbnail_skipped']}",
        f"processed: {result['processed']}",
        f"succeeded: {result['succeeded']}",
        f"failed: {result['failed']}",
        f"tags_inserted: {result['tags_inserted']}",
        f"files_with_tags: {result['files_with_tags']}",
        f"files_without_tags: {result['files_without_tags']}",
        f"top_tags: {result['top_tags']}",
        f"db_updated: {result['db_updated']}",
    ]
    if "encoded_count" in result:
        lines.append(f"encoded_count: {result['encoded_count']}")
        lines.append(f"encode_failed_count: {result['encode_failed_count']}")
        lines.append(f"encode_error_sample: {result['encode_error_sample']}")
    if result.get("warnings"):
        lines.append("warnings:")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
    if result.get("file_results"):
        lines.append("per-file results:")
        for item in result["file_results"]:
            lines.append(f"- file_id={item['file_id']} source={item['source']} status={item['status']}")
            lines.append(f"  source_path: {item['source_path']}")
            lines.append(f"  thumbnail_path: {item['thumbnail_path']}")
            lines.append(f"  source_folder: {item['source_folder']}")
            if item.get("reason") is not None:
                lines.append(f"  reason: {item['reason']}")
            if item.get("tags") is not None:
                lines.append(f"  tags: {item['tags']}")
            if item.get("raw_tags") is not None:
                lines.append(f"  raw_tags: {item['raw_tags']}")
            if item.get("cleaned_tags") is not None:
                lines.append(f"  cleaned_tags: {item['cleaned_tags']}")
            if item.get("filtered_tags") is not None:
                lines.append(f"  filtered_tags: {item['filtered_tags']}")
            if item.get("error") is not None:
                lines.append(f"  error: {item['error']}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run stable small-batch AI labeling without defaulting to heavy models.")
    parser.add_argument("--db-path", help="Optional path to the SQLite database to inspect.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum number of eligible photos to process.")
    parser.add_argument("--dry-run", action="store_true", help="Preview selected file_ids only. No model load, DB write, or network access.")
    parser.add_argument("--apply", action="store_true", help="Actually write photo_tags rows for the selected source.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print structured JSON output only.")
    parser.add_argument("--source", choices=["path", "siglip", "all"], default="path", help="Label source to run. Default is stable path tags.")
    parser.add_argument("--sample-mode", choices=["sequential", "random", "folder-diverse"], default=DEFAULT_SAMPLE_MODE, help="How to sample candidates.")
    parser.add_argument("--seed", type=int, help="Optional random seed for random/folder-diverse sampling.")
    parser.add_argument("--cleanup-noise", action="store_true", help="Preview or remove historical path-tag noise from photo_tags where source='path'.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    dry_run = not args.apply
    if args.dry_run:
        dry_run = True

    if args.cleanup_noise:
        if args.source != "path":
            raise SystemExit("--cleanup-noise currently only supports --source path")
        result = run_path_noise_cleanup(
            db_path=args.db_path,
            dry_run=dry_run,
        )
    else:
        result = run_ai_labeling(
            db_path=args.db_path,
            limit=max(args.limit, 0),
            dry_run=dry_run,
            source=args.source,
            sample_mode=args.sample_mode,
            seed=args.seed,
        )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_ai_labeling_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
