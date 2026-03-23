from __future__ import annotations

import csv
from pathlib import Path


def load_urls(input_value: str) -> list[str]:
    if input_value.startswith(("http://", "https://")):
        return [input_value.strip()]

    path = Path(input_value)
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {input_value}")

    if path.suffix.lower() == ".txt":
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError(f"CSV has no headers: {path}")
            candidates = [name for name in reader.fieldnames if name.lower() in {"url", "event_url", "link"}]
            if not candidates:
                raise ValueError(f"CSV must include one of: url, event_url, link. Found: {reader.fieldnames}")
            field = candidates[0]
            urls = [row[field].strip() for row in reader if row.get(field) and row[field].strip()]
        if not urls:
            raise ValueError(f"CSV contained no URLs in column '{field}': {path}")
        return urls

    raise ValueError("Input must be a URL, .csv, or .txt file")
