from __future__ import annotations

from urllib.parse import quote_plus

from .discovery import DEFAULT_HEADERS, normalized_domain
from .models import ExhibitorRecord


class SearchEnrichmentError(RuntimeError):
    pass


class SearchEnricher:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def enrich_missing_domains(self, records: list[ExhibitorRecord]) -> tuple[list[ExhibitorRecord], int]:
        enriched: list[ExhibitorRecord] = []
        changed = 0
        for record in records:
            if record.official_domain:
                enriched.append(record)
                continue
            domain = self.lookup_domain(record.name)
            if domain:
                changed += 1
                enriched.append(
                    ExhibitorRecord(
                        name=record.name,
                        official_domain=domain,
                        source_url=record.source_url,
                        confidence=min(record.confidence + 0.15, 0.95),
                        raw_payload={**record.raw_payload, "enriched_via": "duckduckgo_html"},
                    )
                )
            else:
                enriched.append(record)
        return enriched, changed

    def lookup_domain(self, company_name: str) -> str | None:
        import requests
        from bs4 import BeautifulSoup

        query = quote_plus(f'{company_name} official website')
        url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.select("a.result__url, a.result__a"):
            href = anchor.get("href", "")
            domain = normalized_domain(href)
            if domain and not self._is_aggregator(domain):
                return domain
        return None

    def _is_aggregator(self, domain: str) -> bool:
        blocked = [
            "linkedin.com",
            "facebook.com",
            "instagram.com",
            "x.com",
            "twitter.com",
            "youtube.com",
            "eventseye.com",
            "10times.com",
            "expodatabase.com",
            "mapquest.com",
            "bloomberg.com",
            "crunchbase.com",
            "wikipedia.org",
        ]
        return any(domain == item or domain.endswith(f".{item}") for item in blocked)
