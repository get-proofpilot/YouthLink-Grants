"""Weekly scoring agent — runs the full AI verification cycle on a schedule.

Rule engine runs instantly on dashboard startup (free). This module handles
the weekly AI verification pass on all rule-matched candidates (rule_score >= 7).
Haiku is cheap enough to verify everything worth looking at.
"""

import logging
from datetime import datetime

from grant_intel.config import Config
from grant_intel.db import (
    get_connection,
    get_rule_score_candidates,
    get_setting,
    get_unscored_foundations,
    get_unscored_rule_opportunities,
    init_db,
    insert_score,
    set_setting,
    update_rule_score,
    upsert_foundation,
    upsert_opportunity,
    upsert_similar_org,
)

logger = logging.getLogger(__name__)

COOLDOWN_DAYS = 6
SETTING_KEY = "last_weekly_run"


def _check_cooldown(conn, force: bool = False) -> tuple[bool, str]:
    """Check if enough time has passed since the last weekly run.

    Returns (should_run, message).
    """
    if force:
        return True, "Cooldown overridden with --force"

    last_run = get_setting(conn, SETTING_KEY)
    if not last_run:
        return True, "No previous weekly run found"

    try:
        last_dt = datetime.fromisoformat(last_run)
    except (ValueError, TypeError):
        return True, "Invalid last-run timestamp, running anyway"

    elapsed = datetime.now() - last_dt
    days_ago = elapsed.days
    next_in = COOLDOWN_DAYS - days_ago

    if days_ago >= COOLDOWN_DAYS:
        return True, f"Last run was {days_ago} days ago — ready to run"

    return False, f"Ran {days_ago} day{'s' if days_ago != 1 else ''} ago, next run in {next_in} day{'s' if next_in != 1 else ''}"


def _refresh_data(config, conn) -> dict:
    """Search Grants.gov + research foundations for new data."""
    from grant_intel.sources.grants_gov import discover_grants
    from grant_intel.sources.propublica import research_similar_orgs, search_foundations_by_keyword

    stats = {"new_opps": 0, "new_foundations": 0}

    # Search Grants.gov
    logger.info("Weekly: searching Grants.gov...")
    try:
        results = discover_grants(config.keywords)
        for opp in results:
            if upsert_opportunity(conn, opp):
                stats["new_opps"] += 1
        logger.info("Weekly: found %d opportunities (%d new)", len(results), stats["new_opps"])
    except Exception:
        logger.exception("Weekly: Grants.gov search failed")

    # Research similar orgs
    try:
        org_infos, _filings = research_similar_orgs(config.similar_orgs)
        for org_info in org_infos:
            upsert_similar_org(conn, org_info)
    except Exception:
        logger.exception("Weekly: similar org research failed")

    # Search foundations
    try:
        from grant_intel.config import FOUNDATION_SEARCH_KEYWORDS
        foundation_keywords = FOUNDATION_SEARCH_KEYWORDS
        foundations = search_foundations_by_keyword(foundation_keywords, states=["AZ", ""])
        for f in foundations:
            if upsert_foundation(conn, f):
                stats["new_foundations"] += 1
        logger.info("Weekly: found %d foundations (%d new)", len(foundations), stats["new_foundations"])
    except Exception:
        logger.exception("Weekly: foundation search failed")

    return stats


def run_weekly_scoring(
    db_path: str,
    config: Config,
    force: bool = False,
    dry_run: bool = False,
    ai_threshold: int = 6,
    batch_size: int = 5,
) -> dict:
    """Run the full weekly scoring cycle.

    Steps:
        1. Check cooldown (skip if ran within 6 days, unless --force)
        2. Refresh data from Grants.gov + foundations
        3. Rule-score any new/unscored opportunities
        4. AI-verify ALL candidates with rule_score >= threshold
        5. AI-score any unscored foundations
        6. Record run timestamp

    Returns a summary dict with counts.
    """
    from grant_intel.scoring.matcher import score_foundations, score_opportunities
    from grant_intel.scoring.rules import score_all_opportunities

    conn = get_connection(db_path)
    init_db(conn)

    summary = {
        "skipped": False,
        "skip_reason": "",
        "new_opps": 0,
        "new_foundations": 0,
        "rule_scored": 0,
        "ai_candidates": 0,
        "ai_scored": 0,
        "foundations_scored": 0,
        "dry_run": dry_run,
    }

    # ── Step 1: Cooldown check ────────────────────────────────────
    should_run, cooldown_msg = _check_cooldown(conn, force=force)
    logger.info("Weekly cooldown: %s", cooldown_msg)

    if not should_run:
        summary["skipped"] = True
        summary["skip_reason"] = cooldown_msg
        conn.close()
        return summary

    # ── Step 2: Refresh data ──────────────────────────────────────
    if not dry_run:
        refresh_stats = _refresh_data(config, conn)
        summary["new_opps"] = refresh_stats["new_opps"]
        summary["new_foundations"] = refresh_stats["new_foundations"]
    else:
        logger.info("Weekly: dry-run — skipping data refresh")

    # ── Step 3: Rule-score new/unscored opportunities ─────────────
    unscored = get_unscored_rule_opportunities(conn)
    if unscored:
        if dry_run:
            summary["rule_scored"] = len(unscored)
            logger.info("Weekly: would rule-score %d opportunities", len(unscored))
        else:
            results = score_all_opportunities(unscored)
            for r in results:
                update_rule_score(conn, r["id"], r["rule_score"], r["rule_explanation"])
            summary["rule_scored"] = len(results)
            logger.info("Weekly: rule-scored %d opportunities", len(results))

    # ── Step 4: AI-verify candidates with rule_score >= threshold ─
    candidates = get_rule_score_candidates(conn, threshold=ai_threshold)
    summary["ai_candidates"] = len(candidates)

    if candidates:
        if dry_run:
            logger.info(
                "Weekly: would AI-score %d candidates (rule_score >= %d)",
                len(candidates), ai_threshold,
            )
        elif not config.anthropic_api_key:
            logger.warning("Weekly: no ANTHROPIC_API_KEY — skipping AI scoring")
        else:
            logger.info(
                "Weekly: AI-scoring %d candidates (rule_score >= %d)...",
                len(candidates), ai_threshold,
            )
            ai_scores = score_opportunities(
                config.anthropic_api_key, config.org, candidates, batch_size=batch_size,
            )
            for s in ai_scores:
                insert_score(conn, s)
            summary["ai_scored"] = len(ai_scores)
            logger.info("Weekly: AI-scored %d opportunities", len(ai_scores))

    # ── Step 5: AI-score unscored foundations ──────────────────────
    unscored_foundations = get_unscored_foundations(conn)
    if unscored_foundations:
        if dry_run:
            summary["foundations_scored"] = len(unscored_foundations)
            logger.info("Weekly: would AI-score %d foundations", len(unscored_foundations))
        elif not config.anthropic_api_key:
            logger.warning("Weekly: no ANTHROPIC_API_KEY — skipping foundation scoring")
        else:
            logger.info("Weekly: AI-scoring %d foundations...", len(unscored_foundations))
            foundation_scores = score_foundations(
                config.anthropic_api_key, config.org, unscored_foundations, batch_size=batch_size,
            )
            for s in foundation_scores:
                insert_score(conn, s)
            summary["foundations_scored"] = len(foundation_scores)
            logger.info("Weekly: AI-scored %d foundations", len(foundation_scores))

    # ── Step 6: Record run timestamp ──────────────────────────────
    if not dry_run:
        set_setting(conn, SETTING_KEY, datetime.now().isoformat())
        logger.info("Weekly: recorded run timestamp")

    conn.close()
    return summary
