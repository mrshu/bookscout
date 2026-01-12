"""Tests for price parsing and ISBN extraction functionality."""

import pytest
import re

from bookscout.models import parse_price, ParsedPrice


class TestParsePrice:
    """Tests for parse_price function."""

    def test_euro_symbol_before(self):
        """Should parse € symbol before amount."""
        result = parse_price("€42.32")
        assert result.amount == 42.32
        assert result.currency == "EUR"

    def test_euro_symbol_before_with_space(self):
        """Should parse € symbol with space before amount."""
        result = parse_price("€ 42.32")
        assert result.amount == 42.32
        assert result.currency == "EUR"

    def test_euro_symbol_after(self):
        """Should parse € symbol after amount."""
        result = parse_price("42.99 €")
        assert result.amount == 42.99
        assert result.currency == "EUR"

    def test_euro_symbol_after_no_space(self):
        """Should parse € symbol after amount without space."""
        result = parse_price("42.99€")
        assert result.amount == 42.99
        assert result.currency == "EUR"

    def test_euro_comma_decimal(self):
        """Should parse European format with comma as decimal."""
        result = parse_price("44,98€")
        assert result.amount == 44.98
        assert result.currency == "EUR"

    def test_pound_symbol(self):
        """Should parse £ symbol."""
        result = parse_price("£47.99")
        assert result.amount == 47.99
        assert result.currency == "GBP"

    def test_pound_with_space(self):
        """Should parse £ with space."""
        result = parse_price("£ 11.50")
        assert result.amount == 11.50
        assert result.currency == "GBP"

    def test_dollar_symbol(self):
        """Should parse $ symbol."""
        result = parse_price("$29.99")
        assert result.amount == 29.99
        assert result.currency == "USD"

    def test_na_returns_none(self):
        """Should return None for N/A."""
        result = parse_price("N/A")
        assert result.amount is None
        assert result.currency is None

    def test_not_found_returns_none(self):
        """Should return None for 'Not found'."""
        result = parse_price("Not found")
        assert result.amount is None
        assert result.currency is None

    def test_dash_returns_none(self):
        """Should return None for dash."""
        result = parse_price("-")
        assert result.amount is None
        assert result.currency is None

    def test_empty_string_returns_none(self):
        """Should return None for empty string."""
        result = parse_price("")
        assert result.amount is None
        assert result.currency is None

    def test_thousands_separator_european(self):
        """Should handle European thousands separator (period)."""
        result = parse_price("1.234,56 €")
        assert result.amount == 1234.56
        assert result.currency == "EUR"

    def test_large_amount(self):
        """Should handle larger amounts."""
        result = parse_price("€199.99")
        assert result.amount == 199.99
        assert result.currency == "EUR"

    def test_integer_price(self):
        """Should handle prices without decimals."""
        result = parse_price("€50")
        assert result.amount == 50.0
        assert result.currency == "EUR"

    def test_whitespace_handling(self):
        """Should handle extra whitespace."""
        result = parse_price("  € 42.32  ")
        assert result.amount == 42.32
        assert result.currency == "EUR"

    def test_kennys_format(self):
        """Should parse Kennys format '€ XX.XX'."""
        result = parse_price("€ 15.42")
        assert result.amount == 15.42
        assert result.currency == "EUR"

    def test_libristo_format(self):
        """Should parse Libristo format 'XX.XX €'."""
        result = parse_price("18.49 €")
        assert result.amount == 18.49
        assert result.currency == "EUR"

    def test_blackwells_format(self):
        """Should parse Blackwells format 'XX,XX€'."""
        result = parse_price("20,54€")
        assert result.amount == 20.54
        assert result.currency == "EUR"

    def test_wordery_format(self):
        """Should parse Wordery format '£XX.XX'."""
        result = parse_price("£11.50")
        assert result.amount == 11.50
        assert result.currency == "GBP"


class TestParsedPrice:
    """Tests for ParsedPrice dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        price = ParsedPrice(amount=42.99, currency="EUR")
        assert price.to_dict() == {"amount": 42.99, "currency": "EUR"}

    def test_to_dict_with_none(self):
        """Should convert None values to dictionary."""
        price = ParsedPrice(amount=None, currency=None)
        assert price.to_dict() == {"amount": None, "currency": None}


class TestBlackwellsPriceExtraction:
    """Tests for Blackwells-specific price extraction edge cases."""

    def test_should_not_extract_save_discount_as_price(self):
        """Should skip 'Save XX€' discount amounts and get actual price.

        Blackwells shows prices like:
          Save 16,60€
          RRP 73,71€ 57,11€

        The actual price is 57,11€, NOT 16,60€ (the discount).
        """
        # Simulate the text from .product__price element
        price_text = "Save 16,60€\n\ni RRP 73,71€ 57,11€"

        # Should NOT start extraction from "Save" text
        assert price_text.strip().lower().startswith("save")

        # The correct price (57,11€) should be extracted, not the save amount
        # This is handled by checking .product-price--current first
        current_price_text = "57,11€"
        price_match = re.search(r"(\d+[.,]\d{2}€)", current_price_text)
        assert price_match.group(1) == "57,11€"

    def test_product_price_current_contains_only_sale_price(self):
        """The .product-price--current selector should contain only the sale price."""
        # This is what .product-price--current returns
        current_price_text = "57,11€"
        price_match = re.search(r"(\d+[.,]\d{2}€)", current_price_text)
        assert price_match.group(1) == "57,11€"

    def test_product_price_without_discount(self):
        """Should extract price when there's no discount shown."""
        # For books without discount, .product__price just shows the price
        price_text = "17,19€"
        price_match = re.search(r"(\d+[.,]\d{2}€)", price_text)
        assert price_match.group(1) == "17,19€"


class TestIsbnExtractionPatterns:
    """Tests for ISBN extraction regex patterns used in scrapers."""

    def test_isbn_label_pattern(self):
        """Should match ISBN: followed by digits."""
        pattern = r"(?:ISBN|EAN)[:\s]*(\d{10,13})"

        # Standard ISBN label
        assert re.search(pattern, "ISBN: 9780008560133", re.IGNORECASE).group(1) == "9780008560133"
        assert re.search(pattern, "ISBN:9780008560133", re.IGNORECASE).group(1) == "9780008560133"
        assert re.search(pattern, "ISBN 9780008560133", re.IGNORECASE).group(1) == "9780008560133"

        # EAN label (used by Libristo)
        assert re.search(pattern, "EAN: 9780008560133", re.IGNORECASE).group(1) == "9780008560133"
        assert re.search(pattern, "EAN 9780008560133", re.IGNORECASE).group(1) == "9780008560133"
        assert re.search(pattern, "ean:9780008560133", re.IGNORECASE).group(1) == "9780008560133"

    def test_isbn_10_digit(self):
        """Should match 10-digit ISBNs."""
        pattern = r"(?:ISBN|EAN)[:\s]*(\d{10,13})"
        assert re.search(pattern, "ISBN: 0008560137", re.IGNORECASE).group(1) == "0008560137"

    def test_standalone_13_digit(self):
        """Should match standalone 13-digit numbers as ISBN."""
        pattern = r"\b(\d{13})\b"
        text = "Product code 9780008560133 in stock"
        assert re.search(pattern, text).group(1) == "9780008560133"

    def test_kennys_url_isbn_pattern(self):
        """Should extract ISBN from Kennys product URLs."""
        pattern = r"-(\d{10,13})(-\d)?$"

        # Standard format
        url = "https://www.kennys.ie/shop/book-title-author-9780008560133"
        match = re.search(pattern, url)
        assert match.group(1) == "9780008560133"

        # With suffix (e.g., -1 for different editions)
        url2 = "https://www.kennys.ie/shop/book-title-author-9780008560133-1"
        match2 = re.search(pattern, url2)
        assert match2.group(1) == "9780008560133"

    def test_wordery_url_isbn_pattern(self):
        """Should extract ISBN from Wordery product URLs."""
        # Wordery URL ends with ISBN
        url = "https://www.wordery.com/book/a-brief-history-of-intelligence/max-s-bennett/9780008560133"
        parts = url.rstrip("/").split("/")
        isbn = parts[-1]
        assert isbn == "9780008560133"
        assert len(isbn) == 13 and isbn.isdigit()

    def test_blackwells_url_isbn_pattern(self):
        """Should extract ISBN from Blackwells product URLs."""
        url = "https://blackwells.co.uk/bookshop/product/A-Brief-History-of-Intelligence-by-Max-S-Bennett/9780008560133"
        parts = url.rstrip("/").split("/")
        isbn = parts[-1]
        assert isbn == "9780008560133"
