from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTIONS_CSV = ROOT / "questions.sample.csv"
ALLOWED_EXPECTED_TYPES = {"factual", "ambiguous", "normative", "procedural"}


def validate_questions_csv(path: Path) -> list[str]:
    errors: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"subset", "question_text", "expected_type"}
        missing_headers = sorted(required - set(reader.fieldnames or []))
        if missing_headers:
            errors.append(f"Missing CSV headers: {', '.join(missing_headers)}")
            return errors

        for row in reader:
            line_number = reader.line_num

            if None in row and row[None]:
                errors.append(f"Line {line_number}: extra columns detected")
                continue

            subset = (row.get("subset") or "").strip()
            question_text = (row.get("question_text") or "").strip()
            expected_type = (row.get("expected_type") or "").strip().lower()

            if not subset:
                errors.append(f"Line {line_number}: subset is empty")
            if not question_text:
                errors.append(f"Line {line_number}: question_text is empty")
            if not expected_type:
                errors.append(f"Line {line_number}: expected_type is empty")
            elif expected_type not in ALLOWED_EXPECTED_TYPES:
                allowed = ", ".join(sorted(ALLOWED_EXPECTED_TYPES))
                errors.append(
                    f"Line {line_number}: invalid expected_type '{expected_type}' (allowed: {allowed})"
                )
    return errors


def main() -> int:
    errors = validate_questions_csv(QUESTIONS_CSV)
    if errors:
        print(f"Validation failed for {QUESTIONS_CSV}")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"Validation passed for {QUESTIONS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
