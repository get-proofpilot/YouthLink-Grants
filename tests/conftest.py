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
def sample_org_profile():
    """An OrgProfile instance for testing the writer module."""
    from grant_intel.config import OrgProfile

    return OrgProfile(
        name="Youth Link Ministries",
        ein="12-3456789",
        tax_status="501(c)(3)",
        city="Chandler",
        state="AZ",
        zip_code="85224",
        mission="Connect, coach, and resource youth pastors and ministry leaders for Christ-centered impact on the next generation.",
        serves="Youth pastors and ministry leaders (NOT youth directly)",
        programs=[
            {"name": "Local Youth Leader Networks", "description": "PHX, East Valley, Release Time networking groups"},
            {"name": "Coaching", "description": "One-on-one and group coaching relationships for youth pastors"},
            {"name": "Resources & Speaking", "description": "Shared ministry resources, curriculum, and speaking engagements"},
        ],
        budget_range="under_250k",
        years_active=19,
        ntee_codes=["X20", "X80", "B80", "S", "T"],
    )


@pytest.fixture
def sample_nofa_text():
    """Realistic NOFA text for a federal capacity-building grant."""
    return """NOTICE OF FUNDING AVAILABILITY (NOFA)

U.S. Department of Health and Human Services
Administration for Community Living
Program: Community-Based Nonprofit Capacity Building

Application Deadline: June 30, 2026

Award Range: $50,000 - $150,000
Expected Number of Awards: 15

Eligible Applicants: 501(c)(3) nonprofit organizations with at least 5 years
of demonstrated service in community-based programming.

Required Narrative Sections:
1. Statement of Need (maximum 3 pages)
2. Project Description (maximum 5 pages)
3. Goals and Objectives (maximum 2 pages)
4. Evaluation Plan (maximum 2 pages)
5. Organizational Capacity (maximum 2 pages)
6. Budget Justification (maximum 2 pages)
7. Sustainability Plan (maximum 1 page)

Review Criteria:
- Mission alignment and demonstrated need (25 points)
- Quality of project design (25 points)
- Measurable objectives and evaluation approach (20 points)
- Organizational track record (15 points)
- Budget reasonableness (10 points)
- Sustainability plan (5 points)

Priority Areas:
- Professional development for community-serving professionals
- Peer learning networks
- Leadership pipeline development
- Rural and underserved community outreach

Restrictions:
- Funds may not be used for religious worship services or proselytization
- Indirect costs limited to 10% of direct costs
"""


@pytest.fixture
def mock_claude_section_response():
    """Mock Claude response for a grant narrative section."""
    return (
        "In Maricopa County, 43% of youth pastors leave ministry within their "
        "first five years. That number climbs to 61% in rural Arizona communities "
        "where isolation compounds the already-difficult work of shepherding "
        "teenagers through the hardest years of their lives.\n\n"
        "The pastors who stay describe the same pattern: long hours, thin budgets, "
        "and almost no one checking in on how they're doing. [INSERT: number of "
        "youth pastors currently serving in Maricopa County] youth pastors serve "
        "across the county, most of them working part-time or bivocational. The "
        "churches they serve often lack the resources to invest in their "
        "professional growth.\n\n"
        "National organizations offer conferences and curriculum, but the gap "
        "is local and relational. A youth pastor in Glendale needs someone who "
        "understands the specific pressures of Arizona ministry — the transient "
        "population, the megachurch-small church dynamic, the summer heat that "
        "empties programs from May through September.\n\n"
        "Youth Link Ministries has spent 19 years filling exactly this gap, "
        "connecting [INSERT: total number served] youth ministry leaders through "
        "peer networks, one-on-one coaching, and shared resources. This project "
        "would deepen that work."
    )


@pytest.fixture
def mock_claude_loi_response():
    """Mock Claude response for a foundation Letter of Inquiry."""
    return (
        "Dear Smith Family Foundation,\n\n"
        "Last spring, a youth pastor in Mesa called our office to say she was "
        "done. Ten years of ministry, and she'd hit the wall — burned out, "
        "underpaid, and feeling like nobody understood what she was going "
        "through. Three months later, after joining one of our coaching "
        "cohorts, she told us she'd found her footing again.\n\n"
        "She's not unusual. Across Arizona, youth pastors are leaving ministry "
        "at alarming rates — [INSERT: current attrition percentage] in Maricopa "
        "County alone within the first five years. The adults who dedicate "
        "their careers to guiding young people through faith and life are "
        "themselves running on empty.\n\n"
        "Youth Link Ministries requests $25,000 from the Smith Family "
        "Foundation to support the Arizona Youth Pastor Network project, "
        "a 12-month initiative to expand our peer coaching and networking "
        "program to reach [INSERT: target number] additional youth ministry "
        "leaders across the East Valley.\n\n"
        "For questions, please contact [INSERT: contact name, title, phone, email].\n\n"
        "With gratitude,\n"
        "[INSERT: Executive Director name and title]"
    )


@pytest.fixture
def sample_requirements():
    """Parsed NOFA requirements for testing."""
    return {
        "funder_name": "U.S. Department of Health and Human Services",
        "program_name": "Community-Based Nonprofit Capacity Building",
        "deadline": "2026-06-30",
        "award_range": {"min": 50000, "max": 150000},
        "eligible_applicants": "501(c)(3) nonprofit organizations",
        "required_sections": [
            "Statement of Need",
            "Project Description",
            "Goals and Objectives",
            "Evaluation Plan",
            "Organizational Capacity",
            "Budget Justification",
            "Sustainability Plan",
        ],
        "page_limits": {"narrative": 17, "budget": 2},
        "evaluation_criteria": [
            "Mission alignment and demonstrated need (25 points)",
            "Quality of project design (25 points)",
            "Measurable objectives and evaluation approach (20 points)",
        ],
        "focus_areas": [
            "Professional development",
            "Peer learning networks",
            "Leadership pipeline development",
        ],
        "restrictions": [
            "No religious worship services or proselytization",
            "Indirect costs limited to 10%",
        ],
        "questions_to_answer": [],
        "raw_text": "NOFA text...",
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
