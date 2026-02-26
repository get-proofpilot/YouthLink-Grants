"""Extract structured requirements from NOFA/RFP text or URL."""

import json
import logging
import re

import anthropic
import requests
from lxml import html as lxml_html

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a grant analyst. Parse the following NOFA / RFP / \
funder guidelines text and extract structured requirements.

Respond with valid JSON only — no markdown fences, no explanation. Use this schema:

{{
  "funder_name": "string — the funding agency or foundation name",
  "program_name": "string — the grant program name",
  "deadline": "string — application deadline in YYYY-MM-DD format if available, else empty string",
  "award_range": {{"min": 0, "max": 0}},
  "eligible_applicants": "string — who can apply",
  "required_sections": ["list of required narrative sections"],
  "page_limits": {{"narrative": 0, "budget": 0}},
  "evaluation_criteria": ["list of scoring/review criteria with weights if given"],
  "focus_areas": ["list of priority areas or topics the funder cares about"],
  "restrictions": ["list of any restrictions, e.g. no religious proselytizing"],
  "questions_to_answer": ["list of specific questions the applicant must address"]
}}

If a field is not mentioned in the text, use a reasonable default (empty string, \
empty list, or 0). Do not make up information that isn't in the text.

TEXT TO PARSE:
{text}"""


def extract_requirements_from_text(text: str, api_key: str) -> dict:
    """Use Claude Haiku to parse NOFA/RFP text into structured requirements.

    Returns a dict with keys: funder_name, program_name, deadline, award_range,
    eligible_applicants, required_sections, page_limits, evaluation_criteria,
    focus_areas, restrictions, questions_to_answer, raw_text.
    """
    if not text or not text.strip():
        return _empty_requirements()

    client = anthropic.Anthropic(api_key=api_key)

    # Truncate very long documents to stay within context
    truncated = text[:15000]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(text=truncated),
                }
            ],
        )

        response_text = response.content[0].text
        # Strip any accidental markdown fences
        response_text = re.sub(r"^```json\s*", "", response_text.strip())
        response_text = re.sub(r"\s*```$", "", response_text.strip())

        parsed = json.loads(response_text)
        parsed["raw_text"] = text
        return parsed

    except (json.JSONDecodeError, anthropic.APIError):
        logger.exception("Failed to extract requirements from text")
        result = _empty_requirements()
        result["raw_text"] = text
        return result


def extract_requirements_from_url(url: str, api_key: str) -> dict:
    """Fetch page content, strip HTML, then extract requirements.

    Falls back gracefully if the URL is behind a login or returns an error.
    """
    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (grant-intel research tool)"
        })
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("Failed to fetch URL: %s", url)
        result = _empty_requirements()
        result["raw_text"] = f"[Could not fetch URL: {url}]"
        return result

    # Strip HTML to plain text using lxml
    try:
        doc = lxml_html.fromstring(resp.content)
        # Remove script and style elements
        for element in doc.iter("script", "style"):
            element.drop_tree()
        text = doc.text_content()
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
    except Exception:
        logger.exception("Failed to parse HTML from: %s", url)
        text = resp.text

    if not text or len(text) < 50:
        result = _empty_requirements()
        result["raw_text"] = f"[URL returned insufficient content: {url}]"
        return result

    return extract_requirements_from_text(text, api_key)


def _empty_requirements() -> dict:
    """Return a blank requirements dict."""
    return {
        "funder_name": "",
        "program_name": "",
        "deadline": "",
        "award_range": {"min": 0, "max": 0},
        "eligible_applicants": "",
        "required_sections": [],
        "page_limits": {},
        "evaluation_criteria": [],
        "focus_areas": [],
        "restrictions": [],
        "questions_to_answer": [],
        "raw_text": "",
    }
