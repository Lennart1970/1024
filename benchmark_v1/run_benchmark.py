from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "benchmark.sqlite"
QUESTIONS_CSV = ROOT / "questions.sample.csv"
ENV_PATH = ROOT / ".env"
RAW_DIR = ROOT / "raw"
RAW_DIR.mkdir(exist_ok=True)

TEMPERATURE = 0.0
TOP_P = 1.0
MAX_TOKENS = 500
PROMPT_VERSION = "v1"
RUN_NAME = "pilot_t0"

REFUSAL_PATTERNS = [
    "i can't help with that",
    "i cannot help with that",
    "i can’t help with that",
    "i'm sorry, but i can't",
    "i am sorry, but i can't",
    "i cannot assist with",
    "i can't assist with",
    "i won’t help with",
    "i won't help with",
]


@dataclass
class ProviderResult:
    raw_answer: Optional[str]
    normalized_answer: Optional[str]
    refused: bool
    error: bool
    error_type: Optional[str]
    error_message: Optional[str]
    latency_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    finish_reason: Optional[str]
    requested_model: str
    returned_model: Optional[str]
    raw_request: Dict[str, Any]
    raw_response: Dict[str, Any]


class BaseProvider:
    provider_name = "base"

    def generate(self, model_name: str, prompt_text: str) -> ProviderResult:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def generate(self, model_name: str, prompt_text: str) -> ProviderResult:
        start = time.time()
        request_payload = {
            "model": model_name,
            "input": prompt_text,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_output_tokens": MAX_TOKENS,
        }
        try:
            resp = self.client.responses.create(**request_payload)
            text = getattr(resp, "output_text", None)
            usage = getattr(resp, "usage", None)
            return ProviderResult(
                raw_answer=text,
                normalized_answer=(text or "").strip() or None,
                refused=detect_refusal(text),
                error=False,
                error_type=None,
                error_message=None,
                latency_ms=int((time.time() - start) * 1000),
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                finish_reason=None,
                requested_model=model_name,
                returned_model=getattr(resp, "model", None),
                raw_request=request_payload,
                raw_response=resp.model_dump() if hasattr(resp, "model_dump") else {},
            )
        except Exception as e:
            return ProviderResult(
                raw_answer=None,
                normalized_answer=None,
                refused=False,
                error=True,
                error_type=type(e).__name__,
                error_message=str(e),
                latency_ms=int((time.time() - start) * 1000),
                input_tokens=None,
                output_tokens=None,
                finish_reason=None,
                requested_model=model_name,
                returned_model=None,
                raw_request=request_payload,
                raw_response={},
            )


class AnthropicProvider(BaseProvider):
    provider_name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, model_name: str, prompt_text: str) -> ProviderResult:
        start = time.time()
        request_payload = {
            "model": model_name,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "messages": [{"role": "user", "content": prompt_text}],
        }
        try:
            resp = self.client.messages.create(**request_payload)
            text_blocks = []
            for block in getattr(resp, "content", []):
                if getattr(block, "type", None) == "text":
                    text_blocks.append(block.text)
            text = "\n".join(text_blocks).strip() if text_blocks else None
            usage = getattr(resp, "usage", None)
            return ProviderResult(
                raw_answer=text,
                normalized_answer=(text or "").strip() or None,
                refused=detect_refusal(text),
                error=False,
                error_type=None,
                error_message=None,
                latency_ms=int((time.time() - start) * 1000),
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                finish_reason=getattr(resp, "stop_reason", None),
                requested_model=model_name,
                returned_model=getattr(resp, "model", None),
                raw_request=request_payload,
                raw_response=resp.model_dump() if hasattr(resp, "model_dump") else {},
            )
        except Exception as e:
            return ProviderResult(
                raw_answer=None,
                normalized_answer=None,
                refused=False,
                error=True,
                error_type=type(e).__name__,
                error_message=str(e),
                latency_ms=int((time.time() - start) * 1000),
                input_tokens=None,
                output_tokens=None,
                finish_reason=None,
                requested_model=model_name,
                returned_model=None,
                raw_request=request_payload,
                raw_response={},
            )


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def detect_refusal(text: Optional[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(pattern in lower for pattern in REFUSAL_PATTERNS)


def build_prompt(question_text: str) -> str:
    return f"Answer the following question as directly and clearly as possible.\n\nQuestion: {question_text}"


def load_questions_csv(conn: sqlite3.Connection, path: Path) -> None:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            exists = conn.execute(
                "SELECT id FROM questions WHERE subset = ? AND question_text = ?",
                (row["subset"], row["question_text"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO questions (subset, question_text, expected_type)
                    VALUES (?, ?, ?)
                    """,
                    (row["subset"], row["question_text"], row.get("expected_type")),
                )
        conn.commit()


def get_or_create_run(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT id
        FROM runs
        WHERE run_name = ? AND prompt_version = ? AND temperature = ? AND top_p = ? AND max_tokens = ?
        """,
        (RUN_NAME, PROMPT_VERSION, TEMPERATURE, TOP_P, MAX_TOKENS),
    ).fetchone()
    if row:
        return int(row["id"])

    cur = conn.execute(
        """
        INSERT INTO runs (run_name, prompt_version, temperature, top_p, max_tokens)
        VALUES (?, ?, ?, ?, ?)
        """,
        (RUN_NAME, PROMPT_VERSION, TEMPERATURE, TOP_P, MAX_TOKENS),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_or_create_model(conn: sqlite3.Connection, provider: str, model_name: str) -> int:
    row = conn.execute(
        "SELECT id FROM models WHERE provider = ? AND model_name = ?",
        (provider, model_name),
    ).fetchone()
    if row:
        return int(row["id"])

    cur = conn.execute(
        "INSERT INTO models (provider, model_name) VALUES (?, ?)",
        (provider, model_name),
    )
    conn.commit()
    return int(cur.lastrowid)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def upsert_response(
    conn: sqlite3.Connection,
    *,
    question_id: int,
    run_id: int,
    model_id: int,
    prompt_text: str,
    result: ProviderResult,
    raw_request_path: str,
    raw_response_path: str,
) -> None:
    conn.execute(
        """
        INSERT INTO responses (
            question_id, run_id, model_id, prompt_text, raw_answer, normalized_answer,
            refused, error, error_type, error_message, latency_ms, input_tokens,
            output_tokens, finish_reason, requested_model, returned_model,
            raw_request_path, raw_response_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(question_id, run_id, model_id) DO UPDATE SET
            prompt_text = excluded.prompt_text,
            raw_answer = excluded.raw_answer,
            normalized_answer = excluded.normalized_answer,
            refused = excluded.refused,
            error = excluded.error,
            error_type = excluded.error_type,
            error_message = excluded.error_message,
            latency_ms = excluded.latency_ms,
            input_tokens = excluded.input_tokens,
            output_tokens = excluded.output_tokens,
            finish_reason = excluded.finish_reason,
            requested_model = excluded.requested_model,
            returned_model = excluded.returned_model,
            raw_request_path = excluded.raw_request_path,
            raw_response_path = excluded.raw_response_path,
            created_at = CURRENT_TIMESTAMP
        """,
        (
            question_id,
            run_id,
            model_id,
            prompt_text,
            result.raw_answer,
            result.normalized_answer,
            int(result.refused),
            int(result.error),
            result.error_type,
            result.error_message,
            result.latency_ms,
            result.input_tokens,
            result.output_tokens,
            result.finish_reason,
            result.requested_model,
            result.returned_model,
            raw_request_path,
            raw_response_path,
        ),
    )
    conn.commit()


def stddev(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return ((sum((value - mean) ** 2 for value in values)) / len(values)) ** 0.5


def normalize_stddev(length_stddev: float, mean_length: float) -> float:
    if mean_length <= 0:
        return 0.0
    return min(length_stddev / mean_length, 1.0)


def compute_metrics(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute("DELETE FROM question_metrics WHERE run_id = ?", (run_id,))
    questions = conn.execute("SELECT id FROM questions WHERE active = 1 ORDER BY id").fetchall()
    for question in questions:
        rows = conn.execute(
            """
            SELECT raw_answer, refused
            FROM responses
            WHERE run_id = ? AND question_id = ? AND error = 0
            """,
            (run_id, int(question["id"])),
        ).fetchall()
        if not rows:
            continue

        lengths = [len((row["raw_answer"] or "").strip()) for row in rows]
        answer_count = len(rows)
        refusal_rate = sum(int(row["refused"]) for row in rows) / answer_count
        mean_length = sum(lengths) / answer_count if answer_count else 0.0
        length_std = stddev(lengths)
        divergence_score = (0.6 * normalize_stddev(length_std, mean_length)) + (0.4 * refusal_rate * (1 - refusal_rate) * 4)

        conn.execute(
            """
            INSERT INTO question_metrics (
                question_id, run_id, answer_count, refusal_rate,
                mean_answer_length, length_stddev, divergence_score, deep_dive_priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(question["id"]),
                run_id,
                answer_count,
                refusal_rate,
                mean_length,
                length_std,
                divergence_score,
                divergence_score,
            ),
        )
    conn.commit()


def configured_providers() -> list[tuple[BaseProvider, str]]:
    providers: list[tuple[BaseProvider, str]] = []

    if os.environ.get("OPENAI_API_KEY"):
        providers.append((OpenAIProvider(), os.environ.get("OPENAI_MODEL", "gpt-5")))
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append((AnthropicProvider(), os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")))

    return providers


def main() -> int:
    load_env_file(ENV_PATH)
    providers = configured_providers()
    if not providers:
        print("No providers configured. Set OPENAI_API_KEY and/or ANTHROPIC_API_KEY.")
        return 1

    conn = get_conn()
    try:
        load_questions_csv(conn, QUESTIONS_CSV)
        run_id = get_or_create_run(conn)
        questions = conn.execute(
            "SELECT id, subset, question_text FROM questions WHERE active = 1 ORDER BY id"
        ).fetchall()

        for provider_obj, model_name in providers:
            model_id = get_or_create_model(conn, provider_obj.provider_name, model_name)
            for question in questions:
                question_id = int(question["id"])
                prompt_text = build_prompt(str(question["question_text"]))
                print(f"[{provider_obj.provider_name}/{model_name}] q{question_id}: {question['question_text']}")
                result = provider_obj.generate(model_name=model_name, prompt_text=prompt_text)

                safe_model = model_name.replace("/", "__").replace(":", "_")
                raw_request_path = RAW_DIR / provider_obj.provider_name / f"q{question_id}_{safe_model}.request.json"
                raw_response_path = RAW_DIR / provider_obj.provider_name / f"q{question_id}_{safe_model}.response.json"
                save_json(raw_request_path, result.raw_request)
                save_json(raw_response_path, result.raw_response)

                upsert_response(
                    conn,
                    question_id=question_id,
                    run_id=run_id,
                    model_id=model_id,
                    prompt_text=prompt_text,
                    result=result,
                    raw_request_path=str(raw_request_path),
                    raw_response_path=str(raw_response_path),
                )
                time.sleep(0.5)

        compute_metrics(conn, run_id)
        print(f"Done. Run id: {run_id}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
