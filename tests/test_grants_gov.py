"""Tests for Grants.gov API client."""

import responses

from grant_intel.sources.grants_gov import (
    SEARCH_URL,
    discover_grants,
    parse_opportunity,
    search_opportunities,
)


@responses.activate
def test_search_opportunities_basic(grants_gov_search_response):
    """Test basic keyword search."""
    responses.post(SEARCH_URL, json=grants_gov_search_response)

    results = search_opportunities("faith-based")
    assert len(results) == 2
    assert results[0]["id"] == "12345"
    assert results[1]["id"] == "67890"


@responses.activate
def test_search_opportunities_pagination():
    """Test pagination through multiple pages."""
    page1 = {
        "totalCount": 3,
        "oppHits": [
            {"id": "1", "title": "Grant 1"},
            {"id": "2", "title": "Grant 2"},
        ],
    }
    page2 = {
        "totalCount": 3,
        "oppHits": [
            {"id": "3", "title": "Grant 3"},
        ],
    }
    responses.post(SEARCH_URL, json=page1)
    responses.post(SEARCH_URL, json=page2)

    results = search_opportunities("test", rows=2)
    assert len(results) == 3


@responses.activate
def test_search_opportunities_empty():
    """Test search with no results."""
    responses.post(SEARCH_URL, json={"totalCount": 0, "oppHits": []})

    results = search_opportunities("nonexistent")
    assert len(results) == 0


def test_parse_opportunity():
    """Test parsing a Grants.gov hit into standardized dict."""
    hit = {
        "id": "12345",
        "number": "HHS-2026-001",
        "title": "Test Grant",
        "agency": "HHS",
        "description": "A test grant.",
        "fundingCategory": "IS",
        "awardFloor": 25000,
        "awardCeiling": 100000,
        "expectedAwards": 10,
        "closeDate": "2026-06-15",
        "openDate": "2026-02-01",
        "oppStatus": "posted",
        "eligibility": "Nonprofits",
    }

    opp = parse_opportunity(hit, "pastoral development", tier=1)
    assert opp["source"] == "grants_gov"
    assert opp["opportunity_id"] == "12345"
    assert opp["title"] == "Test Grant"
    assert opp["keyword_tier"] == 1
    assert opp["matched_keyword"] == "pastoral development"
    assert "12345" in opp["url"]


@responses.activate
def test_discover_grants_deduplication(grants_gov_search_response):
    """Test that discover_grants deduplicates across keywords."""
    # Same results returned for both keywords
    responses.post(SEARCH_URL, json=grants_gov_search_response)
    responses.post(SEARCH_URL, json=grants_gov_search_response)

    keywords = {
        "tier1": ["keyword1", "keyword2"],
    }
    results = discover_grants(keywords)
    # Should deduplicate to 2 unique opportunities, not 4
    assert len(results) == 2


@responses.activate
def test_discover_grants_multiple_tiers(grants_gov_search_response):
    """Test discovery across multiple keyword tiers."""
    responses.post(SEARCH_URL, json=grants_gov_search_response)
    responses.post(SEARCH_URL, json={"totalCount": 0, "oppHits": []})

    keywords = {
        "tier1": ["pastoral development"],
        "tier2": ["community development"],
    }
    results = discover_grants(keywords)
    assert len(results) == 2
    assert results[0]["keyword_tier"] == 1
