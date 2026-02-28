"""ProPublica Nonprofit Explorer API client for 990 research."""

import logging

from grant_intel.utils.rate_limiter import RateLimiter, request_with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://projects.propublica.org/nonprofits/api/v2"

# Polite rate limit: 1 req per 2 seconds (no key, be conservative)
_rate_limiter = RateLimiter(calls_per_second=0.5)


def search_orgs(query: str, state: str = "") -> list[dict]:
    """Search for nonprofit organizations by keyword."""
    params = {"q": query}
    if state:
        params["state[id]"] = state

    all_orgs = []
    page = 0

    while True:
        params["page"] = page
        response = request_with_retry(
            "GET",
            f"{BASE_URL}/search.json",
            rate_limiter=_rate_limiter,
            params=params,
        )
        # ProPublica returns 404 when no results match a state-filtered query
        if response.status_code == 404:
            break
        response.raise_for_status()
        data = response.json()

        orgs = data.get("organizations", [])
        if not orgs:
            break

        all_orgs.extend(orgs)
        total = data.get("total_results", 0)

        logger.debug("ProPublica search: got %d/%d for query=%r", len(all_orgs), total, query)

        page += 1
        if len(all_orgs) >= total:
            break
        # Limit pages to avoid excessive API calls
        if page >= 10:
            break

    return all_orgs


def get_organization(ein: str) -> dict | None:
    """Get detailed organization data including filings by EIN."""
    clean_ein = ein.replace("-", "")
    response = request_with_retry(
        "GET",
        f"{BASE_URL}/organizations/{clean_ein}.json",
        rate_limiter=_rate_limiter,
    )
    if response.status_code == 404:
        logger.warning("Organization not found: EIN=%s", ein)
        return None
    response.raise_for_status()
    return response.json()


def extract_org_info(data: dict) -> dict:
    """Extract standardized org info from ProPublica response."""
    org = data.get("organization", {})
    return {
        "name": org.get("name", ""),
        "ein": str(org.get("ein", "")),
        "city": org.get("city", ""),
        "state": org.get("state", ""),
        "total_revenue": org.get("income_amount"),
        "total_assets": org.get("asset_amount"),
        "ntee_code": org.get("ntee_code", ""),
        "mission": org.get("subsection_code", ""),
        "source": "propublica",
        "raw": org,
    }


def extract_filings(data: dict) -> list[dict]:
    """Extract filing data from ProPublica response."""
    filings = data.get("filings_with_data", [])
    return [
        {
            "tax_period": f.get("tax_prd", ""),
            "form_type": _form_type_name(f.get("formtype")),
            "total_revenue": f.get("totrevenue"),
            "total_expenses": f.get("totfuncexpns"),
            "total_assets": f.get("totassetsend"),
            "pdf_url": f.get("pdf_url", ""),
        }
        for f in filings
    ]


def _form_type_name(code) -> str:
    """Convert ProPublica form type code to name."""
    mapping = {0: "990", 1: "990EZ", 2: "990PF"}
    return mapping.get(code, str(code))


def research_similar_orgs(similar_org_list: list[dict]) -> tuple[list[dict], list[dict]]:
    """Research similar organizations via ProPublica.

    Args:
        similar_org_list: List of dicts with 'name' and 'ein' keys.

    Returns:
        Tuple of (org_infos, all_filings) where org_infos are standardized
        org dicts and all_filings contain filing data.
    """
    org_infos = []
    all_filings = []

    for org_entry in similar_org_list:
        ein = org_entry.get("ein", "")
        name = org_entry.get("name", "")

        if not ein:
            logger.warning("No EIN for org: %s, searching by name", name)
            search_results = search_orgs(name)
            if search_results:
                ein = str(search_results[0].get("ein", ""))
            else:
                logger.warning("Could not find org: %s", name)
                continue

        logger.info("Researching org: %s (EIN: %s)", name, ein)
        try:
            data = get_organization(ein)
            if not data:
                continue

            org_info = extract_org_info(data)
            org_info["name"] = name  # Use the name from our config
            org_infos.append(org_info)

            filings = extract_filings(data)
            for f in filings:
                f["org_ein"] = ein
                f["org_name"] = name
            all_filings.extend(filings)

            logger.info(
                "Found %d filings for %s (revenue: %s)",
                len(filings),
                name,
                org_info.get("total_revenue", "N/A"),
            )
        except Exception:
            logger.exception("Error researching org: %s", name)

    logger.info(
        "ProPublica research complete: %d orgs, %d filings",
        len(org_infos),
        len(all_filings),
    )
    return org_infos, all_filings


def search_foundations_by_keyword(
    keywords: list[str],
    states: list[str] | None = None,
) -> list[dict]:
    """Search for foundations by keyword to find potential funders.

    Searches ProPublica for 990-PF filers matching mission-related keywords.
    """
    foundations = []
    seen_eins = set()

    for keyword in keywords:
        search_states = states or [""]
        for state in search_states:
            try:
                results = search_orgs(keyword, state=state)
                for org in results:
                    ein = str(org.get("ein", ""))
                    if ein and ein not in seen_eins:
                        seen_eins.add(ein)
                        foundations.append({
                            "name": org.get("name", ""),
                            "ein": ein,
                            "city": org.get("city", ""),
                            "state": org.get("state", ""),
                            "source": "propublica",
                        })
            except Exception:
                logger.exception("Error searching foundations: keyword=%r", keyword)

    logger.info("Found %d potential foundations via keyword search", len(foundations))
    return foundations
