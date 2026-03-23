from __future__ import annotations

import argparse
from pathlib import Path

from .db import Database
from .runner import BatchRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exhibitor_scraper.py",
        description="Qualification-first exhibitor domain scraper v2",
    )
    parser.add_argument("--db", default="exhibitor_scraper.sqlite3", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run a batch from URL/CSV/TXT input")
    run_cmd.add_argument("--input", required=True, help="Path to CSV/TXT or a single URL")
    run_cmd.add_argument("--export", default="exports", help="Export directory")
    run_cmd.add_argument("--resume", action="store_true", help="Skip already-successful events")

    pilot_cmd = sub.add_parser("pilot", help="Run discovery + 10-record pilot for a single event")
    pilot_cmd.add_argument("--url", required=True, help="Event URL")

    sub.add_parser("summary", help="Print event run summary")

    retry_cmd = sub.add_parser("retry-failed", help="Retry failed events from the database")
    retry_cmd.add_argument("--export", default="exports", help="Export directory")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    db = Database(Path(args.db))
    db.initialize()
    runner = BatchRunner(db=db, export_dir=Path(getattr(args, "export", "exports")))

    if args.command == "run":
        result = runner.run_input(args.input, resume=args.resume)
        return 0 if result.failed == 0 else 2
    if args.command == "pilot":
        runner.run_single(url=args.url, pilot_only=True)
        return 0
    if args.command == "summary":
        print(runner.render_summary())
        return 0
    if args.command == "retry-failed":
        result = runner.retry_failed()
        return 0 if result.failed == 0 else 2

    parser.error(f"Unknown command: {args.command}")
    return 1
