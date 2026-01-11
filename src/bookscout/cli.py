"""BookScout CLI - Book price comparison tool."""

import asyncio
import json
from enum import Enum
from typing import Annotated

import typer
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

from bookscout.models import BookResult
from bookscout.scrapers import BlackwellsScraper, KennysScraper, WorderyScraper

app = typer.Typer(
    name="bookscout",
    help="Compare book prices across Blackwells, Kennys, and Wordery.",
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
    wordery = "wordery"


SCRAPER_MAP = {
    Store.blackwells: BlackwellsScraper,
    Store.kennys: KennysScraper,
    Store.wordery: WorderyScraper,
}


async def run_scrapers(
    query: str,
    stores: list[Store],
    isbn_mode: bool = False,
) -> list[BookResult | None]:
    """Run scrapers in parallel and return results."""
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
            processed = []
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
    """Display results as JSON."""
    output = []
    for store, result in zip(stores, results):
        if result:
            output.append({
                "store": result.store,
                "title": result.title,
                "price": result.price,
                "url": result.url,
                "isbn": result.isbn,
            })
        else:
            output.append({
                "store": store.value.capitalize(),
                "title": None,
                "price": None,
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
