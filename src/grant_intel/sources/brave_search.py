"""Brave Search API — discover active grant opportunities from the web.

API: GET https://api.search.brave.com/res/v1/web/search
Free tier: 2,000 requests/month, 1 request/second.
Auth: X-Subscription-Token header from BRAVE_API_KEY env var.
"""

import logging
import re
from urllib.parse import urlparse

from grant_intel.db import upsert_web_opportunity
from grant_intel.utils.rate_limiter import RateLimiter, request_with_retry

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_rate_limiter = RateLimiter(calls_per_second=1.0)

# Indicators that a search result is a grant/funding opportunity
GRANT_INDICATORS = [
    "apply", "application", "deadline", "rfp", "rfa",
    "request for proposal", "letter of inquiry", "loi",
    "grant program", "funding opportunity", "grant cycle",
    "eligibility", "award", "submit", "guidelines",
]


def search(query: str, api_key: str, count: int = 20) -> list[dict]:
    """Execute a single Brave Search query.

    Returns a list of search result dicts with keys: title, url, description.
    """
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": min(count, 20)}

    try:
        resp = request_with_retry(
            "GET", SEARCH_URL,
            rate_limiter=_rate_limiter,
            headers=headers,
            params=params,
        )
        if resp.status_code != 200:
            logger.warning("Brave Search returned %d for query: %s", resp.status_code, query)
            return []

        data = resp.json()
        web_results = data.get("web", {}).get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
            }
            for r in web_results
        ]
    except Exception:
        logger.exception("Brave Search failed for query: %s", query)
        return []


def is_grant_result(result: dict) -> bool:
    """Heuristic filter: does this result look like a grant opportunity?

    Requires at least 2 grant indicators in the title + description.
    Filters out CDN/file URLs and generic non-page results.
    """
    url = result.get("url", "").lower()
    title = result.get("title", "").lower()

    # Skip CDN, file downloads, and non-page URLs
    if any(s in url for s in ["cdn.", "website-files", ".pdf", ".doc", ".xlsx"]):
        return False
    # Skip results with generic/empty titles
    if title in ("", "website-files", "untitled", "document"):
        return False

    text = f"{result.get('title', '')} {result.get('description', '')}".lower()
    matches = sum(1 for indicator in GRANT_INDICATORS if indicator in text)
    return matches >= 2


def parse_web_opportunity(result: dict, query: str) -> dict:
    """Parse a Brave Search result into a web_opportunity record."""
    title = result.get("title", "")
    description = result.get("description", "")
    text = f"{title} {description}".lower()

    # Extract funder name from URL domain (most reliable signal)
    funder_name = ""
    try:
        domain = urlparse(result.get("url", "")).netloc
        # Strip www. and common suffixes
        domain_name = domain.replace("www.", "").split(".")[0]
        # Skip generic aggregator domains
        skip_domains = {"instrumentl", "fundsforngos", "grantwatch", "grants", "google",
                        "bing", "wikipedia", "youtube", "facebook", "twitter"}
        if domain_name and domain_name not in skip_domains and len(domain_name) > 2:
            # Convert domain to readable name: "lillyendowment" → "Lilly Endowment" isn't easy
            # so just use the title's org name if we can find it
            for sep in [" – ", " — ", " | ", " - "]:
                if sep in title:
                    parts = [p.strip() for p in title.split(sep)]
                    # The last segment is often the site/org name
                    if len(parts[-1]) < 50:
                        funder_name = parts[-1]
                    break
    except Exception:
        pass

    # Try to extract deadline
    deadline = ""
    deadline_patterns = [
        r"deadline[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        r"due[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        r"closes?\s+(\w+\s+\d{1,2},?\s+\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in deadline_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            deadline = match.group(1)
            break

    # Try to extract award amounts
    award_min = None
    award_max = None
    amount_patterns = [
        r"\$(\d[\d,]+)\s*(?:to|[-–])\s*\$(\d[\d,]+)",
        r"up\s+to\s+\$(\d[\d,]+)",
        r"\$(\d[\d,]+)\s+(?:grant|award|each)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 2:
                    award_min = int(groups[0].replace(",", ""))
                    award_max = int(groups[1].replace(",", ""))
                else:
                    award_max = int(groups[0].replace(",", ""))
            except (ValueError, TypeError):
                pass
            break

    return {
        "title": title,
        "funder_name": funder_name,
        "url": result.get("url", ""),
        "description": description,
        "deadline": deadline,
        "award_min": award_min,
        "award_max": award_max,
        "source": "brave_search",
        "search_query": query,
    }


def discover_web_opportunities(queries: list[str], conn, api_key: str) -> dict:
    """Run all search queries and save discovered opportunities.

    Returns stats: {queries_run, results_total, grant_results, saved_new}
    """
    stats = {"queries_run": 0, "results_total": 0, "grant_results": 0, "saved_new": 0}

    for query in queries:
        results = search(query, api_key)
        stats["queries_run"] += 1
        stats["results_total"] += len(results)

        for result in results:
            if not is_grant_result(result):
                continue

            stats["grant_results"] += 1
            opp = parse_web_opportunity(result, query)

            if upsert_web_opportunity(conn, opp):
                stats["saved_new"] += 1
                logger.info("New web opportunity: %s", opp["title"][:80])

        logger.debug("Query %d/%d: '%s' → %d results, %d grant-like",
                      stats["queries_run"], len(queries), query[:50],
                      len(results), stats["grant_results"])

    logger.info(
        "Brave Search complete: %d queries, %d total results, %d grant-like, %d new saved",
        stats["queries_run"], stats["results_total"],
        stats["grant_results"], stats["saved_new"],
    )
    return stats
