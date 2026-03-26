# GitHub Pages deploy

This folder is ready for a simple static deployment via GitHub Pages.

## Publish

1. Push this repository to GitHub.
2. In the repo settings, open **Pages**.
3. Set:
   - **Source**: Deploy from a branch
   - **Branch**: `main`
   - **Folder**: `/benchmark_v1` if you publish via a docs-style branch layout, or move/copy `benchmark_v1/index.html` to repo root and publish from `/root`.

## Files you want public

- `index.html`
- `README_GITHUB_PAGES.md`
- optionally `questions.sample.csv`

## Files you do NOT want public

- `.env`
- `raw/`
- anything containing API keys or private request metadata

## Easiest GitHub Pages shape

If you want the simplest Pages setup, copy these to repo root before pushing:

- `benchmark_v1/index.html` -> `index.html`
- optional: `benchmark_v1/questions.sample.csv` -> `questions.sample.csv`

Then enable Pages from branch `main` and folder `/root`.
