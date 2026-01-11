"""Libristo.eu scraper."""

import re
import urllib.parse

from bookscout.models import BookResult

from .base import BaseScraper


class LibristoScraper(BaseScraper):
    """Scraper for libristo.eu."""

    name = "Libristo"
    base_url = "https://www.libristo.eu"

    async def search(self, query: str) -> BookResult | None:
        """Search Libristo for a book."""
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"{self.base_url}/en/search?q={encoded_query}"

        page = await self._new_page()
        try:
            await page.goto(search_url, wait_until="networkidle")

            # Handle cookie consent if present
            try:
                accept_btn = await page.query_selector('button:has-text("Accept")')
                if accept_btn:
                    await accept_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            # Wait for search results to load
            await page.wait_for_timeout(2000)

            return await self._extract_first_result(page)
        finally:
            await page.close()

    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search Libristo by ISBN."""
        return await self.search(isbn)

    async def _extract_first_result(self, page) -> BookResult | None:
        """Extract the first search result from the page."""
        # Look for product links - Libristo uses /en/book/ or similar patterns
        all_links = await page.query_selector_all("a[href]")

        product_href = None
        for link in all_links:
            href = await link.get_attribute("href")
            if href and ("/book/" in href or "/kniha/" in href or "/buch/" in href):
                # Skip navigation/category links
                if "/book/category" in href or "/book/search" in href:
                    continue
                product_href = href
                break

        if not product_href:
            return None

        return await self._extract_from_product_page(page, product_href)

    async def _extract_from_product_page(self, page, href: str) -> BookResult | None:
        """Navigate to a product page and extract details."""
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        await page.goto(url, wait_until="domcontentloaded")

        # Handle cookie consent if present
        try:
            accept_btn = await page.query_selector('button:has-text("Accept")')
            if accept_btn:
                await accept_btn.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

        await page.wait_for_load_state("networkidle")

        # Extract title from h1
        title_el = await page.query_selector("h1")
        title = await title_el.inner_text() if title_el else "Unknown"

        # Extract price - look for € pattern (Libristo uses Euro)
        price = "N/A"
        all_text = await page.inner_text("body")

        # Find prices in format €XX.XX or XX,XX € or XX.XX €
        prices = re.findall(r"(?:€\s*\d+[.,]\d{2}|\d+[.,]\d{2}\s*€)", all_text)
        if prices:
            # Clean up the price format
            price = prices[0].strip()

        # Try to extract ISBN from the page
        isbn = None
        isbn_match = re.search(r"ISBN[:\s]*(\d{10,13})", all_text, re.IGNORECASE)
        if isbn_match:
            isbn = isbn_match.group(1)
        else:
            # Try to find ISBN in URL
            url_isbn = re.search(r"(\d{13}|\d{10})", href)
            if url_isbn:
                isbn = url_isbn.group(1)

        return BookResult(
            store=self.name,
            title=title.strip(),
            price=price,
            url=url,
            isbn=isbn,
        )
