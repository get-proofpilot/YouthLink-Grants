"""CSV report generation."""

import csv
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def export_opportunities_csv(
    opportunities: list[dict],
    output_dir: str = "output",
) -> str:
    """Export scored grant opportunities to CSV.

    Returns the path to the generated CSV file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"grant_opportunities_{date.today().isoformat()}.csv"
    filepath = Path(output_dir) / filename

    fieldnames = [
        "Rank",
        "Score",
        "Title",
        "Agency",
        "Deadline",
        "Urgency",
        "Award Floor",
        "Award Ceiling",
        "Status",
        "Explanation",
        "URL",
        "Keyword Tier",
        "Matched Keyword",
        "Source",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for rank, opp in enumerate(opportunities, 1):
            writer.writerow({
                "Rank": rank,
                "Score": opp.get("score", "N/A"),
                "Title": opp.get("title", ""),
                "Agency": opp.get("agency", ""),
                "Deadline": opp.get("deadline", ""),
                "Urgency": opp.get("urgency", ""),
                "Award Floor": _format_currency(opp.get("award_floor")),
                "Award Ceiling": _format_currency(opp.get("award_ceiling")),
                "Status": opp.get("status", ""),
                "Explanation": opp.get("explanation", ""),
                "URL": opp.get("url", ""),
                "Keyword Tier": opp.get("keyword_tier", ""),
                "Matched Keyword": opp.get("matched_keyword", ""),
                "Source": opp.get("source", ""),
            })

    logger.info("Exported %d opportunities to %s", len(opportunities), filepath)
    return str(filepath)


def export_foundations_csv(
    foundations: list[dict],
    output_dir: str = "output",
) -> str:
    """Export foundation prospects to CSV.

    Returns the path to the generated CSV file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"foundation_prospects_{date.today().isoformat()}.csv"
    filepath = Path(output_dir) / filename

    fieldnames = [
        "Rank",
        "Score",
        "Foundation Name",
        "EIN",
        "State",
        "Total Giving",
        "Focus Areas",
        "Explanation",
        "Source",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for rank, foundation in enumerate(foundations, 1):
            writer.writerow({
                "Rank": rank,
                "Score": foundation.get("score", "N/A"),
                "Foundation Name": foundation.get("name", ""),
                "EIN": foundation.get("ein", ""),
                "State": foundation.get("state", ""),
                "Total Giving": _format_currency(foundation.get("total_giving")),
                "Focus Areas": foundation.get("focus_areas", ""),
                "Explanation": foundation.get("explanation", ""),
                "Source": foundation.get("source", ""),
            })

    logger.info("Exported %d foundations to %s", len(foundations), filepath)
    return str(filepath)


def _format_currency(value) -> str:
    """Format a number as currency string."""
    if value is None:
        return ""
    try:
        return f"${int(value):,}"
    except (ValueError, TypeError):
        return str(value)
