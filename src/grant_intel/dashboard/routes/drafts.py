"""Drafts list and detail pages."""

import json

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from grant_intel.db import get_all_drafts, get_connection, get_draft, update_draft_status

drafts_bp = Blueprint("drafts", __name__)


@drafts_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        drafts = get_all_drafts(conn)

        # Optional status filter
        status_filter = request.args.get("status")
        if status_filter:
            drafts = [d for d in drafts if d.get("status") == status_filter]

        return render_template("drafts.html", drafts=drafts)
    finally:
        conn.close()


@drafts_bp.route("/<int:draft_id>")
@login_required
def detail(draft_id):
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            return render_template("draft_detail.html", draft=None), 404

        # Parse sections JSON for tabbed view
        sections = {}
        if draft.get("sections_json"):
            try:
                sections = json.loads(draft["sections_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        return render_template("draft_detail.html", draft=draft, sections=sections)
    finally:
        conn.close()


@drafts_bp.route("/<int:draft_id>/status", methods=["POST"])
@login_required
def change_status(draft_id):
    new_status = request.form.get("status", "")
    if new_status not in ("draft", "review", "submitted"):
        flash("Invalid status.", "danger")
        return redirect(url_for("drafts.detail", draft_id=draft_id))

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        update_draft_status(conn, draft_id, new_status)
        flash(f"Draft status updated to '{new_status}'.", "success")
    finally:
        conn.close()

    return redirect(url_for("drafts.detail", draft_id=draft_id))
