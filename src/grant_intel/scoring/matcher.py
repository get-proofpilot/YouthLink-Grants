"""Claude API scoring engine for grant opportunity matching."""

import json
import logging
import re
import sqlite3
from datetime import date, datetime

import anthropic

from grant_intel.config import OrgProfile
from grant_intel.scoring.rules import score_all_opportunities

logger = logging.getLogger(__name__)


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences from Claude's response before JSON parsing."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text

SCORING_SYSTEM_PROMPT = """You are a grant analyst for {org_name}, a {tax_status} nonprofit in {city}, {state}.

MISSION: {mission}

KEY DISTINCTION: {serves}

PROGRAMS:
{programs}

BUDGET: {budget_range} annual
NTEE CODES: {ntee_codes}

Score each grant opportunity or foundation on a scale of 1-10 based on these weighted criteria:
- Mission alignment (40%): Does this fund pastoral development, ministry leadership, or clergy support?
- Budget match (15%): Is the award range appropriate for a small nonprofit?
- Geographic eligibility (15%): Arizona, national, or open geographic scope?
- Applicant type (15%): Does it accept 501(c)(3) religious/faith-based orgs?
- Program overlap (15%): Does it map to networking, coaching, or resource programs?

CRITICAL: {org_name} serves youth PASTORS and ministry LEADERS, not youth directly.
Grants for direct youth services should score LOWER unless they also fund leader development.

Respond with valid JSON only. No markdown, no code blocks."""

OPPORTUNITY_PROMPT = """Score these grant opportunities for {org_name}:

{items_json}

Respond with a JSON array. For each item:
{{
  "id": <the id from the input>,
  "score": <1-10 integer>,
  "explanation": "<2-3 sentence explanation of fit>",
  "urgency": "<one of: 30_day, 60_day, 90_day, none>"
}}"""

FOUNDATION_PROMPT = """Score these foundation prospects for {org_name}:

{items_json}

Respond with a JSON array. For each item:
{{
  "id": <the id from the input>,
  "score": <1-10 integer>,
  "explanation": "<2-3 sentence explanation of why this foundation might fund {org_name}>"
}}"""


def build_system_prompt(org: OrgProfile) -> str:
    """Build the scoring system prompt from org profile."""
    programs_text = "\n".join(
        f"- {p['name']}: {p['description']}" for p in org.programs
    )
    return SCORING_SYSTEM_PROMPT.format(
        org_name=org.name,
        tax_status=org.tax_status,
        city=org.city,
        state=org.state,
        mission=org.mission,
        serves=org.serves,
        programs=programs_text,
        budget_range=org.budget_range,
        ntee_codes=", ".join(org.ntee_codes),
    )


def _calculate_urgency(deadline: str) -> str:
    """Calculate urgency based on deadline date."""
    if not deadline:
        return "none"
    try:
        deadline_date = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
        days_left = (deadline_date - date.today()).days
        if days_left < 0:
            return "none"
        if days_left <= 30:
            return "30_day"
        if days_left <= 60:
            return "60_day"
        if days_left <= 90:
            return "90_day"
        return "none"
    except (ValueError, TypeError):
        return "none"


def score_opportunities(
    api_key: str,
    org: OrgProfile,
    opportunities: list[dict],
    batch_size: int = 5,
) -> list[dict]:
    """Score opportunities using Claude API.

    Uses Haiku for bulk scoring.
    """
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(org)
    all_scores = []

    for i in range(0, len(opportunities), batch_size):
        batch = opportunities[i : i + batch_size]

        items = []
        for opp in batch:
            items.append({
                "id": opp["id"],
                "title": opp.get("title", ""),
                "agency": opp.get("agency", ""),
                "description": opp.get("description", "")[:500],
                "deadline": opp.get("deadline", ""),
                "award_floor": opp.get("award_floor"),
                "award_ceiling": opp.get("award_ceiling"),
                "status": opp.get("status", ""),
                "eligibility": opp.get("eligibility", ""),
                "funding_category": opp.get("funding_category", ""),
            })

        user_prompt = OPPORTUNITY_PROMPT.format(
            org_name=org.name,
            items_json=json.dumps(items, indent=2),
        )

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = _clean_json_response(response.content[0].text)
            scores = json.loads(response_text)

            for score_data in scores:
                opp_id = score_data.get("id")
                matching_opp = next((o for o in batch if o["id"] == opp_id), None)
                deadline = matching_opp.get("deadline", "") if matching_opp else ""

                all_scores.append({
                    "opportunity_id": opp_id,
                    "foundation_id": None,
                    "score": min(10, max(1, int(score_data.get("score", 1)))),
                    "explanation": score_data.get("explanation", ""),
                    "urgency": score_data.get("urgency", _calculate_urgency(deadline)),
                    "model_used": "claude-haiku-4-5-20251001",
                })

            logger.info(
                "Scored batch %d-%d: %d scores",
                i + 1,
                min(i + batch_size, len(opportunities)),
                len(scores),
            )
        except anthropic.AuthenticationError:
            logger.error("Invalid API key — aborting scoring")
            break
        except (json.JSONDecodeError, anthropic.APIError):
            logger.exception("Error scoring batch %d-%d", i + 1, i + batch_size)

    return all_scores


def score_with_funnel(
    conn: sqlite3.Connection,
    org: OrgProfile,
    api_key: str | None = None,
    ai_threshold: int = 6,
    rules_only: bool = False,
    batch_size: int = 5,
) -> dict:
    """3-tier scoring funnel: rules first, then AI for top candidates.

    Returns summary dict with counts for each tier.
    """
    from grant_intel.db import (
        get_rule_score_candidates,
        get_unscored_rule_opportunities,
        insert_score,
        update_rule_score,
    )

    summary = {"rule_scored": 0, "ai_scored": 0, "ai_skipped": 0}

    # ── Tier 1: Rule-score everything unscored ─────────────────────
    unscored = get_unscored_rule_opportunities(conn)
    if unscored:
        results = score_all_opportunities(unscored)
        for r in results:
            update_rule_score(conn, r["id"], r["rule_score"], r["rule_explanation"])
        summary["rule_scored"] = len(results)
        logger.info("Rule-scored %d opportunities", len(results))

    # ── Tier 2: AI-score top candidates ────────────────────────────
    if rules_only or not api_key:
        candidates = get_rule_score_candidates(conn, threshold=ai_threshold)
        summary["ai_skipped"] = len(candidates)
        logger.info("Skipping AI scoring (%s)", "rules-only mode" if rules_only else "no API key")
        return summary

    candidates = get_rule_score_candidates(conn, threshold=ai_threshold)
    if candidates:
        logger.info(
            "Sending %d candidates (rule_score >= %d) to Claude AI",
            len(candidates), ai_threshold,
        )
        ai_scores = score_opportunities(api_key, org, candidates, batch_size=batch_size)
        for s in ai_scores:
            insert_score(conn, s)
        summary["ai_scored"] = len(ai_scores)
    else:
        logger.info("No candidates above AI threshold (%d)", ai_threshold)

    return summary


def score_foundations(
    api_key: str,
    org: OrgProfile,
    foundations: list[dict],
    batch_size: int = 5,
) -> list[dict]:
    """Score foundation prospects using Claude API."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(org)
    all_scores = []

    for i in range(0, len(foundations), batch_size):
        batch = foundations[i : i + batch_size]

        items = []
        for f in batch:
            items.append({
                "id": f["id"],
                "name": f.get("name", ""),
                "ein": f.get("ein", ""),
                "state": f.get("state", ""),
                "total_giving": f.get("total_giving"),
                "focus_areas": f.get("focus_areas", ""),
            })

        user_prompt = FOUNDATION_PROMPT.format(
            org_name=org.name,
            items_json=json.dumps(items, indent=2),
        )

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = _clean_json_response(response.content[0].text)
            scores = json.loads(response_text)

            for score_data in scores:
                all_scores.append({
                    "opportunity_id": None,
                    "foundation_id": score_data.get("id"),
                    "score": min(10, max(1, int(score_data.get("score", 1)))),
                    "explanation": score_data.get("explanation", ""),
                    "urgency": "",
                    "model_used": "claude-haiku-4-5-20251001",
                })

            logger.info("Scored foundation batch %d-%d", i + 1, i + batch_size)
        except anthropic.AuthenticationError:
            logger.error("Invalid API key — aborting foundation scoring")
            break
        except (json.JSONDecodeError, anthropic.APIError):
            logger.exception("Error scoring foundation batch %d-%d", i + 1, i + batch_size)

    return all_scores
