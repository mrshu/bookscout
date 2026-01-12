"""Tests for ISBN validation functionality."""

import pytest

from bookscout.cli import find_canonical_isbn
from bookscout.models import BookResult


class TestFindCanonicalIsbn:
    """Tests for find_canonical_isbn function."""

    def test_returns_none_for_empty_list(self):
        """Should return None when no results provided."""
        assert find_canonical_isbn([]) is None

    def test_returns_none_for_all_none_results(self):
        """Should return None when all results are None."""
        assert find_canonical_isbn([None, None, None]) is None

    def test_returns_none_when_no_isbns(self, book_without_isbn):
        """Should return None when no results have ISBNs."""
        results = [book_without_isbn, book_without_isbn]
        assert find_canonical_isbn(results) is None

    def test_returns_single_isbn(self, kleppmann_book):
        """Should return the ISBN when only one result has it."""
        results = [kleppmann_book, None]
        assert find_canonical_isbn(results) == "9781449373320"

    def test_returns_majority_isbn(self, kleppmann_book, wrong_book):
        """Should return the most common ISBN (majority vote)."""
        # Create another result with the correct ISBN
        another_correct = BookResult(
            store="Store2",
            title="DDIA",
            price="€40.00",
            url="https://example.com/ddia2",
            isbn="9781449373320",
        )
        # 2 correct, 1 wrong -> should return correct
        results = [kleppmann_book, another_correct, wrong_book]
        assert find_canonical_isbn(results) == "9781449373320"

    def test_returns_most_common_when_tie(self):
        """When tied, should return one of the most common (first in counter)."""
        book1 = BookResult(
            store="Store1",
            title="Book 1",
            price="€10",
            url="https://example.com/1",
            isbn="1111111111111",
        )
        book2 = BookResult(
            store="Store2",
            title="Book 2",
            price="€10",
            url="https://example.com/2",
            isbn="2222222222222",
        )
        results = [book1, book2]
        # Should return one of them (Counter behavior)
        result = find_canonical_isbn(results)
        assert result in ["1111111111111", "2222222222222"]

    def test_ignores_none_results(self, kleppmann_book):
        """Should ignore None results when counting ISBNs."""
        results = [kleppmann_book, None, None, None]
        assert find_canonical_isbn(results) == "9781449373320"

    def test_ignores_results_without_isbn(self, kleppmann_book, book_without_isbn):
        """Should ignore results without ISBN when counting."""
        results = [kleppmann_book, book_without_isbn, book_without_isbn]
        assert find_canonical_isbn(results) == "9781449373320"

    def test_mixed_results(self, kleppmann_book, wrong_book, book_without_isbn):
        """Should handle mix of correct, wrong, and no ISBN results."""
        another_correct = BookResult(
            store="Store3",
            title="DDIA",
            price="£45.00",
            url="https://example.com/ddia3",
            isbn="9781449373320",
        )
        results = [
            kleppmann_book,      # correct ISBN
            wrong_book,          # wrong ISBN
            book_without_isbn,   # no ISBN
            None,                # failed
            another_correct,     # correct ISBN
        ]
        # 2 correct vs 1 wrong -> correct wins
        assert find_canonical_isbn(results) == "9781449373320"


class TestIsbnValidationIntegration:
    """Integration tests for ISBN validation in search flow."""

    def test_detects_mismatched_isbn(self, kleppmann_book, wrong_book):
        """Should detect when a result has different ISBN than canonical."""
        canonical = "9781449373320"

        # kleppmann_book matches
        assert kleppmann_book.isbn == canonical

        # wrong_book doesn't match
        assert wrong_book.isbn != canonical
        assert wrong_book.isbn == "9798279289592"

    def test_identifies_stores_needing_retry(self, kleppmann_book, wrong_book, book_without_isbn):
        """Should identify which stores need to be re-searched."""
        results = [kleppmann_book, wrong_book, book_without_isbn, None]
        stores = ["blackwells", "wordery", "libristo", "kennys"]

        canonical_isbn = find_canonical_isbn(results)
        assert canonical_isbn == "9781449373320"

        # Find stores that need retry
        stores_to_retry = []
        for i, (store, result) in enumerate(zip(stores, results)):
            if result and result.isbn and result.isbn != canonical_isbn:
                stores_to_retry.append((i, store))
            elif result is None:
                stores_to_retry.append((i, store))

        # wordery (wrong ISBN) and kennys (None) should be retried
        assert len(stores_to_retry) == 2
        retry_stores = [store for _, store in stores_to_retry]
        assert "wordery" in retry_stores
        assert "kennys" in retry_stores
        # libristo has no ISBN but has a result, so not retried
        assert "libristo" not in retry_stores
