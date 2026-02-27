"""Foundations list and detail pages."""

from flask import Blueprint, current_app, render_template
from flask_login import login_required

from grant_intel.db import (
    get_all_foundations,
    get_connection,
    get_drafts_by_foundation,
    get_foundation_by_id,
    get_foundation_grants_list,
    get_pipeline_entry_by_target,
)

foundations_bp = Blueprint("foundations", __name__)


@foundations_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        foundations = get_all_foundations(conn)
        return render_template("foundations.html", foundations=foundations)
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
