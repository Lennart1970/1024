from __future__ import annotations

import json
from pathlib import Path

from .db import Database
from .discovery import DiscoveryError, EventDiscoverer
from .enrichment import SearchEnricher
from .exporter import Exporter
from .extractors import ExtractionError, Extractor
from .inputs import load_urls
from .models import RunStats
from .pagination import PaginationAuditError, PaginationAuditor
from .pilot import PilotFailure, PilotRunner


class BatchRunner:
    def __init__(self, db: Database, export_dir: Path) -> None:
        self.db = db
        self.exporter = Exporter(db, export_dir)
        self.discoverer = EventDiscoverer()
        self.extractor = Extractor()
        self.enricher = SearchEnricher()
        self.pilot_runner = PilotRunner(self.extractor)
        self.pagination_auditor = PaginationAuditor(self.extractor)

    def run_input(self, input_value: str, resume: bool = False) -> RunStats:
        urls = load_urls(input_value)
        stats = RunStats(total=len(urls))
        for url in urls:
            if resume and self.db.successful_event_exists(url):
                stats.skipped += 1
                continue
            try:
                self.run_single(url=url, pilot_only=False)
                stats.completed += 1
            except Exception as exc:
                stats.failed += 1
                print(f"FAILED {url}: {exc}")
        export_path = self.exporter.export_apollo_csv()
        print(f"Apollo-ready export: {export_path}")
        return stats

    def retry_failed(self) -> RunStats:
        urls = self.db.failed_event_urls()
        stats = RunStats(total=len(urls))
        for url in urls:
            try:
                self.run_single(url=url, pilot_only=False)
                stats.completed += 1
            except Exception as exc:
                stats.failed += 1
                print(f"FAILED {url}: {exc}")
        export_path = self.exporter.export_apollo_csv()
        print(f"Apollo-ready export: {export_path}")
        return stats

    def run_single(self, url: str, pilot_only: bool = False) -> None:
        event_id = self.db.upsert_event(url, status="running")
        self.db.log(event_id, "INFO", "start", f"Starting event run for {url}")
        try:
            discovery = self.discoverer.discover(url)
            self.db.log(event_id, "INFO", "discover", f"Discovered {discovery.directory_url}", json.dumps(discovery.details or {}))
            self.db.update_event(event_id, directory_url=discovery.directory_url, extraction_method=discovery.extraction_method, expected_count=discovery.expected_count)

            pilot = self.pilot_runner.run(discovery)
            self.db.log(event_id, "INFO", "pilot", f"Pilot passed with {len(pilot.records)} records")
            self.db.update_event(event_id, pilot_count=len(pilot.records), pilot_passed=1)
            if pilot_only:
                self.db.update_event(event_id, status="pilot_passed")
                print(f"Pilot passed for {url} using {discovery.extraction_method} -> {discovery.directory_url}")
                return

            audit = self.pagination_auditor.audit(discovery)
            self.db.log(event_id, "INFO", "pagination", f"Pagination audit passed; expected_count={audit.expected_count}")

            records = self.extractor.extract(discovery)
            if not records:
                raise ExtractionError("Full scrape produced zero records after successful pilot")
            if discovery.expected_count and len(records) < max(3, int(discovery.expected_count * 0.5)):
                raise ExtractionError(f"Expected about {discovery.expected_count} exhibitors but only extracted {len(records)}")

            missing_before = sum(1 for row in records if not row.official_domain)
            if missing_before:
                self.db.log(event_id, "WARN", "enrichment", f"{missing_before} exhibitors missing domains; running search enrichment fallback")
                records, enriched_count = self.enricher.enrich_missing_domains(records)
                self.db.log(event_id, "INFO", "enrichment", f"Search enrichment filled {enriched_count} missing domains")
            missing_after = [row.name for row in records if not row.official_domain]
            if missing_after:
                sample = ", ".join(missing_after[:5])
                raise ExtractionError(f"Domain enrichment incomplete; still missing domains for {len(missing_after)} exhibitors. Sample: {sample}")

            prepared = []
            for row in records:
                payload = json.dumps(row.raw_payload, ensure_ascii=False) if row.raw_payload else None
                prepared.append((row.name, row.official_domain, row.source_url, row.confidence, payload))
            self.db.replace_exhibitors(event_id, prepared)
            avg_confidence = sum(row.confidence for row in records) / len(records)
            self.db.update_event(event_id, status="completed", actual_count=len(records), expected_count=audit.expected_count, confidence_avg=avg_confidence, last_error=None)
            self.db.log(event_id, "INFO", "complete", f"Completed event with {len(records)} exhibitors")
            print(f"COMPLETED {url}: {len(records)} exhibitors via {discovery.extraction_method}")
        except (DiscoveryError, PilotFailure, PaginationAuditError, ExtractionError, Exception) as exc:
            self.db.update_event(event_id, status="failed", last_error=str(exc))
            self.db.log(event_id, "ERROR", "failed", str(exc))
            raise

    def render_summary(self) -> str:
        rows = self.db.summary_rows()
        if not rows:
            return "No event runs recorded yet."
        lines = []
        for row in rows:
            lines.append(" | ".join([row["status"], row["event_url"], row["extraction_method"] or "n/a", f"pilot={row['pilot_passed']}", f"expected={row['expected_count'] or 'n/a'}", f"actual={row['actual_count'] or 'n/a'}", row["last_error"] or "ok"]))
        return "\n".join(lines)
