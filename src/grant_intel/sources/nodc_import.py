"""NODC (Nonprofit Open Data Collective) foundation grants CSV importer.

Imports grant disbursement records from the NODC 990 grants dataset.
This reverses the discovery model: instead of searching by foundation name,
we find foundations by what they've actually funded.
"""

import csv
import logging

from grant_intel.db import get_foundation_by_ein, insert_foundation_grant, upsert_foundation

logger = logging.getLogger(__name__)

# Keywords indicating grants relevant to pastoral/youth/ministry work
RELEVANCE_KEYWORDS = [
    "youth ministry", "youth pastor", "pastoral", "christian",
    "church", "clergy", "minister", "ministry", "faith",
    "evangelical", "bible", "theological", "seminary",
    "worship", "discipleship", "spiritual", "chaplain",
    "leadership development", "youth worker", "youth development",
    "community outreach", "after school", "mentoring",
    "capacity building", "nonprofit training",
]

# Common column name mappings (NODC CSVs vary in headers)
COLUMN_MAPS = {
    "filer_ein": ["EIN", "ein", "filer_ein", "FILER_EIN", "foundation_ein"],
    "filer_name": ["NAME", "name", "filer_name", "FILER_NAME", "foundation_name", "OrganizationName"],
    "recipient_name": ["RecipientPersonNm", "recipient_name", "RECIPIENT_NAME", "RecipientBusinessName",
                       "grantee_name", "GranteeNm"],
    "recipient_ein": ["RecipientEIN", "recipient_ein", "RECIPIENT_EIN", "grantee_ein", "GranteeEIN"],
    "amount": ["CashGrantAmt", "amount", "AMOUNT", "grant_amount", "Amt", "GrantAmt"],
    "purpose": ["PurposeOfGrantTxt", "purpose", "PURPOSE", "grant_purpose", "PurposeTxt", "Description"],
    "tax_year": ["TaxYr", "tax_year", "TAX_YEAR", "TaxPeriod", "tax_period"],
    "city": ["RecipientCityNm", "city", "CITY", "filer_city", "CityNm"],
    "state": ["RecipientStateAbbreviationCd", "state", "STATE", "filer_state", "StateAbbreviationCd"],
}


def _map_columns(headers: list[str]) -> dict[str, str | None]:
    """Auto-detect column mapping from CSV headers."""
    header_set = set(headers)
    mapping = {}
    for field, candidates in COLUMN_MAPS.items():
        mapping[field] = None
        for candidate in candidates:
            if candidate in header_set:
                mapping[field] = candidate
                break
    return mapping


def _is_relevant(purpose: str, recipient_name: str) -> bool:
    """Check if a grant record is relevant based on purpose/recipient keywords."""
    text = f"{purpose} {recipient_name}".lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def import_nodc_grants(csv_path: str, conn, filter_relevant: bool = True) -> dict:
    """Import NODC grant records from CSV.

    Args:
        csv_path: Path to the NODC grants CSV file.
        conn: SQLite connection.
        filter_relevant: If True, only import grants matching relevance keywords.

    Returns:
        Stats dict: {total_rows, imported, filtered_out, foundations_discovered}
    """
    stats = {
        "total_rows": 0,
        "imported": 0,
        "filtered_out": 0,
        "foundations_discovered": 0,
        "errors": 0,
    }

    seen_eins = set()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        col_map = _map_columns(reader.fieldnames or [])

        if not col_map["filer_ein"]:
            logger.error("CSV missing required EIN column. Headers: %s", reader.fieldnames)
            return stats

        logger.info("Column mapping: %s", {k: v for k, v in col_map.items() if v})

        for row in reader:
            stats["total_rows"] += 1

            filer_ein = (row.get(col_map["filer_ein"]) or "").strip().replace("-", "")
            filer_name = (row.get(col_map["filer_name"] or "") or "").strip()
            recipient_name = (row.get(col_map["recipient_name"] or "") or "").strip()
            recipient_ein = (row.get(col_map["recipient_ein"] or "") or "").strip().replace("-", "")
            purpose = (row.get(col_map["purpose"] or "") or "").strip()

            # Parse amount
            amount_str = (row.get(col_map["amount"] or "") or "0").strip()
            try:
                amount = int(float(amount_str.replace(",", "").replace("$", "")))
            except (ValueError, TypeError):
                amount = 0

            # Parse tax year
            tax_year_str = (row.get(col_map["tax_year"] or "") or "").strip()
            try:
                tax_year = int(tax_year_str[:4]) if tax_year_str else None
            except (ValueError, TypeError):
                tax_year = None

            # Filter by relevance
            if filter_relevant and not _is_relevant(purpose, recipient_name):
                stats["filtered_out"] += 1
                continue

            # Auto-discover new foundations from grant records
            if filer_ein and filer_ein not in seen_eins:
                seen_eins.add(filer_ein)
                existing = get_foundation_by_ein(conn, filer_ein)
                if not existing:
                    city = (row.get(col_map["city"] or "") or "").strip()
                    state = (row.get(col_map["state"] or "") or "").strip()
                    foundation = {
                        "name": filer_name or f"Foundation EIN {filer_ein}",
                        "ein": filer_ein,
                        "city": city,
                        "state": state,
                        "source": "nodc_csv",
                        "focus_areas": [],
                        "raw": {"discovered_via": "nodc_grant_import"},
                    }
                    if upsert_foundation(conn, foundation):
                        stats["foundations_discovered"] += 1
                        logger.debug("Discovered foundation: %s (EIN %s)", filer_name, filer_ein)

            # Look up foundation_id
            foundation = get_foundation_by_ein(conn, filer_ein) if filer_ein else None
            foundation_id = foundation["id"] if foundation else None

            try:
                grant = {
                    "foundation_id": foundation_id,
                    "foundation_ein": filer_ein,
                    "recipient_name": recipient_name,
                    "recipient_ein": recipient_ein,
                    "amount": amount,
                    "purpose": purpose,
                    "tax_year": tax_year,
                }
                insert_foundation_grant(conn, grant)
                stats["imported"] += 1
            except Exception:
                stats["errors"] += 1
                if stats["errors"] <= 5:
                    logger.exception("Error importing grant row %d", stats["total_rows"])

            # Progress logging every 10k rows
            if stats["total_rows"] % 10000 == 0:
                logger.info(
                    "Progress: %d rows processed, %d imported, %d filtered",
                    stats["total_rows"], stats["imported"], stats["filtered_out"],
                )

    logger.info(
        "NODC import complete: %d total rows, %d imported, %d filtered, %d foundations discovered",
        stats["total_rows"], stats["imported"], stats["filtered_out"],
        stats["foundations_discovered"],
    )
    return stats
