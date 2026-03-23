from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from .discovery import DEFAULT_HEADERS, normalized_domain
from .models import EventDiscovery, ExhibitorRecord


class ExtractionError(RuntimeError):
    pass


class Extractor:
    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout

    def extract(self, discovery: EventDiscovery, limit: int | None = None) -> list[ExhibitorRecord]:
        method = discovery.extraction_method
        if method == "hidden_api":
            records = self._extract_hidden_api(discovery.directory_url)
        elif method == "embedded_json":
            records = self._extract_embedded_json(discovery.directory_url)
        elif method == "iframe_directory":
            records = self._extract_html_directory(discovery.directory_url)
        elif method in {"a_z_listing", "static_pagination"}:
            records = self._extract_paginated_html(discovery.directory_url)
        elif method == "playwright_spa":
            records = self._extract_playwright_spa(discovery.directory_url)
        else:
            raise ExtractionError(f"Unsupported extraction method: {method}")

        records = self._dedupe(records)
        if limit is not None:
            records = records[:limit]
        return records

    def _extract_hidden_api(self, url: str) -> list[ExhibitorRecord]:
        import requests

        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception as exc:
            raise ExtractionError(f"Hidden API did not return JSON: {url}") from exc
        return self._records_from_any(payload, source_url=url)

    def _extract_embedded_json(self, url: str) -> list[ExhibitorRecord]:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        payloads = []
        for tag in soup.select('script[type="application/ld+json"], script#__NEXT_DATA__'):
            raw = tag.string or tag.get_text("", strip=True)
            if not raw:
                continue
            try:
                payloads.append(json.loads(raw))
            except Exception:
                continue
        records: list[ExhibitorRecord] = []
        for payload in payloads:
            records.extend(self._records_from_any(payload, source_url=url))
        if not records:
            raise ExtractionError(f"No exhibitor records found in embedded JSON at {url}")
        return records

    def _extract_html_directory(self, url: str) -> list[ExhibitorRecord]:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        records = self._records_from_cards(soup, url)
        if not records:
            raise ExtractionError(f"No exhibitor cards detected in HTML directory: {url}")
        return records

    def _extract_paginated_html(self, url: str) -> list[ExhibitorRecord]:
        import requests
        from bs4 import BeautifulSoup

        page_urls = self._pagination_urls(url)
        records: list[ExhibitorRecord] = []
        for page_url in page_urls:
            response = requests.get(page_url, headers=DEFAULT_HEADERS, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            records.extend(self._records_from_cards(soup, page_url))
        if not records:
            raise ExtractionError(f"Pagination audit found zero exhibitors at {url}")
        return records

    def _extract_playwright_spa(self, url: str) -> list[ExhibitorRecord]:
        from bs4 import BeautifulSoup

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ExtractionError(
                "Playwright extraction required but playwright is not installed. Install with: pip install playwright && playwright install"
            ) from exc

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        records = self._records_from_cards(soup, url)
        if records:
            return records
        raise ExtractionError(f"Playwright rendered page but no exhibitors could be extracted: {url}")

    def _pagination_urls(self, root_url: str) -> list[str]:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(root_url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        urls = {root_url}
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if re.search(r"page=\d+", href, flags=re.IGNORECASE) or re.search(r"/page/\d+", href, flags=re.IGNORECASE):
                urls.add(urljoin(root_url, href))
        return sorted(urls)

    def _records_from_cards(self, soup, source_url: str) -> list[ExhibitorRecord]:
        selectors = [".exhibitor-card", ".vendor-card", ".company-card", "[data-exhibitor-id]", "article", ".card", "li"]
        records: list[ExhibitorRecord] = []
        seen_names: set[str] = set()
        for selector in selectors:
            for node in soup.select(selector):
                name = self._extract_name(node)
                if not name or len(name) < 2:
                    continue
                clean_name = self._clean_name(name)
                if clean_name.lower() in seen_names:
                    continue
                website = self._extract_website(node)
                seen_names.add(clean_name.lower())
                records.append(ExhibitorRecord(name=clean_name, official_domain=normalized_domain(website), source_url=source_url, confidence=self._score(clean_name, website, source="html"), raw_payload={"selector": selector}))
        return records

    def _records_from_any(self, payload, source_url: str) -> list[ExhibitorRecord]:
        records: list[ExhibitorRecord] = []
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise ExtractionError("Payload type not supported for record extraction")
        for item in payload:
            records.extend(self._walk_payload(item, source_url=source_url))
        if not records:
            raise ExtractionError(f"No exhibitor-like records found in payload from {source_url}")
        return records

    def _walk_payload(self, item, source_url: str) -> list[ExhibitorRecord]:
        records: list[ExhibitorRecord] = []
        if isinstance(item, list):
            for child in item:
                records.extend(self._walk_payload(child, source_url))
            return records
        if isinstance(item, dict):
            name = self._first(item, ["name", "company", "exhibitorName", "title"])
            website = self._first(item, ["website", "url", "companyWebsite", "domain"])
            if name:
                records.append(ExhibitorRecord(name=self._clean_name(str(name)), official_domain=normalized_domain(str(website)) if website else None, source_url=source_url, confidence=self._score(str(name), str(website) if website else None, source="json"), raw_payload=item))
            for value in item.values():
                if isinstance(value, (dict, list)):
                    records.extend(self._walk_payload(value, source_url))
        return records

    def _extract_name(self, node) -> str | None:
        for selector in ["h1", "h2", "h3", "h4", ".name", ".title", "strong", "a"]:
            target = node.select_one(selector)
            if target:
                text = target.get_text(" ", strip=True)
                if text:
                    return text
        text = node.get_text(" ", strip=True)
        return text[:120] if text else None

    def _extract_website(self, node) -> str | None:
        for anchor in node.select("a[href]"):
            href = anchor.get("href", "")
            if href.startswith("http") and not any(bad in href.lower() for bad in ["facebook.com", "linkedin.com", "instagram.com", "twitter.com", "x.com"]):
                return href
        return None

    def _clean_name(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" -|\t\n\r")

    def _score(self, name: str, website: str | None, source: str) -> float:
        score = 0.45
        if len(name) >= 4:
            score += 0.15
        if website:
            score += 0.3
        if source == "json":
            score += 0.1
        elif source == "html":
            score += 0.05
        return min(score, 0.99)

    def _first(self, payload: dict, keys: list[str]):
        for key in keys:
            if key in payload and payload[key]:
                return payload[key]
        return None

    def _dedupe(self, records: list[ExhibitorRecord]) -> list[ExhibitorRecord]:
        deduped: dict[tuple[str, str | None], ExhibitorRecord] = {}
        for record in records:
            key = (record.name.lower(), record.official_domain)
            existing = deduped.get(key)
            if existing is None or record.confidence > existing.confidence:
                deduped[key] = record
        return sorted(deduped.values(), key=lambda item: item.name.lower())
