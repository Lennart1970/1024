from __future__ import annotations

import csv
from pathlib import Path

from .db import Database

APOLLO_COLUMNS = ["Company", "Company Domain", "Source Event URL", "Directory URL", "Extraction Method", "Confidence", "Source URL"]


class Exporter:
    def __init__(self, db: Database, export_dir: Path) -> None:
        self.db = db
        self.export_dir = export_dir

    def export_apollo_csv(self) -> Path:
        rows = self.db.export_rows()
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / "apollo_ready_exhibitors.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
            writer.writerow(APOLLO_COLUMNS)
            for row in rows:
                writer.writerow([row["exhibitor_name"], row["official_domain"] or "", row["event_url"], row["directory_url"] or "", row["extraction_method"] or "", row["confidence"], row["source_url"] or ""])
        return path
