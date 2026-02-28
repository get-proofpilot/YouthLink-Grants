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


# Expanded foundation search keywords — used by CLI, dashboard, and weekly agent
FOUNDATION_SEARCH_KEYWORDS = [
    # Mission-specific
    "youth ministry foundation",
    "christian leadership grant",
    "pastoral development",
    "church leadership",
    "clergy support",
    "ministry coaching",
    # Known funders of this work (search by name to find related foundations)
    "lilly endowment",
    "chatlos foundation",
    "stewardship foundation",
    "maclellan foundation",
    # Broader secular terms that catch relevant foundations
    "leadership development nonprofit",
    "youth worker training",
    "nonprofit capacity building",
    "faith community",
    "spiritual development",
]


# Pre-vetted Christian foundations with known giving in pastoral/youth/ministry space
CURATED_FOUNDATIONS = [
    {
        "name": "Lilly Endowment Inc.",
        "ein": "350868122",
        "city": "Indianapolis",
        "state": "IN",
        "website": "https://lillyendowment.org",
        "focus_areas": ["clergy renewal", "pastoral leadership", "theological education"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "National Christian Foundation",
        "ein": "581493949",
        "city": "Alpharetta",
        "state": "GA",
        "website": "https://www.ncfgiving.com",
        "focus_areas": ["christian ministry", "donor-advised funds", "church support"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "The Chatlos Foundation Inc.",
        "ein": "136161425",
        "city": "Longwood",
        "state": "FL",
        "website": "https://www.chatlos.org",
        "focus_areas": ["bible colleges", "religious causes", "higher education"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "Stewardship Foundation",
        "ein": "910900291",
        "city": "Tacoma",
        "state": "WA",
        "website": "https://www.stewardshipfdn.org",
        "focus_areas": ["christian leadership", "youth development", "education"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "MacLellan Foundation Inc.",
        "ein": "626041468",
        "city": "Chattanooga",
        "state": "TN",
        "website": "https://www.maclellan.net",
        "focus_areas": ["world evangelism", "christian education", "discipleship"],
        "accepts_applications": False,
        "source": "curated",
    },
    {
        "name": "Crowell Trust",
        "ein": "956038007",
        "city": "Sierra Madre",
        "state": "CA",
        "website": "https://www.crowelltrust.org",
        "focus_areas": ["evangelical christianity", "christian education", "church ministry"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "M.J. Murdock Charitable Trust",
        "ein": "237456468",
        "city": "Vancouver",
        "state": "WA",
        "website": "https://murdocktrust.org",
        "focus_areas": ["education", "scientific research", "religion", "arts"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "Kern Family Foundation",
        "ein": "391905498",
        "city": "Waukesha",
        "state": "WI",
        "website": "https://www.kfrn.org",
        "focus_areas": ["character education", "faith and work", "pastoral leadership"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "Koch Foundation Inc.",
        "ein": "591885997",
        "city": "Gainesville",
        "state": "FL",
        "website": "https://www.kochfoundation.org",
        "focus_areas": ["catholic education", "evangelization", "religious formation"],
        "accepts_applications": True,
        "source": "curated",
    },
    {
        "name": "Templeton Religion Trust",
        "ein": "464649055",
        "city": "Nassau",
        "state": "BS",
        "website": "https://www.templetonreligiontrust.org",
        "focus_areas": ["religious scholarship", "science and religion", "character virtue"],
        "accepts_applications": True,
        "source": "curated",
    },
]


# Brave Search API queries for active grant discovery
BRAVE_SEARCH_QUERIES = [
    # Specific known funders
    '"lilly endowment" clergy renewal grant application 2026',
    '"chatlos foundation" grant application religious',
    '"kern family foundation" pastoral leadership grant',
    '"crowell trust" christian ministry grant application',
    '"stewardship foundation" youth ministry grant',
    # Arizona community foundations
    'site:azfoundation.org grants faith youth ministry',
    'Arizona community foundation grants "faith-based" 2026',
    # Broad faith-based
    'christian foundation grants "youth ministry" apply 2026',
    'faith-based grants "pastoral development" application',
    '"clergy support" grant application 2026',
    'foundation grants "church leadership" development',
    '"ministry coaching" grant funding application',
    # Denominational
    'denomination grant "youth ministry" application 2026',
    'evangelical grant "leadership development" application',
    # Capacity building
    '"nonprofit capacity building" faith-based grant 2026',
    '"youth worker" training grant application',
    '"spiritual development" youth grant funding',
    'christian nonprofit grant "capacity building" 2026',
]
