"""Settings page — read-only org profile viewer."""

from flask import Blueprint, current_app, render_template
from flask_login import login_required

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/")
@login_required
def index():
    config = current_app.config["GRANT_CONFIG"]
    return render_template(
        "settings.html",
        org=config.org,
        keywords=config.keywords,
        similar_orgs=config.similar_orgs,
    )
