import argparse
import csv
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from scripts.run_ai_labeling import (  # noqa: E402
    CAPACITY_TOKEN_PATTERN,
    COUNT_SIZE_FRAGMENT_PATTERN,
    COUNT_TOKEN_PATTERN,
    BROKEN_COUNT_FRAGMENT_PATTERN,
    DATE_PATTERN,
    NO_INDEX_PATTERN,
    PATH_NOISE_TAGS,
    PURE_NUMBER_PATTERN,
    _resolve_settings,
)


DEVICE_TAGS = {"dcim", "mobile", "mobilebackup", "moments", "sm-n9600", "iphone", "snapseed"}


def guess_tag_type(tag: str) -> str:
    normalized = tag.strip()
    lowered = normalized.lower()

    if lowered.startswith("category:"):
        return "category"
    if lowered.startswith("year:") or lowered.startswith("date:") or DATE_PATTERN.search(lowered):
        return "year"
    if lowered in DEVICE_TAGS:
        return "source_device"
    if lowered in PATH_NOISE_TAGS:
        return "possible_noise"
    if PURE_NUMBER_PATTERN.match(normalized):
        return "numeric_or_size_noise"
    if CAPACITY_TOKEN_PATTERN.match(lowered):
        return "numeric_or_size_noise"
    if COUNT_TOKEN_PATTERN.match(lowered):
        return "numeric_or_size_noise"
    if BROKEN_COUNT_FRAGMENT_PATTERN.match(lowered):
        return "numeric_or_size_noise"
    if NO_INDEX_PATTERN.match(lowered):
        return "numeric_or_size_noise"
    if COUNT_SIZE_FRAGMENT_PATTERN.match(lowered):
        return "numeric_or_size_noise"
    if any("\u4e00" <= ch <= "\u9fff" for ch in normalized):
        return "chinese_semantic"
    return "unknown"


def build_cleaning_plan_template() -> Dict[str, Any]:
    return {
        "delete_tags": ["gb", "p-3", "p+28v"],
        "rename_tags": {
            "sm-n9600": "device:sm-n9600",
            "dcim": "source:dcim",
        },
        "keep_tags": ["category:life", "year:2019", "日常生活"],
    }


def audit_path_tags(
    db_path: Optional[str] = None,
    source: str = "path",
    top: int = 200,
) -> Dict[str, Any]:
    settings = _resolve_settings(db_path)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                pt.tag AS tag,
                pt.source AS current_source,
                COUNT(*) AS count,
                COUNT(DISTINCT pt.file_id) AS distinct_file_count
            FROM photo_tags pt
            WHERE pt.source = ?
            GROUP BY pt.tag, pt.source
            ORDER BY count DESC, pt.tag ASC
            LIMIT ?
            """,
            (source, max(int(top), 0)),
        ).fetchall()

        audit_items: List[Dict[str, Any]] = []
        for row in rows:
            tag = row["tag"]
            samples = conn.execute(
                """
                SELECT pt.file_id, f.file_path
                FROM photo_tags pt
                JOIN files f ON f.id = pt.file_id
                WHERE pt.source = ? AND pt.tag = ?
                ORDER BY pt.file_id
                LIMIT 5
                """,
                (source, tag),
            ).fetchall()
            audit_items.append(
                {
                    "tag": tag,
                    "count": row["count"],
                    "distinct_file_count": row["distinct_file_count"],
                    "sample_file_ids": [sample["file_id"] for sample in samples],
                    "sample_paths": [sample["file_path"] for sample in samples],
                    "current_source": row["current_source"],
                    "guessed_type": guess_tag_type(tag),
                }
            )

        return {
            "db_path": os.path.abspath(settings.db_path),
            "source": source,
            "top": max(int(top), 0),
            "audit_items": audit_items,
            "cleaning_plan_template": build_cleaning_plan_template(),
        }
    finally:
        conn.close()


def export_audit(payload: Dict[str, Any], export_path: str) -> None:
    target = os.path.abspath(export_path)
    if target.lower().endswith(".csv"):
        with open(target, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "tag",
                    "count",
                    "distinct_file_count",
                    "sample_file_ids",
                    "sample_paths",
                    "current_source",
                    "guessed_type",
                ],
            )
            writer.writeheader()
            for item in payload["audit_items"]:
                writer.writerow(
                    {
                        "tag": item["tag"],
                        "count": item["count"],
                        "distinct_file_count": item["distinct_file_count"],
                        "sample_file_ids": json.dumps(item["sample_file_ids"], ensure_ascii=False),
                        "sample_paths": json.dumps(item["sample_paths"], ensure_ascii=False),
                        "current_source": item["current_source"],
                        "guessed_type": item["guessed_type"],
                    }
                )
        return

    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def format_audit_text(payload: Dict[str, Any]) -> str:
    lines = [
        "Path Tag Audit Report",
        f"db_path: {payload['db_path']}",
        f"source: {payload['source']}",
        f"top: {payload['top']}",
    ]
    for item in payload["audit_items"]:
        lines.append(
            f"- tag={item['tag']} count={item['count']} distinct_file_count={item['distinct_file_count']} guessed_type={item['guessed_type']}"
        )
        lines.append(f"  sample_file_ids: {item['sample_file_ids']}")
        lines.append(f"  sample_paths: {item['sample_paths']}")
    lines.append("cleaning_plan_template:")
    lines.append(json.dumps(payload["cleaning_plan_template"], ensure_ascii=False, indent=2))
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Read-only audit for path tags before any future cleanup or LLM review.")
    parser.add_argument("--db-path", help="Optional path to the SQLite database to inspect.")
    parser.add_argument("--source", default="path", help="Tag source to audit. Default is path.")
    parser.add_argument("--top", type=int, default=200, help="How many top tags to inspect.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print structured JSON output only.")
    parser.add_argument("--export", help="Optional export path (.json or .csv).")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    payload = audit_path_tags(
        db_path=args.db_path,
        source=args.source,
        top=max(args.top, 0),
    )
    if args.export:
        export_audit(payload, args.export)
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_audit_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
