# Exhibitor Domain Scraper v2

Qualification-first batch scraper for exhibitor directories.

## Features
- Input via single URL, CSV, or TXT
- Discovery-first workflow: directory URL -> extraction method -> 10-record pilot -> pagination audit -> full scrape
- SQLite persistence (`events`, `exhibitors`, `event_logs`)
- Per-event diagnostics and loud failure modes
- Deduplication + confidence scoring
- Apollo-ready CSV export
- Continues batch processing when one event fails

## CLI
```bash
python exhibitor_scraper.py run --input events.csv
python exhibitor_scraper.py pilot --url https://example.com/event
python exhibitor_scraper.py summary
python exhibitor_scraper.py retry-failed
```

## Install
```bash
pip install requests beautifulsoup4
# optional for SPA rendering
pip install playwright
playwright install
```

## Notes
- No CAPTCHA bypass, stealth, contact scraping, or CRM integration.
- If a site needs search enrichment for missing domains, add it explicitly and log it explicitly; this version does not hide that behind a silent fallback.
