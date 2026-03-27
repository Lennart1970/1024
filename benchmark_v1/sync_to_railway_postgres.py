from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent
SQLITE_PATH = ROOT / "benchmark.sqlite"


def get_latest_run_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT r.id
        FROM runs r
        LEFT JOIN question_metrics qm ON qm.run_id = r.id
        GROUP BY r.id
        ORDER BY
          CASE WHEN COUNT(qm.id) > 0 THEN 1 ELSE 0 END DESC,
          r.id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("No runs found in benchmark.sqlite")
    return int(row["id"])


def get_complete_run_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT r.id
        FROM runs r
        JOIN question_metrics qm ON qm.run_id = r.id
        GROUP BY r.id
        ORDER BY r.id
        """
    ).fetchall()
    return [int(row["id"]) for row in rows]


def ensure_pg_schema(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            CREATE SCHEMA IF NOT EXISTS benchmark_v1;

            CREATE TABLE IF NOT EXISTS benchmark_v1.runs (
              run_id BIGINT PRIMARY KEY,
              run_name TEXT NOT NULL,
              prompt_version TEXT NOT NULL,
              temperature DOUBLE PRECISION NOT NULL,
              top_p DOUBLE PRECISION,
              max_tokens INTEGER,
              created_at TEXT NOT NULL,
              synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS benchmark_v1.question_metrics (
              run_id BIGINT NOT NULL,
              question_id BIGINT NOT NULL,
              subset TEXT NOT NULL,
              question_text TEXT NOT NULL,
              answer_count INTEGER,
              refusal_rate DOUBLE PRECISION,
              mean_answer_length DOUBLE PRECISION,
              length_stddev DOUBLE PRECISION,
              divergence_score DOUBLE PRECISION,
              deep_dive_priority DOUBLE PRECISION,
              notes TEXT,
              lexical_divergence DOUBLE PRECISION,
              stance_divergence DOUBLE PRECISION,
              self_report_divergence DOUBLE PRECISION,
              refusal_divergence DOUBLE PRECISION,
              length_divergence DOUBLE PRECISION,
              synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (run_id, question_id)
            );
            """
        )
    pg_conn.commit()


def sync_run(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection, run_id: int) -> None:
    run_row = sqlite_conn.execute(
        """
        SELECT id, run_name, prompt_version, temperature, top_p, max_tokens, created_at
        FROM runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    if run_row is None:
        raise RuntimeError(f"Run id {run_id} does not exist")

    metrics_rows = sqlite_conn.execute(
        """
        SELECT
          qm.run_id,
          qm.question_id,
          q.subset,
          q.question_text,
          qm.answer_count,
          qm.refusal_rate,
          qm.mean_answer_length,
          qm.length_stddev,
          qm.divergence_score,
          qm.deep_dive_priority,
          qm.notes,
          qm.lexical_divergence,
          qm.stance_divergence,
          qm.self_report_divergence,
          qm.refusal_divergence,
          qm.length_divergence
        FROM question_metrics qm
        JOIN questions q ON q.id = qm.question_id
        WHERE qm.run_id = ?
        ORDER BY qm.question_id
        """,
        (run_id,),
    ).fetchall()

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO benchmark_v1.runs
            (run_id, run_name, prompt_version, temperature, top_p, max_tokens, created_at, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (run_id) DO UPDATE SET
              run_name = EXCLUDED.run_name,
              prompt_version = EXCLUDED.prompt_version,
              temperature = EXCLUDED.temperature,
              top_p = EXCLUDED.top_p,
              max_tokens = EXCLUDED.max_tokens,
              created_at = EXCLUDED.created_at,
              synced_at = NOW()
            """,
            (
                int(run_row["id"]),
                str(run_row["run_name"]),
                str(run_row["prompt_version"]),
                float(run_row["temperature"]),
                float(run_row["top_p"]) if run_row["top_p"] is not None else None,
                int(run_row["max_tokens"]) if run_row["max_tokens"] is not None else None,
                str(run_row["created_at"]),
            ),
        )

        for row in metrics_rows:
            cur.execute(
                """
                INSERT INTO benchmark_v1.question_metrics
                (
                  run_id, question_id, subset, question_text, answer_count, refusal_rate,
                  mean_answer_length, length_stddev, divergence_score, deep_dive_priority,
                  notes, lexical_divergence, stance_divergence, self_report_divergence,
                  refusal_divergence, length_divergence, synced_at
                )
                VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (run_id, question_id) DO UPDATE SET
                  subset = EXCLUDED.subset,
                  question_text = EXCLUDED.question_text,
                  answer_count = EXCLUDED.answer_count,
                  refusal_rate = EXCLUDED.refusal_rate,
                  mean_answer_length = EXCLUDED.mean_answer_length,
                  length_stddev = EXCLUDED.length_stddev,
                  divergence_score = EXCLUDED.divergence_score,
                  deep_dive_priority = EXCLUDED.deep_dive_priority,
                  notes = EXCLUDED.notes,
                  lexical_divergence = EXCLUDED.lexical_divergence,
                  stance_divergence = EXCLUDED.stance_divergence,
                  self_report_divergence = EXCLUDED.self_report_divergence,
                  refusal_divergence = EXCLUDED.refusal_divergence,
                  length_divergence = EXCLUDED.length_divergence,
                  synced_at = NOW()
                """,
                (
                    int(row["run_id"]),
                    int(row["question_id"]),
                    str(row["subset"]),
                    str(row["question_text"]),
                    int(row["answer_count"]) if row["answer_count"] is not None else None,
                    float(row["refusal_rate"]) if row["refusal_rate"] is not None else None,
                    float(row["mean_answer_length"]) if row["mean_answer_length"] is not None else None,
                    float(row["length_stddev"]) if row["length_stddev"] is not None else None,
                    float(row["divergence_score"]) if row["divergence_score"] is not None else None,
                    float(row["deep_dive_priority"]) if row["deep_dive_priority"] is not None else None,
                    str(row["notes"] or ""),
                    float(row["lexical_divergence"]) if row["lexical_divergence"] is not None else None,
                    float(row["stance_divergence"]) if row["stance_divergence"] is not None else None,
                    float(row["self_report_divergence"]) if row["self_report_divergence"] is not None else None,
                    float(row["refusal_divergence"]) if row["refusal_divergence"] is not None else None,
                    float(row["length_divergence"]) if row["length_divergence"] is not None else None,
                ),
            )

    pg_conn.commit()
    print(f"Synced run {run_id} with {len(metrics_rows)} question_metrics rows")


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set. Use `railway run -- <command>` or set env first.")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    try:
        run_id_override = (os.environ.get("BENCHMARK_SYNC_RUN_ID") or "").strip()
        sync_all_complete = (os.environ.get("BENCHMARK_SYNC_ALL_COMPLETE") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        with psycopg.connect(db_url) as pg_conn:
            ensure_pg_schema(pg_conn)
            if run_id_override:
                sync_run(sqlite_conn, pg_conn, int(run_id_override))
            elif sync_all_complete:
                run_ids = get_complete_run_ids(sqlite_conn)
                for run_id in run_ids:
                    sync_run(sqlite_conn, pg_conn, run_id)
                print(f"Backfilled {len(run_ids)} completed runs")
            else:
                sync_run(sqlite_conn, pg_conn, get_latest_run_id(sqlite_conn))
    finally:
        sqlite_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
