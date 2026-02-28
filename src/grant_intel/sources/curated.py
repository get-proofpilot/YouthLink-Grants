"""Seed curated, pre-vetted foundations into the database."""

import logging

from grant_intel.config import CURATED_FOUNDATIONS
from grant_intel.db import upsert_foundation

logger = logging.getLogger(__name__)


def seed_curated_foundations(conn) -> int:
    """Upsert all curated foundations. Returns count of newly inserted."""
    new_count = 0
    for entry in CURATED_FOUNDATIONS:
        foundation = {
            "name": entry["name"],
            "ein": entry["ein"],
            "city": entry.get("city", ""),
            "state": entry.get("state", ""),
            "total_assets": entry.get("total_assets"),
            "total_giving": entry.get("total_giving"),
            "focus_areas": entry.get("focus_areas", []),
            "contact_info": "",
            "website": entry.get("website", ""),
            "source": "curated",
            "raw": {"curated": True, "accepts_applications": entry.get("accepts_applications")},
        }
        if upsert_foundation(conn, foundation):
            new_count += 1
            logger.info("Seeded new foundation: %s (EIN %s)", entry["name"], entry["ein"])
        else:
            logger.debug("Foundation already exists: %s", entry["name"])

    # Set accepts_applications flag on curated foundations
    for entry in CURATED_FOUNDATIONS:
        accepts = 1 if entry.get("accepts_applications") else 0
        conn.execute(
            "UPDATE foundations SET accepts_applications = ? WHERE ein = ?",
            (accepts, entry["ein"]),
        )
    conn.commit()

    logger.info("Curated seeding complete: %d new of %d total", new_count, len(CURATED_FOUNDATIONS))
    return new_count
