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


def find_canonical_isbn(results: list[BookResult | None]) -> str | None:
    """Find the most common ISBN among results (majority vote)."""
    isbns = [r.isbn for r in results if r and r.isbn]
    if not isbns:
        return None
    # Return the most common ISBN
    counter = Counter(isbns)
    most_common = counter.most_common(1)
    if most_common:
        return most_common[0][0]
    return None


async def run_scrapers(
    query: str,
    stores: list[Store],
    isbn_mode: bool = False,
    validate_isbn: bool = True,
) -> list[BookResult | None]:
    """Run scrapers in parallel and return results.

    If validate_isbn is True and searching by title, will re-search stores
    that return a different ISBN than the majority.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            scrapers = [SCRAPER_MAP[store](browser) for store in stores]

            if isbn_mode:
                tasks = [scraper.search_isbn(query) for scraper in scrapers]
            else:
                tasks = [scraper.search(query) for scraper in scrapers]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to None
            processed: list[BookResult | None] = []
            for r in results:
                if isinstance(r, Exception):
                    processed.append(None)
                else:
                    processed.append(r)

            # ISBN validation: re-search mismatched stores with the correct ISBN
            if validate_isbn and not isbn_mode:
                canonical_isbn = find_canonical_isbn(processed)
                if canonical_isbn:
                    # Find stores that returned a different ISBN
                    stores_to_retry: list[tuple[int, Store]] = []
                    for i, (store, result) in enumerate(zip(stores, processed)):
                        if result and result.isbn and result.isbn != canonical_isbn:
                            stores_to_retry.append((i, store))
                        elif result is None:
                            # Also retry stores that failed, using ISBN
                            stores_to_retry.append((i, store))

                    # Re-search with canonical ISBN
                    if stores_to_retry:
                        retry_scrapers = [SCRAPER_MAP[store](browser) for _, store in stores_to_retry]
                        retry_tasks = [scraper.search_isbn(canonical_isbn) for scraper in retry_scrapers]
                        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)

                        # Update results with retried values
                        for (idx, _), retry_result in zip(stores_to_retry, retry_results):
                            if not isinstance(retry_result, Exception) and retry_result:
                                processed[idx] = retry_result

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
