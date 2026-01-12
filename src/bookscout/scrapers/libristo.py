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
        search_url = f"{self.base_url}/en/search?t={encoded_query}"

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
            await page.wait_for_timeout(3000)

            return await self._extract_first_result(page)
        finally:
            await page.close()

    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search Libristo by ISBN."""
        return await self.search(isbn)

    async def _extract_first_result(self, page) -> BookResult | None:
        """Extract the first search result from the page."""
        # Use JavaScript to find product links - they follow pattern /en/book/{slug}_{id}
        product_href = await page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                // Match /en/book/ or /sk/kniha/ etc patterns with underscore+digits at end
                if (href.match(/\\/(book|kniha|buch)\\/[^/]+_\\d+$/)) {
                    return href;
                }
            }
            return null;
        }''')

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
        # Libristo uses "EAN" label instead of "ISBN"
        isbn = None
        isbn_match = re.search(r"(?:ISBN|EAN)[:\s]*(\d{10,13})", all_text, re.IGNORECASE)
        if isbn_match:
            isbn = isbn_match.group(1)
        else:
            # Try to find standalone 13-digit ISBN
            isbn_13 = re.search(r"\b(\d{13})\b", all_text)
            if isbn_13:
                isbn = isbn_13.group(1)
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
