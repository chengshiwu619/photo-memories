import argparse
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.startup_integrity import (  # noqa: E402
    build_startup_integrity_report,
    format_integrity_report_text,
)


class _CliSettings:
    def __init__(self, db_path: str):
        photo_data_dir = os.path.dirname(os.path.abspath(db_path))
        self.db_path = os.path.abspath(db_path)
        self.photo_data_dir = photo_data_dir
        self.thumbnail_dir = os.path.join(photo_data_dir, "thumbnails")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run startup integrity checks in dry-run mode.")
    parser.add_argument("--db-path", help="Optional path to the SQLite database to inspect.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print the full JSON report.")
    parser.add_argument(
        "--max-samples",
        type=int,
        default=5,
        help="Maximum number of sample ids / paths to include per check.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    settings = _CliSettings(args.db_path) if args.db_path else None
    report = build_startup_integrity_report(
        dry_run=True,
        db_path=args.db_path,
        settings=settings,
        max_samples=max(args.max_samples, 0),
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_integrity_report_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
