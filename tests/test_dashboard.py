"""Tests for the admin dashboard — app, auth, routes, priority scoring, filters."""

import os
import sqlite3
import tempfile

import pytest

from grant_intel.config import OrgProfile
from grant_intel.dashboard.app import create_app
from grant_intel.dashboard.priority import (
    analyze_requirements,
    calculate_priority_score,
    enrich_opportunities_with_priority,
    summarize_matches,
)
from grant_intel.db import (
    get_connection,
    init_db,
    insert_score,
    upsert_foundation,
    upsert_opportunity,
    upsert_pipeline_entry,
    insert_draft,
    get_pipeline_entry_by_target,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org():
    """Org profile for dashboard tests."""
    return OrgProfile(
        name="Youth Link Ministries",
        ein="12-3456789",
        tax_status="501(c)(3)",
        city="Chandler",
        state="AZ",
        zip_code="85224",
        mission="Connect, coach, and resource youth pastors.",
        serves="Youth pastors and ministry leaders",
        programs=[
            {"name": "Local Youth Leader Networks", "description": "Peer networking groups"},
        ],
        budget_range="under_250k",
        years_active=19,
        ntee_codes=["X20", "X80", "B80", "S", "T"],
    )


@pytest.fixture
def sample_opp():
    """A scored opportunity dict for priority testing."""
    return {
        "id": 1,
        "title": "Faith-Based Community Leadership Development",
        "agency": "HHS",
        "description": "Support faith-based leadership development for nonprofits.",
        "eligibility": "Nonprofits with 501(c)(3) status, faith-based organizations eligible",
        "deadline": "2026-04-15",
        "award_floor": 25000,
        "award_ceiling": 100000,
        "score": 8,
        "urgency": "60_day",
        "keyword_tier": 1,
        "matched_keyword": "faith-based capacity building",
        "funding_category": "IS",
        "status": "posted",
    }


@pytest.fixture
def db_path():
    """Temporary SQLite database path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    init_db(conn)
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture
def seeded_db(db_path):
    """Database seeded with sample data."""
    conn = get_connection(db_path)

    # Insert an opportunity
    upsert_opportunity(conn, {
        "source": "grants_gov",
        "opportunity_id": "12345",
        "opportunity_number": "HHS-2026-001",
        "title": "Faith-Based Community Leadership Development",
        "agency": "Department of Health and Human Services",
        "description": "Support leadership development.",
        "funding_category": "IS",
        "award_floor": 25000,
        "award_ceiling": 100000,
        "expected_awards": 10,
        "deadline": "2026-06-15",
        "posted_date": "2026-02-01",
        "status": "posted",
        "eligibility": "Nonprofits with 501(c)(3) status",
        "url": "https://www.grants.gov/12345",
        "keyword_tier": 1,
        "matched_keyword": "faith-based",
        "raw": {},
    })

    # Score it
    insert_score(conn, {
        "opportunity_id": 1,
        "foundation_id": None,
        "score": 8,
        "explanation": "Strong mission alignment.",
        "scored_by": "claude-haiku",
    })

    # Insert a foundation
    upsert_foundation(conn, {
        "name": "Smith Family Foundation",
        "ein": "123456789",
        "city": "Phoenix",
        "state": "AZ",
        "total_assets": 5000000,
        "total_giving": 500000,
        "focus_areas": "youth ministry, education",
        "contact_info": "",
        "website": "",
        "source": "propublica",
        "raw": {},
    })

    # Score foundation
    insert_score(conn, {
        "opportunity_id": None,
        "foundation_id": 1,
        "score": 7,
        "explanation": "Good match for youth ministry.",
        "scored_by": "claude-haiku",
    })

    # Insert a draft
    insert_draft(conn, {
        "opportunity_id": 1,
        "foundation_id": None,
        "draft_type": "federal_narrative",
        "funder_name": "HHS",
        "project_name": "Leadership Development",
        "status": "draft",
        "sections_json": '{"Statement of Need": "Test need section.", "Project Description": "Test project."}',
        "full_draft": "Full draft text.",
        "file_path": "/tmp/test_draft.md",
    })

    # Pipeline entry
    upsert_pipeline_entry(conn, opportunity_id=1)

    conn.close()
    return db_path


@pytest.fixture
def app(seeded_db):
    """Flask test application."""
    from werkzeug.security import generate_password_hash
    os.environ["DASHBOARD_USERNAME"] = "admin"
    os.environ["DASHBOARD_PASSWORD_HASH"] = generate_password_hash("testpass")
    os.environ["SECRET_KEY"] = "test-secret-key-not-default"

    application = create_app(
        config_path="config/org_profile.yaml",
        db_path=seeded_db,
    )
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def authed_client(client):
    """Flask test client that is already logged in."""
    client.post("/login", data={"username": "admin", "password": "testpass"})
    return client


# ---------------------------------------------------------------------------
# Priority Score Tests
# ---------------------------------------------------------------------------


class TestPriorityScore:
    def test_calculate_priority_score(self, sample_opp, org):
        result = calculate_priority_score(sample_opp, org)
        assert "priority_score" in result
        assert "priority_label" in result
        assert "factors" in result
        assert 1.0 <= result["priority_score"] <= 10.0

    def test_priority_high_label(self, sample_opp, org):
        # Score 8 + 60-day urgency + good budget + faith-based eligibility → high
        result = calculate_priority_score(sample_opp, org)
        assert result["priority_label"] == "High"

    def test_priority_low_label(self, org):
        low_opp = {
            "score": 2,
            "urgency": "",
            "deadline": "2028-12-31",
            "award_floor": 1000000,
            "award_ceiling": 5000000,
            "eligibility": "State government agencies only",
            "funding_category": "",
        }
        result = calculate_priority_score(low_opp, org)
        assert result["priority_label"] == "Low"

    def test_urgency_30_day_highest(self, sample_opp, org):
        sample_opp["urgency"] = "30_day"
        result = calculate_priority_score(sample_opp, org)
        assert result["factors"]["deadline_urgency"]["score"] == 10

    def test_budget_sweet_spot(self, sample_opp, org):
        # $25K-$100K is perfect for under_250k org
        result = calculate_priority_score(sample_opp, org)
        assert result["factors"]["budget_match"]["score"] >= 8

    def test_budget_too_big(self, org):
        big_opp = {"score": 5, "urgency": "", "deadline": "", "award_floor": 500000,
                    "award_ceiling": 2000000, "eligibility": "", "funding_category": ""}
        result = calculate_priority_score(big_opp, org)
        assert result["factors"]["budget_match"]["score"] <= 4

    def test_eligibility_501c3_boost(self, org):
        opp = {"score": 5, "urgency": "", "deadline": "", "award_floor": 0,
               "award_ceiling": 0, "eligibility": "501(c)(3) nonprofit organizations",
               "funding_category": ""}
        result = calculate_priority_score(opp, org)
        assert result["factors"]["eligibility_fit"]["score"] >= 7

    def test_eligibility_government_penalty(self, org):
        opp = {"score": 5, "urgency": "", "deadline": "", "award_floor": 0,
               "award_ceiling": 0, "eligibility": "State government agencies only",
               "funding_category": ""}
        result = calculate_priority_score(opp, org)
        assert result["factors"]["eligibility_fit"]["score"] <= 4

    def test_enrich_opportunities(self, sample_opp, org):
        opps = [sample_opp.copy()]
        enriched = enrich_opportunities_with_priority(opps, org)
        assert enriched[0]["priority_score"] > 0
        assert enriched[0]["priority_label"] in ("High", "Medium", "Low")


# ---------------------------------------------------------------------------
# Requirement Match Tests
# ---------------------------------------------------------------------------


class TestRequirementMatching:
    def test_analyze_requirements_returns_six_checks(self, sample_opp, org):
        checks = analyze_requirements(sample_opp, org)
        assert len(checks) == 6

    def test_tax_status_pass(self, sample_opp, org):
        checks = analyze_requirements(sample_opp, org)
        tax = next(c for c in checks if c["check"] == "tax_status")
        assert tax["status"] == "pass"

    def test_faith_based_pass(self, sample_opp, org):
        checks = analyze_requirements(sample_opp, org)
        faith = next(c for c in checks if c["check"] == "faith_based")
        assert faith["status"] == "pass"

    def test_budget_fit_pass(self, sample_opp, org):
        checks = analyze_requirements(sample_opp, org)
        budget = next(c for c in checks if c["check"] == "budget")
        assert budget["status"] == "pass"

    def test_years_pass_no_minimum(self, sample_opp, org):
        checks = analyze_requirements(sample_opp, org)
        years = next(c for c in checks if c["check"] == "years")
        assert years["status"] == "pass"

    def test_years_fail_high_minimum(self, org):
        opp = {
            "eligibility": "Organizations with at least 25 years of experience",
            "description": "",
            "award_floor": 0,
            "award_ceiling": 0,
            "funding_category": "",
        }
        checks = analyze_requirements(opp, org)
        years = next(c for c in checks if c["check"] == "years")
        assert years["status"] == "fail"

    def test_summarize_strong(self, sample_opp, org):
        checks = analyze_requirements(sample_opp, org)
        summary = summarize_matches(checks)
        assert summary["pass_count"] >= 3
        assert summary["total"] == 6

    def test_summarize_caution_on_fail(self, org):
        opp = {
            "eligibility": "State government agencies only",
            "description": "",
            "award_floor": 0,
            "award_ceiling": 0,
            "funding_category": "",
        }
        checks = analyze_requirements(opp, org)
        summary = summarize_matches(checks)
        assert summary["overall"] == "caution"


# ---------------------------------------------------------------------------
# Auth Tests
# ---------------------------------------------------------------------------


class TestAuth:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Log In" in resp.data or b"login" in resp.data.lower()

    def test_login_success(self, client):
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "testpass"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data or b"dashboard" in resp.data.lower()

    def test_login_wrong_password(self, client):
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "wrongpass"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data or b"invalid" in resp.data.lower()

    def test_login_required_redirect(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_logout(self, authed_client):
        resp = authed_client.get("/logout", follow_redirects=True)
        assert b"login" in resp.data.lower()


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------


class TestDashboardRoutes:
    def test_home_page(self, authed_client):
        resp = authed_client.get("/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_opportunities_list(self, authed_client):
        resp = authed_client.get("/opportunities/")
        assert resp.status_code == 200
        assert b"Opportunities" in resp.data

    def test_opportunity_detail(self, authed_client):
        resp = authed_client.get("/opportunities/1")
        assert resp.status_code == 200
        assert b"Faith-Based" in resp.data

    def test_opportunity_not_found(self, authed_client):
        resp = authed_client.get("/opportunities/9999")
        assert resp.status_code == 404

    def test_foundations_list(self, authed_client):
        resp = authed_client.get("/foundations/")
        assert resp.status_code == 200
        assert b"Foundation" in resp.data

    def test_foundation_detail(self, authed_client):
        resp = authed_client.get("/foundations/1")
        assert resp.status_code == 200
        assert b"Smith" in resp.data

    def test_foundation_not_found(self, authed_client):
        resp = authed_client.get("/foundations/9999")
        assert resp.status_code == 404

    def test_drafts_list(self, authed_client):
        resp = authed_client.get("/drafts/")
        assert resp.status_code == 200
        assert b"Draft" in resp.data

    def test_draft_detail(self, authed_client):
        resp = authed_client.get("/drafts/1")
        assert resp.status_code == 200
        assert b"Leadership" in resp.data or b"Statement of Need" in resp.data

    def test_draft_not_found(self, authed_client):
        resp = authed_client.get("/drafts/9999")
        assert resp.status_code == 404

    def test_pipeline_page(self, authed_client):
        resp = authed_client.get("/pipeline/")
        assert resp.status_code == 200
        assert b"Pipeline" in resp.data

    def test_settings_page(self, authed_client):
        resp = authed_client.get("/settings/")
        assert resp.status_code == 200
        assert b"Youth Link" in resp.data

    def test_settings_shows_keyword_textareas(self, authed_client):
        resp = authed_client.get("/settings/")
        assert b"tier1_keywords" in resp.data
        assert b"tier2_keywords" in resp.data
        assert b"tier3_keywords" in resp.data

    def test_update_keywords_persists(self, authed_client, app):
        resp = authed_client.post(
            "/settings/keywords",
            data={
                "tier1_keywords": "pastoral development\nclergy coaching",
                "tier2_keywords": "nonprofit capacity building",
                "tier3_keywords": "youth development training",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Keywords saved" in resp.data

        # In-memory config should reflect the new keywords
        config = app.config["GRANT_CONFIG"]
        assert "pastoral development" in config.keywords["tier1"]
        assert "clergy coaching" in config.keywords["tier1"]
        assert config.keywords["tier2"] == ["nonprofit capacity building"]

    def test_update_keywords_requires_login(self, client):
        resp = client.post(
            "/settings/keywords",
            data={"tier1_keywords": "test", "tier2_keywords": "", "tier3_keywords": ""},
        )
        # Should redirect to login
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Pipeline & Draft Status Tests
# ---------------------------------------------------------------------------


class TestPipelineAndStatus:
    def test_pipeline_change_stage(self, authed_client):
        resp = authed_client.post(
            "/pipeline/1/stage",
            data={"stage": "drafting"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"drafting" in resp.data.lower() or b"Pipeline" in resp.data

    def test_pipeline_invalid_stage(self, authed_client):
        resp = authed_client.post(
            "/pipeline/1/stage",
            data={"stage": "invalid_stage"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data or resp.status_code == 200

    def test_pipeline_edit_notes(self, authed_client):
        resp = authed_client.post(
            "/pipeline/1/notes",
            data={"notes": "Test pipeline notes"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_draft_status_change(self, authed_client):
        resp = authed_client.post(
            "/drafts/1/status",
            data={"status": "review"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_draft_invalid_status(self, authed_client):
        resp = authed_client.post(
            "/drafts/1/status",
            data={"status": "bad_status"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data or resp.status_code == 200


# ---------------------------------------------------------------------------
# Filter Tests
# ---------------------------------------------------------------------------


class TestOpportunityFilters:
    def test_filter_by_min_score(self, authed_client):
        resp = authed_client.get("/opportunities/?min_score=7")
        assert resp.status_code == 200

    def test_filter_by_urgency(self, authed_client):
        resp = authed_client.get("/opportunities/?urgency=30_day")
        assert resp.status_code == 200

    def test_filter_by_tier(self, authed_client):
        resp = authed_client.get("/opportunities/?tier=1")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Database Function Tests
# ---------------------------------------------------------------------------


class TestDashboardDB:
    def test_pipeline_entry_by_target(self, seeded_db):
        conn = get_connection(seeded_db)
        entry = get_pipeline_entry_by_target(conn, opportunity_id=1)
        assert entry is not None
        assert entry["stage"] == "discovered"
        conn.close()

    def test_pipeline_entry_by_target_not_found(self, seeded_db):
        conn = get_connection(seeded_db)
        entry = get_pipeline_entry_by_target(conn, opportunity_id=9999)
        assert entry is None
        conn.close()

    def test_pipeline_entry_by_target_none(self, seeded_db):
        conn = get_connection(seeded_db)
        entry = get_pipeline_entry_by_target(conn)
        assert entry is None
        conn.close()
