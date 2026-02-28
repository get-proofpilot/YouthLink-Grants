"""Action endpoints — trigger scoring, search, drafts from the dashboard."""

import logging
import sys

from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import login_required

from grant_intel.db import (
    get_connection,
    get_unscored_foundations,
    get_unscored_opportunities,
    get_unscored_web_opportunities,
    init_db,
    insert_draft,
    insert_score,
    insert_web_score,
    upsert_foundation,
    upsert_opportunity,
)

logger = logging.getLogger(__name__)

actions_bp = Blueprint("actions", __name__)


@actions_bp.route("/search", methods=["POST"])
@login_required
def trigger_search():
    """Run Grants.gov search."""
    config = current_app.config["GRANT_CONFIG"]
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.sources.grants_gov import discover_grants

        results = discover_grants(config.keywords)
        new_count = 0
        for opp in results:
            if upsert_opportunity(conn, opp):
                new_count += 1
        flash(f"Search complete: {len(results)} opportunities found ({new_count} new).", "success")
    except Exception as e:
        logger.exception("Search failed")
        flash(f"Search failed: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("main.home"))


@actions_bp.route("/score", methods=["POST"])
@login_required
def trigger_scoring():
    """Score all unscored opportunities and foundations."""
    config = current_app.config["GRANT_CONFIG"]

    if not config.anthropic_api_key:
        flash("ANTHROPIC_API_KEY not configured.", "danger")
        return redirect(url_for("main.home"))

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.scoring.matcher import score_foundations, score_opportunities, score_web_opportunities

        unscored_opps = get_unscored_opportunities(conn)
        unscored_founds = get_unscored_foundations(conn)
        unscored_web = get_unscored_web_opportunities(conn)

        scored = 0
        if unscored_opps:
            opp_scores = score_opportunities(config.anthropic_api_key, config.org, unscored_opps)
            for s in opp_scores:
                insert_score(conn, s)
            scored += len(opp_scores)

        if unscored_founds:
            f_scores = score_foundations(config.anthropic_api_key, config.org, unscored_founds)
            for s in f_scores:
                insert_score(conn, s)
            scored += len(f_scores)

        if unscored_web:
            w_scores = score_web_opportunities(config.anthropic_api_key, config.org, unscored_web)
            for s in w_scores:
                insert_web_score(conn, s)
            scored += len(w_scores)

        flash(f"Scoring complete: {scored} items scored.", "success")
    except Exception as e:
        logger.exception("Scoring failed")
        flash(f"Scoring failed: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("main.home"))


@actions_bp.route("/draft/<int:opp_id>", methods=["POST"])
@login_required
def trigger_draft(opp_id):
    """Generate a federal narrative draft for an opportunity."""
    config = current_app.config["GRANT_CONFIG"]

    if not config.anthropic_api_key:
        flash("ANTHROPIC_API_KEY not configured.", "danger")
        return redirect(url_for("opportunities.detail", opp_id=opp_id))

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.db import get_opportunity_by_id
        from grant_intel.writer.agent import build_draft_record, draft_federal_narrative

        opp = get_opportunity_by_id(conn, opp_id)
        if not opp:
            flash("Opportunity not found.", "danger")
            return redirect(url_for("opportunities.index"))

        requirements = {
            "funder_name": opp.get("agency", ""),
            "program_name": opp.get("title", ""),
            "deadline": opp.get("deadline", ""),
            "award_range": {"min": opp.get("award_floor", 0) or 0, "max": opp.get("award_ceiling", 0) or 0},
            "eligible_applicants": opp.get("eligibility", ""),
            "required_sections": [],
            "page_limits": {},
            "evaluation_criteria": [],
            "focus_areas": [],
            "restrictions": [],
            "questions_to_answer": [],
            "raw_text": opp.get("description", ""),
        }

        filepath, sections = draft_federal_narrative(
            api_key=config.anthropic_api_key,
            org=config.org,
            requirements=requirements,
        )

        record = build_draft_record(
            opportunity_id=opp_id,
            foundation_id=None,
            draft_type="federal_narrative",
            funder_name=requirements.get("funder_name", ""),
            project_name=requirements.get("program_name", ""),
            requirements=requirements,
            sections=sections,
            full_draft_path=filepath,
        )
        draft_id = insert_draft(conn, record)
        flash(f"Draft generated! ({len(sections)} sections)", "success")
        return redirect(url_for("drafts.detail", draft_id=draft_id))
    except Exception as e:
        logger.exception("Draft generation failed")
        flash(f"Draft generation failed: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("opportunities.detail", opp_id=opp_id))


@actions_bp.route("/seed", methods=["POST"])
@login_required
def trigger_seed():
    """Seed curated foundations into the database."""
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.sources.curated import seed_curated_foundations
        new_count = seed_curated_foundations(conn)
        flash(f"Seeding complete: {new_count} new curated foundations added.", "success")
    except Exception as e:
        logger.exception("Seeding failed")
        flash(f"Seeding failed: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("main.home"))


@actions_bp.route("/enrich", methods=["POST"])
@login_required
def trigger_enrich():
    """Enrich foundations with ProPublica data."""
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.sources.givingtuesday import enrich_all_foundations
        stats = enrich_all_foundations(conn)
        flash(
            f"Enrichment complete: {stats['enriched']} enriched, "
            f"{stats['skipped']} skipped, {stats['failed']} failed.",
            "success",
        )
    except Exception as e:
        logger.exception("Enrichment failed")
        flash(f"Enrichment failed: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("main.home"))


@actions_bp.route("/brave-search", methods=["POST"])
@login_required
def trigger_brave_search():
    """Run Brave Search for web grant opportunities."""
    config = current_app.config["GRANT_CONFIG"]
    if not config.brave_api_key:
        flash("BRAVE_API_KEY not configured.", "danger")
        return redirect(url_for("main.home"))

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.config import BRAVE_SEARCH_QUERIES
        from grant_intel.sources.brave_search import discover_web_opportunities
        stats = discover_web_opportunities(BRAVE_SEARCH_QUERIES, conn, config.brave_api_key)
        flash(
            f"Brave Search complete: {stats['queries_run']} queries, "
            f"{stats['grant_results']} grant-like results, {stats['saved_new']} new saved.",
            "success",
        )
    except Exception as e:
        logger.exception("Brave Search failed")
        flash(f"Brave Search failed: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("web_opportunities.index"))


@actions_bp.route("/loi/<int:foundation_id>", methods=["POST"])
@login_required
def trigger_loi(foundation_id):
    """Generate a foundation LOI."""
    config = current_app.config["GRANT_CONFIG"]

    if not config.anthropic_api_key:
        flash("ANTHROPIC_API_KEY not configured.", "danger")
        return redirect(url_for("foundations.detail", foundation_id=foundation_id))

    amount = request.form.get("amount", type=int)
    project_name = request.form.get("project_name", "")

    if not amount or not project_name:
        flash("Amount and project name are required.", "danger")
        return redirect(url_for("foundations.detail", foundation_id=foundation_id))

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        from grant_intel.db import get_foundation_by_id
        from grant_intel.writer.agent import build_draft_record, draft_foundation_loi

        foundation = get_foundation_by_id(conn, foundation_id)
        if not foundation:
            flash("Foundation not found.", "danger")
            return redirect(url_for("foundations.index"))

        filepath, loi_text = draft_foundation_loi(
            api_key=config.anthropic_api_key,
            org=config.org,
            requirements={},
            funder_name=foundation["name"],
            amount=amount,
            project_name=project_name,
        )

        record = build_draft_record(
            opportunity_id=None,
            foundation_id=foundation_id,
            draft_type="foundation_loi",
            funder_name=foundation["name"],
            project_name=project_name,
            requirements={},
            sections={"Letter of Inquiry": loi_text},
            full_draft_path=filepath,
        )
        draft_id = insert_draft(conn, record)
        flash("LOI generated!", "success")
        return redirect(url_for("drafts.detail", draft_id=draft_id))
    except Exception as e:
        logger.exception("LOI generation failed")
        flash(f"LOI generation failed: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("foundations.detail", foundation_id=foundation_id))
