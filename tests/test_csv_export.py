"""Tests for CSV export."""

import csv
import os
import tempfile

from grant_intel.delivery.csv_export import export_foundations_csv, export_opportunities_csv


def test_export_opportunities_csv():
    """Test generating opportunities CSV."""
    opportunities = [
        {
            "score": 8,
            "title": "Test Grant",
            "agency": "HHS",
            "deadline": "2026-06-15",
            "urgency": "60_day",
            "award_floor": 25000,
            "award_ceiling": 100000,
            "status": "posted",
            "explanation": "Good fit for YLM.",
            "url": "https://grants.gov/12345",
            "keyword_tier": 1,
            "matched_keyword": "pastoral development",
            "source": "grants_gov",
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = export_opportunities_csv(opportunities, tmpdir)
        assert os.path.exists(path)
        assert "grant_opportunities_" in path

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["Score"] == "8"
            assert rows[0]["Title"] == "Test Grant"
            assert rows[0]["Award Floor"] == "$25,000"
            assert rows[0]["Award Ceiling"] == "$100,000"


def test_export_foundations_csv():
    """Test generating foundations CSV."""
    foundations = [
        {
            "score": 7,
            "name": "Smith Foundation",
            "ein": "123456789",
            "state": "AZ",
            "total_giving": 500000,
            "focus_areas": "youth ministry",
            "explanation": "Strong match.",
            "source": "propublica",
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = export_foundations_csv(foundations, tmpdir)
        assert os.path.exists(path)

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["Foundation Name"] == "Smith Foundation"
            assert rows[0]["Total Giving"] == "$500,000"


def test_export_empty_opportunities():
    """Test exporting empty opportunity list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = export_opportunities_csv([], tmpdir)
        assert os.path.exists(path)

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 0
