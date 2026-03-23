from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EventDiscovery:
    event_url: str
    directory_url: str
    extraction_method: str
    expected_count: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExhibitorRecord:
    name: str
    official_domain: str | None
    source_url: str | None
    confidence: float
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunStats:
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
