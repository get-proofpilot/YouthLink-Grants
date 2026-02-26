"""Section-by-section generation with cross-section context threading."""

import logging
import re

import anthropic

from grant_intel.config import OrgProfile
from grant_intel.writer.prompts import BANNED_WORDS, build_section_prompt, build_system_prompt

logger = logging.getLogger(__name__)

# Default section order for a federal grant narrative
DEFAULT_SECTIONS = [
    "Statement of Need",
    "Project Description",
    "Goals and Objectives",
    "Evaluation Plan",
    "Organizational Capacity",
    "Budget Justification",
    "Sustainability",
]

WRITING_MODEL = "claude-sonnet-4-6"


def generate_section(
    api_key: str,
    org: OrgProfile,
    requirements: dict,
    section_name: str,
    previous_sections: dict[str, str],
) -> str:
    """Generate one section of a grant narrative.

    Each call sends all previously-written sections as context so the
    Project Description references the Statement of Need, the Evaluation
    Plan references Goals/Objectives, and Budget ties to activities.
    """
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(org)
    user_prompt = build_section_prompt(section_name, requirements, previous_sections)

    # Build conversation with prior sections as context
    messages = []

    if previous_sections:
        # Provide previous sections as assistant context
        prior_summary = "\n\n".join(
            f"[{name}]\n{content}" for name, content in previous_sections.items()
        )
        messages.append({
            "role": "user",
            "content": (
                "I've already written these sections of the grant narrative. "
                "Keep them in mind for consistency.\n\n" + prior_summary
            ),
        })
        messages.append({
            "role": "assistant",
            "content": (
                "Understood. I've reviewed the sections you've written so far "
                "and will maintain consistency with the data, tone, and "
                "commitments made in them."
            ),
        })

    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.messages.create(
            model=WRITING_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )
        raw_text = response.content[0].text
        return post_process_section(raw_text)

    except anthropic.APIError:
        logger.exception("Error generating section: %s", section_name)
        return f"[ERROR: Failed to generate {section_name}. Retry or write manually.]"


def post_process_section(text: str) -> str:
    """Clean up a generated section.

    - Strip stray markdown headers (the template handles headers)
    - Flag any banned words that slipped through
    """
    # Remove leading markdown headers the model might add
    text = re.sub(r"^#{1,3}\s+.*\n+", "", text.strip())

    # Check for banned words and add inline warnings
    lower_text = text.lower()
    found = []
    for word in BANNED_WORDS:
        if word.lower() in lower_text:
            found.append(word)

    if found:
        warning = (
            "\n\n[REVIEW: The following words should be replaced — "
            + ", ".join(f'"{w}"' for w in found)
            + ". They sound AI-generated.]"
        )
        text += warning

    return text.strip()


def determine_sections(requirements: dict) -> list[str]:
    """Determine which sections to write based on funder requirements.

    If the NOFA specifies required sections, use those (mapped to our
    standard names). Otherwise, use the default section order.
    """
    required = requirements.get("required_sections", [])

    if not required:
        return DEFAULT_SECTIONS

    # Map funder section names to our standard names
    mapping = {
        "statement of need": "Statement of Need",
        "need": "Statement of Need",
        "needs assessment": "Statement of Need",
        "project description": "Project Description",
        "project design": "Project Description",
        "project narrative": "Project Description",
        "program design": "Project Description",
        "goals and objectives": "Goals and Objectives",
        "goals": "Goals and Objectives",
        "objectives": "Goals and Objectives",
        "evaluation": "Evaluation Plan",
        "evaluation plan": "Evaluation Plan",
        "evaluation design": "Evaluation Plan",
        "organizational capacity": "Organizational Capacity",
        "organizational background": "Organizational Capacity",
        "organization description": "Organizational Capacity",
        "capacity": "Organizational Capacity",
        "budget justification": "Budget Justification",
        "budget narrative": "Budget Justification",
        "budget": "Budget Justification",
        "sustainability": "Sustainability",
        "sustainability plan": "Sustainability",
    }

    sections = []
    for name in required:
        normalized = name.strip().lower()
        matched = mapping.get(normalized)
        if matched and matched not in sections:
            sections.append(matched)
        elif normalized not in mapping and name not in sections:
            # Unknown section — keep it as-is, agent will handle generically
            sections.append(name)

    # Ensure we have at least the core sections
    for core in ["Statement of Need", "Project Description", "Goals and Objectives"]:
        if core not in sections:
            sections.insert(0, core)

    return sections
