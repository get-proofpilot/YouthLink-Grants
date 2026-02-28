"""Foundation enrichment via ProPublica Nonprofit Explorer API.

ProPublica provides: total_revenue, total_assets, NTEE code, filing history.
Free, no auth, rate-limited to ~1 req/2sec (we share the existing limiter).

Originally planned for GivingTuesday 990 Infrastructure API, but that API
returns 403 on all endpoints as of Feb 2026. ProPublica provides the same
data reliably.
"""

import logging

from grant_intel.db import get_foundations_needing_enrichment, update_foundation_enrichment
from grant_intel.sources.propublica import get_organization, search_orgs

logger = logging.getLogger(__name__)


def enrich_foundation(ein: str, name: str = "") -> dict:
    """Fetch enrichment data for a single foundation via ProPublica.

    Tries direct EIN lookup first, then falls back to name search.
    Returns a dict with: total_assets, total_giving, revenue, ntee_code
    (any subset, depending on what ProPublica has).
    """
    data = get_organization(ein)

    # Fallback: search by name if EIN lookup fails
    if not data and name:
        logger.debug("EIN lookup failed for %s, trying name search: %s", ein, name)
        results = search_orgs(name)
        for result in results:
            # Match on name similarity — avoid picking a different org with the same name
            result_name = result.get("name", "").lower()
            search_name = name.lower()
            # Require the search name to be a substring of the result name or vice versa
            if search_name not in result_name and result_name not in search_name:
                continue
            fallback_ein = str(result.get("ein", ""))
            if fallback_ein:
                data = get_organization(fallback_ein)
                if data:
                    break

    if not data:
        return {}

    org = data.get("organization", {})
    filings = data.get("filings_with_data", [])

    result = {}

    # NTEE code
    ntee = org.get("ntee_code", "")
    if ntee:
        result["ntee_code"] = ntee

    # Financial data from org summary
    if org.get("asset_amount"):
        result["total_assets"] = int(org["asset_amount"])
    if org.get("income_amount"):
        result["revenue"] = int(org["income_amount"])

    # Get total giving from the latest filing (grants paid + other disbursements)
    if filings:
        # Sort by tax period descending
        sorted_filings = sorted(
            filings,
            key=lambda f: f.get("tax_prd", 0),
            reverse=True,
        )
        latest = sorted_filings[0]
        # totfuncexpns = total functional expenses (closest to "total giving" for foundations)
        total_expenses = latest.get("totfuncexpns")
        if total_expenses:
            result["total_giving"] = int(total_expenses)
        # If we got assets from filing but not from org summary, use filing data
        if "total_assets" not in result and latest.get("totassetsend"):
            result["total_assets"] = int(latest["totassetsend"])
        if "revenue" not in result and latest.get("totrevenue"):
            result["revenue"] = int(latest["totrevenue"])

    return result


def enrich_foundations_batch(foundations: list[dict], conn) -> dict:
    """Enrich a batch of foundations via ProPublica.

    Returns stats: {enriched: int, skipped: int, failed: int}
    """
    stats = {"enriched": 0, "skipped": 0, "failed": 0}

    for f in foundations:
        ein = f.get("ein", "")
        if not ein:
            stats["skipped"] += 1
            continue

        try:
            data = enrich_foundation(ein, name=f.get("name", ""))
            if data:
                update_foundation_enrichment(conn, ein, data)
                stats["enriched"] += 1
                logger.info(
                    "Enriched %s (EIN %s): assets=%s, revenue=%s, ntee=%s",
                    f.get("name", "?"), ein,
                    data.get("total_assets", "?"),
                    data.get("revenue", "?"),
                    data.get("ntee_code", "?"),
                )
            else:
                stats["skipped"] += 1
                logger.debug("No enrichment data for EIN %s (%s)", ein, f.get("name", ""))
        except Exception:
            stats["failed"] += 1
            logger.exception("Failed to enrich EIN %s", ein)

    logger.info(
        "Enrichment complete: %d enriched, %d skipped, %d failed",
        stats["enriched"], stats["skipped"], stats["failed"],
    )
    return stats


def enrich_all_foundations(conn) -> dict:
    """Enrich all foundations that need enrichment."""
    foundations = get_foundations_needing_enrichment(conn)
    if not foundations:
        logger.info("No foundations need enrichment")
        return {"enriched": 0, "skipped": 0, "failed": 0}

    logger.info("Enriching %d foundations via ProPublica...", len(foundations))
    return enrich_foundations_batch(foundations, conn)
