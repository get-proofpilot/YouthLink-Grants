"""Opportunities list and detail pages."""

import math

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from grant_intel.dashboard.priority import (
    analyze_requirements,
    calculate_priority_score,
    enrich_opportunities_with_priority,
    summarize_matches,
)
from grant_intel.db import (
    get_all_opportunities,
    get_connection,
    get_drafts_by_opportunity,
    get_opportunity_by_id,
    get_pipeline_entry,
)

opportunities_bp = Blueprint("opportunities", __name__)

PAGE_SIZE = 50


@opportunities_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        config = current_app.config["GRANT_CONFIG"]
        opps = get_all_opportunities(conn)
        opps = enrich_opportunities_with_priority(opps, config.org)

        # Apply filters from query params
        min_score = request.args.get("min_score", type=int)
        urgency = request.args.get("urgency")
        tier = request.args.get("tier", type=int)
        status = request.args.get("status")

        if min_score is not None:
            opps = [o for o in opps if (o.get("score") or 0) >= min_score]
        if urgency:
            opps = [o for o in opps if o.get("urgency") == urgency]
        if tier:
            opps = [o for o in opps if o.get("keyword_tier") == tier]
        if status:
            opps = [o for o in opps if o.get("status") == status]

        # Paginate filtered results
        total = len(opps)
        page = max(1, request.args.get("page", 1, type=int))
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        page = min(page, total_pages)
        offset = (page - 1) * PAGE_SIZE
        opps = opps[offset : offset + PAGE_SIZE]

        return render_template(
            "opportunities.html",
            opportunities=opps,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    finally:
        conn.close()


@opportunities_bp.route("/<int:opp_id>")
@login_required
def detail(opp_id):
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        config = current_app.config["GRANT_CONFIG"]
        opp = get_opportunity_by_id(conn, opp_id)
        if not opp:
            return render_template("opportunity_detail.html", opp=None), 404

        priority = calculate_priority_score(opp, config.org)
        checks = analyze_requirements(opp, config.org)
        match_summary = summarize_matches(checks)
        drafts = get_drafts_by_opportunity(conn, opp_id)

        # Check pipeline status
        pipeline_entry = None
        try:
            entries = conn.execute(
                "SELECT * FROM pipeline_entries WHERE opportunity_id = ?", (opp_id,)
            ).fetchone()
            if entries:
                pipeline_entry = dict(entries)
        except Exception:
            pass

        return render_template(
            "opportunity_detail.html",
            opp=opp,
            priority=priority,
            checks=checks,
            match_summary=match_summary,
            drafts=drafts,
            pipeline_entry=pipeline_entry,
        )
    finally:
        conn.close()
