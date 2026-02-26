"""Tests for database operations."""

from grant_intel.db import (
    get_all_foundations,
    get_all_opportunities,
    get_pipeline_stats,
    get_unscored_foundations,
    get_unscored_opportunities,
    insert_score,
    upsert_foundation,
    upsert_opportunity,
    upsert_similar_org,
)


def test_init_db(test_db):
    """Test database schema is created."""
    tables = test_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row["name"] for row in tables}
    assert "opportunities" in table_names
    assert "foundations" in table_names
    assert "foundation_grants" in table_names
    assert "similar_orgs" in table_names
    assert "scores" in table_names
    assert "pipeline" in table_names


def test_upsert_opportunity_new(test_db, sample_opportunity):
    """Test inserting a new opportunity."""
    is_new = upsert_opportunity(test_db, sample_opportunity)
    assert is_new is True

    row = test_db.execute(
        "SELECT * FROM opportunities WHERE opportunity_id = ?",
        (sample_opportunity["opportunity_id"],),
    ).fetchone()
    assert row is not None
    assert row["title"] == sample_opportunity["title"]
    assert row["agency"] == sample_opportunity["agency"]


def test_upsert_opportunity_duplicate(test_db, sample_opportunity):
    """Test that duplicate opportunities are updated, not duplicated."""
    upsert_opportunity(test_db, sample_opportunity)
    is_new = upsert_opportunity(test_db, sample_opportunity)
    assert is_new is False

    count = test_db.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    assert count == 1


def test_upsert_foundation_new(test_db, sample_foundation):
    """Test inserting a new foundation."""
    is_new = upsert_foundation(test_db, sample_foundation)
    assert is_new is True

    row = test_db.execute(
        "SELECT * FROM foundations WHERE ein = ?",
        (sample_foundation["ein"],),
    ).fetchone()
    assert row is not None
    assert row["name"] == sample_foundation["name"]


def test_upsert_foundation_duplicate(test_db, sample_foundation):
    """Test that duplicate foundations are updated."""
    upsert_foundation(test_db, sample_foundation)
    is_new = upsert_foundation(test_db, sample_foundation)
    assert is_new is False

    count = test_db.execute("SELECT COUNT(*) FROM foundations").fetchone()[0]
    assert count == 1


def test_insert_score(test_db, sample_opportunity):
    """Test inserting a match score."""
    upsert_opportunity(test_db, sample_opportunity)
    opp_row = test_db.execute("SELECT id FROM opportunities LIMIT 1").fetchone()

    insert_score(test_db, {
        "opportunity_id": opp_row["id"],
        "foundation_id": None,
        "score": 8,
        "explanation": "Strong mission alignment.",
        "urgency": "60_day",
        "model_used": "claude-haiku-4-5-20251001",
    })

    score_row = test_db.execute("SELECT * FROM scores LIMIT 1").fetchone()
    assert score_row["score"] == 8
    assert score_row["explanation"] == "Strong mission alignment."


def test_get_unscored_opportunities(test_db, sample_opportunity):
    """Test fetching unscored opportunities."""
    upsert_opportunity(test_db, sample_opportunity)

    unscored = get_unscored_opportunities(test_db)
    assert len(unscored) == 1

    # Score it, then check again
    opp_row = test_db.execute("SELECT id FROM opportunities LIMIT 1").fetchone()
    insert_score(test_db, {
        "opportunity_id": opp_row["id"],
        "score": 7,
        "explanation": "Good fit.",
        "urgency": "none",
        "model_used": "test",
    })

    unscored = get_unscored_opportunities(test_db)
    assert len(unscored) == 0


def test_get_unscored_foundations(test_db, sample_foundation):
    """Test fetching unscored foundations."""
    upsert_foundation(test_db, sample_foundation)

    unscored = get_unscored_foundations(test_db)
    assert len(unscored) == 1


def test_get_pipeline_stats(test_db, sample_opportunity, sample_foundation):
    """Test pipeline statistics."""
    upsert_opportunity(test_db, sample_opportunity)
    upsert_foundation(test_db, sample_foundation)

    stats = get_pipeline_stats(test_db)
    assert stats["total_opportunities"] == 1
    assert stats["total_foundations"] == 1
    assert stats["scored_opportunities"] == 0
    assert stats["scored_foundations"] == 0


def test_upsert_similar_org(test_db):
    """Test inserting a similar org."""
    org = {
        "name": "National Network of Youth Ministries",
        "ein": "953537789",
        "city": "San Diego",
        "state": "CA",
        "total_revenue": 800000,
        "total_expenses": 750000,
        "ntee_code": "X20",
        "mission": "",
        "source": "propublica",
        "raw": {},
    }
    is_new = upsert_similar_org(test_db, org)
    assert is_new is True

    is_new = upsert_similar_org(test_db, org)
    assert is_new is False


def test_get_all_opportunities(test_db, sample_opportunity):
    """Test getting all opportunities with scores."""
    upsert_opportunity(test_db, sample_opportunity)
    opps = get_all_opportunities(test_db)
    assert len(opps) == 1
    assert opps[0]["title"] == sample_opportunity["title"]


def test_get_all_foundations(test_db, sample_foundation):
    """Test getting all foundations with scores."""
    upsert_foundation(test_db, sample_foundation)
    foundations = get_all_foundations(test_db)
    assert len(foundations) == 1
    assert foundations[0]["name"] == sample_foundation["name"]
