import argparse
from contextlib import contextmanager
from collections import Counter, defaultdict
import json
import os
import random
import sqlite3
import sys
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


DEFAULT_LIMIT = 10
SIGLIP_SOURCE = "siglip"
DEFAULT_SAMPLE_MODE = "sequential"


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


@contextmanager
def _temporary_thumbnail_settings(settings: Any):
    try:
        from infra.image import thumbnail_loader
    except Exception:
        yield
        return

    original_get_settings = thumbnail_loader.get_settings
    original_loader = thumbnail_loader._loader
    try:
        thumbnail_loader.get_settings = lambda: settings
        if original_loader is not None:
            try:
                original_loader.clear()
            except Exception:
                pass
        thumbnail_loader._loader = None
        yield
    finally:
        thumbnail_loader.get_settings = original_get_settings
        try:
            active_loader = thumbnail_loader._loader
            if active_loader is not None:
                active_loader.clear()
        except Exception:
            pass
        thumbnail_loader._loader = None
        if original_loader is not None:
            thumbnail_loader._loader = original_loader


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

    folders = list(grouped.keys())
    rng.shuffle(folders)
    for folder in folders:
        rng.shuffle(grouped[folder])

    selected: List[Dict[str, Any]] = []
    while folders and len(selected) < limit:
        next_round: List[str] = []
        for folder in folders:
            bucket = grouped[folder]
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))
            if bucket:
                next_round.append(folder)
        folders = next_round
    return selected


def _select_siglip_candidates(
    conn: sqlite3.Connection,
    limit: int,
    sample_mode: str = DEFAULT_SAMPLE_MODE,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
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

    candidates: List[Dict[str, Any]] = []
    already_tagged_skipped = 0
    invalid_thumbnail_skipped = 0
    for row in rows:
        if row["has_siglip_tags"]:
            already_tagged_skipped += 1
            continue
        thumb_path = row["thumbnail_path"]
        if not thumb_path or not os.path.exists(thumb_path):
            invalid_thumbnail_skipped += 1
            continue
        candidates.append(
            {
                "file_id": row["file_id"],
                "source_path": row["source_path"],
                "thumbnail_path": thumb_path,
                "source_folder": os.path.dirname(row["source_path"]) or "",
                "current_status": "ready_for_siglip",
            }
        )

    selected = _pick_candidates(candidates, limit=limit, sample_mode=sample_mode, seed=seed)
    return {
        "candidate_count": len(candidates),
        "selected": selected,
        "already_tagged_skipped": already_tagged_skipped,
        "invalid_thumbnail_skipped": invalid_thumbnail_skipped,
    }


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
        "source_folder": item["source_folder"],
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


def _normalize_path_key(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    return os.path.normcase(os.path.abspath(os.path.normpath(value)))


def _iter_result_entries(raw_results: Any) -> tuple[List[tuple[Any, Any]], List[str]]:
    warnings: List[str] = []
    entries: List[tuple[Any, Any]] = []

    if isinstance(raw_results, dict):
        return list(raw_results.items()), warnings

    if isinstance(raw_results, (list, tuple)):
        for item in raw_results:
            if isinstance(item, dict):
                if "tags" not in item:
                    warnings.append(f"ignored result dict without tags key: {item!r}")
                    continue
                key = item.get("file_id", item.get("path", item.get("thumbnail_path", item.get("source_path"))))
                entries.append((key, item.get("tags")))
                continue
            if isinstance(item, (list, tuple)) and len(item) == 2:
                entries.append((item[0], item[1]))
                continue
            warnings.append(f"ignored unsupported result entry: {item!r}")
        return entries, warnings

    warnings.append("generate_tags_batch returned an unsupported non-mapping result; unable to map outputs to file_id.")
    return entries, warnings


def _normalize_tag_results(
    raw_results: Any,
    selected: List[Dict[str, Any]],
) -> tuple[Dict[int, Optional[List[str]]], List[str], List[Any]]:
    warnings: List[str] = []
    normalized: Dict[int, Optional[List[str]]] = {}
    unmapped_keys: List[Any] = []

    entries, entry_warnings = _iter_result_entries(raw_results)
    warnings.extend(entry_warnings)
    if not entries and not isinstance(raw_results, dict):
        return normalized, warnings, unmapped_keys
    if isinstance(raw_results, dict) and len(raw_results) == 0:
        return normalized, warnings, unmapped_keys

    by_thumbnail_path = {
        _normalize_path_key(item["thumbnail_path"]): item["file_id"] for item in selected
    }
    by_source_path = {
        _normalize_path_key(item["source_path"]): item["file_id"] for item in selected
    }
    by_file_id = {item["file_id"]: item["file_id"] for item in selected}
    by_file_id_str = {str(item["file_id"]): item["file_id"] for item in selected}

    for key, value in entries:
        mapped_file_id: Optional[int] = None
        if isinstance(key, int) and key in by_file_id:
            mapped_file_id = key
        elif isinstance(key, str):
            if key in by_file_id_str:
                mapped_file_id = by_file_id_str[key]
            elif key.isdigit():
                mapped_file_id = by_file_id.get(int(key))
            if mapped_file_id is None:
                mapped_file_id = by_thumbnail_path.get(_normalize_path_key(key))
            if mapped_file_id is None:
                mapped_file_id = by_source_path.get(_normalize_path_key(key))

        if mapped_file_id is None:
            warnings.append(f"unmapped tag result key ignored: {key!r}")
            unmapped_keys.append(key)
            continue

        normalized[mapped_file_id] = value

    return normalized, warnings, unmapped_keys


def run_ai_recognition_validation(
    db_path: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = True,
    sample_mode: str = DEFAULT_SAMPLE_MODE,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    settings = _resolve_settings(db_path)
    db_path = os.path.abspath(settings.db_path)
    dependency_available = _siglip_dependency_available()

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        selection = _select_siglip_candidates(
            conn,
            max(int(limit), 0),
            sample_mode=sample_mode,
            seed=seed,
        )
        selected = selection["selected"]
        selected_folders = sorted({item["source_folder"] for item in selected if item["source_folder"]})
        result: Dict[str, Any] = {
            "dry_run": dry_run,
            "mode": "siglip_tag_validation",
            "db_path": db_path,
            "limit": max(int(limit), 0),
            "sample_mode": sample_mode,
            "seed": seed,
            "candidate_count": selection["candidate_count"],
            "selected": len(selected),
            "selected_folder_count": len(selected_folders),
            "selected_source_folder_samples": selected_folders[:10],
            "already_tagged_skipped": selection["already_tagged_skipped"],
            "invalid_thumbnail_skipped": selection["invalid_thumbnail_skipped"],
            "skipped": selection["already_tagged_skipped"] + selection["invalid_thumbnail_skipped"],
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "model_loaded": False,
            "db_updated": 0,
            "dependency_available": dependency_available,
            "tags_inserted": 0,
            "files_with_tags": 0,
            "files_without_tags": 0,
            "no_tags_count": 0,
            "failed_count": 0,
            "top_tags": [],
            "result_type": None,
            "result_len": None,
            "result_key_sample": [],
            "candidate_file_id_sample": [item["file_id"] for item in selected[:5]],
            "candidate_thumbnail_path_sample": [item["thumbnail_path"] for item in selected[:5]],
            "candidate_source_path_sample": [item["source_path"] for item in selected[:5]],
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

        ready_items: List[Dict[str, Any]] = []
        for item in selected:
            if not os.path.exists(item["thumbnail_path"]):
                result["processed"] += 1
                result["failed"] += 1
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="failed_missing_thumbnail",
                        reason="thumbnail_missing_before_inference",
                        error="thumbnail_path no longer exists at apply time",
                    )
                )
            else:
                ready_items.append(item)

        if not ready_items:
            result["warnings"].append("All selected items were skipped because thumbnails were missing at apply time.")
            return result

        try:
            with _temporary_thumbnail_settings(settings):
                raw_tag_results = _generate_siglip_tags([item["file_id"] for item in ready_items])
            result["model_loaded"] = True
            result["result_type"] = type(raw_tag_results).__name__
            try:
                result["result_len"] = len(raw_tag_results)
            except Exception:
                result["result_len"] = None
        except Exception as exc:
            result["failed"] += len(ready_items)
            result["processed"] += len(ready_items)
            for item in ready_items:
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="failed_model_error",
                        error=str(exc),
                        reason="tag generation crashed",
                    )
                )
            result["warnings"].append(f"SigLIP batch generation failed before any DB write: {exc}")
            return result

        tags_by_file, mapping_warnings, unmapped_keys = _normalize_tag_results(raw_tag_results, ready_items)
        result["warnings"].extend(mapping_warnings)
        if isinstance(raw_tag_results, dict):
            result["result_key_sample"] = list(raw_tag_results.keys())[:5]
        elif isinstance(raw_tag_results, (list, tuple)):
            result["result_key_sample"] = [
                entry[0] if isinstance(entry, (list, tuple)) and len(entry) >= 1 else entry
                for entry in list(raw_tag_results)[:5]
            ]
        candidate_file_id_sample = [item["file_id"] for item in ready_items[:5]]
        empty_result = isinstance(raw_tag_results, dict) and len(raw_tag_results) == 0

        pending_rows: List[tuple[int, str, str]] = []
        run_tag_counter: Counter[str] = Counter()
        for item in ready_items:
            result["processed"] += 1
            if item["file_id"] not in tags_by_file:
                if empty_result:
                    reason = "no_encoded_images_or_empty_result"
                    error = (
                        "generate_tags_batch returned an empty result for the whole batch; "
                        f"candidate_file_id_sample={candidate_file_id_sample}"
                    )
                else:
                    reason = "result_mapping_missing"
                    error = (
                        "generate_tags_batch returned no result for this file_id; "
                        f"result_key_sample={unmapped_keys[:5]} candidate_file_id_sample={candidate_file_id_sample}"
                    )
                result["failed"] += 1
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="failed_result_mapping",
                        reason=reason,
                        error=error,
                    )
                )
                continue

            labels = tags_by_file[item["file_id"]]
            if labels is None:
                result["failed"] += 1
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="failed_result_mapping",
                        reason="result_value_invalid",
                        error="generate_tags_batch returned an invalid non-list value for this file_id",
                    )
                )
                continue

            if not isinstance(labels, list):
                result["failed"] += 1
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="failed_result_mapping",
                        reason="result_value_invalid",
                        error="generate_tags_batch returned a non-list tag payload for this file_id",
                    )
                )
                continue

            result["succeeded"] += 1
            if not labels:
                result["files_without_tags"] += 1
                result["no_tags_count"] += 1
                result["file_results"].append(
                    _build_file_result(
                        item,
                        status="succeeded_no_tags",
                        reason="no_tags_above_threshold",
                        labels=[],
                    )
                )
                continue

            result["files_with_tags"] += 1
            for label in labels:
                pending_rows.append((item["file_id"], label, SIGLIP_SOURCE))
                run_tag_counter[label] += 1
            result["file_results"].append(
                _build_file_result(
                    item,
                    status="succeeded_with_tags",
                    reason="tags_generated",
                    labels=labels,
                )
            )

        if pending_rows:
            before_changes = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
                pending_rows,
            )
            conn.commit()
            result["db_updated"] = conn.total_changes - before_changes
            result["tags_inserted"] = result["db_updated"]

        result["failed_count"] = result["failed"]
        result["top_tags"] = [
            {"tag": tag, "count": count}
            for tag, count in run_tag_counter.most_common(10)
        ]

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
        f"sample_mode: {result['sample_mode']}",
        f"seed: {result['seed']}",
        f"candidate_count: {result['candidate_count']}",
        f"selected: {result['selected']}",
        f"selected_folder_count: {result['selected_folder_count']}",
        f"selected_source_folder_samples: {result['selected_source_folder_samples']}",
        f"already_tagged_skipped: {result['already_tagged_skipped']}",
        f"invalid_thumbnail_skipped: {result['invalid_thumbnail_skipped']}",
        f"skipped: {result['skipped']}",
        f"processed: {result['processed']}",
        f"succeeded: {result['succeeded']}",
        f"failed: {result['failed']}",
        f"model_loaded: {result['model_loaded']}",
        f"db_updated: {result['db_updated']}",
        f"tags_inserted: {result['tags_inserted']}",
        f"files_with_tags: {result['files_with_tags']}",
        f"files_without_tags: {result['files_without_tags']}",
        f"no_tags_count: {result['no_tags_count']}",
        f"failed_count: {result['failed_count']}",
        f"top_tags: {result['top_tags']}",
        f"result_type: {result['result_type']}",
        f"result_len: {result['result_len']}",
        f"result_key_sample: {result['result_key_sample']}",
        f"candidate_file_id_sample: {result['candidate_file_id_sample']}",
        f"candidate_thumbnail_path_sample: {result['candidate_thumbnail_path_sample']}",
        f"candidate_source_path_sample: {result['candidate_source_path_sample']}",
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
    parser.add_argument(
        "--sample-mode",
        choices=["sequential", "random", "folder-diverse"],
        default=DEFAULT_SAMPLE_MODE,
        help="How to sample candidates for small-batch validation.",
    )
    parser.add_argument("--seed", type=int, help="Optional random seed for random / folder-diverse sampling.")
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
        sample_mode=args.sample_mode,
        seed=args.seed,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_ai_recognition_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
