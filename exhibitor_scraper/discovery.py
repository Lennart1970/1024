from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from .models import EventDiscovery

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ExhibitorDomainScraper/2.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


class DiscoveryError(RuntimeError):
    pass


class EventDiscoverer:
    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout

    def discover(self, event_url: str) -> EventDiscovery:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(event_url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        for strategy in (
            self._discover_hidden_api,
            self._discover_embedded_json,
            self._discover_iframe,
            self._discover_directory_links,
            self._discover_playwright_spa,
        ):
            found = strategy(event_url, html, soup)
            if found:
                return found

        raise DiscoveryError(f"Could not discover exhibitor directory URL from event page: {event_url}")

    def _discover_hidden_api(self, event_url: str, html: str, soup: BeautifulSoup) -> EventDiscovery | None:
        patterns = [
            r'https?://[^\"\']+(?:api|graphql|directory|exhibitor)[^\"\']+',
            r'/(?:api|graphql|directory|exhibitors?)[^\"\']+',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                candidate = urljoin(event_url, match.group(0))
                return EventDiscovery(event_url=event_url, directory_url=candidate, extraction_method="hidden_api")
        return None

    def _discover_embedded_json(self, event_url: str, html: str, soup: BeautifulSoup) -> EventDiscovery | None:
        if "__NEXT_DATA__" in html or 'application/ld+json' in html:
            return EventDiscovery(event_url=event_url, directory_url=event_url, extraction_method="embedded_json")
        return None

    def _discover_iframe(self, event_url: str, html: str, soup: BeautifulSoup) -> EventDiscovery | None:
        for iframe in soup.select("iframe[src]"):
            src = iframe.get("src", "")
            if any(token in src.lower() for token in ["exhibitor", "directory", "list", "vendor"]):
                return EventDiscovery(event_url=event_url, directory_url=urljoin(event_url, src), extraction_method="iframe_directory")
        return None

    def _discover_directory_links(self, event_url: str, html: str, soup: BeautifulSoup) -> EventDiscovery | None:
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            text = " ".join(anchor.stripped_strings).lower()
            if any(token in href.lower() for token in ["exhibitor", "directory", "vendor", "a-z", "alphabetical"]):
                return EventDiscovery(event_url=event_url, directory_url=urljoin(event_url, href), extraction_method="static_pagination")
            if any(token in text for token in ["exhibitor list", "exhibitors", "directory", "vendors", "view all exhibitors"]):
                return EventDiscovery(event_url=event_url, directory_url=urljoin(event_url, href), extraction_method="a_z_listing")
        return None

    def _discover_playwright_spa(self, event_url: str, html: str, soup: BeautifulSoup) -> EventDiscovery | None:
        root = soup.select_one("div#__next, div#app, div[data-reactroot]")
        if root is not None:
            return EventDiscovery(event_url=event_url, directory_url=event_url, extraction_method="playwright_spa")
        return None


def normalized_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    domain = parsed.netloc.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None
