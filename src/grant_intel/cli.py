"""CLI entry point for grant-intel tool."""

import logging
import sys

import click

from grant_intel.config import load_config
from grant_intel.db import (
    get_all_foundations,
    get_all_opportunities,
    get_connection,
    get_pipeline_stats,
    get_top_foundations,
    get_top_opportunities,
    get_unscored_foundations,
    get_unscored_opportunities,
    init_db,
    insert_draft,
    insert_foundation_grant,
    insert_score,
    upsert_foundation,
    upsert_opportunity,
    upsert_similar_org,
)

logger = logging.getLogger("grant_intel")


@click.group()
@click.option("--config", "config_path", default="config/org_profile.yaml", help="Path to org profile YAML")
@click.option("--db", "db_path", default="data/grants.db", help="Path to SQLite database")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config_path, db_path, verbose):
    """YouthLink Grant Intelligence Tool.

    Discover grants, research foundations, score opportunities,
    and deliver weekly reports for Youth Link Ministries.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(profile_path=config_path, db_path=db_path)
    ctx.obj["db_path"] = db_path


@cli.command("db-init")
@click.pass_context
def db_init(ctx):
    """Initialize or reset the database."""
    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)
    conn.close()
    click.echo("Database initialized.")


@cli.command()
@click.option("--tier", type=click.Choice(["1", "2", "3", "all"]), default="all", help="Keyword tier to search")
@click.pass_context
def search(ctx, tier):
    """Search Grants.gov for grant opportunities."""
    from grant_intel.sources.grants_gov import discover_grants

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    if tier == "all":
        keywords = config.keywords
    else:
        tier_key = f"tier{tier}"
        keywords = {tier_key: config.keywords.get(tier_key, [])}

    click.echo(f"Searching Grants.gov with {sum(len(v) for v in keywords.values())} keywords...")

    results = discover_grants(keywords)

    new_count = 0
    for opp in results:
        if upsert_opportunity(conn, opp):
            new_count += 1

    conn.close()
    click.echo(f"Found {len(results)} opportunities ({new_count} new, {len(results) - new_count} existing).")


@cli.command()
@click.pass_context
def research(ctx):
    """Research foundations via ProPublica 990 filings."""
    from grant_intel.sources.propublica import research_similar_orgs, search_foundations_by_keyword

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    click.echo(f"Researching {len(config.similar_orgs)} similar organizations...")

    # Research similar orgs
    org_infos, filings = research_similar_orgs(config.similar_orgs)

    new_orgs = 0
    for org_info in org_infos:
        if upsert_similar_org(conn, org_info):
            new_orgs += 1

    click.echo(f"Found {len(org_infos)} similar orgs ({new_orgs} new), {len(filings)} filings.")

    # Search for foundations by keyword
    from grant_intel.config import FOUNDATION_SEARCH_KEYWORDS
    foundation_keywords = FOUNDATION_SEARCH_KEYWORDS
    click.echo(f"Searching for foundation prospects ({len(foundation_keywords)} keywords)...")
    foundations = search_foundations_by_keyword(foundation_keywords, states=["AZ", ""])

    new_foundations = 0
    for f in foundations:
        if upsert_foundation(conn, f):
            new_foundations += 1

    conn.close()
    click.echo(f"Found {len(foundations)} foundation prospects ({new_foundations} new).")


@cli.command()
@click.option("--batch-size", default=5, help="Items per scoring batch")
@click.option("--rules-only", is_flag=True, help="Only run rule-based scoring (no AI)")
@click.option("--ai-threshold", default=6, type=int, help="Minimum rule score to send to AI (default 6)")
@click.pass_context
def score(ctx, batch_size, rules_only, ai_threshold):
    """Score opportunities and foundations using rule engine + Claude AI funnel."""
    from grant_intel.scoring.matcher import score_foundations, score_with_funnel

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    api_key = config.anthropic_api_key if not rules_only else None

    if not rules_only and not config.anthropic_api_key:
        click.echo("No ANTHROPIC_API_KEY set — running rules-only scoring.", err=True)
        rules_only = True

    # Score opportunities via funnel
    click.echo("Scoring opportunities (rule engine → AI funnel)...")
    summary = score_with_funnel(
        conn=conn,
        org=config.org,
        api_key=api_key,
        ai_threshold=ai_threshold,
        rules_only=rules_only,
        batch_size=batch_size,
    )
    click.echo(f"  Rule-scored: {summary['rule_scored']} opportunities")
    if rules_only:
        click.echo(f"  AI skipped:  {summary['ai_skipped']} candidates (rules-only mode)")
    else:
        click.echo(f"  AI-scored:   {summary['ai_scored']} top candidates (threshold >= {ai_threshold})")

    # Score foundations (AI only, no rule engine for foundations)
    if not rules_only and config.anthropic_api_key:
        unscored_foundations = get_unscored_foundations(conn)
        if unscored_foundations:
            click.echo(f"Scoring {len(unscored_foundations)} foundations with AI...")
            foundation_scores = score_foundations(
                config.anthropic_api_key,
                config.org,
                unscored_foundations,
                batch_size=batch_size,
            )
            for s in foundation_scores:
                insert_score(conn, s)
            click.echo(f"Scored {len(foundation_scores)} foundations.")
        else:
            click.echo("No unscored foundations.")

    conn.close()


@cli.command()
@click.option("--output-dir", default="output", help="Output directory for CSV files")
@click.pass_context
def report(ctx, output_dir):
    """Generate CSV reports of scored opportunities and foundations."""
    from grant_intel.delivery.csv_export import export_foundations_csv, export_opportunities_csv

    conn = get_connection(ctx.obj["db_path"])

    opportunities = get_all_opportunities(conn)
    foundations = get_all_foundations(conn)

    if opportunities:
        path = export_opportunities_csv(opportunities, output_dir)
        click.echo(f"Opportunities report: {path}")
    else:
        click.echo("No opportunities to report.")

    if foundations:
        path = export_foundations_csv(foundations, output_dir)
        click.echo(f"Foundations report: {path}")
    else:
        click.echo("No foundations to report.")

    conn.close()


@cli.command()
@click.option("--dry-run", is_flag=True, help="Render email to file without sending")
@click.pass_context
def digest(ctx, dry_run):
    """Send weekly email digest."""
    from grant_intel.delivery.email_digest import dry_run_digest, render_digest, send_digest

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])

    opportunities = get_top_opportunities(conn, limit=15)
    foundations = get_top_foundations(conn, limit=10)
    stats = get_pipeline_stats(conn)

    if dry_run:
        path = dry_run_digest(opportunities, foundations, stats)
        click.echo(f"Digest rendered to: {path}")
    else:
        html = render_digest(opportunities, foundations, stats)
        success = send_digest(
            html,
            config.smtp_host,
            config.smtp_port,
            config.smtp_user,
            config.smtp_pass,
            config.email_to,
        )
        if success:
            click.echo("Digest email sent.")
        else:
            click.echo("Failed to send digest. Check SMTP configuration.", err=True)

    conn.close()


@cli.command()
@click.option("--force", is_flag=True, help="Bypass the 6-day cooldown guard")
@click.option("--dry-run", is_flag=True, help="Show what would be scored without calling AI")
@click.option("--rescore", is_flag=True, help="Re-score ALL opportunities with latest rule engine")
@click.option("--ai-threshold", default=6, type=int, help="Minimum rule score to send to AI (default 6)")
@click.option("--batch-size", default=5, help="Items per AI scoring batch")
@click.pass_context
def weekly(ctx, force, dry_run, rescore, ai_threshold, batch_size):
    """Run the weekly AI scoring cycle.

    Refreshes data, rule-scores new opportunities, then AI-verifies all
    candidates with rule_score >= threshold. Includes a 6-day cooldown to
    prevent accidental double-runs.

    \b
    Trigger via:
      - Railway cron: railway run grant-intel weekly
      - System cron:  0 6 * * 1 cd /path && grant-intel weekly
      - Manual:       grant-intel weekly
    """
    from grant_intel.scoring.weekly import run_weekly_scoring

    config = ctx.obj["config"]
    db_path = ctx.obj["db_path"]

    click.echo("=== Weekly Scoring Agent ===\n")

    if rescore:
        from grant_intel.db import clear_rule_scores, get_connection as _gc
        click.echo("Clearing all rule scores for full rescore...")
        _conn = _gc(db_path)
        clear_rule_scores(_conn)
        _conn.close()

    summary = run_weekly_scoring(
        db_path=db_path,
        config=config,
        force=force,
        dry_run=dry_run,
        ai_threshold=ai_threshold,
        batch_size=batch_size,
    )

    if summary["skipped"]:
        click.echo(f"Skipped: {summary['skip_reason']}")
        click.echo("Use --force to override the cooldown.")
        return

    prefix = "[DRY RUN] " if dry_run else ""
    click.echo(f"{prefix}New opportunities:    {summary['new_opps']}")
    click.echo(f"{prefix}New foundations:       {summary['new_foundations']}")
    click.echo(f"{prefix}Rule-scored:          {summary['rule_scored']}")
    click.echo(f"{prefix}AI candidates (>= {ai_threshold}): {summary['ai_candidates']}")
    click.echo(f"{prefix}AI-scored opps:       {summary['ai_scored']}")
    click.echo(f"{prefix}AI-scored foundations: {summary['foundations_scored']}")

    if not dry_run:
        click.echo("\n=== Weekly scoring complete ===")
    else:
        click.echo("\n=== Dry run complete — no AI calls made ===")


@cli.command()
@click.pass_context
def run(ctx):
    """Run full pipeline: search, research, score, report, digest."""
    click.echo("=== YouthLink Grant Intelligence Pipeline ===\n")

    click.echo("Step 1/5: Searching Grants.gov...")
    ctx.invoke(search, tier="all")
    click.echo()

    click.echo("Step 2/5: Researching foundations...")
    ctx.invoke(research)
    click.echo()

    click.echo("Step 3/5: Running weekly scoring agent...")
    ctx.invoke(weekly, force=True)
    click.echo()

    click.echo("Step 4/5: Generating reports...")
    ctx.invoke(report)
    click.echo()

    click.echo("Step 5/5: Sending digest...")
    ctx.invoke(digest, dry_run=True)
    click.echo()

    click.echo("=== Pipeline complete ===")


@cli.command()
@click.argument("opportunity_id", type=int)
@click.option("--nofa-file", type=click.Path(exists=True), help="Path to file containing NOFA/RFP text")
@click.option("--nofa-url", help="URL to fetch NOFA/RFP from")
@click.option("--output-dir", default="output/drafts", help="Output directory for drafts")
@click.pass_context
def draft(ctx, opportunity_id, nofa_file, nofa_url, output_dir):
    """Generate a federal grant narrative draft for an opportunity."""
    from grant_intel.writer.agent import build_draft_record, draft_federal_narrative
    from grant_intel.writer.extractor import (
        extract_requirements_from_text,
        extract_requirements_from_url,
    )

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])

    if not config.anthropic_api_key:
        click.echo("Error: ANTHROPIC_API_KEY not set. Add it to .env file.", err=True)
        sys.exit(1)

    # Look up the opportunity
    row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
    if not row:
        click.echo(f"Error: Opportunity #{opportunity_id} not found in database.", err=True)
        conn.close()
        sys.exit(1)

    opp = dict(row)
    click.echo(f"Opportunity: {opp['title']}")
    click.echo(f"Agency: {opp.get('agency', 'N/A')}")

    # Extract requirements
    if nofa_file:
        with open(nofa_file) as f:
            nofa_text = f.read()
        click.echo("Extracting requirements from file...")
        requirements = extract_requirements_from_text(nofa_text, config.anthropic_api_key)
    elif nofa_url:
        click.echo(f"Fetching and extracting requirements from URL...")
        requirements = extract_requirements_from_url(nofa_url, config.anthropic_api_key)
    else:
        # Use what we have from the opportunity record
        click.echo("No NOFA provided — using opportunity description for context.")
        requirements = {
            "funder_name": opp.get("agency", ""),
            "program_name": opp.get("title", ""),
            "deadline": opp.get("deadline", ""),
            "award_range": {
                "min": opp.get("award_floor", 0) or 0,
                "max": opp.get("award_ceiling", 0) or 0,
            },
            "eligible_applicants": opp.get("eligibility", ""),
            "required_sections": [],
            "page_limits": {},
            "evaluation_criteria": [],
            "focus_areas": [],
            "restrictions": [],
            "questions_to_answer": [],
            "raw_text": opp.get("description", ""),
        }

    click.echo(f"Funder: {requirements.get('funder_name', 'Unknown')}")
    click.echo(f"Writing narrative draft ({len(requirements.get('required_sections', []) or [])} required sections)...")

    filepath, sections = draft_federal_narrative(
        api_key=config.anthropic_api_key,
        org=config.org,
        requirements=requirements,
        output_dir=output_dir,
    )

    # Store in database
    record = build_draft_record(
        opportunity_id=opportunity_id,
        foundation_id=None,
        draft_type="federal_narrative",
        funder_name=requirements.get("funder_name", ""),
        project_name=requirements.get("program_name", ""),
        requirements=requirements,
        sections=sections,
        full_draft_path=filepath,
    )
    draft_id = insert_draft(conn, record)
    conn.close()

    click.echo(f"\nDraft saved to: {filepath}")
    click.echo(f"Draft ID: {draft_id}")
    click.echo(f"Sections written: {', '.join(sections.keys())}")
    click.echo("\nReview items marked with [BRACKETS] and fill in org-specific data.")


@cli.command()
@click.argument("foundation_id", type=int)
@click.option("--guidelines-file", type=click.Path(exists=True), help="Path to funder guidelines text")
@click.option("--guidelines-url", help="URL to fetch funder guidelines from")
@click.option("--amount", type=int, required=True, help="Dollar amount to request")
@click.option("--project", required=True, help="Project name")
@click.option("--output-dir", default="output/drafts", help="Output directory for drafts")
@click.pass_context
def loi(ctx, foundation_id, guidelines_file, guidelines_url, amount, project, output_dir):
    """Generate a foundation Letter of Inquiry."""
    from grant_intel.writer.agent import build_draft_record, draft_foundation_loi
    from grant_intel.writer.extractor import (
        extract_requirements_from_text,
        extract_requirements_from_url,
    )

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])

    if not config.anthropic_api_key:
        click.echo("Error: ANTHROPIC_API_KEY not set. Add it to .env file.", err=True)
        sys.exit(1)

    # Look up the foundation
    row = conn.execute("SELECT * FROM foundations WHERE id = ?", (foundation_id,)).fetchone()
    if not row:
        click.echo(f"Error: Foundation #{foundation_id} not found in database.", err=True)
        conn.close()
        sys.exit(1)

    foundation = dict(row)
    funder_name = foundation["name"]
    click.echo(f"Foundation: {funder_name}")
    click.echo(f"Request amount: ${amount:,}")
    click.echo(f"Project: {project}")

    # Extract guidelines if provided
    if guidelines_file:
        with open(guidelines_file) as f:
            guidelines_text = f.read()
        click.echo("Extracting funder guidelines...")
        requirements = extract_requirements_from_text(guidelines_text, config.anthropic_api_key)
    elif guidelines_url:
        click.echo("Fetching funder guidelines from URL...")
        requirements = extract_requirements_from_url(guidelines_url, config.anthropic_api_key)
    else:
        requirements = {
            "funder_name": funder_name,
            "program_name": project,
            "focus_areas": [],
            "restrictions": [],
            "eligible_applicants": "",
            "raw_text": "",
        }

    click.echo("Writing Letter of Inquiry...")

    filepath, loi_text = draft_foundation_loi(
        api_key=config.anthropic_api_key,
        org=config.org,
        requirements=requirements,
        funder_name=funder_name,
        amount=amount,
        project_name=project,
        output_dir=output_dir,
    )

    # Store in database
    record = build_draft_record(
        opportunity_id=None,
        foundation_id=foundation_id,
        draft_type="foundation_loi",
        funder_name=funder_name,
        project_name=project,
        requirements=requirements,
        sections={"Letter of Inquiry": loi_text},
        full_draft_path=filepath,
    )
    draft_id = insert_draft(conn, record)
    conn.close()

    click.echo(f"\nLOI saved to: {filepath}")
    click.echo(f"Draft ID: {draft_id}")
    click.echo("\nReview items marked with [BRACKETS] and fill in org-specific data.")


@cli.command("seed-foundations")
@click.pass_context
def seed_foundations(ctx):
    """Seed curated, pre-vetted foundations into the database."""
    from grant_intel.sources.curated import seed_curated_foundations

    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    click.echo("Seeding curated foundations...")
    new_count = seed_curated_foundations(conn)
    conn.close()
    click.echo(f"Seeded {new_count} new foundations.")


@cli.command("enrich")
@click.pass_context
def enrich(ctx):
    """Enrich foundations with financial data from GivingTuesday 990 API."""
    from grant_intel.sources.givingtuesday import enrich_all_foundations

    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    click.echo("Enriching foundations via GivingTuesday 990 API...")
    stats = enrich_all_foundations(conn)
    conn.close()
    click.echo(f"Enriched: {stats['enriched']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")


@cli.command("brave-search")
@click.option("--query", "custom_query", default=None, help="Run a single custom search query")
@click.pass_context
def brave_search(ctx, custom_query):
    """Discover grant opportunities via Brave Search API."""
    from grant_intel.config import BRAVE_SEARCH_QUERIES
    from grant_intel.sources.brave_search import discover_web_opportunities

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    if not config.brave_api_key:
        click.echo("Error: BRAVE_API_KEY not set. Add it to .env file.", err=True)
        conn.close()
        return

    queries = [custom_query] if custom_query else BRAVE_SEARCH_QUERIES
    click.echo(f"Running {len(queries)} Brave Search queries...")
    stats = discover_web_opportunities(queries, conn, config.brave_api_key)
    conn.close()
    click.echo(
        f"Queries: {stats['queries_run']}, Results: {stats['results_total']}, "
        f"Grant-like: {stats['grant_results']}, New saved: {stats['saved_new']}"
    )


@cli.command("import-grants")
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--no-filter", is_flag=True, help="Import all grants without relevance filtering")
@click.pass_context
def import_grants(ctx, csv_path, no_filter):
    """Import historical grant data from NODC CSV file."""
    from grant_intel.sources.nodc_import import import_nodc_grants

    conn = get_connection(ctx.obj["db_path"])
    init_db(conn)

    click.echo(f"Importing grants from {csv_path}...")
    stats = import_nodc_grants(csv_path, conn, filter_relevant=not no_filter)
    conn.close()
    click.echo(
        f"Total rows: {stats['total_rows']}, Imported: {stats['imported']}, "
        f"Filtered: {stats['filtered_out']}, Foundations discovered: {stats['foundations_discovered']}"
    )
    if stats.get("errors"):
        click.echo(f"Errors: {stats['errors']}", err=True)


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=5000, type=int, help="Port to listen on")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def dashboard(ctx, host, port, debug):
    """Launch the admin dashboard web server."""
    from grant_intel.dashboard.app import create_app

    app = create_app(
        config_path=ctx.parent.params.get("config_path", "config/org_profile.yaml"),
        db_path=ctx.obj["db_path"],
    )
    click.echo(f"Starting dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


@cli.command()
@click.pass_context
def status(ctx):
    """Show pipeline statistics."""
    conn = get_connection(ctx.obj["db_path"])
    stats = get_pipeline_stats(conn)

    click.echo("Pipeline Status:")
    click.echo(f"  Opportunities: {stats['total_opportunities']} total, {stats['scored_opportunities']} scored")
    click.echo(f"  Foundations:   {stats['total_foundations']} total, {stats['scored_foundations']} scored")
    click.echo(f"  Drafts:       {stats['total_drafts']} total")

    conn.close()


if __name__ == "__main__":
    cli()
