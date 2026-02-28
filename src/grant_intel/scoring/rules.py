"""Rule-based scoring engine for grant opportunity pre-filtering.

Tier 1 of the scoring funnel — scores every opportunity instantly using
title keywords, description scanning, CFDA code matching, agency lookup,
and award range analysis. Eliminates ~85% of irrelevant records so only
promising candidates go to Claude AI for deeper analysis.

Scoring formula:
    base 5 + title_delta + desc_delta + agency_delta + cfda_delta
    + tier_delta + award_delta + deadline_delta
    clamped to 1-10, with kill overrides.
"""

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

# ── Title keyword signals ──────────────────────────────────────────────
# These are checked against the TITLE field only

STRONG_POSITIVE = [
    "ministry", "pastoral", "clergy", "faith-based", "faith based",
    "church", "chaplain", "religious leader", "youth pastor",
    "seminary", "theological", "minister", "congregation",
    "faith community", "religious organization",
]

POSITIVE = [
    "youth development", "youth mentoring", "community-based", "community based",
    "nonprofit capacity", "after-school", "after school", "youth leader",
    "leadership training", "workforce development for youth",
    "mentoring program", "peer learning network", "peer mentoring",
    "volunteer network", "social emotional learning", "positive youth",
]

WEAK_POSITIVE = [
    "leadership development", "coaching", "networking",
    "professional development", "capacity building",
    "nonprofit", "volunteer", "community service",
    "organizational development", "community engagement",
]

STRONG_NEGATIVE = [
    "biomedical", "pharmaceutical", "clinical trial", "cancer",
    "hiv", "laboratory", "genome", "molecular", "neuroscience",
    "pathology", "oncology", "immunology", "virology", "epidemiology",
    "cell biology", "biochemistry", "protein", "stem cell",
    "drug discovery", "clinical research", "vaccine",
    "nuclear", "particle physics", "astrophysics",
    "artificial intelligence", "autonomous", "quantum",
    "semiconductor", "nanotechnology", "photonics",
]

NEGATIVE = [
    "military", "defense", "tribal", "energy", "environmental",
    "transportation", "agricultural", "housing", "fisheries",
    "wildfire", "forestry", "geological", "marine", "ocean",
    "cybersecurity", "spectrum", "infrastructure",
    "water treatment", "wastewater", "dam safety",
    "broadband", "telecom", "spectrum auction",
    "alzheimer", "dementia", "aging", "geriatric",
]

# ── Description-only signals ──────────────────────────────────────────
# These are checked against the DESCRIPTION field (when available).
# Separate from title signals because descriptions are longer and need
# more specific phrases to avoid false positives.

DESC_STRONG_POSITIVE = [
    "faith-based organization", "faith based organization",
    "religious organization", "church", "ministry",
    "clergy", "pastoral", "pastor", "seminary",
    "youth pastor", "youth ministry", "youth leader",
    "spiritual development", "christian",
]

DESC_POSITIVE = [
    "leadership development", "leadership training",
    "capacity building", "mentoring",
    "professional development", "coaching",
    "nonprofit organization", "community-based organization",
    "community based organization", "501(c)(3)",
    "peer network", "peer learning",
    "volunteer", "community engagement",
]

DESC_NEGATIVE = [
    "clinical trial", "biomedical", "pharmaceutical",
    "genome", "laboratory", "vaccine",
    "military", "defense contract",
]

# ── Agency relevance ───────────────────────────────────────────────────

# These agencies fund science/defense/etc. — cap score at 2
KILL_AGENCY_NAMES = [
    "national institutes of health",
    "national science foundation",
    "department of defense",
    "department of energy",
    "environmental protection agency",
    "national aeronautics and space administration",
    "department of agriculture",
    "national institute of standards and technology",
    "national oceanic and atmospheric administration",
    "department of veterans affairs",
    "army", "navy", "air force",
    "defense advanced research",
    "defense logistics",
    "missile defense",
]
KILL_AGENCY_ABBREVS = {
    "nih", "nsf", "dod", "doe", "epa", "nasa", "usda", "nist", "noaa",
    "darpa", "dtra",
}

# These agencies fund youth/community/nonprofit work — boost
BOOST_AGENCIES = {
    "office of juvenile justice": 2,
    "administration for children": 2,
    "americorps": 3,
    "corporation for national": 2,
    "department of education": 1,
    "substance abuse and mental health": 1,
    "health resources and services": 1,
    "administration for community living": 1,
    "office of community services": 2,
    "children's bureau": 2,
    "family and youth services": 3,
}

# ── CFDA / Assistance Listing code signals ─────────────────────────────
# CFDA codes map directly to federal programs. This is the most reliable
# signal we have from the search API.

# Highly relevant program areas — boost by +2 to +3
BOOST_CFDA_PREFIXES = {
    "94": 3,    # AmeriCorps / Corporation for National & Community Service
    "84": 1,    # Department of Education (some programs relevant)
}

# Specific CFDA codes known to fund youth/community/faith-based work
BOOST_CFDA_EXACT = {
    # AmeriCorps programs
    "94.006": 3,  # AmeriCorps State and National
    "94.002": 3,  # AmeriCorps VISTA
    "94.011": 2,  # AmeriCorps Foster Grandparent
    "94.013": 2,  # AmeriCorps RSVP
    # DOJ youth programs
    "16.726": 3,  # Juvenile Mentoring Program
    "16.540": 2,  # Youth Gang Prevention
    "16.541": 2,  # Part E State Challenge Activities
    "16.543": 3,  # Missing Children's Assistance
    "16.548": 2,  # Title V Delinquency Prevention
    "16.731": 2,  # Community-Based Violence Intervention
    # HHS community/youth programs
    "93.550": 2,  # Transitional Living for Homeless Youth
    "93.557": 2,  # Community Services Block Grant
    "93.558": 1,  # TANF (some components)
    "93.590": 2,  # Community-Based Family Resource
    "93.591": 2,  # Family Violence Prevention
    "93.592": 2,  # Family Violence Prevention - State Grants
    "93.623": 2,  # Children/Youth Exposed to Violence
    "93.670": 2,  # Child Abuse/Neglect State Grants
    "93.674": 2,  # Chafee Foster Care
    # Education programs
    "84.047": 1,  # TRIO Upward Bound
    "84.184": 2,  # Safe and Drug-Free Schools (community grants)
    "84.215": 2,  # Fund for Improvement of Education
    "84.235": 2,  # Rehabilitation Services - Vocational Training
    "84.310": 2,  # Statewide Family Engagement Centers
    "84.326": 2,  # Special Education Technical Assistance
    "84.411": 2,  # Education Innovation and Research
    # CNCS / National Service
    "94.019": 3,  # Social Innovation Fund
}

# Kill CFDA prefixes — these are science/defense/medical research
KILL_CFDA_PREFIXES = {
    "47",   # NSF
    "81",   # DOE
    "12",   # DOD
    "43",   # NASA
    "10",   # USDA
    "66",   # EPA
    "15",   # DOI
    "20",   # DOT
}

# ── Award range scoring ──────────────────────────────────────────────
# YLM budget is under $250K. Matching award ranges:
# Sweet spot: $25K-$500K (typical small nonprofit grants)
# Too large: floor > $1M (probably for big institutions)
# Too small: ceiling < $5K (not worth pursuing)


def _score_title(title: str) -> tuple[int, list[str]]:
    """Score based on title keywords. Returns (delta, reasons)."""
    delta = 0
    reasons = []

    strong_pos_hits = [kw for kw in STRONG_POSITIVE if kw in title]
    pos_hits = [kw for kw in POSITIVE if kw in title]
    weak_pos_hits = [kw for kw in WEAK_POSITIVE if kw in title]
    strong_neg_hits = [kw for kw in STRONG_NEGATIVE if kw in title]
    neg_hits = [kw for kw in NEGATIVE if kw in title]

    if strong_pos_hits:
        delta += 5
        reasons.append(f"Strong title match: {', '.join(strong_pos_hits[:3])}")
    if pos_hits:
        delta += 3
        reasons.append(f"Positive title: {', '.join(pos_hits[:3])}")
    if weak_pos_hits and not strong_pos_hits and not pos_hits:
        delta += 1
        reasons.append(f"Weak title match: {', '.join(weak_pos_hits[:3])}")

    if strong_neg_hits:
        delta -= 5
        reasons.append(f"Irrelevant field: {', '.join(strong_neg_hits[:3])}")
    if neg_hits:
        delta -= 3
        reasons.append(f"Likely irrelevant: {', '.join(neg_hits[:3])}")

    return delta, reasons, bool(strong_pos_hits)


def _score_description(description: str) -> tuple[int, list[str]]:
    """Score based on description content. Returns (delta, reasons)."""
    if not description:
        return 0, []

    delta = 0
    reasons = []
    desc_lower = description.lower()

    strong_pos = [kw for kw in DESC_STRONG_POSITIVE if kw in desc_lower]
    pos = [kw for kw in DESC_POSITIVE if kw in desc_lower]
    neg = [kw for kw in DESC_NEGATIVE if kw in desc_lower]

    if strong_pos:
        delta += 3
        reasons.append(f"Description mentions: {', '.join(strong_pos[:3])}")
    elif pos:
        delta += 1
        reasons.append(f"Description has: {', '.join(pos[:3])}")

    if neg:
        delta -= 2
        reasons.append(f"Description red flag: {', '.join(neg[:2])}")

    return delta, reasons


def _score_agency(agency: str) -> tuple[int, list[str], bool]:
    """Score based on agency. Returns (delta, reasons, is_kill_agency)."""
    delta = 0
    reasons = []

    is_kill_agency = (
        any(kill in agency for kill in KILL_AGENCY_NAMES)
        or agency.strip() in KILL_AGENCY_ABBREVS
    )

    boost_amount = 0
    for boost_key, boost_val in BOOST_AGENCIES.items():
        if boost_key in agency:
            boost_amount = max(boost_amount, boost_val)

    if is_kill_agency:
        reasons.append(f"Agency ({agency[:40]}) rarely funds ministry work")
    if boost_amount:
        delta += boost_amount
        reasons.append(f"Agency ({agency[:40]}) funds youth/community work")

    return delta, reasons, is_kill_agency


def _score_cfda(cfda_codes: str) -> tuple[int, list[str], bool]:
    """Score based on CFDA/Assistance Listing codes. Returns (delta, reasons, is_kill)."""
    if not cfda_codes:
        return 0, [], False

    delta = 0
    reasons = []
    is_kill = False
    codes = [c.strip() for c in cfda_codes.split(",") if c.strip()]

    best_boost = 0
    best_code = ""

    for code in codes:
        prefix = code.split(".")[0]

        # Check exact code matches first (most specific)
        if code in BOOST_CFDA_EXACT:
            boost = BOOST_CFDA_EXACT[code]
            if boost > best_boost:
                best_boost = boost
                best_code = code

        # Check prefix matches
        elif prefix in BOOST_CFDA_PREFIXES:
            boost = BOOST_CFDA_PREFIXES[prefix]
            if boost > best_boost:
                best_boost = boost
                best_code = code

        # Check kill prefixes
        if prefix in KILL_CFDA_PREFIXES:
            is_kill = True

    if best_boost:
        delta += best_boost
        reasons.append(f"CFDA {best_code} is a relevant program area (+{best_boost})")

    if is_kill and not best_boost:
        reasons.append(f"CFDA codes indicate science/defense/agriculture program")

    return delta, reasons, is_kill


def _score_award_range(award_floor: int | None, award_ceiling: int | None) -> tuple[int, list[str]]:
    """Score based on award amounts. Returns (delta, reasons)."""
    delta = 0
    reasons = []

    floor = award_floor or 0
    ceiling = award_ceiling or 0

    if floor > 1_000_000:
        delta -= 2
        reasons.append(f"Award floor ${floor:,} too large for small nonprofit")
    elif floor > 500_000:
        delta -= 1
        reasons.append(f"Award floor ${floor:,} may be high for YLM budget")

    if 0 < ceiling < 5_000:
        delta -= 1
        reasons.append(f"Award ceiling ${ceiling:,} too small to pursue")
    elif 25_000 <= ceiling <= 500_000:
        delta += 1
        reasons.append(f"Award range fits small nonprofit (ceiling ${ceiling:,})")

    return delta, reasons


def _score_deadline(deadline: str) -> tuple[int, list[str]]:
    """Score based on deadline proximity. Returns (delta, reasons)."""
    if not deadline:
        return 0, []

    delta = 0
    reasons = []

    try:
        deadline_date = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
        days_left = (deadline_date - date.today()).days

        if days_left < 0:
            delta -= 2
            reasons.append(f"Deadline passed ({deadline[:10]})")
        elif days_left <= 14:
            delta -= 1
            reasons.append(f"Deadline in {days_left} days — very tight")
    except (ValueError, TypeError):
        pass

    return delta, reasons


def _score_eligibility(eligibility: str) -> tuple[int, list[str]]:
    """Score based on eligibility text. Returns (delta, reasons)."""
    if not eligibility:
        return 0, []

    delta = 0
    reasons = []
    elig_lower = eligibility.lower()

    # Positive eligibility signals
    faith_signals = ["faith-based", "faith based", "religious", "church", "501(c)(3)"]
    if any(s in elig_lower for s in faith_signals):
        delta += 2
        reasons.append("Eligibility includes faith-based/religious organizations")

    nonprofit_signals = ["nonprofit", "non-profit", "community-based"]
    if any(s in elig_lower for s in nonprofit_signals):
        delta += 1
        reasons.append("Eligibility includes nonprofits")

    # Negative eligibility signals
    restrict_signals = [
        "state government only", "tribal government only",
        "for-profit only", "higher education only",
        "public housing", "state agencies only",
    ]
    if any(s in elig_lower for s in restrict_signals):
        delta -= 3
        reasons.append("Eligibility restricts to non-applicable org types")

    return delta, reasons


def score_opportunity(opp: dict) -> tuple[int, str]:
    """Score a single opportunity using all available signals.

    Returns (score 1-10, explanation string).

    Composite: base 5 + title + description + agency + CFDA + tier + award + deadline + eligibility
    Kill overrides cap score at 2 unless strong positive title signals exist.
    """
    title = (opp.get("title") or "").lower()
    agency = (opp.get("agency") or "").lower()
    description = opp.get("description") or ""
    eligibility = opp.get("eligibility") or ""
    cfda_codes = opp.get("cfda_codes") or ""
    keyword_tier = opp.get("keyword_tier") or 0
    award_floor = opp.get("award_floor")
    award_ceiling = opp.get("award_ceiling")
    deadline = opp.get("deadline") or ""

    reasons = []

    # ── Score each signal ──────────────────────────────────────────
    title_delta, title_reasons, has_strong_pos = _score_title(title)
    reasons.extend(title_reasons)

    desc_delta, desc_reasons = _score_description(description)
    reasons.extend(desc_reasons)

    agency_delta, agency_reasons, is_kill_agency = _score_agency(agency)
    reasons.extend(agency_reasons)

    cfda_delta, cfda_reasons, is_kill_cfda = _score_cfda(cfda_codes)
    reasons.extend(cfda_reasons)

    award_delta, award_reasons = _score_award_range(award_floor, award_ceiling)
    reasons.extend(award_reasons)

    deadline_delta, deadline_reasons = _score_deadline(deadline)
    reasons.extend(deadline_reasons)

    elig_delta, elig_reasons = _score_eligibility(eligibility)
    reasons.extend(elig_reasons)

    # Keyword tier weighting
    tier_delta = 0
    if keyword_tier == 1:
        tier_delta += 1
        reasons.append("Matched on Tier 1 (specific) keyword")
    elif keyword_tier == 3:
        tier_delta -= 1
        reasons.append("Matched on Tier 3 (broad) keyword")

    # ── Composite ──────────────────────────────────────────────────
    raw_score = (
        5
        + title_delta
        + desc_delta
        + agency_delta
        + cfda_delta
        + tier_delta
        + award_delta
        + deadline_delta
        + elig_delta
    )

    # Kill override: cap at 2 if both agency AND CFDA indicate irrelevant area
    # Unless the title has strong positive signals (rare but possible)
    if (is_kill_agency or is_kill_cfda) and not has_strong_pos:
        raw_score = min(raw_score, 2)

    final_score = max(1, min(10, raw_score))
    explanation = "; ".join(reasons) if reasons else "No strong signals found"

    return final_score, explanation


def score_all_opportunities(opportunities: list[dict]) -> list[dict]:
    """Score a batch of opportunities with rules. Returns list of result dicts.

    Each result: {id, rule_score, rule_explanation}
    """
    results = []
    for opp in opportunities:
        score, explanation = score_opportunity(opp)
        results.append({
            "id": opp["id"],
            "rule_score": score,
            "rule_explanation": explanation,
        })
    return results
