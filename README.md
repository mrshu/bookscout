# BookScout

A CLI tool that finds book prices across multiple bookstores. Built for humans
who want quick price comparisons and AI agents that need structured book data.

## Why BookScout?

Finding the best price for a book means checking multiple stores manually.
BookScout does this in parallel, returning prices from:

- **Blackwells** (UK) — <https://blackwells.co.uk>
- **Kennys** (Ireland) — <https://kennys.ie>
- **Wordery** (UK) — <https://wordery.com>

Results come back in seconds with direct links to purchase.

## Installation

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone https://github.com/mrshu/bookscout
cd bookscout
uv sync

# Install Playwright browser
uv run playwright install chromium
```

## Usage

### Search by title

```bash
uv run bookscout "Atomic Habits"
```

```text
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Store      ┃ Title                     ┃   Price ┃ Link                     ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Blackwells │ Atomic Habits...          │  20,54€ │ https://blackwells.co.uk │
│ Kennys     │ The Atomic Habits Work... │ € 15.42 │ https://www.kennys.ie/sh │
│ Wordery    │ Atomic Habits...          │  £17.99 │ https://wordery.com/book │
└────────────┴───────────────────────────┴─────────┴──────────────────────────┘
```

### Search by ISBN

```bash
uv run bookscout --isbn 9781847941831
```

### JSON output (for agents)

```bash
uv run bookscout "Software Architecture Hard Parts" --format json
```

```json
[
  {
    "store": "Blackwells",
    "title": "Software Architecture: The Hard Parts...",
    "price": "53,58€",
    "url": "https://blackwells.co.uk/bookshop/product/...",
    "isbn": "9781492086895"
  },
  {
    "store": "Kennys",
    "title": "Software Architecture: The Hard Parts...",
    "price": "€ 75.31",
    "url": "https://www.kennys.ie/shop/...",
    "isbn": null
  }
]
```

### CSV output

```bash
uv run bookscout "Domain Driven Design" --format csv
```

### Search specific stores

```bash
uv run bookscout "Clean Code" --store blackwells --store wordery
```

## For AI Agents

BookScout is designed to be agent-friendly:

- **Structured output**: Use `--format json` for machine-readable results
- **Deterministic**: Same query returns consistent result structure
- **Fast**: Parallel scraping across all stores
- **Direct links**: Each result includes a purchase URL

Example agent workflow:

```bash
# Agent searches for a book
result=$(uv run bookscout "Designing Data-Intensive Applications" -f json)

# Parse JSON to find lowest price or preferred store
echo "$result" | jq '.[] | select(.price != null)'
```

## Options

| Option     | Short | Description                                     |
|------------|-------|-------------------------------------------------|
| `--isbn`   | `-i`  | Search by ISBN instead of title                 |
| `--format` | `-f`  | Output format: `table` (default), `json`, `csv` |
| `--store`  | `-s`  | Limit to specific stores (repeatable)           |

## How it works

BookScout uses [Playwright](https://playwright.dev/) to render JavaScript-heavy
bookstore sites in a headless browser. Each store has a dedicated scraper that:

1. Performs a search query
2. Finds results matching the query title
3. Extracts price, title, URL, and ISBN
4. Returns structured data

Searches run in parallel for speed.

## Limitations

- **Currency**: Prices shown in each store's native currency (EUR, GBP)
- **Availability**: Returns first matching result per store
- **Bot protection**: Some stores may occasionally block automated requests

## License

MIT
