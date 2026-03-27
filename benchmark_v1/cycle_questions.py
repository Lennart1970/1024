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
ALLOWED_EXPECTED_TYPES = {"factual", "ambiguous", "normative", "procedural"}


def normalize_expected_type(question_text: str, expected_type: str) -> tuple[str, str]:
    qtext = (question_text or "").strip()
    etype = (expected_type or "").strip().lower()
    if etype in ALLOWED_EXPECTED_TYPES:
        return qtext, etype
    for allowed in sorted(ALLOWED_EXPECTED_TYPES):
        marker = f",{allowed}"
        if qtext.lower().endswith(marker):
            return qtext[: -len(marker)].strip(), allowed
    return qtext, "ambiguous"


def read_csv(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if None in row and row[None]:
                extras = [part for part in row[None] if part is not None]
                row["question_text"] = ",".join([row.get("question_text", ""), *extras]).strip()
                del row[None]
            question_text, expected_type = normalize_expected_type(
                (row.get("question_text") or "").strip(),
                (row.get("expected_type") or "").strip(),
            )
            rows.append(
                {
                    "subset": (row.get("subset") or "").strip(),
                    "question_text": question_text,
                    "expected_type": expected_type,
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["subset", "question_text", "expected_type"])
        writer.writeheader()
        writer.writerows(rows)


def get_least_interesting_active_questions(db_path: Path, limit: int) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select
              q.subset,
              q.question_text,
              avg(
                (0.60 * coalesce(qm.deep_dive_priority, qm.divergence_score, 0.0))
                + (0.25 * coalesce(qm.lexical_divergence, 0.0))
                + (0.15 * coalesce(qm.stance_divergence, 0.0))
              ) as avg_interest,
              avg(coalesce(qm.divergence_score, 0.0)) as avg_divergence,
              count(qm.id) as metric_count
            from questions q
            left join question_metrics qm on qm.question_id = q.id
            where q.active = 1
              and q.subset not like 'self_report%'
            group by q.id, q.subset, q.question_text
            order by avg_interest asc, avg_divergence asc, metric_count desc, q.id asc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [(str(row["subset"]), str(row["question_text"])) for row in rows]
    finally:
        conn.close()


def build_generated_followups(
    db_path: Path,
    limit: int,
    excluded_keys: set[tuple[str, str]],
) -> list[dict[str, str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        seeds = conn.execute(
            """
            select
              q.subset,
              q.question_text,
              q.expected_type,
              avg(coalesce(qm.divergence_score, 0.0)) as avg_divergence,
              avg(coalesce(qm.lexical_divergence, 0.0)) as avg_lexical,
              avg(coalesce(qm.stance_divergence, 0.0)) as avg_stance
            from questions q
            join question_metrics qm on qm.question_id = q.id
            group by q.id, q.subset, q.question_text, q.expected_type
            order by
              (0.55 * avg(coalesce(qm.divergence_score, 0.0)))
              + (0.30 * avg(coalesce(qm.lexical_divergence, 0.0)))
              + (0.15 * avg(coalesce(qm.stance_divergence, 0.0))) desc,
              q.id asc
            limit 200
            """
        ).fetchall()
    finally:
        conn.close()

    templates = [
        (
            "followup_evidence",
            "What single piece of evidence would most change your answer to this question: {q}",
            "ambiguous",
        ),
        (
            "followup_disagreement",
            "If two strong models disagree on this question, what is the most likely reason for disagreement: {q}",
            "ambiguous",
        ),
        (
            "followup_uncertainty",
            "What is the most important uncertainty to state before answering this question: {q}",
            "procedural",
        ),
        (
            "followup_confidence",
            "Give a concise answer to this question plus a confidence score from 0 to 100: {q}",
            "procedural",
        ),
    ]

    generated: list[dict[str, str]] = []
    seen = set(excluded_keys)
    for seed in seeds:
        if len(generated) >= limit:
            break
        seed_subset = str(seed["subset"])
        seed_question = str(seed["question_text"]).strip()
        _, seed_expected = normalize_expected_type(
            seed_question,
            str(seed["expected_type"] or "").strip(),
        )
        for suffix, template, default_expected in templates:
            if len(generated) >= limit:
                break
            subset = f"{seed_subset}_{suffix}"
            question_text = template.format(q=seed_question)
            key = (subset, question_text)
            if key in seen:
                continue
            expected_type = seed_expected if seed_expected in {"factual", "ambiguous", "normative", "procedural"} else default_expected
            generated.append(
                {
                    "subset": subset,
                    "question_text": question_text,
                    "expected_type": expected_type,
                }
            )
            seen.add(key)
    return generated


def get_top_divergent_inactive(
    db_path: Path,
    limit: int,
    excluded_keys: set[tuple[str, str]],
    include_self_report: bool = False,
) -> list[dict[str, str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where_extra = "" if include_self_report else "and q.subset not like 'self_report%'"
        rows = conn.execute(
            f"""
            select
              q.subset,
              q.question_text,
              q.expected_type,
              avg(coalesce(qm.deep_dive_priority, qm.divergence_score, 0.0)) as avg_interest,
              avg(coalesce(qm.divergence_score, 0.0)) as avg_divergence,
              count(qm.id) as metric_count
            from questions q
            left join question_metrics qm on qm.question_id = q.id
            where q.active = 0
              {where_extra}
            group by q.id, q.subset, q.question_text, q.expected_type
            order by avg_interest desc, avg_divergence desc, metric_count desc, q.id asc
            """
        ).fetchall()

        picked: list[dict[str, str]] = []
        seen = set(excluded_keys)
        for row in rows:
            key = (str(row["subset"]), str(row["question_text"]))
            if key in seen:
                continue
            picked.append(
                {
                    "subset": str(row["subset"]),
                    "question_text": str(row["question_text"]),
                    "expected_type": normalize_expected_type(
                        str(row["question_text"] or ""),
                        str(row["expected_type"] or ""),
                    )[1],
                }
            )
            seen.add(key)
            if len(picked) >= limit:
                break
        return picked
    finally:
        conn.close()


def rotate_questions() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    active_rows = read_csv(ACTIVE_PATH)
    bank_rows = read_csv(BANK_PATH)
    write_csv(ACTIVE_PATH, active_rows)
    write_csv(BANK_PATH, bank_rows)

    current_keys = {(row["subset"], row["question_text"]) for row in active_rows}
    drop_keys = set(get_least_interesting_active_questions(DB_PATH, DROP_COUNT))
    kept_rows = [row for row in active_rows if (row["subset"], row["question_text"]) not in drop_keys]

    additions: list[dict[str, str]] = []
    remaining_bank: list[dict[str, str]] = []
    addition_keys: set[tuple[str, str]] = set()

    for row in bank_rows:
        key = (row["subset"], row["question_text"])
        if len(additions) < ADD_COUNT and key not in current_keys and key not in addition_keys:
            additions.append(row)
            addition_keys.add(key)
        else:
            remaining_bank.append(row)

    if len(additions) < ADD_COUNT:
        backfill = get_top_divergent_inactive(
            DB_PATH,
            ADD_COUNT - len(additions),
            excluded_keys=current_keys | addition_keys,
            include_self_report=False,
        )
        additions.extend(backfill)
        addition_keys.update((row["subset"], row["question_text"]) for row in backfill)

    if len(additions) < ADD_COUNT:
        final_backfill = get_top_divergent_inactive(
            DB_PATH,
            ADD_COUNT - len(additions),
            excluded_keys=current_keys | addition_keys,
            include_self_report=True,
        )
        additions.extend(final_backfill)
        addition_keys.update((row["subset"], row["question_text"]) for row in final_backfill)

    if len(additions) < ADD_COUNT:
        generated = build_generated_followups(
            DB_PATH,
            ADD_COUNT - len(additions),
            excluded_keys=current_keys | addition_keys,
        )
        additions.extend(generated)
        addition_keys.update((row["subset"], row["question_text"]) for row in generated)

    if len(additions) < ADD_COUNT:
        print(
            f"Warning: expected {ADD_COUNT} additions but only found {len(additions)} candidates. "
            "Continuing with a smaller rotation."
        )

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

    run_step([str(ROOT / 'validate_questions.py')])
    run_step([str(ROOT / 'run_benchmark.py')])
    run_step([str(ROOT / 'generate_report.py')])
    print("Cycle complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
