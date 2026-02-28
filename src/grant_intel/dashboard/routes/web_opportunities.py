"""Web opportunities list page — grants discovered via Brave Search."""

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from grant_intel.db import get_all_web_opportunities, get_connection

web_opportunities_bp = Blueprint("web_opportunities", __name__)


@web_opportunities_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        opps = get_all_web_opportunities(conn)

        # Optional filters
        funder = request.args.get("funder", "").strip()
        if funder:
            opps = [o for o in opps if funder.lower() in (o.get("funder_name") or "").lower()]

        return render_template("web_opportunities.html", opportunities=opps)
    finally:
        conn.close()
