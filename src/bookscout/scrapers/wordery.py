"""Wordery.com scraper."""

import re
import urllib.parse

from playwright.async_api import TimeoutError as PlaywrightTimeout

from bookscout.models import BookResult

from .base import BaseScraper


class WorderyScraper(BaseScraper):
    """Scraper for wordery.com."""

    name = "Wordery"
    base_url = "https://wordery.com"

    async def search(self, query: str) -> BookResult | None:
        """Search Wordery for a book."""
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"{self.base_url}/search?term={encoded_query}"

        page = await self._new_page()
        try:
            await page.goto(search_url, wait_until="networkidle")

            # Handle cookie consent if present
            try:
                accept_btn = await page.query_selector('button:has-text("Accept All")')
                if accept_btn:
                    await accept_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            # Wait for search results to load fully
            await page.wait_for_timeout(2000)

            return await self._extract_first_result(page)
        finally:
            await page.close()

    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search Wordery by ISBN."""
        return await self.search(isbn)

    async def _extract_first_result(self, page) -> BookResult | None:
        """Extract the first search result from the page."""
        # Wordery product URLs follow pattern: /book/{title}/{author}/{isbn}
        # Use JavaScript to get resolved href (not the attribute) since Wordery
        # uses empty or anchor-only href attributes with base URL resolution
        product_href = await page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            for (const a of links) {
                const href = a.href;  // resolved URL, not attribute
                if (href && href.includes('/book/')) {
                    // Check if URL ends with ISBN-like pattern
                    const parts = href.replace(/#.*$/, '').split('/');
                    const lastPart = parts[parts.length - 1];
                    if (lastPart && lastPart.length >= 10 && /^[0-9Xx]+$/.test(lastPart)) {
                        return href.replace(/#.*$/, '');  // Remove any hash
                    }
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
            accept_btn = await page.query_selector('button:has-text("Accept All")')
            if accept_btn:
                await accept_btn.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

        await page.wait_for_load_state("networkidle")

        # Extract title from h1
        title_el = await page.query_selector("h1")
        title = await title_el.inner_text() if title_el else "Unknown"

        # Extract price - look for £ pattern
        price = "N/A"
        all_text = await page.inner_text("body")

        # Find prices in format £XX.XX
        prices = re.findall(r"£\d+[.,]\d{2}", all_text)
        if prices:
            price = prices[0]  # First price is usually the main one

        # Extract ISBN from URL - pattern is /book/{title}/{author}/{isbn}
        parts = href.rstrip("/").split("/")
        isbn = None
        if parts:
            last_part = parts[-1]
            if len(last_part) >= 10 and last_part.replace("X", "").replace("x", "").isdigit():
                isbn = last_part

        return BookResult(
            store=self.name,
            title=title.strip(),
            price=price,
            url=url,
            isbn=isbn,
        )
