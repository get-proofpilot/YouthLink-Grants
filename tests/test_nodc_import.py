"""Tests for NODC CSV grant importer — column mapping, filtering, and foundation discovery."""

import csv
import io
import sqlite3
import tempfile
import os

import pytest

from grant_intel.db import get_all_foundations, get_connection, init_db
from grant_intel.sources.nodc_import import (
    _is_relevant,
    _map_columns,
    import_nodc_grants,
)


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _write_csv(rows: list[dict], headers: list[str]) -> str:
    """Write a CSV to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ── _map_columns ──────────────────────────────────────────────────────────────

class TestMapColumns:
    def test_maps_standard_nodc_headers(self):
        headers = ["EIN", "NAME", "RecipientPersonNm", "RecipientEIN",
                   "CashGrantAmt", "PurposeOfGrantTxt", "TaxYr"]
        mapping = _map_columns(headers)
        assert mapping["filer_ein"] == "EIN"
        assert mapping["filer_name"] == "NAME"
        assert mapping["recipient_name"] == "RecipientPersonNm"
        assert mapping["amount"] == "CashGrantAmt"
        assert mapping["purpose"] == "PurposeOfGrantTxt"
        assert mapping["tax_year"] == "TaxYr"

    def test_maps_alternate_headers(self):
        headers = ["ein", "name", "grantee_name", "grantee_ein",
                   "grant_amount", "grant_purpose", "tax_year"]
        mapping = _map_columns(headers)
        assert mapping["filer_ein"] == "ein"
        assert mapping["amount"] == "grant_amount"
        assert mapping["purpose"] == "grant_purpose"

    def test_returns_none_for_missing_columns(self):
        mapping = _map_columns(["col_a", "col_b"])
        assert mapping["filer_ein"] is None
        assert mapping["amount"] is None


# ── _is_relevant ──────────────────────────────────────────────────────────────

class TestIsRelevant:
    def test_matches_youth_ministry(self):
        assert _is_relevant("Support for youth ministry programs", "First Baptist Church") is True

    def test_matches_pastoral(self):
        assert _is_relevant("Pastoral leadership training grant", "Seminary") is True

    def test_matches_recipient_name(self):
        assert _is_relevant("General operations", "Youth Pastor Coalition") is True

    def test_rejects_unrelated(self):
        assert _is_relevant("Environmental conservation project", "Green Earth Inc") is False

    def test_matches_leadership_development(self):
        assert _is_relevant("Leadership development for community nonprofits", "Community Org") is True

    def test_case_insensitive(self):
        assert _is_relevant("YOUTH PASTOR SUPPORT PROGRAM", "Ministry Org") is True


# ── import_nodc_grants ────────────────────────────────────────────────────────

class TestImportNodcGrants:
    def test_imports_relevant_rows(self, mem_conn):
        rows = [
            {
                "EIN": "123456789",
                "NAME": "Faith Foundation",
                "RecipientPersonNm": "Youth Link Ministries",
                "RecipientEIN": "987654321",
                "CashGrantAmt": "25000",
                "PurposeOfGrantTxt": "Youth ministry leadership development",
                "TaxYr": "2023",
                "RecipientCityNm": "Phoenix",
                "RecipientStateAbbreviationCd": "AZ",
            },
        ]
        path = _write_csv(rows, list(rows[0].keys()))
        try:
            stats = import_nodc_grants(path, mem_conn, filter_relevant=True)
            assert stats["total_rows"] == 1
            assert stats["imported"] == 1
            assert stats["filtered_out"] == 0
        finally:
            os.unlink(path)

    def test_filters_irrelevant_rows(self, mem_conn):
        rows = [
            {
                "EIN": "111111111",
                "NAME": "Green Foundation",
                "RecipientPersonNm": "Environmental Org",
                "RecipientEIN": "222222222",
                "CashGrantAmt": "10000",
                "PurposeOfGrantTxt": "Reforestation and carbon offset programs",
                "TaxYr": "2023",
                "RecipientCityNm": "Portland",
                "RecipientStateAbbreviationCd": "OR",
            },
        ]
        path = _write_csv(rows, list(rows[0].keys()))
        try:
            stats = import_nodc_grants(path, mem_conn, filter_relevant=True)
            assert stats["total_rows"] == 1
            assert stats["filtered_out"] == 1
            assert stats["imported"] == 0
        finally:
            os.unlink(path)

    def test_discovers_new_foundation(self, mem_conn):
        rows = [
            {
                "EIN": "350868122",
                "NAME": "Lilly Endowment Inc.",
                "RecipientPersonNm": "Pastoral Institute",
                "RecipientEIN": "555555555",
                "CashGrantAmt": "100000",
                "PurposeOfGrantTxt": "Clergy renewal and pastoral leadership",
                "TaxYr": "2023",
                "RecipientCityNm": "Indianapolis",
                "RecipientStateAbbreviationCd": "IN",
            },
        ]
        path = _write_csv(rows, list(rows[0].keys()))
        try:
            stats = import_nodc_grants(path, mem_conn, filter_relevant=True)
            assert stats["foundations_discovered"] == 1
            foundations = get_all_foundations(mem_conn)
            eins = [f["ein"] for f in foundations]
            assert "350868122" in eins
        finally:
            os.unlink(path)

    def test_skips_duplicate_foundation(self, mem_conn):
        rows = [
            {
                "EIN": "123456789",
                "NAME": "Test Foundation",
                "RecipientPersonNm": "Youth Pastor Network",
                "RecipientEIN": "111111111",
                "CashGrantAmt": "5000",
                "PurposeOfGrantTxt": "Youth ministry support",
                "TaxYr": "2022",
                "RecipientCityNm": "Phoenix",
                "RecipientStateAbbreviationCd": "AZ",
            },
            {
                "EIN": "123456789",
                "NAME": "Test Foundation",
                "RecipientPersonNm": "Church Leadership Program",
                "RecipientEIN": "222222222",
                "CashGrantAmt": "8000",
                "PurposeOfGrantTxt": "Pastoral development training",
                "TaxYr": "2022",
                "RecipientCityNm": "Phoenix",
                "RecipientStateAbbreviationCd": "AZ",
            },
        ]
        path = _write_csv(rows, list(rows[0].keys()))
        try:
            stats = import_nodc_grants(path, mem_conn, filter_relevant=True)
            # Only 1 new foundation despite 2 rows with same EIN
            assert stats["foundations_discovered"] == 1
            assert stats["imported"] == 2
        finally:
            os.unlink(path)

    def test_no_filter_imports_all(self, mem_conn):
        rows = [
            {
                "EIN": "123456789",
                "NAME": "Any Foundation",
                "RecipientPersonNm": "Unrelated Org",
                "RecipientEIN": "999999999",
                "CashGrantAmt": "5000",
                "PurposeOfGrantTxt": "Environmental research project",
                "TaxYr": "2023",
                "RecipientCityNm": "Chicago",
                "RecipientStateAbbreviationCd": "IL",
            },
        ]
        path = _write_csv(rows, list(rows[0].keys()))
        try:
            stats = import_nodc_grants(path, mem_conn, filter_relevant=False)
            assert stats["imported"] == 1
            assert stats["filtered_out"] == 0
        finally:
            os.unlink(path)

    def test_returns_error_when_ein_column_missing(self, mem_conn):
        rows = [{"col_a": "val", "col_b": "val"}]
        path = _write_csv(rows, ["col_a", "col_b"])
        try:
            stats = import_nodc_grants(path, mem_conn)
            assert stats["imported"] == 0
            assert stats["total_rows"] == 0
        finally:
            os.unlink(path)

    def test_handles_malformed_amount(self, mem_conn):
        rows = [
            {
                "EIN": "123456789",
                "NAME": "Faith Foundation",
                "RecipientPersonNm": "Youth Ministry Org",
                "RecipientEIN": "987654321",
                "CashGrantAmt": "not-a-number",
                "PurposeOfGrantTxt": "Youth ministry leadership",
                "TaxYr": "2023",
                "RecipientCityNm": "Chandler",
                "RecipientStateAbbreviationCd": "AZ",
            },
        ]
        path = _write_csv(rows, list(rows[0].keys()))
        try:
            stats = import_nodc_grants(path, mem_conn, filter_relevant=True)
            # Should import with amount=0, not error
            assert stats["imported"] == 1
            assert stats["errors"] == 0
        finally:
            os.unlink(path)
