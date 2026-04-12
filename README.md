# coffeedb

coffeedb is a small SQLite-backed scraper for the World's 100 Best Coffee Shops website. It can capture the current live ranking, replay archived list/detail pages from the Wayback Machine, and keep each scrape as a dated snapshot so ranking and detail changes remain queryable over time.

This repository is intentionally simple. The code is organized so a human or Copilot can answer three questions quickly:

1. How do I run it?
2. Where does the data come from?
3. Why is the database shaped this way?

## Quick start

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Initialize a database

```bash
coffeedb init --db coffee.db
```

### Scrape the live site

```bash
coffeedb scrape live --db coffee.db
```

### Scrape historical snapshots from Wayback

```bash
coffeedb scrape historical --db coffee.db --limit 5
```

### Query the latest top shops

```bash
coffeedb query top --db coffee.db --n 10
```

### Query one shop's ranking history

```bash
coffeedb query history onyx-coffee-lab --db coffee.db
```

## CLI overview

### `coffeedb init`

Creates the SQLite schema. It is safe to re-run on a new database.

Important: the current schema compatibility check is intentionally simple. If the database shape does not match the expected final schema, the code drops the old tables and recreates them. That keeps the project easy to reason about, but it is destructive for incompatible old databases. Back up an existing database before re-initializing it.

### `coffeedb scrape live`

Fetches the current list page and then each detail page from the live site. Each run creates or reuses today's snapshot and stores:

- the list-page rank and display fields shown on the ranking page
- the parsed detail fields from the shop page
- the detail page URL used for that scrape

### `coffeedb scrape historical`

Uses the Wayback CDX API to find archived list pages, then requests archived list and detail pages from the Wayback Machine.

Useful options:

- `--limit`: process only the first `N` snapshots
- `--timestamp`: process specific Wayback timestamps
- `--delay`: seconds to wait between Wayback requests
- `--fresh`: bypass the local HTTP cache
- `--debug`: print per-snapshot diagnostics

### `coffeedb query top`

Shows the ranking table for the latest snapshot, or for a specific `--date`.

### `coffeedb query history`

Shows how one shop slug moved across snapshots.

## Data sources and scraper assumptions

The scraper is tied to the current HTML structure used by the site.

- List pages are expected to expose shops inside Elementor loop items.
- Detail pages are expected to expose the main content inside a `single-post` Elementor container.
- Contact details are most reliable under the `Contact` section.
- Missing city/country values are inferred from the address when possible.

These heuristics are deliberate. The code prefers a few explicit parsing rules over a generic parser that is harder to debug.

## Cache behavior

HTTP requests go through a small on-disk cache backed by `hishel`.

- Only `GET` requests are cached.
- Only successful `2xx` responses are cached.
- `--fresh` bypasses the cache for that command.

Environment variables:

- `COFFEEDB_CACHE_DIR`: override the cache directory. Default: `.cache/coffeedb/http`
- `COFFEEDB_CACHE_DEBUG`: print cache hit/miss telemetry when set to `1`, `true`, `yes`, or `on`

## Project structure

```text
src/coffeedb/
	cli.py          Typer commands and scrape/query orchestration
	constants.py    Shared URLs, timeouts, and helper URL builders
	db.py           SQLite schema and persistence helpers
	http_client.py  Cached HTTP client helpers
	scraper.py      HTML parsing for list and detail pages
	wayback.py      CDX lookup and archived page fetching
```

## Database design

The database is temporal by design. The same shop can appear in many snapshots, and each snapshot can preserve both rank and detail data as they existed at that time.

Core rules:

- `shops` stores stable identity by slug
- `snapshots` stores when and where a collection came from
- `rankings` stores the list-page state for one shop in one snapshot
- `shop_details` stores the parsed detail-page state for one shop in one snapshot

This means a shop can change rank, name formatting, country text, address, or links over time without overwriting prior history.

More detail is in [docs/architecture.md](docs/architecture.md).

## For Copilot and contributors

When editing this project, keep these boundaries intact:

- `scraper.py` should focus on HTML parsing only
- `wayback.py` should focus on archive discovery and archived-page fetches
- `db.py` should own schema and SQL writes
- `cli.py` should orchestrate workflow, not duplicate parsing or persistence rules

Readability matters more than cleverness here. Prefer named constants, small helpers, and explicit fallbacks over abstraction for its own sake.

## Verification checklist

After a refactor, these commands are the minimum smoke test:

```bash
coffeedb init --db /tmp/coffee.db
coffeedb query top --db /tmp/coffee.db
coffeedb scrape historical --db /tmp/coffee.db --limit 1
```

The historical command is the fastest end-to-end check because it exercises snapshot lookup, archived fetches, list parsing, detail parsing, and database writes.
