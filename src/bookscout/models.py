"""Data models for BookScout."""

import re
from dataclasses import dataclass


@dataclass
class BookResult:
    """Result from a bookstore search."""

    store: str
    title: str
    price: str  # Keep as string to preserve original formatting (e.g., "€12.99", "£10.50")
    url: str
    isbn: str | None = None


@dataclass
class ParsedPrice:
    """Parsed price with numeric value and currency code."""

    amount: float | None
    currency: str | None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {"amount": self.amount, "currency": self.currency}


# Currency symbol to ISO code mapping
CURRENCY_MAP = {
    "€": "EUR",
    "£": "GBP",
    "$": "USD",
    "¥": "JPY",
    "CHF": "CHF",
    "kr": "SEK",  # Could also be NOK, DKK
}


def parse_price(price_str: str) -> ParsedPrice:
    """Parse a price string into amount and currency.

    Handles formats like:
    - "€42.32", "€ 42.32"
    - "42,99 €", "42.99€"
    - "£47.99"
    - "44,98€"
    - "N/A", "Not found"

    Returns:
        ParsedPrice with amount (float) and currency (ISO code like "EUR", "GBP")
    """
    if not price_str or price_str in ("N/A", "Not found", "-"):
        return ParsedPrice(amount=None, currency=None)

    # Clean up the string
    price_str = price_str.strip()

    # Detect currency
    currency = None
    for symbol, code in CURRENCY_MAP.items():
        if symbol in price_str:
            currency = code
            break

    # Extract numeric value
    # Remove currency symbols and whitespace, keeping digits, comma, period
    numeric_str = re.sub(r"[€£$¥]", "", price_str)
    numeric_str = numeric_str.replace("CHF", "").replace("kr", "").strip()

    # Handle European format (comma as decimal separator)
    # If we have both comma and period, comma is thousands separator
    # If we have only comma, it's likely decimal separator
    if "," in numeric_str and "." in numeric_str:
        # Format like "1.234,56" -> remove dots, replace comma with dot
        numeric_str = numeric_str.replace(".", "").replace(",", ".")
    elif "," in numeric_str:
        # Format like "42,99" -> replace comma with dot
        numeric_str = numeric_str.replace(",", ".")

    # Extract the number
    match = re.search(r"(\d+\.?\d*)", numeric_str)
    if match:
        try:
            amount = float(match.group(1))
            return ParsedPrice(amount=amount, currency=currency)
        except ValueError:
            pass

    return ParsedPrice(amount=None, currency=currency)
