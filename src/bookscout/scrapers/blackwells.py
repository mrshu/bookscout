"""Blackwells.co.uk scraper."""

import re
import urllib.parse

from playwright.async_api import TimeoutError as PlaywrightTimeout

from bookscout.models import BookResult

from .base import BaseScraper, SearchResultItem, title_matches_query


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

    async def get_search_results(self, query: str) -> list[SearchResultItem]:
        """Extract ISBNs and URLs from search results without visiting product pages."""
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"{self.base_url}/bookshop/search?keyword={encoded_query}"

        page = await self._new_page()
        try:
            await page.goto(search_url, wait_until="domcontentloaded")

            try:
                await page.wait_for_selector(".book-info, .product-info, .search-result", timeout=10000)
            except PlaywrightTimeout:
                return []

            # Extract all product links with ISBNs from URLs
            # URL format: /bookshop/product/Title-Slug/ISBN
            links = await page.query_selector_all('a[href*="/bookshop/product/"]')
            results = []
            seen_isbns = set()

            for link in links[:15]:
                href = await link.get_attribute("href")
                if not href:
                    continue

                # Extract ISBN from URL (last part)
                parts = href.rstrip("/").split("/")
                if parts:
                    potential_isbn = parts[-1]
                    # Check if it's a valid ISBN (10 or 13 digits)
                    if len(potential_isbn) >= 10 and potential_isbn.replace("X", "").replace("x", "").isdigit():
                        if potential_isbn not in seen_isbns:
                            seen_isbns.add(potential_isbn)
                            url = href if href.startswith("http") else f"{self.base_url}{href}"
                            # Extract title from URL slug
                            title = parts[-2].replace("-by-", " ").replace("-", " ") if len(parts) >= 2 else None
                            results.append(SearchResultItem(isbn=potential_isbn, url=url, title=title))

            return results
        finally:
            await page.close()

    async def get_product_details(self, url: str) -> BookResult | None:
        """Fetch full product details from a product page URL."""
        page = await self._new_page()
        try:
            return await self._extract_from_product_page(page, url)
        finally:
            await page.close()

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

        # Extract price - use CSS selectors for the current/sale price
        price = "N/A"

        # Try to find the main product price using specific CSS classes
        # Order matters: most specific first to avoid grabbing "Save XX€" discount amounts
        price_selectors = [
            ".product-price--current",   # Current/sale price (most specific)
            ".product__price",           # Main product price container
            ".product-price",            # Generic price container
        ]

        for selector in price_selectors:
            price_el = await page.query_selector(selector)
            if price_el:
                price_text = await price_el.inner_text()

                # Skip if this is a "Save" discount amount
                if price_text.strip().lower().startswith("save"):
                    continue

                # Extract price pattern from the text
                price_match = re.search(r"(\d+[.,]\d{2}€)", price_text)
                if price_match:
                    price = price_match.group(1)
                    break

        # Fallback: look for price near the title/add to basket area
        if price == "N/A":
            all_text = await page.inner_text("body")
            lines = all_text.split("\n")

            for i, line in enumerate(lines):
                # Look for "Add to basket" and get the price above it
                if "Add to basket" in line:
                    # Check previous lines for a price
                    for j in range(1, 5):
                        if i - j >= 0:
                            prev_line = lines[i - j].strip()
                            price_match = re.match(r"^(\d+[.,]\d{2}€)$", prev_line)
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
