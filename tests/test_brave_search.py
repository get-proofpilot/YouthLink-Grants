"""Tests for Brave Search grant detection heuristic and parser."""

import pytest

from grant_intel.sources.brave_search import is_grant_result, parse_web_opportunity


# ── is_grant_result ──────────────────────────────────────────────────────────

class TestIsGrantResult:
    def test_passes_with_two_indicators(self):
        result = {
            "title": "Youth Ministry Grant Application 2026",
            "description": "Submit your application before the deadline to receive award funding.",
            "url": "https://lillyendowment.org/grants/youth-ministry",
        }
        assert is_grant_result(result) is True

    def test_rejects_pdf_url(self):
        result = {
            "title": "Grant Application Guidelines",
            "description": "Eligibility deadline apply award submit",
            "url": "https://example.org/guidelines.pdf",
        }
        assert is_grant_result(result) is False

    def test_rejects_cdn_url(self):
        result = {
            "title": "Grant Program Details",
            "description": "application deadline award eligibility submit",
            "url": "https://cdn.example.org/grant-details",
        }
        assert is_grant_result(result) is False

    def test_rejects_empty_title(self):
        result = {
            "title": "",
            "description": "apply deadline award eligibility submit rfp",
            "url": "https://example.org/grants",
        }
        assert is_grant_result(result) is False

    def test_rejects_insufficient_indicators(self):
        result = {
            "title": "About Our Foundation",
            "description": "We support communities across Arizona.",
            "url": "https://example.org/about",
        }
        assert is_grant_result(result) is False

    def test_passes_with_loi_indicator(self):
        result = {
            "title": "Letter of Inquiry — Pastoral Development Fund",
            "description": "Submit an LOI to apply for our 2026 grant cycle.",
            "url": "https://foundation.org/loi",
        }
        assert is_grant_result(result) is True

    def test_rejects_website_files_url(self):
        result = {
            "title": "Grant Award Application",
            "description": "deadline apply eligibility award submit rfp",
            "url": "https://uploads.website-files.com/grant.pdf",
        }
        assert is_grant_result(result) is False


# ── parse_web_opportunity ────────────────────────────────────────────────────

class TestParseWebOpportunity:
    def test_extracts_title_and_url(self):
        result = {
            "title": "Youth Ministry Leadership Grant",
            "description": "Grants for pastoral development organizations.",
            "url": "https://lillyendowment.org/youth-ministry-grant",
        }
        parsed = parse_web_opportunity(result, query="youth ministry grant")
        assert parsed["title"] == "Youth Ministry Leadership Grant"
        assert parsed["url"] == "https://lillyendowment.org/youth-ministry-grant"
        assert parsed["description"] == "Grants for pastoral development organizations."

    def test_extracts_award_range(self):
        result = {
            "title": "Capacity Building Grant",
            "description": "Awards range from $25,000 to $100,000 for eligible nonprofits.",
            "url": "https://example.org/grant",
        }
        parsed = parse_web_opportunity(result, query="capacity building")
        assert parsed["award_min"] == 25000
        assert parsed["award_max"] == 100000

    def test_extracts_up_to_amount(self):
        result = {
            "title": "Ministry Support Grant",
            "description": "Up to $50,000 available for qualifying organizations.",
            "url": "https://example.org/ministry",
        }
        parsed = parse_web_opportunity(result, query="ministry support")
        assert parsed["award_min"] is None
        assert parsed["award_max"] == 50000

    def test_extracts_funder_from_title_separator(self):
        result = {
            "title": "Youth Pastor Grant Program | Lilly Endowment",
            "description": "Apply for funding through the Lilly Endowment program.",
            "url": "https://lillyendowment.org/programs",
        }
        parsed = parse_web_opportunity(result, query="youth pastor grant")
        assert parsed["funder_name"] == "Lilly Endowment"

    def test_no_award_amounts_returns_none(self):
        result = {
            "title": "Faith Community Grant",
            "description": "Grants for faith-based organizations. Apply by June 30.",
            "url": "https://example.org/faith",
        }
        parsed = parse_web_opportunity(result, query="faith community")
        assert parsed["award_min"] is None
        assert parsed["award_max"] is None

    def test_search_query_stored(self):
        result = {
            "title": "Youth Ministry Grant",
            "description": "Apply for youth ministry funding.",
            "url": "https://example.org/grant",
        }
        parsed = parse_web_opportunity(result, query="youth ministry grant 2026")
        assert parsed["search_query"] == "youth ministry grant 2026"

    def test_handles_missing_fields_gracefully(self):
        parsed = parse_web_opportunity({}, query="test")
        assert parsed["title"] == ""
        assert parsed["url"] == ""
        assert parsed["award_min"] is None
        assert parsed["award_max"] is None
