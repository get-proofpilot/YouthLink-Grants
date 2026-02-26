"""IRS 990-PF XML parser for foundation grant research."""

import logging
from io import BytesIO

from lxml import etree

from grant_intel.utils.rate_limiter import RateLimiter, request_with_retry

logger = logging.getLogger(__name__)

# IRS e-file XML is available on S3
IRS_XML_BASE = "https://s3.amazonaws.com/irs-form-990"

_rate_limiter = RateLimiter(calls_per_second=2.0)

# Common XML namespaces in IRS 990-PF filings
NAMESPACES = {
    "irs": "http://www.irs.gov/efile",
}

# Keywords to match in grant recipients/purposes
MATCH_KEYWORDS = [
    "youth ministry",
    "youth pastor",
    "pastoral",
    "christian",
    "church",
    "ministry",
    "faith",
    "clergy",
    "arizona",
    "leadership training",
    "religious",
]


def download_990pf_xml(object_id: str) -> bytes | None:
    """Download a 990-PF XML filing from IRS S3 bucket."""
    url = f"{IRS_XML_BASE}/{object_id}_public.xml"
    try:
        response = request_with_retry("GET", url, rate_limiter=_rate_limiter)
        if response.status_code == 404:
            logger.debug("990-PF XML not found: %s", object_id)
            return None
        response.raise_for_status()
        return response.content
    except Exception:
        logger.exception("Error downloading 990-PF XML: %s", object_id)
        return None


def parse_990pf_grants(xml_data: bytes, foundation_ein: str = "") -> list[dict]:
    """Parse grant disbursements from a 990-PF XML filing.

    Extracts grants from GrantOrContributionPdDuringYr elements.
    """
    grants = []

    try:
        tree = etree.parse(BytesIO(xml_data))
        root = tree.getroot()
    except etree.XMLSyntaxError:
        logger.warning("Invalid XML in 990-PF filing")
        return grants

    # Try both namespaced and non-namespaced paths
    grant_elements = _find_grant_elements(root)

    for elem in grant_elements:
        grant = _parse_grant_element(elem, root.nsmap)
        if grant:
            grant["foundation_ein"] = foundation_ein
            grants.append(grant)

    logger.debug(
        "Parsed %d grants from 990-PF (EIN: %s)",
        len(grants),
        foundation_ein,
    )
    return grants


def _find_grant_elements(root) -> list:
    """Find grant elements in the XML tree, handling namespace variations."""
    elements = []

    # Common element names across 990-PF schema versions
    grant_paths = [
        ".//GrantOrContributionPdDurYrGrp",
        ".//GrantOrContributionPdDuringYr",
        ".//{http://www.irs.gov/efile}GrantOrContributionPdDurYrGrp",
        ".//{http://www.irs.gov/efile}GrantOrContributionPdDuringYr",
    ]

    for path in grant_paths:
        found = root.findall(path)
        if found:
            elements.extend(found)
            break

    return elements


def _parse_grant_element(elem, nsmap: dict) -> dict | None:
    """Parse a single grant element into a dict."""
    ns = nsmap.get(None, "")
    prefix = f"{{{ns}}}" if ns else ""

    # Recipient name (business or person)
    recipient_name = (
        _get_text(elem, f".//{prefix}RecipientBusinessName//{prefix}BusinessNameLine1Txt")
        or _get_text(elem, f".//{prefix}RecipientBusinessName//{prefix}BusinessNameLine1")
        or _get_text(elem, f".//{prefix}RecipientPersonNm")
        or _get_text(elem, ".//RecipientBusinessName//BusinessNameLine1Txt")
        or _get_text(elem, ".//RecipientBusinessName//BusinessNameLine1")
        or _get_text(elem, ".//RecipientPersonNm")
        or ""
    )

    # Recipient EIN
    recipient_ein = (
        _get_text(elem, f".//{prefix}RecipientEIN")
        or _get_text(elem, ".//RecipientEIN")
        or ""
    )

    # Grant amount
    amount_str = (
        _get_text(elem, f".//{prefix}Amt")
        or _get_text(elem, f".//{prefix}GrantOrContributionAmt")
        or _get_text(elem, ".//Amt")
        or _get_text(elem, ".//GrantOrContributionAmt")
        or "0"
    )
    try:
        amount = int(amount_str)
    except ValueError:
        amount = 0

    # Purpose
    purpose = (
        _get_text(elem, f".//{prefix}GrantOrContributionPurposeTxt")
        or _get_text(elem, f".//{prefix}PurposeOfGrantOrContriTxt")
        or _get_text(elem, ".//GrantOrContributionPurposeTxt")
        or _get_text(elem, ".//PurposeOfGrantOrContriTxt")
        or ""
    )

    if not recipient_name and not amount:
        return None

    return {
        "recipient_name": recipient_name,
        "recipient_ein": recipient_ein,
        "amount": amount,
        "purpose": purpose,
    }


def _get_text(elem, path: str) -> str:
    """Get text content of an element found by xpath."""
    found = elem.find(path)
    if found is not None and found.text:
        return found.text.strip()
    return ""


def filter_relevant_grants(grants: list[dict]) -> list[dict]:
    """Filter grants to those matching YLM-relevant keywords."""
    relevant = []
    for grant in grants:
        searchable = (
            f"{grant.get('recipient_name', '')} {grant.get('purpose', '')}"
        ).lower()
        if any(kw in searchable for kw in MATCH_KEYWORDS):
            relevant.append(grant)
    return relevant


def research_foundation_grants(
    foundation_eins: list[str],
    object_ids: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Research grants made by a list of foundations.

    If object_ids is provided (mapping EIN -> list of S3 object IDs),
    downloads and parses those specific 990-PF filings.
    Otherwise, this is a no-op (need object IDs from ProPublica filings).

    Returns list of grant dicts with foundation_ein, recipient info, amounts.
    """
    all_grants = []

    if not object_ids:
        logger.info(
            "No 990-PF object IDs provided; skipping IRS XML parsing. "
            "Foundation grant data will come from ProPublica filings."
        )
        return all_grants

    for ein in foundation_eins:
        ids = object_ids.get(ein, [])
        for obj_id in ids:
            xml_data = download_990pf_xml(obj_id)
            if not xml_data:
                continue

            grants = parse_990pf_grants(xml_data, foundation_ein=ein)
            relevant = filter_relevant_grants(grants)
            all_grants.extend(relevant)
            logger.info(
                "EIN %s: %d total grants, %d relevant",
                ein,
                len(grants),
                len(relevant),
            )

    logger.info("IRS 990-PF research complete: %d relevant grants found", len(all_grants))
    return all_grants
