"""Shared test fixtures."""

import sqlite3

import pytest

from grant_intel.db import init_db


@pytest.fixture
def test_db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_opportunity():
    """A sample Grants.gov opportunity dict."""
    return {
        "source": "grants_gov",
        "opportunity_id": "12345",
        "opportunity_number": "HHS-2026-001",
        "title": "Faith-Based Community Leadership Development",
        "agency": "Department of Health and Human Services",
        "description": "Support leadership development for faith-based community organizations.",
        "funding_category": "IS",
        "award_floor": 25000,
        "award_ceiling": 100000,
        "expected_awards": 10,
        "deadline": "2026-06-15",
        "posted_date": "2026-02-01",
        "status": "posted",
        "eligibility": "Nonprofits with 501(c)(3) status",
        "url": "https://www.grants.gov/search-results-detail/12345",
        "keyword_tier": 1,
        "matched_keyword": "faith-based capacity building",
        "raw": {"id": "12345"},
    }


@pytest.fixture
def sample_foundation():
    """A sample foundation dict."""
    return {
        "name": "Smith Family Foundation",
        "ein": "123456789",
        "city": "Phoenix",
        "state": "AZ",
        "total_assets": 5000000,
        "total_giving": 500000,
        "focus_areas": ["youth ministry", "Christian education"],
        "contact_info": "",
        "website": "",
        "source": "propublica",
        "raw": {},
    }


@pytest.fixture
def grants_gov_search_response():
    """Mock Grants.gov search2 API response."""
    return {
        "totalCount": 2,
        "oppHits": [
            {
                "id": "12345",
                "number": "HHS-2026-001",
                "title": "Faith-Based Community Leadership Development",
                "agency": "Department of Health and Human Services",
                "description": "Support leadership development programs.",
                "fundingCategory": "IS",
                "awardFloor": 25000,
                "awardCeiling": 100000,
                "expectedAwards": 10,
                "closeDate": "2026-06-15",
                "openDate": "2026-02-01",
                "oppStatus": "posted",
                "eligibility": "Nonprofits",
            },
            {
                "id": "67890",
                "number": "ED-2026-005",
                "title": "Nonprofit Capacity Building Grants",
                "agency": "Department of Education",
                "description": "Build organizational capacity for nonprofits.",
                "fundingCategory": "ED",
                "awardFloor": 10000,
                "awardCeiling": 50000,
                "expectedAwards": 20,
                "closeDate": "2026-08-01",
                "openDate": "2026-03-01",
                "oppStatus": "posted",
                "eligibility": "Nonprofits",
            },
        ],
    }


@pytest.fixture
def propublica_org_response():
    """Mock ProPublica organization API response."""
    return {
        "organization": {
            "name": "National Network of Youth Ministries",
            "ein": "953537789",
            "city": "San Diego",
            "state": "CA",
            "income_amount": 800000,
            "asset_amount": 500000,
            "ntee_code": "X20",
            "subsection_code": "3",
        },
        "filings_with_data": [
            {
                "tax_prd": "202212",
                "formtype": 0,
                "totrevenue": 800000,
                "totfuncexpns": 750000,
                "totassetsend": 500000,
                "pdf_url": "https://example.com/990.pdf",
            }
        ],
        "filings_without_data": [],
        "data_source": "IRS",
        "api_version": 2,
    }


@pytest.fixture
def sample_990pf_xml():
    """Sample IRS 990-PF XML for testing grant parsing."""
    return b"""<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile" returnVersion="2022v5.0">
  <ReturnData>
    <IRS990PF>
      <SupplementaryInformationGrp>
        <GrantOrContributionPdDurYrGrp>
          <RecipientBusinessName>
            <BusinessNameLine1Txt>Youth Ministry International</BusinessNameLine1Txt>
          </RecipientBusinessName>
          <RecipientEIN>987654321</RecipientEIN>
          <Amt>50000</Amt>
          <GrantOrContributionPurposeTxt>Youth ministry leadership training</GrantOrContributionPurposeTxt>
        </GrantOrContributionPdDurYrGrp>
        <GrantOrContributionPdDurYrGrp>
          <RecipientBusinessName>
            <BusinessNameLine1Txt>Local Community Center</BusinessNameLine1Txt>
          </RecipientBusinessName>
          <RecipientEIN>111222333</RecipientEIN>
          <Amt>25000</Amt>
          <GrantOrContributionPurposeTxt>After-school programs</GrantOrContributionPurposeTxt>
        </GrantOrContributionPdDurYrGrp>
        <GrantOrContributionPdDurYrGrp>
          <RecipientBusinessName>
            <BusinessNameLine1Txt>Arizona Christian University</BusinessNameLine1Txt>
          </RecipientBusinessName>
          <RecipientEIN>444555666</RecipientEIN>
          <Amt>75000</Amt>
          <GrantOrContributionPurposeTxt>Pastoral education and training</GrantOrContributionPurposeTxt>
        </GrantOrContributionPdDurYrGrp>
      </SupplementaryInformationGrp>
    </IRS990PF>
  </ReturnData>
</Return>"""
