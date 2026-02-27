"""Flask application factory for the Grant Intelligence dashboard."""

import os
from pathlib import Path

from flask import Flask

from grant_intel.config import load_config
from grant_intel.db import get_connection, init_db

_BASE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BASE_DIR.parent.parent.parent
_TEMPLATES_DIR = _PROJECT_ROOT / "templates" / "dashboard"
_STATIC_DIR = _PROJECT_ROOT / "static"


def create_app(config_path: str = "config/org_profile.yaml", db_path: str = "data/grants.db"):
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATES_DIR),
        static_folder=str(_STATIC_DIR),
    )

    app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
    app.config["DB_PATH"] = db_path
    app.config["CONFIG_PATH"] = config_path

    # Load org config
    grant_config = load_config(profile_path=config_path, db_path=db_path)
    app.config["GRANT_CONFIG"] = grant_config

    # Ensure database is initialized
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    # Setup Flask-Login
    from grant_intel.dashboard.auth import auth_bp, init_login_manager
    init_login_manager(app)

    # Register blueprints
    from grant_intel.dashboard.routes.main import main_bp
    from grant_intel.dashboard.routes.opportunities import opportunities_bp
    from grant_intel.dashboard.routes.foundations import foundations_bp
    from grant_intel.dashboard.routes.drafts import drafts_bp
    from grant_intel.dashboard.routes.pipeline import pipeline_bp
    from grant_intel.dashboard.routes.actions import actions_bp
    from grant_intel.dashboard.routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(opportunities_bp, url_prefix="/opportunities")
    app.register_blueprint(foundations_bp, url_prefix="/foundations")
    app.register_blueprint(drafts_bp, url_prefix="/drafts")
    app.register_blueprint(pipeline_bp, url_prefix="/pipeline")
    app.register_blueprint(actions_bp, url_prefix="/actions")
    app.register_blueprint(settings_bp, url_prefix="/settings")

    # Register Jinja2 filters
    from grant_intel.dashboard.filters import register_filters
    register_filters(app)

    # Context processor for org name in nav
    @app.context_processor
    def inject_globals():
        return {"org_name": grant_config.org.name}

    return app
