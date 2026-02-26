"""Tests for Claude API scoring engine."""

from grant_intel.config import OrgProfile
from grant_intel.scoring.matcher import _calculate_urgency, build_system_prompt


def test_build_system_prompt():
    """Test system prompt construction."""
    org = OrgProfile(
        name="Youth Link Ministries",
        tax_status="501(c)(3)",
        city="Chandler",
        state="AZ",
        mission="Connect, coach, and resource youth pastors.",
        serves="Youth pastors (NOT youth directly)",
        programs=[
            {"name": "Networking", "description": "Leader networks"},
            {"name": "Coaching", "description": "Pastoral coaching"},
        ],
        budget_range="under_250k",
        ntee_codes=["X20", "X80"],
    )

    prompt = build_system_prompt(org)
    assert "Youth Link Ministries" in prompt
    assert "501(c)(3)" in prompt
    assert "Chandler" in prompt
    assert "youth pastors" in prompt.lower() or "Youth pastors" in prompt
    assert "NOT youth directly" in prompt
    assert "X20" in prompt
    assert "Networking" in prompt
    assert "Coaching" in prompt


def test_calculate_urgency_30_day():
    """Test urgency calculation for deadlines within 30 days."""
    from datetime import date, timedelta

    deadline = (date.today() + timedelta(days=15)).isoformat()
    assert _calculate_urgency(deadline) == "30_day"


def test_calculate_urgency_60_day():
    """Test urgency calculation for deadlines within 60 days."""
    from datetime import date, timedelta

    deadline = (date.today() + timedelta(days=45)).isoformat()
    assert _calculate_urgency(deadline) == "60_day"


def test_calculate_urgency_90_day():
    """Test urgency calculation for deadlines within 90 days."""
    from datetime import date, timedelta

    deadline = (date.today() + timedelta(days=75)).isoformat()
    assert _calculate_urgency(deadline) == "90_day"


def test_calculate_urgency_none():
    """Test urgency for distant deadlines."""
    from datetime import date, timedelta

    deadline = (date.today() + timedelta(days=120)).isoformat()
    assert _calculate_urgency(deadline) == "none"


def test_calculate_urgency_empty():
    """Test urgency for empty deadline."""
    assert _calculate_urgency("") == "none"
    assert _calculate_urgency(None) == "none"
