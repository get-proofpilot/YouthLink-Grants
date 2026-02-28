"""Flask application factory for the Grant Intelligence dashboard."""

import logging
import os
import threading
from pathlib import Path

from flask import Flask

from grant_intel.config import load_config
from grant_intel.db import get_connection, init_db

logger = logging.getLogger(__name__)

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

    # Populate data on first boot if database is empty
    opp_count = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    conn.close()

    if opp_count == 0 and os.getenv("AUTO_POPULATE", "true").lower() == "true":
        logger.info("Database empty — starting background data pipeline")

        def _populate():
            try:
                _run_data_pipeline(grant_config, db_path)
            except Exception:
                logger.exception("Background data pipeline failed")

        threading.Thread(target=_populate, daemon=True).start()

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
    from grant_intel.dashboard.routes.web_opportunities import web_opportunities_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(opportunities_bp, url_prefix="/opportunities")
    app.register_blueprint(foundations_bp, url_prefix="/foundations")
    app.register_blueprint(web_opportunities_bp, url_prefix="/web-opportunities")
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


def _run_data_pipeline(config, db_path: str):
    """Run the grant discovery + foundation research pipeline."""
    from grant_intel.db import upsert_foundation, upsert_opportunity, upsert_similar_org
    from grant_intel.sources.grants_gov import discover_grants
    from grant_intel.sources.propublica import research_similar_orgs, search_foundations_by_keyword

    conn = get_connection(db_path)
    init_db(conn)

    # Step 1: Search Grants.gov
    logger.info("Pipeline: searching Grants.gov with %d keywords...",
                sum(len(v) for v in config.keywords.values()))
    try:
        results = discover_grants(config.keywords)
        new_count = 0
        for opp in results:
            if upsert_opportunity(conn, opp):
                new_count += 1
        logger.info("Pipeline: found %d opportunities (%d new)", len(results), new_count)
    except Exception:
        logger.exception("Pipeline: Grants.gov search failed")

    # Step 2: Research similar orgs
    logger.info("Pipeline: researching %d similar organizations...", len(config.similar_orgs))
    try:
        org_infos, filings = research_similar_orgs(config.similar_orgs)
        for org_info in org_infos:
            upsert_similar_org(conn, org_info)
        logger.info("Pipeline: found %d orgs, %d filings", len(org_infos), len(filings))
    except Exception:
        logger.exception("Pipeline: similar org research failed")

    # Step 3: Search for foundations
    logger.info("Pipeline: searching for foundation prospects...")
    try:
        from grant_intel.config import FOUNDATION_SEARCH_KEYWORDS
        foundation_keywords = FOUNDATION_SEARCH_KEYWORDS
        foundations = search_foundations_by_keyword(foundation_keywords, states=["AZ", ""])
        new_foundations = 0
        for f in foundations:
            if upsert_foundation(conn, f):
                new_foundations += 1
        logger.info("Pipeline: found %d foundations (%d new)", len(foundations), new_foundations)
    except Exception:
        logger.exception("Pipeline: foundation search failed")

    # Step 4: Seed curated foundations
    logger.info("Pipeline: seeding curated foundations...")
    try:
        from grant_intel.sources.curated import seed_curated_foundations
        new_curated = seed_curated_foundations(conn)
        logger.info("Pipeline: seeded %d new curated foundations", new_curated)
    except Exception:
        logger.exception("Pipeline: curated foundation seeding failed")

    # Step 5: Enrich foundations via GivingTuesday 990 API
    logger.info("Pipeline: enriching foundations via GivingTuesday 990 API...")
    try:
        from grant_intel.sources.givingtuesday import enrich_all_foundations
        enrich_stats = enrich_all_foundations(conn)
        logger.info("Pipeline: enriched %d foundations", enrich_stats.get("enriched", 0))
    except Exception:
        logger.exception("Pipeline: foundation enrichment failed")

    # Step 6: Rule-score all opportunities (instant, free — AI runs on weekly schedule only)
    logger.info("Pipeline: running rule-based scoring (rules only, no AI)...")
    try:
        from grant_intel.scoring.matcher import score_with_funnel

        conn = get_connection(db_path)
        summary = score_with_funnel(
            conn=conn,
            org=config.org,
            api_key=None,
            ai_threshold=6,
            rules_only=True,
        )
        logger.info(
            "Pipeline: rule-scored %d opportunities (AI deferred to weekly schedule)",
            summary["rule_scored"],
        )
    except Exception:
        logger.exception("Pipeline: scoring failed")

    conn.close()
    logger.info("Pipeline: data population complete")
