"""Kennys.ie scraper."""

import re
import urllib.parse

from playwright.async_api import TimeoutError as PlaywrightTimeout

from bookscout.models import BookResult

from .base import BaseScraper, SearchResultItem, title_matches_query


class KennysScraper(BaseScraper):
    """Scraper for kennys.ie."""

    name = "Kennys"
    base_url = "https://www.kennys.ie"

    async def search(self, query: str) -> BookResult | None:
        """Search Kennys for a book."""
        page = await self._new_page()
        try:
            # First navigate to the elasticsearch page
            await page.goto(f"{self.base_url}/elasticsearch", wait_until="networkidle")

            # Then trigger the search via hash change (this is how Kennys works)
            await page.evaluate(f'window.location.hash = "ges:searchword={query}"')

            # Wait for results to render
            await page.wait_for_timeout(4000)

            return await self._extract_first_result(page, query)
        finally:
            await page.close()

    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search Kennys by ISBN."""
        return await self.search(isbn)

    async def get_search_results(self, query: str) -> list[SearchResultItem]:
        """Extract ISBNs and URLs from search results without visiting product pages."""
        page = await self._new_page()
        try:
            await page.goto(f"{self.base_url}/elasticsearch", wait_until="networkidle")
            await page.evaluate(f'window.location.hash = "ges:searchword={query}"')
            await page.wait_for_timeout(4000)

            # Extract product links with ISBNs from URLs
            # Kennys URL format: /shop/book-title-author-ISBN or /category/book-title-ISBN
            product_data = await page.evaluate("""() => {
                const results = [];
                const seen = new Set();

                // Look for links in search result titles
                const resultLinks = document.querySelectorAll('.result-title a[href], .search-result a[href]');
                for (const a of resultLinks) {
                    const href = a.href;
                    if (!href || !href.includes('kennys.ie')) continue;

                    // Extract ISBN from URL (pattern: -XXXXXXXXXXXX at end or -XXXXXXXXXXXX-1)
                    const isbnMatch = href.match(/-(\\d{10,13})([-]\\d)?$/);
                    if (isbnMatch && !seen.has(isbnMatch[1])) {
                        seen.add(isbnMatch[1]);
                        // Extract title from URL slug
                        const parts = href.split('/');
                        const slug = parts[parts.length - 1];
                        const title = slug.replace(/-\\d{10,13}(-\\d)?$/, '').replace(/-/g, ' ');
                        results.push({
                            isbn: isbnMatch[1],
                            url: href,
                            title: title
                        });
                        if (results.length >= 10) break;
                    }
                }
                return results;
            }""")

            return [SearchResultItem(isbn=item['isbn'], url=item['url'], title=item.get('title')) for item in product_data]
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
        # Find product links from search results
        # Kennys search results have links inside elements with class 'result-title'
        product_hrefs = await page.evaluate("""() => {
            const hrefs = [];
            const seen = new Set();

            // First, try to find links in search result titles (most reliable)
            const resultLinks = document.querySelectorAll('.result-title a[href], .search-result a[href]');
            for (const a of resultLinks) {
                const href = a.href;
                if (href && !seen.has(href) && href.includes('kennys.ie')) {
                    hrefs.push(href);
                    seen.add(href);
                }
            }

            // If no result links found, fall back to general product link detection
            if (hrefs.length === 0) {
                const allAnchors = document.querySelectorAll('a[href]');
                for (const a of allAnchors) {
                    const href = a.href;
                    if (!href || seen.has(href) || !href.includes('kennys.ie')) continue;

                    // Product URLs typically have ISBN pattern at the end
                    // e.g., /shop/book-title-author-9780008560133
                    if (href.match(/kennys\\.ie\\/[^\\/]+\\/[^\\/?#]+-\\d{10,13}(-\\d)?$/)) {
                        hrefs.push(href);
                        seen.add(href);
                    }
                    if (hrefs.length >= 15) break;
                }
            }

            return hrefs;
        }""")

        if not product_hrefs:
            return None

        # Try each product and find one that matches the query
        for href in product_hrefs:
            # Extract title from URL slug
            parts = href.rstrip("/").split("/")
            if len(parts) >= 2:
                slug = parts[-1]
                # Remove ISBN from end if present
                slug = re.sub(r"-\d{10,13}(-\d)?$", "", slug)
                url_title = slug.replace("-", " ")

                if title_matches_query(url_title, query):
                    result = await self._extract_from_product_page(page, href)
                    if result:
                        return result

        # Fallback: return first result
        return await self._extract_from_product_page(page, product_hrefs[0])

    async def _extract_from_product_page(self, page, href: str) -> BookResult | None:
        """Navigate to a product page and extract details."""
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        # Extract title - try h1 first, then page title
        title_el = await page.query_selector("h1")
        title = await title_el.inner_text() if title_el else ""

        if not title.strip():
            # Use page title and extract book name (before " - ")
            page_title = await page.title()
            if " - " in page_title:
                title = page_title.split(" - ")[0].strip()
            else:
                title = page_title

        # Extract price - look for sale price pattern
        # Kennys shows € XX.XX format
        price = "N/A"

        all_text = await page.inner_text("body")

        # Find prices in format € XX.XX
        prices = re.findall(r"€\s*\d+[.,]\d{2}", all_text)
        if prices:
            # Filter out very high prices (likely filter labels like "€100 - €200")
            valid_prices = [p for p in prices if float(p.replace("€", "").replace(",", ".").strip()) < 100]
            if valid_prices:
                # The sale price is usually the second one (first is RRP)
                # But if there's only one, use that
                if len(valid_prices) >= 2:
                    price = valid_prices[1]  # Sale price
                else:
                    price = valid_prices[0]

        # Extract ISBN from page if available
        isbn = None
        isbn_match = re.search(r"ISBN[:\s]*(\d{10,13})", all_text, re.IGNORECASE)
        if isbn_match:
            isbn = isbn_match.group(1)

        return BookResult(
            store=self.name,
            title=title.strip(),
            price=price.strip() if price else "N/A",
            url=url,
            isbn=isbn,
        )
