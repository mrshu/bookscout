"""BookScout CLI - Book price comparison tool."""

import asyncio
import json
from collections import Counter
from enum import Enum
from typing import Annotated

import typer
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

from bookscout.models import BookResult, parse_price
from bookscout.scrapers import BlackwellsScraper, KennysScraper, LibristoScraper, WorderyScraper

app = typer.Typer(
    name="bookscout",
    help="Compare book prices across Blackwells, Kennys, Libristo, and Wordery.",
    no_args_is_help=True,
)
console = Console()


class OutputFormat(str, Enum):
    """Output format options."""

    table = "table"
    json = "json"
    csv = "csv"


class Store(str, Enum):
    """Available bookstores."""

    blackwells = "blackwells"
    kennys = "kennys"
    libristo = "libristo"
    wordery = "wordery"


SCRAPER_MAP = {
    Store.blackwells: BlackwellsScraper,
    Store.kennys: KennysScraper,
    Store.libristo: LibristoScraper,
    Store.wordery: WorderyScraper,
}


def find_canonical_isbn(isbns: list[str]) -> str | None:
    """Find the most common ISBN from a list (majority vote)."""
    if not isbns:
        return None
    counter = Counter(isbns)
    most_common = counter.most_common(1)
    if most_common:
        return most_common[0][0]
    return None


def find_canonical_isbn_weighted(
    store_results: list[list],  # List of SearchResultItem lists per store
    self_pub_penalty: float = 0.3,
) -> str | None:
    """Find the best ISBN using frequency + ranking weight.

    ISBNs that appear earlier in search results get higher scores.
    Score = sum of (1 / position) for each occurrence.

    Example:
    - ISBN at position 1 in 2 stores: 1/1 + 1/1 = 2.0
    - ISBN at position 3 in 3 stores: 1/3 + 1/3 + 1/3 = 1.0

    This prefers ISBNs ranked highly across multiple stores over
    ISBNs that appear frequently but at lower positions.

    Args:
        store_results: List of SearchResultItem lists, one per store.
        self_pub_penalty: Multiplier for 979-8 ISBNs (0.0-1.0). Default 0.3.
            The 979-8 prefix is US-only, introduced ~2020 when 978 ran out.
            Amazon KDP assigns free 979-8 ISBNs to self-published books
            (imprint shows as "Independently published"). While not all
            979-8 books are knockoffs, the mass-produced "summary" books
            that copy popular titles are almost exclusively 979-8 via KDP.
            Set to 1.0 to disable penalty.
            See: https://www.isbn-international.org/content/changes-united-states-isbn-prefixes
    """
    isbn_scores: dict[str, float] = {}

    for results in store_results:
        seen_in_store: set[str] = set()
        for position, item in enumerate(results, start=1):
            if item.isbn and item.isbn not in seen_in_store:
                seen_in_store.add(item.isbn)
                # Score = 1/position (position 1 = 1.0, position 2 = 0.5, etc.)
                score = 1.0 / position
                isbn_scores[item.isbn] = isbn_scores.get(item.isbn, 0) + score

    if not isbn_scores:
        return None

    # Penalize ISBNs starting with 979-8 (often self-published knockoffs)
    if self_pub_penalty < 1.0:
        for isbn in isbn_scores:
            if isbn.startswith("9798"):
                isbn_scores[isbn] *= self_pub_penalty

    # Return ISBN with highest score
    return max(isbn_scores, key=isbn_scores.get)


def find_canonical_isbn_from_results(results: list[BookResult | None]) -> str | None:
    """Find the most common ISBN among BookResult objects (majority vote)."""
    isbns = [r.isbn for r in results if r and r.isbn]
    return find_canonical_isbn(isbns)


async def run_scrapers(
    query: str,
    stores: list[Store],
    isbn_mode: bool = False,
    validate_isbn: bool = True,
) -> list[BookResult | None]:
    """Run scrapers in parallel and return results.

    If validate_isbn is True and searching by title, uses a two-phase approach:
    1. Extract ISBNs from search results pages (fast, no product page visits)
    2. Find canonical ISBN via majority vote across all search results
    3. Fetch product details only for the correct ISBN
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            scrapers = [SCRAPER_MAP[store](browser) for store in stores]

            if isbn_mode:
                # Direct ISBN search - no validation needed
                tasks = [scraper.search_isbn(query) for scraper in scrapers]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                processed: list[BookResult | None] = []
                for r in results:
                    if isinstance(r, Exception):
                        processed.append(None)
                    else:
                        processed.append(r)
                return processed

            # Two-phase approach for title search with ISBN validation
            if validate_isbn:
                # Phase 1: Get search results (ISBNs) from all stores in parallel
                search_tasks = [scraper.get_search_results(query) for scraper in scrapers]
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

                # Collect search results from all stores
                store_search_results: list[list] = []

                for result in search_results:
                    if isinstance(result, Exception) or not result:
                        store_search_results.append([])
                    else:
                        store_search_results.append(result)

                # Find canonical ISBN using weighted scoring (frequency + ranking)
                canonical_isbn = find_canonical_isbn_weighted(store_search_results)

                if canonical_isbn:
                    # Phase 2: For each store, find the URL with matching ISBN and fetch details
                    # Build tasks for parallel execution
                    async def fetch_details(scraper, search_items, isbn):
                        """Fetch product details for a single store."""
                        # Find the URL with matching ISBN
                        matching_url = None
                        for item in search_items:
                            if item.isbn == isbn:
                                matching_url = item.url
                                break

                        try:
                            if matching_url:
                                return await scraper.get_product_details(matching_url)
                            else:
                                return await scraper.search_isbn(isbn)
                        except Exception:
                            return None

                    # Run all product detail fetches in parallel
                    detail_tasks = [
                        fetch_details(scraper, store_search_results[i], canonical_isbn)
                        for i, scraper in enumerate(scrapers)
                    ]
                    processed = await asyncio.gather(*detail_tasks)

                    return list(processed)

            # Fallback: old approach (no two-phase, or no canonical ISBN found)
            tasks = [scraper.search(query) for scraper in scrapers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed: list[BookResult | None] = []
            for r in results:
                if isinstance(r, Exception):
                    processed.append(None)
                else:
                    processed.append(r)

            return processed
        finally:
            await browser.close()


def display_table(results: list[BookResult | None], stores: list[Store]) -> None:
    """Display results as a rich table."""
    table = Table(title="Book Prices")
    table.add_column("Store", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Price", style="green", justify="right")
    table.add_column("Link", style="blue")

    for store, result in zip(stores, results):
        if result:
            table.add_row(
                result.store,
                result.title[:50] + "..." if len(result.title) > 50 else result.title,
                result.price,
                result.url,
            )
        else:
            table.add_row(store.value.capitalize(), "-", "Not found", "-")

    console.print(table)

    # Show best price (simple string comparison - works for same currency)
    found_results = [r for r in results if r and r.price != "N/A"]
    if found_results:
        console.print()
        # Just show all prices found since they might be different currencies
        console.print("[bold]Prices found:[/bold]")
        for r in found_results:
            console.print(f"  {r.store}: {r.price}")


def display_json(results: list[BookResult | None], stores: list[Store]) -> None:
    """Display results as JSON with normalized price/currency."""
    output = []
    for store, result in zip(stores, results):
        if result:
            parsed = parse_price(result.price)
            output.append({
                "store": result.store,
                "title": result.title,
                "price": parsed.amount,
                "currency": parsed.currency,
                "url": result.url,
                "isbn": result.isbn,
            })
        else:
            output.append({
                "store": store.value.capitalize(),
                "title": None,
                "price": None,
                "currency": None,
                "url": None,
                "isbn": None,
            })

    console.print(json.dumps(output, indent=2))


def display_csv(results: list[BookResult | None], stores: list[Store]) -> None:
    """Display results as CSV."""
    console.print("store,title,price,url,isbn")
    for store, result in zip(stores, results):
        if result:
            # Escape quotes in title
            title = result.title.replace('"', '""')
            console.print(f'{result.store},"{title}","{result.price}",{result.url},{result.isbn or ""}')
        else:
            console.print(f'{store.value.capitalize()},"","Not found","",""')


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(help="Book title to search for"),
    ] = "",
    isbn: Annotated[
        str | None,
        typer.Option("--isbn", "-i", help="Search by ISBN instead of title"),
    ] = None,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
    store: Annotated[
        list[Store] | None,
        typer.Option("--store", "-s", help="Specific stores to search (can be repeated)"),
    ] = None,
) -> None:
    """Search for a book across bookstores and compare prices."""
    # Determine search query
    if isbn:
        search_query = isbn
        isbn_mode = True
    elif query:
        search_query = query
        isbn_mode = False
    else:
        console.print("[red]Error:[/red] Please provide a book title or --isbn")
        raise typer.Exit(1)

    # Determine which stores to search
    stores = store if store else list(Store)

    # Show progress
    with console.status(f"[bold green]Searching for '{search_query}'..."):
        results = asyncio.run(run_scrapers(search_query, stores, isbn_mode))

    # Display results
    if format == OutputFormat.table:
        display_table(results, stores)
    elif format == OutputFormat.json:
        display_json(results, stores)
    elif format == OutputFormat.csv:
        display_csv(results, stores)


if __name__ == "__main__":
    app()
