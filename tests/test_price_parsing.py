"""Tests for price parsing functionality."""

import pytest

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
