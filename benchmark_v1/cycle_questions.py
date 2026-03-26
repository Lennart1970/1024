from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "benchmark.sqlite"
ACTIVE_PATH = ROOT / "questions.sample.csv"
BANK_PATH = ROOT / "question_bank.csv"
DROP_COUNT = 6
ADD_COUNT = 12


def read_csv(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if None in row and row[None]:
                extras = [part for part in row[None] if part is not None]
                row["question_text"] = ",".join([row.get("question_text", ""), *extras]).strip()
                del row[None]
            rows.append({
                "subset": (row.get("subset") or "").strip(),
                "question_text": (row.get("question_text") or "").strip(),
                "expected_type": (row.get("expected_type") or "").strip(),
            })
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write empty CSV to {path}")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["subset", "question_text", "expected_type"])
        writer.writeheader()
        writer.writerows(rows)


def get_latest_run_least_divergent(db_path: Path, limit: int) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        run_row = conn.execute("select id from runs order by id desc limit 1").fetchone()
        if not run_row:
            raise RuntimeError("No benchmark runs found")
        run_id = int(run_row["id"])
        rows = conn.execute(
            """
            select q.subset, q.question_text
            from question_metrics qm
            join questions q on q.id = qm.question_id
            where qm.run_id = ? and q.active = 1
            order by qm.divergence_score asc, q.id asc
            limit ?
            """,
            (run_id, limit),
        ).fetchall()
        return [(str(row["subset"]), str(row["question_text"])) for row in rows]
    finally:
        conn.close()


def rotate_questions() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    active_rows = read_csv(ACTIVE_PATH)
    bank_rows = read_csv(BANK_PATH)

    current_keys = {(row["subset"], row["question_text"]) for row in active_rows}
    drop_keys = set(get_latest_run_least_divergent(DB_PATH, DROP_COUNT))
    kept_rows = [row for row in active_rows if (row["subset"], row["question_text"]) not in drop_keys]

    additions: list[dict[str, str]] = []
    remaining_bank: list[dict[str, str]] = []
    for row in bank_rows:
        key = (row["subset"], row["question_text"])
        if len(additions) < ADD_COUNT and key not in current_keys and key not in {(r['subset'], r['question_text']) for r in additions}:
            additions.append(row)
        else:
            remaining_bank.append(row)

    if len(additions) < ADD_COUNT:
        raise RuntimeError(f"Not enough questions left in bank to add {ADD_COUNT}; only {len(additions)} available")

    next_rows = kept_rows + additions
    write_csv(ACTIVE_PATH, next_rows)
    write_csv(BANK_PATH, remaining_bank)
    return kept_rows, additions


def run_step(args: list[str]) -> None:
    result = subprocess.run([sys.executable, *args], cwd=ROOT.parent)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}")


def main() -> int:
    kept_rows, additions = rotate_questions()
    print(f"Kept {len(kept_rows)} active questions")
    print(f"Added {len(additions)} new questions")
    for row in additions:
        print(f"+ {row['subset']} :: {row['question_text']}")

    run_step([str(ROOT / 'run_benchmark.py')])
    run_step([str(ROOT / 'generate_report.py')])
    print("Cycle complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
