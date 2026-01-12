"""Tests for scraper functionality."""

import pytest

from bookscout.scrapers.base import title_matches_query


class TestTitleMatchesQuery:
    """Tests for title_matches_query function."""

    def test_exact_match(self):
        """Should match when title equals query."""
        assert title_matches_query("Atomic Habits", "Atomic Habits") is True

    def test_case_insensitive(self):
        """Should match case-insensitively."""
        assert title_matches_query("ATOMIC HABITS", "atomic habits") is True
        assert title_matches_query("atomic habits", "ATOMIC HABITS") is True

    def test_partial_match_above_threshold(self):
        """Should match when enough query words are in title."""
        # "Atomic" and "Habits" both in title (2/2 = 100%)
        assert title_matches_query(
            "Atomic Habits: An Easy Way to Build Good Habits",
            "Atomic Habits"
        ) is True

    def test_partial_match_below_threshold(self):
        """Should not match when too few query words are in title."""
        # Only "Data" matches (1/4 = 25% < 50%)
        assert title_matches_query(
            "Data Science Handbook",
            "Designing Data Intensive Applications"
        ) is False

    def test_subset_match(self):
        """Should match when query is subset of title."""
        assert title_matches_query(
            "Designing Data-Intensive Applications: The Big Ideas",
            "Data Intensive Applications"
        ) is True

    def test_custom_threshold(self):
        """Should respect custom threshold."""
        # 1/3 words match = 33%
        # Default threshold (0.5) -> no match
        assert title_matches_query("Python Guide", "Python Data Science", threshold=0.5) is False
        # Lower threshold (0.3) -> match
        assert title_matches_query("Python Guide", "Python Data Science", threshold=0.3) is True

    def test_empty_query(self):
        """Should return True for empty query."""
        assert title_matches_query("Any Title", "") is True

    def test_special_characters_ignored(self):
        """Should handle special characters in titles."""
        assert title_matches_query(
            "Data-Intensive Applications",
            "Data Intensive Applications"
        ) is True

    def test_numbers_in_title(self):
        """Should handle numbers in titles."""
        assert title_matches_query(
            "Python 3.12 Guide",
            "Python 3.12"
        ) is True
