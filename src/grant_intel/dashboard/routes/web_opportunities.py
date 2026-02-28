"""Web opportunities list page — grants discovered via Brave Search."""

import math

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from grant_intel.db import count_web_opportunities, get_connection, get_web_opportunities_paginated

web_opportunities_bp = Blueprint("web_opportunities", __name__)

PAGE_SIZE = 50


@web_opportunities_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        # Funder filter is applied in Python since it's a text substring match
        funder = request.args.get("funder", "").strip()

        if funder:
            # Need all rows to filter; use paginated after filter
            from grant_intel.db import get_all_web_opportunities
            opps = get_all_web_opportunities(conn)
            opps = [o for o in opps if funder.lower() in (o.get("funder_name") or "").lower()]
            total = len(opps)
            page = max(1, request.args.get("page", 1, type=int))
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            page = min(page, total_pages)
            opps = opps[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        else:
            total = count_web_opportunities(conn)
            page = max(1, request.args.get("page", 1, type=int))
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            page = min(page, total_pages)
            opps = get_web_opportunities_paginated(conn, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)

        return render_template(
            "web_opportunities.html",
            opportunities=opps,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    finally:
        conn.close()
