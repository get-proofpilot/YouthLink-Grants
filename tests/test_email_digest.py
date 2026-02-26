"""Tests for email digest rendering."""

import os
import tempfile

from grant_intel.delivery.email_digest import dry_run_digest, render_digest


def test_render_digest():
    """Test rendering the digest HTML template."""
    opportunities = [
        {
            "score": 9,
            "title": "Leadership Development Grant",
            "agency": "HHS",
            "deadline": "2026-04-15",
            "urgency": "30_day",
            "award_floor": 50000,
            "award_ceiling": 200000,
            "explanation": "Excellent mission alignment for pastoral training.",
            "url": "https://grants.gov/test",
        }
    ]
    foundations = [
        {
            "score": 8,
            "name": "Smith Foundation",
            "state": "AZ",
            "total_giving": 1000000,
            "explanation": "Active funder of Christian leadership programs.",
        }
    ]
    stats = {
        "total_opportunities": 10,
        "total_foundations": 5,
        "scored_opportunities": 8,
        "scored_foundations": 4,
    }

    html = render_digest(opportunities, foundations, stats)
    assert "Leadership Development Grant" in html
    assert "9/10" in html
    assert "URGENT" in html
    assert "Smith Foundation" in html
    assert "YLM Grant Intelligence Report" in html


def test_render_digest_empty():
    """Test rendering digest with no data."""
    html = render_digest([], [], {
        "total_opportunities": 0,
        "total_foundations": 0,
        "scored_opportunities": 0,
        "scored_foundations": 0,
    })
    assert "YLM Grant Intelligence Report" in html


def test_dry_run_digest():
    """Test saving digest to file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = dry_run_digest([], [], {
            "total_opportunities": 0,
            "total_foundations": 0,
            "scored_opportunities": 0,
            "scored_foundations": 0,
        }, output_dir=tmpdir)
        assert os.path.exists(path)
        assert path.endswith(".html")
