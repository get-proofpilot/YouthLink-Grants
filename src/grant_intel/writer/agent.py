"""Orchestrator for full federal grant narratives and foundation LOIs."""

import json
import logging
from datetime import date
from pathlib import Path

import anthropic
from jinja2 import Environment, FileSystemLoader

from grant_intel.config import OrgProfile
from grant_intel.writer.prompts import build_loi_prompt, build_system_prompt
from grant_intel.writer.sections import (
    WRITING_MODEL,
    determine_sections,
    generate_section,
    post_process_section,
)

logger = logging.getLogger(__name__)

# Resolve the templates directory relative to the project root
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def draft_federal_narrative(
    api_key: str,
    org: OrgProfile,
    requirements: dict,
    output_dir: str = "output/drafts",
) -> tuple[str, dict]:
    """Generate a complete federal grant narrative.

    Writes sections in order, threading each completed section into the
    context for the next one so the document reads as a coherent whole.

    Returns (filepath, sections_dict).
    """
    sections_to_write = determine_sections(requirements)
    completed_sections: dict[str, str] = {}

    funder = requirements.get("funder_name", "unknown_funder")
    program = requirements.get("program_name", "")

    logger.info(
        "Drafting federal narrative for %s — %d sections",
        funder,
        len(sections_to_write),
    )

    for section_name in sections_to_write:
        logger.info("Writing section: %s", section_name)
        content = generate_section(
            api_key=api_key,
            org=org,
            requirements=requirements,
            section_name=section_name,
            previous_sections=completed_sections,
        )
        completed_sections[section_name] = content
        logger.info("Completed section: %s (%d chars)", section_name, len(content))

    # Render the assembled document
    filepath = _render_draft(
        sections=completed_sections,
        draft_type="Federal Grant Narrative",
        funder_name=funder,
        project_name=program,
        output_dir=output_dir,
    )

    return filepath, completed_sections


def draft_foundation_loi(
    api_key: str,
    org: OrgProfile,
    requirements: dict,
    funder_name: str,
    amount: int,
    project_name: str,
    output_dir: str = "output/drafts",
) -> tuple[str, str]:
    """Generate a foundation Letter of Inquiry.

    Single Claude call — LOIs are short enough for one pass.

    Returns (filepath, loi_text).
    """
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(org)

    # Build funder context from requirements
    funder_context_parts = []
    if requirements.get("focus_areas"):
        funder_context_parts.append(
            "Focus areas: " + ", ".join(requirements["focus_areas"])
        )
    if requirements.get("restrictions"):
        funder_context_parts.append(
            "Restrictions: " + ", ".join(requirements["restrictions"])
        )
    if requirements.get("eligible_applicants"):
        funder_context_parts.append(
            "Eligible applicants: " + requirements["eligible_applicants"]
        )
    funder_context = "\n".join(funder_context_parts)

    user_prompt = build_loi_prompt(
        org=org,
        funder_name=funder_name,
        amount=amount,
        project_name=project_name,
        funder_context=funder_context,
    )

    logger.info("Drafting LOI to %s for $%s", funder_name, f"{amount:,}")

    try:
        response = client.messages.create(
            model=WRITING_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
        loi_text = post_process_section(raw_text)
    except anthropic.APIError:
        logger.exception("Error generating LOI for %s", funder_name)
        loi_text = f"[ERROR: Failed to generate LOI for {funder_name}. Retry or write manually.]"

    # Render via template
    filepath = _render_draft(
        sections={"Letter of Inquiry": loi_text},
        draft_type="Foundation Letter of Inquiry",
        funder_name=funder_name,
        project_name=project_name,
        output_dir=output_dir,
    )

    return filepath, loi_text


def _render_draft(
    sections: dict[str, str],
    draft_type: str,
    funder_name: str,
    project_name: str,
    output_dir: str,
) -> str:
    """Render sections into a Markdown document using the Jinja2 template."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    safe_funder = "".join(
        c if c.isalnum() or c in " -_" else "" for c in funder_name
    ).strip().replace(" ", "_")[:50]

    filename = f"{safe_funder}_{today}.md"
    filepath = str(Path(output_dir) / filename)

    # Try Jinja2 template first, fall back to simple rendering
    try:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template("grant_draft.md.j2")
        rendered = template.render(
            draft_type_label=draft_type,
            funder_name=funder_name,
            project_name=project_name,
            date=today,
            sections=sections,
        )
    except Exception:
        logger.warning("Template not found, using simple rendering")
        rendered = _simple_render(sections, draft_type, funder_name, project_name, today)

    Path(filepath).write_text(rendered, encoding="utf-8")
    logger.info("Draft saved to: %s", filepath)
    return filepath


def _simple_render(
    sections: dict[str, str],
    draft_type: str,
    funder_name: str,
    project_name: str,
    today: str,
) -> str:
    """Fallback renderer if the Jinja2 template is missing."""
    lines = [
        f"# {draft_type}",
        "",
        f"**Funder:** {funder_name}",
        f"**Project:** {project_name}",
        f"**Draft generated:** {today}",
        "",
        "---",
        "",
    ]
    for name, content in sections.items():
        lines.append(f"## {name}")
        lines.append("")
        lines.append(content)
        lines.append("")

    lines.extend([
        "---",
        "",
        "> **Review checklist:** Items marked with [BRACKETS] need org-specific data,",
        "> stories, or verification before submission. Review each section against",
        "> the funder's published requirements.",
    ])
    return "\n".join(lines) + "\n"


def build_draft_record(
    opportunity_id: int | None,
    foundation_id: int | None,
    draft_type: str,
    funder_name: str,
    project_name: str,
    requirements: dict,
    sections: dict[str, str],
    full_draft_path: str,
) -> dict:
    """Build a dict for inserting into the grant_drafts table."""
    full_text = Path(full_draft_path).read_text(encoding="utf-8")
    return {
        "opportunity_id": opportunity_id,
        "foundation_id": foundation_id,
        "draft_type": draft_type,
        "funder_name": funder_name,
        "project_name": project_name,
        "requirements_json": json.dumps(requirements, default=str),
        "sections_json": json.dumps(sections),
        "full_draft": full_text,
        "model_used": WRITING_MODEL,
        "status": "draft",
    }
