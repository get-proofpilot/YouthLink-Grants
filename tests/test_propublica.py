"""Tests for ProPublica Nonprofit Explorer API client."""

import responses

from grant_intel.sources.propublica import (
    BASE_URL,
    extract_filings,
    extract_org_info,
    get_organization,
    research_similar_orgs,
    search_orgs,
)


@responses.activate
def test_search_orgs():
    """Test searching for organizations."""
    mock_response = {
        "total_results": 1,
        "organizations": [
            {
                "ein": "953537789",
                "name": "National Network of Youth Ministries",
                "city": "San Diego",
                "state": "CA",
            }
        ],
    }
    responses.get(f"{BASE_URL}/search.json", json=mock_response)

    results = search_orgs("youth ministry")
    assert len(results) == 1
    assert results[0]["ein"] == "953537789"


@responses.activate
def test_get_organization(propublica_org_response):
    """Test fetching org details by EIN."""
    responses.get(
        f"{BASE_URL}/organizations/953537789.json",
        json=propublica_org_response,
    )

    data = get_organization("953537789")
    assert data is not None
    assert data["organization"]["name"] == "National Network of Youth Ministries"


@responses.activate
def test_get_organization_not_found():
    """Test handling 404 for unknown EIN."""
    responses.get(f"{BASE_URL}/organizations/000000000.json", status=404)

    data = get_organization("000000000")
    assert data is None


def test_extract_org_info(propublica_org_response):
    """Test extracting standardized org info."""
    info = extract_org_info(propublica_org_response)
    assert info["name"] == "National Network of Youth Ministries"
    assert info["ein"] == "953537789"
    assert info["state"] == "CA"
    assert info["source"] == "propublica"


def test_extract_filings(propublica_org_response):
    """Test extracting filing data."""
    filings = extract_filings(propublica_org_response)
    assert len(filings) == 1
    assert filings[0]["tax_period"] == "202212"
    assert filings[0]["form_type"] == "990"
    assert filings[0]["total_revenue"] == 800000


@responses.activate
def test_research_similar_orgs(propublica_org_response):
    """Test researching a list of similar organizations."""
    responses.get(
        f"{BASE_URL}/organizations/953537789.json",
        json=propublica_org_response,
    )

    similar = [{"name": "NNYM", "ein": "953537789"}]
    org_infos, filings = research_similar_orgs(similar)

    assert len(org_infos) == 1
    assert org_infos[0]["name"] == "NNYM"
    assert len(filings) == 1
