from __future__ import annotations

from dataclasses import dataclass

from .extractors import Extractor
from .models import EventDiscovery, ExhibitorRecord


class PilotFailure(RuntimeError):
    pass


@dataclass(slots=True)
class PilotResult:
    passed: bool
    records: list[ExhibitorRecord]
    reason: str


class PilotRunner:
    def __init__(self, extractor: Extractor) -> None:
        self.extractor = extractor

    def run(self, discovery: EventDiscovery) -> PilotResult:
        records = self.extractor.extract(discovery, limit=10)
        if len(records) < 3:
            raise PilotFailure(f"Pilot returned only {len(records)} records for {discovery.directory_url}; refusing full scrape")
        missing_names = [row for row in records if not row.name]
        if missing_names:
            raise PilotFailure("Pilot found records without exhibitor names")
        return PilotResult(passed=True, records=records, reason="Pilot passed")
