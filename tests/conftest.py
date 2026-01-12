"""Pytest configuration and fixtures."""

import pytest

from bookscout.models import BookResult


@pytest.fixture
def sample_book_result():
    """Create a sample BookResult for testing."""
    return BookResult(
        store="TestStore",
        title="Test Book Title",
        price="€19.99",
        url="https://example.com/book/test",
        isbn="9781234567890",
    )


@pytest.fixture
def kleppmann_book():
    """The correct Designing Data-Intensive Applications book."""
    return BookResult(
        store="TestStore",
        title="Designing Data-Intensive Applications",
        price="€42.00",
        url="https://example.com/book/ddia",
        isbn="9781449373320",
    )


@pytest.fixture
def wrong_book():
    """A different book with similar title (knockoff)."""
    return BookResult(
        store="TestStore",
        title="Designing Data Intensive Applications for Modern Systems",
        price="£11.50",
        url="https://example.com/book/wrong",
        isbn="9798279289592",
    )


@pytest.fixture
def book_without_isbn():
    """A book result without ISBN."""
    return BookResult(
        store="TestStore",
        title="Some Book",
        price="€20.00",
        url="https://example.com/book/no-isbn",
        isbn=None,
    )
