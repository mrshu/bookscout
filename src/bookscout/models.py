"""Data models for BookScout."""

from dataclasses import dataclass


@dataclass
class BookResult:
    """Result from a bookstore search."""

    store: str
    title: str
    price: str  # Keep as string to preserve original formatting (e.g., "€12.99", "£10.50")
    url: str
    isbn: str | None = None
