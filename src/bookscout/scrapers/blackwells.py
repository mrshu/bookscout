"""Blackwells.co.uk scraper."""

import re
import urllib.parse

from playwright.async_api import TimeoutError as PlaywrightTimeout

from bookscout.models import BookResult

from .base import BaseScraper, title_matches_query


class BlackwellsScraper(BaseScraper):
    """Scraper for blackwells.co.uk."""

    name = "Blackwells"
    base_url = "https://blackwells.co.uk"

    async def search(self, query: str) -> BookResult | None:
        """Search Blackwells for a book."""
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"{self.base_url}/bookshop/search?keyword={encoded_query}"

        page = await self._new_page()
        try:
            await page.goto(search_url, wait_until="domcontentloaded")

            # Wait for search results to load
            try:
                await page.wait_for_selector(".book-info, .product-info, .search-result", timeout=10000)
            except PlaywrightTimeout:
                return None

            # Try to find the first book result that matches the query
            result = await self._extract_first_result(page, query)
            return result
        finally:
            await page.close()

    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search Blackwells by ISBN."""
        return await self.search(isbn)

    async def _extract_first_result(self, page, query: str) -> BookResult | None:
        """Extract the first search result that matches the query."""
        # Find all product links
        links = await page.query_selector_all('a[href*="/bookshop/product/"]')
        if not links:
            return None

        # Try each product link and check if title matches query
        seen_hrefs = set()
        for link in links[:10]:  # Check up to 10 results
            href = await link.get_attribute("href")
            if not href or href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            # Extract title from URL slug (format: /bookshop/product/Title-Slug/ISBN)
            parts = href.split("/")
            if len(parts) >= 2:
                slug = parts[-2] if parts[-1].isdigit() else parts[-1]
                # Convert slug to readable title
                url_title = slug.replace("-by-", " ").replace("-", " ")

                # Check if this result matches the query
                if title_matches_query(url_title, query):
                    result = await self._extract_from_product_page(page, href, query)
                    if result:
                        return result

        # Fallback: return first result even if title doesn't match well
        if seen_hrefs:
            first_href = list(seen_hrefs)[0]
            return await self._extract_from_product_page(page, first_href, query)

        return None

    async def _extract_from_product_page(self, page, href: str, query: str = "") -> BookResult | None:
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

        # Wait for content to load
        await page.wait_for_load_state("networkidle")

        # Extract title
        title_el = await page.query_selector("h1")
        title = await title_el.inner_text() if title_el else "Unknown"

        # Extract price - look for lines containing "RRP" which have the pattern "RRP XX,XX€ YY,YY€"
        # where YY,YY€ is the actual sale price
        price = "N/A"

        all_text = await page.inner_text("body")
        lines = all_text.split("\n")

        for line in lines:
            line = line.strip()
            # Look for the RRP line pattern: "RRP 20,72€ 20,54€" or "i RRP 20,72€ 20,54€"
            if "RRP" in line:
                # Find all prices in this line
                prices = re.findall(r"\d+[.,]\d{2}€", line)
                if len(prices) >= 2:
                    # The second price is the sale price
                    price = prices[1]
                    break
                elif len(prices) == 1:
                    # Only one price, it's the actual price
                    price = prices[0]
                    break

        # Fallback: look for a price after "Save" line
        if price == "N/A":
            for i, line in enumerate(lines):
                if "Save" in line and "€" in line:
                    # Next lines might have the price
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        price_match = re.match(r"^(\d+[.,]\d{2}€)$", next_line)
                        if price_match:
                            price = price_match.group(1)
                            break
                    if price != "N/A":
                        break

        # Extract ISBN from URL
        isbn = href.split("/")[-1] if "/" in href else None

        return BookResult(
            store=self.name,
            title=title.strip(),
            price=price,
            url=url,
            isbn=isbn,
        )
