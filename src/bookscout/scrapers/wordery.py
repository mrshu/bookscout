"""Wordery.com scraper."""

import re
import urllib.parse

from playwright.async_api import TimeoutError as PlaywrightTimeout

from bookscout.models import BookResult

from .base import BaseScraper, SearchResultItem


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
            await page.goto(search_url, wait_until="domcontentloaded")

            # Handle cookie consent if present
            try:
                accept_btn = await page.query_selector('button:has-text("Accept All")')
                if accept_btn:
                    await accept_btn.click()
            except Exception:
                pass

            # Wait for search results to load (Wordery uses JS to populate hrefs)
            try:
                await page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('a')).some(a => a.href && a.href.includes('/book/'))",
                    timeout=5000
                )
            except Exception:
                pass  # Continue anyway, might still have results

            return await self._extract_first_result(page)
        finally:
            await page.close()

    async def search_isbn(self, isbn: str) -> BookResult | None:
        """Search Wordery by ISBN."""
        return await self.search(isbn)

    async def get_search_results(self, query: str) -> list[SearchResultItem]:
        """Extract ISBNs and URLs from search results without visiting product pages."""
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"{self.base_url}/search?term={encoded_query}"

        page = await self._new_page()
        try:
            await page.goto(search_url, wait_until="domcontentloaded")

            # Handle cookie consent
            try:
                accept_btn = await page.query_selector('button:has-text("Accept All")')
                if accept_btn:
                    await accept_btn.click()
            except Exception:
                pass

            # Wait for search results (Wordery uses JS to populate hrefs)
            try:
                await page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('a')).some(a => a.href && a.href.includes('/book/'))",
                    timeout=5000
                )
            except Exception:
                pass  # Continue anyway, might still have results

            # Extract all product links with ISBNs
            # URL format: /book/{title}/{author}/{isbn}
            product_data = await page.evaluate('''() => {
                const links = document.querySelectorAll('a');
                const results = [];
                const seen = new Set();

                for (const a of links) {
                    const href = a.href;
                    if (href && href.includes('/book/')) {
                        const cleanHref = href.replace(/#.*$/, '');
                        const parts = cleanHref.split('/');
                        const lastPart = parts[parts.length - 1];
                        if (lastPart && lastPart.length >= 10 && /^[0-9Xx]+$/.test(lastPart) && !seen.has(lastPart)) {
                            seen.add(lastPart);
                            results.push({
                                isbn: lastPart,
                                url: cleanHref,
                                title: parts[parts.length - 3] || null
                            });
                            if (results.length >= 10) break;
                        }
                    }
                }
                return results;
            }''')

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
        except Exception:
            pass

        await page.wait_for_load_state("domcontentloaded")

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
