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
    foundation_keywords = [
        "youth ministry foundation",
        "christian leadership grant",
        "pastoral development",
        "church leadership",
    ]
    click.echo("Searching for foundation prospects...")
    foundations = search_foundations_by_keyword(foundation_keywords, states=["AZ", ""])

    new_foundations = 0
    for f in foundations:
        if upsert_foundation(conn, f):
            new_foundations += 1

    conn.close()
    click.echo(f"Found {len(foundations)} foundation prospects ({new_foundations} new).")


@cli.command()
@click.option("--batch-size", default=5, help="Items per scoring batch")
@click.pass_context
def score(ctx):
    """Score opportunities and foundations using Claude AI."""
    from grant_intel.scoring.matcher import score_foundations, score_opportunities

    config = ctx.obj["config"]
    conn = get_connection(ctx.obj["db_path"])

    if not config.anthropic_api_key:
        click.echo("Error: ANTHROPIC_API_KEY not set. Add it to .env file.", err=True)
        sys.exit(1)

    # Score opportunities
    unscored_opps = get_unscored_opportunities(conn)
    if unscored_opps:
        click.echo(f"Scoring {len(unscored_opps)} opportunities...")
        opp_scores = score_opportunities(
            config.anthropic_api_key,
            config.org,
            unscored_opps,
        )
        for s in opp_scores:
            insert_score(conn, s)
        click.echo(f"Scored {len(opp_scores)} opportunities.")
    else:
        click.echo("No unscored opportunities.")

    # Score foundations
    unscored_foundations = get_unscored_foundations(conn)
    if unscored_foundations:
        click.echo(f"Scoring {len(unscored_foundations)} foundations...")
        foundation_scores = score_foundations(
            config.anthropic_api_key,
            config.org,
            unscored_foundations,
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

    click.echo("Step 3/5: Scoring with Claude AI...")
    ctx.invoke(score)
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
