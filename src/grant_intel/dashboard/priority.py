"""Priority Score algorithm and requirement matching for the dashboard.

The existing Claude score (1-10) measures mission alignment. The Priority Score
adds deadline urgency, budget match, and eligibility confidence to answer:
"Which grant should we work on RIGHT NOW?"
"""

import re
from datetime import date, datetime

from grant_intel.config import OrgProfile


# ---------------------------------------------------------------------------
# Priority Score — composite 1-10 ranking
# ---------------------------------------------------------------------------


def calculate_priority_score(opp: dict, org: OrgProfile) -> dict:
    """Calculate a composite Priority Score for an opportunity.

    Returns dict with:
        priority_score: float (1.0-10.0)
        priority_label: "High" | "Medium" | "Low"
        factors: dict of individual factor scores and details
    """
    mission = opp.get("score") or opp.get("rule_score") or 5
    urgency = _urgency_score(opp.get("urgency", ""), opp.get("deadline", ""))
    budget = _budget_match_score(opp.get("award_floor"), opp.get("award_ceiling"), org.budget_range)
    eligibility = _eligibility_score(opp.get("eligibility", ""), org)

    priority = (
        mission * 0.40
        + urgency * 0.20
        + budget * 0.20
        + eligibility * 0.20
    )
    priority = round(priority, 1)

    if priority >= 7:
        label = "High"
    elif priority >= 4:
        label = "Medium"
    else:
        label = "Low"

    return {
        "priority_score": priority,
        "priority_label": label,
        "factors": {
            "mission_fit": {"score": mission, "weight": 0.40},
            "deadline_urgency": {"score": urgency, "weight": 0.20},
            "budget_match": {"score": budget, "weight": 0.20},
            "eligibility_fit": {"score": eligibility, "weight": 0.20},
        },
    }


def _urgency_score(urgency: str, deadline: str) -> int:
    """Convert deadline proximity to a 1-10 score. Closer = higher."""
    mapping = {"30_day": 10, "60_day": 8, "90_day": 6}
    if urgency in mapping:
        return mapping[urgency]

    if not deadline:
        return 2

    try:
        dl = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
        days = (dl - date.today()).days
        if days < 0:
            return 1
        if days <= 30:
            return 10
        if days <= 60:
            return 8
        if days <= 90:
            return 6
        if days <= 180:
            return 4
        return 2
    except (ValueError, TypeError):
        return 2


def _budget_match_score(award_floor: int | None, award_ceiling: int | None, org_budget: str) -> int:
    """Score how well the award range fits a small nonprofit."""
    floor = award_floor or 0
    ceiling = award_ceiling or 0

    if floor == 0 and ceiling == 0:
        return 5

    mid = (floor + ceiling) / 2 if ceiling > 0 else floor

    if org_budget == "under_250k":
        if 10_000 <= mid <= 100_000:
            return 10
        if 100_000 < mid <= 150_000:
            return 8
        if 150_000 < mid <= 250_000:
            return 6
        if 250_000 < mid <= 500_000:
            return 4
        if mid > 500_000:
            return 2
        if mid < 5_000:
            return 3
        return 5

    return 5


def _eligibility_score(eligibility_text: str, org: OrgProfile) -> int:
    """Score confidence that the org meets eligibility requirements."""
    if not eligibility_text:
        return 5

    text = eligibility_text.lower()
    score = 5

    # Positive signals
    if "501(c)(3)" in text or "nonprofit" in text or "non-profit" in text:
        score += 2
    if any(t in text for t in ("faith-based", "faith based", "religious", "community-based")):
        score += 2
    if any(t in text for t in ("small organization", "small nonprofit")):
        score += 1

    # Negative signals
    if any(t in text for t in ("state government", "state agency", "tribal government")):
        score -= 3
    if "for-profit" in text and "nonprofit" not in text:
        score -= 4
    if "higher education" in text or "public institution" in text:
        score -= 2

    return max(1, min(10, score))


def enrich_opportunities_with_priority(opportunities: list[dict], org: OrgProfile) -> list[dict]:
    """Add priority_score and priority_label to each opportunity dict."""
    for opp in opportunities:
        result = calculate_priority_score(opp, org)
        opp["priority_score"] = result["priority_score"]
        opp["priority_label"] = result["priority_label"]
        opp["priority_factors"] = result["factors"]
    opportunities.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    return opportunities


# ---------------------------------------------------------------------------
# Requirement Match Checklist
# ---------------------------------------------------------------------------


def analyze_requirements(opp: dict, org: OrgProfile) -> list[dict]:
    """Analyze whether the org meets the opportunity's requirements.

    Returns a list of dicts with keys:
        check, label, status ("pass"/"fail"/"warn"/"unknown"), detail
    """
    eligibility = (opp.get("eligibility", "") or "").lower()
    description = (opp.get("description", "") or "").lower()
    combined = f"{eligibility} {description}"

    return [
        _check_tax_status(combined, org),
        _check_faith_based(combined),
        _check_geographic(combined, org),
        _check_budget(opp, org),
        _check_years(combined, org),
        _check_ntee(opp, org),
    ]


def summarize_matches(checks: list[dict]) -> dict:
    """Summarize requirement checks into overall assessment."""
    pass_count = sum(1 for c in checks if c["status"] == "pass")
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    total = len(checks)

    if fail_count > 0:
        overall = "caution"
        message = f"{fail_count} requirement(s) may not be met"
    elif warn_count > 1:
        overall = "review"
        message = f"{warn_count} items need verification"
    elif pass_count >= total - 1:
        overall = "strong"
        message = f"{pass_count}/{total} requirements clearly met"
    else:
        overall = "review"
        message = f"{pass_count} confirmed, {total - pass_count} need review"

    return {"overall": overall, "message": message, "pass_count": pass_count, "total": total}


def _check_tax_status(text: str, org: OrgProfile) -> dict:
    if "501(c)(3)" in text or "nonprofit" in text or "non-profit" in text:
        return {"check": "tax_status", "label": "501(c)(3) Eligible", "status": "pass",
                "detail": f"{org.name} is a {org.tax_status} organization"}
    if "government" in text and "nonprofit" not in text:
        return {"check": "tax_status", "label": "501(c)(3) Eligible", "status": "fail",
                "detail": "Appears to require government entities"}
    return {"check": "tax_status", "label": "501(c)(3) Eligible", "status": "unknown",
            "detail": "Applicant type not specified in eligibility text"}


def _check_faith_based(text: str) -> dict:
    positive = any(t in text for t in ("faith-based", "faith based", "religious", "ministry", "church"))
    negative = any(t in text for t in ("secular only", "no religious", "non-religious", "exclude religious"))
    restriction = any(t in text for t in ("no proselytizing", "no proselytization", "no religious worship"))

    if positive and not negative:
        return {"check": "faith_based", "label": "Faith-Based Eligible", "status": "pass",
                "detail": "Faith-based organizations explicitly eligible"}
    if negative:
        return {"check": "faith_based", "label": "Faith-Based Eligible", "status": "fail",
                "detail": "Religious organizations appear excluded"}
    if restriction:
        return {"check": "faith_based", "label": "Faith-Based Eligible", "status": "warn",
                "detail": "Eligible with restrictions on religious content"}
    return {"check": "faith_based", "label": "Faith-Based Eligible", "status": "unknown",
            "detail": "No explicit mention of faith-based eligibility"}


def _check_geographic(text: str, org: OrgProfile) -> dict:
    state_lower = org.state.lower()
    city_lower = org.city.lower()

    if state_lower in text or city_lower in text or "arizona" in text:
        return {"check": "geographic", "label": "Geographic Match", "status": "pass",
                "detail": f"Mentions {org.state} specifically"}
    if "national" in text or "nationwide" in text or "all states" in text:
        return {"check": "geographic", "label": "Geographic Match", "status": "pass",
                "detail": "National scope — all states eligible"}
    return {"check": "geographic", "label": "Geographic Match", "status": "unknown",
            "detail": "No geographic restrictions found"}


def _check_budget(opp: dict, org: OrgProfile) -> dict:
    floor = opp.get("award_floor") or 0
    ceiling = opp.get("award_ceiling") or 0

    if floor == 0 and ceiling == 0:
        return {"check": "budget", "label": "Budget Range Fit", "status": "unknown",
                "detail": "Award range not specified"}

    if org.budget_range == "under_250k":
        mid = (floor + ceiling) / 2 if ceiling > 0 else floor
        if mid <= 250_000:
            return {"check": "budget", "label": "Budget Range Fit", "status": "pass",
                    "detail": f"Award range (${floor:,.0f}–${ceiling:,.0f}) fits org capacity"}
        if mid <= 500_000:
            return {"check": "budget", "label": "Budget Range Fit", "status": "warn",
                    "detail": f"Award range may exceed org capacity to manage"}
        return {"check": "budget", "label": "Budget Range Fit", "status": "warn",
                "detail": f"Large award (${ceiling:,.0f}) requires significant admin capacity"}

    return {"check": "budget", "label": "Budget Range Fit", "status": "unknown",
            "detail": f"Award range: ${floor:,.0f}–${ceiling:,.0f}"}


def _check_years(text: str, org: OrgProfile) -> dict:
    patterns = [
        r"(?:at least|minimum|min\.?)\s+(\d+)\s+years?",
        r"(\d+)\s+years?\s+(?:of )?(?:experience|operation|service)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            required = int(match.group(1))
            if org.years_active >= required:
                return {"check": "years", "label": "Years of Operation", "status": "pass",
                        "detail": f"Requires {required} years; {org.name} has {org.years_active}"}
            return {"check": "years", "label": "Years of Operation", "status": "fail",
                    "detail": f"Requires {required} years; {org.name} has {org.years_active}"}

    return {"check": "years", "label": "Years of Operation", "status": "pass",
            "detail": f"No minimum specified; {org.name} has {org.years_active} years"}


def _check_ntee(opp: dict, org: OrgProfile) -> dict:
    cat = (opp.get("funding_category", "") or "").lower()
    relevance = {
        "is": ["X20", "X80"],
        "ed": ["B80", "X20"],
        "cd": ["S", "T"],
    }
    codes = relevance.get(cat, [])
    if codes:
        overlap = set(codes) & set(org.ntee_codes)
        if overlap:
            return {"check": "ntee", "label": "Program Area Match", "status": "pass",
                    "detail": f"NTEE codes {', '.join(overlap)} align with funding category"}
        return {"check": "ntee", "label": "Program Area Match", "status": "warn",
                "detail": f"Funding category may not align with org's NTEE codes"}

    return {"check": "ntee", "label": "Program Area Match", "status": "unknown",
            "detail": "Unable to determine program area match"}
