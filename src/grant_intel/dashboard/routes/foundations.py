"""Foundations list and detail pages."""

import math

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from grant_intel.db import (
    count_foundations,
    get_connection,
    get_drafts_by_foundation,
    get_foundation_by_id,
    get_foundation_grants_list,
    get_foundations_paginated,
    get_pipeline_entry_by_target,
)

foundations_bp = Blueprint("foundations", __name__)

PAGE_SIZE = 50


@foundations_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        page = max(1, request.args.get("page", 1, type=int))
        total = count_foundations(conn)
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        page = min(page, total_pages)
        offset = (page - 1) * PAGE_SIZE

        foundations = get_foundations_paginated(conn, limit=PAGE_SIZE, offset=offset)
        return render_template(
            "foundations.html",
            foundations=foundations,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    finally:
        conn.close()


@foundations_bp.route("/<int:foundation_id>")
@login_required
def detail(foundation_id):
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        foundation = get_foundation_by_id(conn, foundation_id)
        if not foundation:
            return render_template("foundation_detail.html", foundation=None), 404

        grants = get_foundation_grants_list(conn, foundation_id)
        drafts = get_drafts_by_foundation(conn, foundation_id)
        pipeline_entry = get_pipeline_entry_by_target(conn, foundation_id=foundation_id)

        return render_template(
            "foundation_detail.html",
            foundation=foundation,
            grants=grants,
            drafts=drafts,
            pipeline_entry=pipeline_entry,
        )
    finally:
        conn.close()
