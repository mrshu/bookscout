"""Base scraper class for bookstores."""

import re
from abc import ABC, abstractmethod

from playwright.async_api import Browser, Page

from bookscout.models import BookResult


def title_matches_query(title: str, query: str, threshold: float = 0.5) -> bool:
    """Check if a title matches the search query reasonably well.

    Args:
        title: The book title to check.
        query: The search query.
        threshold: Minimum fraction of query words that must appear in title.

    Returns:
        True if the title is a reasonable match for the query.
    """
    # Normalize both strings
    title_lower = title.lower()
    query_lower = query.lower()

    # Extract words (alphanumeric only)
    query_words = set(re.findall(r"\w+", query_lower))
    title_words = set(re.findall(r"\w+", title_lower))

    if not query_words:
        return True

    # Count how many query words appear in the title
    matching_words = query_words & title_words
    match_ratio = len(matching_words) / len(query_words)

    return match_ratio >= threshold


class BaseScraper(ABC):
    """Abstract base class for bookstore scrapers."""

    name: str = "Unknown"

    def __init__(self, browser: Browser) -> None:
        self.browser = browser

    async def _new_page(self) -> Page:
        """Create a new page with common settings."""
        context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return await context.new_page()

    @abstractmethod
    async def search(self, query: str) -> BookResult | None:
        """Search for a book and return the first result.

        Args:
            query: Book title or ISBN to search for.

        Returns:
            BookResult if found, None otherwise.
        """
        ...

    @abstractmethod
    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search for a book by ISBN.

        Args:
            isbn: ISBN-10 or ISBN-13.

        Returns:
            BookResult if found, None otherwise.
        """
        ...
