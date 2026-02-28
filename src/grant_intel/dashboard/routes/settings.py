"""Settings page — org profile viewer with editable keywords."""

import json

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from grant_intel.db import get_connection, get_setting, set_setting

settings_bp = Blueprint("settings", __name__)

# Settings-table keys for each keyword tier
_KEYWORD_KEYS = {
    "tier1": "keywords_tier1",
    "tier2": "keywords_tier2",
    "tier3": "keywords_tier3",
}


def load_keyword_overrides(db_path: str) -> dict[str, list[str]] | None:
    """Return saved keyword overrides from the settings table, or None if none saved."""
    conn = get_connection(db_path)
    try:
        overrides: dict[str, list[str]] = {}
        found_any = False
        for tier, key in _KEYWORD_KEYS.items():
            val = get_setting(conn, key)
            if val is not None:
                found_any = True
                overrides[tier] = json.loads(val)
        return overrides if found_any else None
    finally:
        conn.close()


@settings_bp.route("/", methods=["GET"])
@login_required
def index():
    config = current_app.config["GRANT_CONFIG"]
    return render_template(
        "settings.html",
        org=config.org,
        keywords=config.keywords,
        similar_orgs=config.similar_orgs,
    )


@settings_bp.route("/keywords", methods=["POST"])
@login_required
def update_keywords():
    db_path = current_app.config["DB_PATH"]
    config = current_app.config["GRANT_CONFIG"]

    new_keywords: dict[str, list[str]] = {}
    for tier in ("tier1", "tier2", "tier3"):
        raw = request.form.get(f"{tier}_keywords", "")
        terms = [line.strip() for line in raw.splitlines() if line.strip()]
        new_keywords[tier] = terms

    conn = get_connection(db_path)
    try:
        for tier, key in _KEYWORD_KEYS.items():
            set_setting(conn, key, json.dumps(new_keywords[tier]))
    finally:
        conn.close()

    # Update in-memory config so changes take effect immediately (no restart needed)
    config.keywords = new_keywords

    flash("Keywords saved successfully.", "success")
    return redirect(url_for("settings.index"))
