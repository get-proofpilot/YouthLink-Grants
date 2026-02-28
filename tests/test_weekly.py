"""Tests for the weekly scoring agent — cooldown, dry-run, and partial failure."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from grant_intel.config import Config, OrgProfile
from grant_intel.db import get_setting, init_db, set_setting
from grant_intel.scoring.weekly import COOLDOWN_DAYS, SETTING_KEY, _check_cooldown, run_weekly_scoring


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def test_config(tmp_path):
    db_path = str(tmp_path / "test.db")
    org = OrgProfile(
        name="Youth Link Ministries",
        ein="12-3456789",
        tax_status="501(c)(3)",
        city="Chandler",
        state="AZ",
        zip_code="85224",
        mission="Connect, coach, and resource youth pastors.",
        serves="Youth pastors and ministry leaders",
        programs=[],
        budget_range="under_250k",
        years_active=19,
        ntee_codes=["X20"],
    )
    return Config(
        org=org,
        keywords={"tier1": ["faith-based capacity"]},
        similar_orgs=[],
        db_path=db_path,
        anthropic_api_key="",
        brave_api_key="",
    )


# ── Cooldown tests ──────────────────────────────────────────────────────────

class TestCheckCooldown:
    def test_no_previous_run_should_run(self, mem_conn):
        should_run, msg = _check_cooldown(mem_conn)
        assert should_run is True
        assert "No previous" in msg

    def test_force_overrides_cooldown(self, mem_conn):
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        set_setting(mem_conn, SETTING_KEY, recent)
        should_run, msg = _check_cooldown(mem_conn, force=True)
        assert should_run is True
        assert "overridden" in msg.lower()

    def test_within_cooldown_skips(self, mem_conn):
        recent = (datetime.now() - timedelta(days=2)).isoformat()
        set_setting(mem_conn, SETTING_KEY, recent)
        should_run, msg = _check_cooldown(mem_conn)
        assert should_run is False
        assert "next run" in msg

    def test_past_cooldown_runs(self, mem_conn):
        old = (datetime.now() - timedelta(days=COOLDOWN_DAYS + 1)).isoformat()
        set_setting(mem_conn, SETTING_KEY, old)
        should_run, msg = _check_cooldown(mem_conn)
        assert should_run is True

    def test_invalid_timestamp_runs_anyway(self, mem_conn):
        set_setting(mem_conn, SETTING_KEY, "not-a-date")
        should_run, msg = _check_cooldown(mem_conn)
        assert should_run is True


# ── Dry-run tests ────────────────────────────────────────────────────────────

class TestRunWeeklyScoringDryRun:
    def test_dry_run_skips_data_refresh(self, test_config):
        with patch("grant_intel.scoring.weekly._refresh_data") as mock_refresh:
            result = run_weekly_scoring(
                test_config.db_path, test_config, dry_run=True
            )
        mock_refresh.assert_not_called()
        assert result["dry_run"] is True

    def test_dry_run_does_not_record_timestamp(self, test_config):
        with patch("grant_intel.scoring.weekly._refresh_data"):
            run_weekly_scoring(test_config.db_path, test_config, dry_run=True)

        import sqlite3 as _sq
        conn = _sq.connect(test_config.db_path)
        conn.row_factory = _sq.Row
        from grant_intel.db import init_db
        init_db(conn)
        last_run = get_setting(conn, SETTING_KEY)
        conn.close()
        assert last_run is None

    def test_dry_run_returns_summary(self, test_config):
        result = run_weekly_scoring(test_config.db_path, test_config, dry_run=True)
        assert "skipped" in result
        assert "dry_run" in result
        assert result["skipped"] is False


# ── Cooldown skip ────────────────────────────────────────────────────────────

class TestCooldownSkip:
    def test_within_cooldown_returns_skipped(self, test_config):
        import sqlite3 as _sq
        conn = _sq.connect(test_config.db_path)
        conn.row_factory = _sq.Row
        from grant_intel.db import init_db
        init_db(conn)
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        set_setting(conn, SETTING_KEY, recent)
        conn.close()

        with patch("grant_intel.scoring.weekly._refresh_data") as mock_refresh:
            result = run_weekly_scoring(test_config.db_path, test_config)

        mock_refresh.assert_not_called()
        assert result["skipped"] is True
        assert result["skip_reason"]

    def test_force_flag_bypasses_cooldown(self, test_config):
        import sqlite3 as _sq
        conn = _sq.connect(test_config.db_path)
        conn.row_factory = _sq.Row
        from grant_intel.db import init_db
        init_db(conn)
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        set_setting(conn, SETTING_KEY, recent)
        conn.close()

        with patch("grant_intel.scoring.weekly._refresh_data", return_value={"new_opps": 0, "new_foundations": 0, "enriched": 0, "web_opps": 0}):
            result = run_weekly_scoring(test_config.db_path, test_config, force=True)

        assert result["skipped"] is False


# ── Timestamp recording ──────────────────────────────────────────────────────

class TestTimestampRecording:
    def test_records_timestamp_on_success(self, test_config):
        with patch("grant_intel.scoring.weekly._refresh_data", return_value={"new_opps": 0, "new_foundations": 0, "enriched": 0, "web_opps": 0}):
            run_weekly_scoring(test_config.db_path, test_config)

        import sqlite3 as _sq
        conn = _sq.connect(test_config.db_path)
        conn.row_factory = _sq.Row
        from grant_intel.db import init_db
        init_db(conn)
        last_run = get_setting(conn, SETTING_KEY)
        conn.close()
        assert last_run is not None
        # Should be a valid ISO datetime
        datetime.fromisoformat(last_run)
