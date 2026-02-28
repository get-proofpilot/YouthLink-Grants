"""Grants.gov REST API client for federal grant discovery."""

import logging

from grant_intel.utils.rate_limiter import RateLimiter, request_with_retry

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.grants.gov/v1/api/search2"
FETCH_URL = "https://api.grants.gov/v1/api/fetchOpportunity"

# Conservative rate limit: 1 req/sec
_rate_limiter = RateLimiter(calls_per_second=1.0)


def search_opportunities(
    keyword: str,
    statuses: str = "posted|forecasted",
    rows: int = 100,
) -> list[dict]:
    """Search Grants.gov for opportunities matching a keyword.

    Paginates through all results automatically.
    """
    all_results = []
    start = 0

    while True:
        payload = {
            "keyword": keyword,
            "oppStatuses": statuses,
            "rows": rows,
            "startRecordNum": start,
        }

        logger.debug("Searching Grants.gov: keyword=%r, start=%d", keyword, start)
        response = request_with_retry(
            "POST",
            SEARCH_URL,
            rate_limiter=_rate_limiter,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        raw = response.json()
        data = raw.get("data", raw)

        hits = data.get("oppHits", [])
        if not hits:
            break

        all_results.extend(hits)
        total = data.get("hitCount", 0)

        logger.debug(
            "Got %d results (total: %d) for keyword=%r",
            len(hits),
            total,
            keyword,
        )

        start += rows
        if start >= total:
            break

    return all_results


def fetch_opportunity_detail(opp_id: str) -> dict:
    """Fetch full details for a single opportunity."""
    response = request_with_retry(
        "POST",
        FETCH_URL,
        rate_limiter=_rate_limiter,
        json={"oppId": opp_id},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def parse_opportunity(hit: dict, keyword: str, tier: int) -> dict:
    """Parse a Grants.gov search hit into a standardized opportunity dict."""
    return {
        "source": "grants_gov",
        "opportunity_id": str(hit.get("id", "")),
        "opportunity_number": hit.get("number", ""),
        "title": hit.get("title", ""),
        "agency": hit.get("agency", ""),
        "description": hit.get("description", ""),
        "funding_category": hit.get("fundingCategory", ""),
        "award_floor": hit.get("awardFloor"),
        "award_ceiling": hit.get("awardCeiling"),
        "expected_awards": hit.get("expectedAwards"),
        "deadline": hit.get("closeDate", ""),
        "posted_date": hit.get("openDate", ""),
        "status": hit.get("oppStatus", ""),
        "eligibility": hit.get("eligibility", ""),
        "url": f"https://www.grants.gov/search-results-detail/{hit.get('id', '')}",
        "keyword_tier": tier,
        "matched_keyword": keyword,
        "raw": hit,
    }


def discover_grants(keywords_by_tier: dict[str, list[str]]) -> list[dict]:
    """Run full discovery across all keyword tiers.

    Args:
        keywords_by_tier: Dict with keys 'tier1', 'tier2', 'tier3',
                         each containing a list of keyword strings.

    Returns:
        List of parsed opportunity dicts, deduplicated by opportunity_id.
    """
    seen_ids = set()
    results = []

    for tier_name, keywords in sorted(keywords_by_tier.items()):
        tier_num = int(tier_name.replace("tier", ""))
        for keyword in keywords:
            logger.info("Searching Grants.gov: tier=%d keyword=%r", tier_num, keyword)
            try:
                hits = search_opportunities(keyword)
                for hit in hits:
                    opp_id = str(hit.get("id", ""))
                    if opp_id and opp_id not in seen_ids:
                        seen_ids.add(opp_id)
                        results.append(parse_opportunity(hit, keyword, tier_num))
            except Exception:
                logger.exception("Error searching for keyword=%r", keyword)

    logger.info("Grants.gov discovery complete: %d unique opportunities found", len(results))
    return results
