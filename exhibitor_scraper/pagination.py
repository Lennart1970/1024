from __future__ import annotations

from dataclasses import dataclass

from .extractors import ExtractionError, Extractor
from .models import EventDiscovery


class PaginationAuditError(RuntimeError):
    pass


@dataclass(slots=True)
class PaginationAudit:
    page_count: int
    expected_count: int | None


class PaginationAuditor:
    def __init__(self, extractor: Extractor) -> None:
        self.extractor = extractor

    def audit(self, discovery: EventDiscovery) -> PaginationAudit:
        try:
            records = self.extractor.extract(discovery)
        except ExtractionError as exc:
            raise PaginationAuditError(str(exc)) from exc

        expected = discovery.expected_count if discovery.expected_count else len(records)
        if expected and len(records) < max(3, int(expected * 0.5)):
            raise PaginationAuditError(f"Pagination audit mismatch: expected about {expected} exhibitors but extracted {len(records)}")
        return PaginationAudit(page_count=1, expected_count=expected)
