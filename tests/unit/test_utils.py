"""Unit tests for src/lib/utils.py — no external dependencies."""

import pytest
from datetime import datetime, timezone

from src.lib.utils import (
    build_date_range,
    match_value_in_columns,
    normalize_list,
    smart_subject_match,
    parse_datetime_utc_flexible,
)


# ---------------------------------------------------------------------------
# parse_datetime_utc_flexible
# ---------------------------------------------------------------------------

class TestParseDatetimeUtcFlexible:
    def test_iso_with_offset(self):
        dt = parse_datetime_utc_flexible("2024-05-03T15:52:11+05:30")
        assert dt.tzinfo is not None
        # 15:52:11 IST = 10:22:11 UTC
        assert dt.hour == 10
        assert dt.minute == 22

    def test_iso_no_offset_treated_as_utc(self):
        dt = parse_datetime_utc_flexible("2024-01-01T12:00:00")
        assert dt.hour == 12
        assert dt.tzinfo == timezone.utc

    def test_date_only(self):
        dt = parse_datetime_utc_flexible("2024-03-15")
        assert dt.year == 2024
        assert dt.month == 3
        assert dt.day == 15

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_datetime_utc_flexible("not-a-date")


# ---------------------------------------------------------------------------
# build_date_range
# ---------------------------------------------------------------------------

class TestBuildDateRange:
    def test_none_both(self):
        start, end = build_date_range(None, None)
        assert start is None and end is None

    def test_date_only_expands_to_day(self):
        start, end = build_date_range("2024-05-01", "2024-05-01")
        assert start.hour == 0 and start.minute == 0
        assert end.hour == 23 and end.minute == 59 and end.second == 59

    def test_start_before_end(self):
        start, end = build_date_range("2024-01-01", "2024-12-31")
        assert start < end

    def test_only_start(self):
        start, end = build_date_range("2024-06-01", None)
        assert start is not None
        assert end is None


# ---------------------------------------------------------------------------
# match_value_in_columns
# ---------------------------------------------------------------------------

class TestMatchValueInColumns:
    def test_exact_substring_in_list(self):
        assert match_value_in_columns("alice@example.com", ["alice@example.com", "bob@x.com"])

    def test_partial_name_match(self):
        assert match_value_in_columns("alice", ["alice smith <alice@example.com>"])

    def test_no_match(self):
        assert not match_value_in_columns("charlie", ["alice@x.com", "bob@x.com"])

    def test_string_column(self):
        assert match_value_in_columns("akshata", "Akshata Patil <akshata@example.com>")

    def test_empty_value_returns_false(self):
        assert not match_value_in_columns("", ["alice@x.com"])

    def test_none_column_returns_false(self):
        assert not match_value_in_columns("alice", None)


# ---------------------------------------------------------------------------
# normalize_list
# ---------------------------------------------------------------------------

class TestNormalizeList:
    def test_list_of_strings(self):
        result = normalize_list(["Alice <alice@x.com>", "Bob <bob@y.com>"])
        assert "alice@x.com" in result
        assert "bob@y.com" in result

    def test_none_input(self):
        result = normalize_list(None)
        assert result == ""

    def test_single_string(self):
        result = normalize_list("Carol <carol@z.com>")
        assert "carol@z.com" in result


# ---------------------------------------------------------------------------
# smart_subject_match
# ---------------------------------------------------------------------------

class TestSmartSubjectMatch:
    def test_exact_match(self):
        assert smart_subject_match("Project Alpha Update", "Project Alpha Update")

    def test_partial_fuzzy_match(self):
        assert smart_subject_match("alpha update", "Project Alpha Update")

    def test_number_must_match(self):
        assert not smart_subject_match("Invoice 1001", "Invoice 2001")

    def test_number_match_relaxes_threshold(self):
        assert smart_subject_match("Invoice 1001", "Re: Invoice 1001 payment")

    def test_no_match(self):
        assert not smart_subject_match("completely different topic", "Project Alpha Update")

    def test_empty_column_value(self):
        assert not smart_subject_match("anything", "")
