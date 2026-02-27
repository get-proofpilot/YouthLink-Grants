"""Dashboard home / overview page."""

from flask import Blueprint, current_app, render_template
from flask_login import login_required

from grant_intel.dashboard.priority import enrich_opportunities_with_priority
from grant_intel.db import (
    get_connection,
    get_dashboard_stats,
    get_score_distribution,
    get_top_opportunities,
    get_upcoming_deadlines,
    get_pipeline_by_stage,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def home():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        config = current_app.config["GRANT_CONFIG"]
        stats = get_dashboard_stats(conn)
        top_opps = get_top_opportunities(conn, limit=10)
        top_opps = enrich_opportunities_with_priority(top_opps, config.org)
        distribution = get_score_distribution(conn)
        upcoming = get_upcoming_deadlines(conn, days=90)
        pipeline = get_pipeline_by_stage(conn)

        pipeline_counts = {k: len(v) for k, v in pipeline.items()}

        return render_template(
            "home.html",
            stats=stats,
            top_opportunities=top_opps,
            distribution=distribution,
            upcoming=upcoming,
            pipeline_counts=pipeline_counts,
        )
    finally:
        conn.close()
