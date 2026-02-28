"""Configuration loading from YAML and environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class OrgProfile:
    name: str = ""
    ein: str = ""
    tax_status: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    mission: str = ""
    serves: str = ""
    programs: list[dict] = field(default_factory=list)
    budget_range: str = ""
    years_active: int = 0
    ntee_codes: list[str] = field(default_factory=list)


@dataclass
class Config:
    org: OrgProfile
    keywords: dict[str, list[str]]
    similar_orgs: list[dict]
    db_path: str = "data/grants.db"
    output_dir: str = "output"
    anthropic_api_key: str = ""
    brave_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_to: list[str] = field(default_factory=list)
    simpler_grants_api_key: str = ""


def load_config(
    profile_path: str = "config/org_profile.yaml",
    similar_orgs_path: str = "config/similar_orgs.yaml",
    db_path: str = "data/grants.db",
) -> Config:
    """Load configuration from YAML files and environment variables."""
    load_dotenv()

    with open(profile_path) as f:
        profile_data = yaml.safe_load(f)

    org_data = profile_data.get("organization", {})
    location = org_data.get("location", {})
    org = OrgProfile(
        name=org_data.get("name", ""),
        ein=org_data.get("ein", ""),
        tax_status=org_data.get("tax_status", ""),
        city=location.get("city", ""),
        state=location.get("state", ""),
        zip_code=location.get("zip", ""),
        mission=org_data.get("mission", ""),
        serves=org_data.get("serves", ""),
        programs=org_data.get("programs", []),
        budget_range=org_data.get("budget_range", ""),
        years_active=org_data.get("years_active", 0),
        ntee_codes=org_data.get("ntee_codes", []),
    )

    keywords = profile_data.get("search_keywords", {})

    similar_orgs = []
    if Path(similar_orgs_path).exists():
        with open(similar_orgs_path) as f:
            similar_data = yaml.safe_load(f)
        similar_orgs = similar_data.get("similar_organizations", [])

    email_to_raw = os.getenv("EMAIL_TO", "")
    email_to = [e.strip() for e in email_to_raw.split(",") if e.strip()]

    return Config(
        org=org,
        keywords=keywords,
        similar_orgs=similar_orgs,
        db_path=db_path,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        brave_api_key=os.getenv("BRAVE_API_KEY", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_pass=os.getenv("SMTP_PASS", ""),
        email_to=email_to,
        simpler_grants_api_key=os.getenv("SIMPLER_GRANTS_API_KEY", ""),
    )


def _load_search_queries(path: str = "config/search_queries.yaml") -> tuple[list[str], list[str]]:
    """Load foundation search keywords and Brave search queries from YAML."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return (
            data.get("foundation_search_keywords", []),
            data.get("brave_search_queries", []),
        )
    except FileNotFoundError:
        return [], []


def _load_curated_foundations(path: str = "config/curated_foundations.yaml") -> list[dict]:
    """Load curated foundations list from YAML."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data.get("foundations", [])
    except FileNotFoundError:
        return []


# Module-level constants loaded from YAML — importable by CLI, dashboard, weekly agent.
# Edit config/search_queries.yaml or config/curated_foundations.yaml to add/remove
# entries without a code change or redeployment.
FOUNDATION_SEARCH_KEYWORDS, BRAVE_SEARCH_QUERIES = _load_search_queries()
CURATED_FOUNDATIONS = _load_curated_foundations()
