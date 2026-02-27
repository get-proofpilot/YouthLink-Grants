"""SQLite database setup and operations."""

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    opportunity_id TEXT,
    opportunity_number TEXT,
    title TEXT NOT NULL,
    agency TEXT,
    description TEXT,
    funding_category TEXT,
    award_floor INTEGER,
    award_ceiling INTEGER,
    expected_awards INTEGER,
    deadline TEXT,
    posted_date TEXT,
    status TEXT,
    eligibility TEXT,
    url TEXT,
    keyword_tier INTEGER,
    matched_keyword TEXT,
    raw_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(source, opportunity_id)
);

CREATE TABLE IF NOT EXISTS foundations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ein TEXT UNIQUE,
    city TEXT,
    state TEXT,
    total_assets INTEGER,
    total_giving INTEGER,
    focus_areas TEXT,
    contact_info TEXT,
    website TEXT,
    source TEXT,
    raw_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS foundation_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER REFERENCES foundations(id),
    foundation_ein TEXT,
    recipient_name TEXT,
    recipient_ein TEXT,
    amount INTEGER,
    purpose TEXT,
    tax_year INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS similar_orgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ein TEXT UNIQUE,
    city TEXT,
    state TEXT,
    total_revenue INTEGER,
    total_expenses INTEGER,
    ntee_code TEXT,
    mission TEXT,
    source TEXT,
    raw_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER REFERENCES opportunities(id),
    foundation_id INTEGER REFERENCES foundations(id),
    score INTEGER NOT NULL,
    explanation TEXT,
    urgency TEXT,
    model_used TEXT,
    scored_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER REFERENCES opportunities(id),
    foundation_id INTEGER REFERENCES foundations(id),
    status TEXT DEFAULT 'new',
    notes TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipeline_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER UNIQUE REFERENCES opportunities(id),
    foundation_id INTEGER UNIQUE REFERENCES foundations(id),
    stage TEXT NOT NULL DEFAULT 'discovered',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grant_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER REFERENCES opportunities(id),
    foundation_id INTEGER REFERENCES foundations(id),
    draft_type TEXT NOT NULL,
    funder_name TEXT,
    project_name TEXT,
    requirements_json TEXT,
    sections_json TEXT,
    full_draft TEXT,
    model_used TEXT,
    status TEXT DEFAULT 'draft',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a SQLite connection, creating the database file if needed."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection):
    """Create all tables."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("Database initialized")


def upsert_opportunity(conn: sqlite3.Connection, opp: dict) -> bool:
    """Insert or update an opportunity. Returns True if new."""
    try:
        conn.execute(
            """INSERT INTO opportunities
            (source, opportunity_id, opportunity_number, title, agency, description,
             funding_category, award_floor, award_ceiling, expected_awards,
             deadline, posted_date, status, eligibility, url,
             keyword_tier, matched_keyword, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                opp.get("source", ""),
                opp.get("opportunity_id", ""),
                opp.get("opportunity_number", ""),
                opp.get("title", ""),
                opp.get("agency", ""),
                opp.get("description", ""),
                opp.get("funding_category", ""),
                opp.get("award_floor"),
                opp.get("award_ceiling"),
                opp.get("expected_awards"),
                opp.get("deadline", ""),
                opp.get("posted_date", ""),
                opp.get("status", ""),
                opp.get("eligibility", ""),
                opp.get("url", ""),
                opp.get("keyword_tier", 0),
                opp.get("matched_keyword", ""),
                json.dumps(opp.get("raw", {})),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Already exists, update
        conn.execute(
            """UPDATE opportunities SET
            title=?, agency=?, description=?, status=?, deadline=?,
            updated_at=datetime('now')
            WHERE source=? AND opportunity_id=?""",
            (
                opp.get("title", ""),
                opp.get("agency", ""),
                opp.get("description", ""),
                opp.get("status", ""),
                opp.get("deadline", ""),
                opp.get("source", ""),
                opp.get("opportunity_id", ""),
            ),
        )
        conn.commit()
        return False


def upsert_foundation(conn: sqlite3.Connection, foundation: dict) -> bool:
    """Insert or update a foundation. Returns True if new."""
    try:
        conn.execute(
            """INSERT INTO foundations
            (name, ein, city, state, total_assets, total_giving,
             focus_areas, contact_info, website, source, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                foundation.get("name", ""),
                foundation.get("ein", ""),
                foundation.get("city", ""),
                foundation.get("state", ""),
                foundation.get("total_assets"),
                foundation.get("total_giving"),
                json.dumps(foundation.get("focus_areas", [])),
                foundation.get("contact_info", ""),
                foundation.get("website", ""),
                foundation.get("source", ""),
                json.dumps(foundation.get("raw", {})),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.execute(
            """UPDATE foundations SET
            name=?, total_assets=?, total_giving=?, updated_at=datetime('now')
            WHERE ein=?""",
            (
                foundation.get("name", ""),
                foundation.get("total_assets"),
                foundation.get("total_giving"),
                foundation.get("ein", ""),
            ),
        )
        conn.commit()
        return False


def insert_foundation_grant(conn: sqlite3.Connection, grant: dict):
    """Insert a foundation grant record."""
    conn.execute(
        """INSERT OR IGNORE INTO foundation_grants
        (foundation_id, foundation_ein, recipient_name, recipient_ein,
         amount, purpose, tax_year)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            grant.get("foundation_id"),
            grant.get("foundation_ein", ""),
            grant.get("recipient_name", ""),
            grant.get("recipient_ein", ""),
            grant.get("amount"),
            grant.get("purpose", ""),
            grant.get("tax_year"),
        ),
    )
    conn.commit()


def upsert_similar_org(conn: sqlite3.Connection, org: dict) -> bool:
    """Insert or update a similar org. Returns True if new."""
    try:
        conn.execute(
            """INSERT INTO similar_orgs
            (name, ein, city, state, total_revenue, total_expenses,
             ntee_code, mission, source, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                org.get("name", ""),
                org.get("ein", ""),
                org.get("city", ""),
                org.get("state", ""),
                org.get("total_revenue"),
                org.get("total_expenses"),
                org.get("ntee_code", ""),
                org.get("mission", ""),
                org.get("source", ""),
                json.dumps(org.get("raw", {})),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def insert_score(conn: sqlite3.Connection, score: dict):
    """Insert a match score."""
    conn.execute(
        """INSERT INTO scores
        (opportunity_id, foundation_id, score, explanation, urgency, model_used)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (
            score.get("opportunity_id"),
            score.get("foundation_id"),
            score["score"],
            score.get("explanation", ""),
            score.get("urgency", ""),
            score.get("model_used", ""),
        ),
    )
    conn.commit()


def get_unscored_opportunities(conn: sqlite3.Connection) -> list[dict]:
    """Get opportunities that haven't been scored yet."""
    rows = conn.execute(
        """SELECT o.* FROM opportunities o
        LEFT JOIN scores s ON s.opportunity_id = o.id
        WHERE s.id IS NULL
        ORDER BY o.deadline ASC"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_unscored_foundations(conn: sqlite3.Connection) -> list[dict]:
    """Get foundations that haven't been scored yet."""
    rows = conn.execute(
        """SELECT f.* FROM foundations f
        LEFT JOIN scores s ON s.foundation_id = f.id
        WHERE s.id IS NULL
        ORDER BY f.total_giving DESC"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_top_opportunities(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    """Get top-scored opportunities with their scores."""
    rows = conn.execute(
        """SELECT o.*, s.score, s.explanation, s.urgency
        FROM opportunities o
        JOIN scores s ON s.opportunity_id = o.id
        WHERE o.status IN ('posted', 'forecasted')
        ORDER BY s.score DESC, o.deadline ASC
        LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_top_foundations(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    """Get top-scored foundations with their scores."""
    rows = conn.execute(
        """SELECT f.*, s.score, s.explanation
        FROM foundations f
        JOIN scores s ON s.foundation_id = f.id
        ORDER BY s.score DESC, f.total_giving DESC
        LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_all_opportunities(conn: sqlite3.Connection) -> list[dict]:
    """Get all opportunities with optional scores."""
    rows = conn.execute(
        """SELECT o.*, s.score, s.explanation, s.urgency
        FROM opportunities o
        LEFT JOIN scores s ON s.opportunity_id = o.id
        ORDER BY s.score DESC NULLS LAST, o.deadline ASC"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_all_foundations(conn: sqlite3.Connection) -> list[dict]:
    """Get all foundations with optional scores."""
    rows = conn.execute(
        """SELECT f.*, s.score, s.explanation
        FROM foundations f
        LEFT JOIN scores s ON s.foundation_id = f.id
        ORDER BY s.score DESC NULLS LAST, f.total_giving DESC"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_pipeline_stats(conn: sqlite3.Connection) -> dict:
    """Get summary statistics for the pipeline."""
    opp_count = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    foundation_count = conn.execute("SELECT COUNT(*) FROM foundations").fetchone()[0]
    scored_opps = conn.execute(
        "SELECT COUNT(DISTINCT opportunity_id) FROM scores WHERE opportunity_id IS NOT NULL"
    ).fetchone()[0]
    scored_foundations = conn.execute(
        "SELECT COUNT(DISTINCT foundation_id) FROM scores WHERE foundation_id IS NOT NULL"
    ).fetchone()[0]
    draft_count = conn.execute("SELECT COUNT(*) FROM grant_drafts").fetchone()[0]
    return {
        "total_opportunities": opp_count,
        "total_foundations": foundation_count,
        "scored_opportunities": scored_opps,
        "scored_foundations": scored_foundations,
        "total_drafts": draft_count,
    }


# ---------------------------------------------------------------------------
# Grant drafts CRUD
# ---------------------------------------------------------------------------


def insert_draft(conn: sqlite3.Connection, draft: dict) -> int:
    """Insert a grant draft record. Returns the new draft ID."""
    cursor = conn.execute(
        """INSERT INTO grant_drafts
        (opportunity_id, foundation_id, draft_type, funder_name, project_name,
         requirements_json, sections_json, full_draft, model_used, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            draft.get("opportunity_id"),
            draft.get("foundation_id"),
            draft.get("draft_type", ""),
            draft.get("funder_name", ""),
            draft.get("project_name", ""),
            draft.get("requirements_json", "{}"),
            draft.get("sections_json", "{}"),
            draft.get("full_draft", ""),
            draft.get("model_used", ""),
            draft.get("status", "draft"),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_draft(conn: sqlite3.Connection, draft_id: int) -> dict | None:
    """Get a single draft by ID."""
    row = conn.execute(
        "SELECT * FROM grant_drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    return dict(row) if row else None


def get_drafts_by_opportunity(conn: sqlite3.Connection, opp_id: int) -> list[dict]:
    """Get all drafts for a given opportunity."""
    rows = conn.execute(
        "SELECT * FROM grant_drafts WHERE opportunity_id = ? ORDER BY created_at DESC",
        (opp_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_drafts_by_foundation(conn: sqlite3.Connection, foundation_id: int) -> list[dict]:
    """Get all drafts for a given foundation."""
    rows = conn.execute(
        "SELECT * FROM grant_drafts WHERE foundation_id = ? ORDER BY created_at DESC",
        (foundation_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_draft_status(conn: sqlite3.Connection, draft_id: int, status: str):
    """Update the status of a draft (e.g., 'draft', 'review', 'submitted')."""
    conn.execute(
        "UPDATE grant_drafts SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, draft_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Dashboard queries
# ---------------------------------------------------------------------------


def get_opportunity_by_id(conn: sqlite3.Connection, opp_id: int) -> dict | None:
    """Get a single opportunity with its score."""
    row = conn.execute(
        """SELECT o.*, s.score, s.explanation, s.urgency
        FROM opportunities o
        LEFT JOIN scores s ON s.opportunity_id = o.id
        WHERE o.id = ?""",
        (opp_id,),
    ).fetchone()
    return dict(row) if row else None


def get_foundation_by_id(conn: sqlite3.Connection, foundation_id: int) -> dict | None:
    """Get a single foundation with its score."""
    row = conn.execute(
        """SELECT f.*, s.score, s.explanation
        FROM foundations f
        LEFT JOIN scores s ON s.foundation_id = f.id
        WHERE f.id = ?""",
        (foundation_id,),
    ).fetchone()
    return dict(row) if row else None


def get_foundation_grants_list(conn: sqlite3.Connection, foundation_id: int) -> list[dict]:
    """Get all grants made by a specific foundation."""
    rows = conn.execute(
        """SELECT fg.* FROM foundation_grants fg
        WHERE fg.foundation_id = ?
        ORDER BY fg.amount DESC""",
        (foundation_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_all_drafts(conn: sqlite3.Connection) -> list[dict]:
    """Get all drafts with linked opportunity/foundation names."""
    rows = conn.execute(
        """SELECT gd.*,
            o.title as opportunity_title,
            f.name as foundation_name
        FROM grant_drafts gd
        LEFT JOIN opportunities o ON gd.opportunity_id = o.id
        LEFT JOIN foundations f ON gd.foundation_id = f.id
        ORDER BY gd.created_at DESC"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_score_distribution(conn: sqlite3.Connection) -> dict:
    """Get count of scores by range."""
    row = conn.execute(
        """SELECT
            COALESCE(SUM(CASE WHEN score >= 7 THEN 1 ELSE 0 END), 0) as high,
            COALESCE(SUM(CASE WHEN score >= 4 AND score < 7 THEN 1 ELSE 0 END), 0) as medium,
            COALESCE(SUM(CASE WHEN score < 4 THEN 1 ELSE 0 END), 0) as low
        FROM scores"""
    ).fetchone()
    return {"high": row[0], "medium": row[1], "low": row[2]}


def get_upcoming_deadlines(conn: sqlite3.Connection, days: int = 90) -> list[dict]:
    """Get opportunities with deadlines within N days."""
    rows = conn.execute(
        """SELECT o.*, s.score, s.urgency
        FROM opportunities o
        LEFT JOIN scores s ON s.opportunity_id = o.id
        WHERE o.deadline != '' AND o.deadline IS NOT NULL
        AND date(o.deadline) BETWEEN date('now') AND date('now', '+' || ? || ' days')
        ORDER BY o.deadline ASC""",
        (days,),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Pipeline entries CRUD
# ---------------------------------------------------------------------------


def upsert_pipeline_entry(
    conn: sqlite3.Connection,
    opportunity_id: int | None = None,
    foundation_id: int | None = None,
    stage: str = "discovered",
    notes: str = "",
) -> int:
    """Insert or update a pipeline entry. Returns entry ID."""
    if opportunity_id:
        existing = conn.execute(
            "SELECT id FROM pipeline_entries WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
    elif foundation_id:
        existing = conn.execute(
            "SELECT id FROM pipeline_entries WHERE foundation_id = ?",
            (foundation_id,),
        ).fetchone()
    else:
        raise ValueError("Must provide opportunity_id or foundation_id")

    if existing:
        entry_id = existing[0]
        conn.execute(
            "UPDATE pipeline_entries SET stage = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
            (stage, notes, entry_id),
        )
        conn.commit()
        return entry_id

    cursor = conn.execute(
        """INSERT INTO pipeline_entries (opportunity_id, foundation_id, stage, notes)
        VALUES (?, ?, ?, ?)""",
        (opportunity_id, foundation_id, stage, notes),
    )
    conn.commit()
    return cursor.lastrowid


def update_pipeline_stage(conn: sqlite3.Connection, entry_id: int, stage: str, notes: str = ""):
    """Update a pipeline entry's stage."""
    if notes:
        conn.execute(
            "UPDATE pipeline_entries SET stage = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
            (stage, notes, entry_id),
        )
    else:
        conn.execute(
            "UPDATE pipeline_entries SET stage = ?, updated_at = datetime('now') WHERE id = ?",
            (stage, entry_id),
        )
    conn.commit()


def update_pipeline_notes(conn: sqlite3.Connection, entry_id: int, notes: str):
    """Update pipeline entry notes."""
    conn.execute(
        "UPDATE pipeline_entries SET notes = ?, updated_at = datetime('now') WHERE id = ?",
        (notes, entry_id),
    )
    conn.commit()


def get_all_pipeline_entries(conn: sqlite3.Connection) -> list[dict]:
    """Get all pipeline entries with linked data."""
    rows = conn.execute(
        """SELECT pe.*,
            o.title as opportunity_title, o.agency, o.deadline,
            f.name as foundation_name,
            s.score
        FROM pipeline_entries pe
        LEFT JOIN opportunities o ON pe.opportunity_id = o.id
        LEFT JOIN foundations f ON pe.foundation_id = f.id
        LEFT JOIN scores s ON (
            (s.opportunity_id = pe.opportunity_id AND pe.opportunity_id IS NOT NULL)
            OR (s.foundation_id = pe.foundation_id AND pe.foundation_id IS NOT NULL)
        )
        ORDER BY pe.updated_at DESC"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_pipeline_by_stage(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Group pipeline entries by stage for dashboard view."""
    entries = get_all_pipeline_entries(conn)
    grouped: dict[str, list[dict]] = {
        "discovered": [], "drafting": [], "submitted": [],
        "awarded": [], "declined": [],
    }
    for entry in entries:
        stage = entry.get("stage", "discovered")
        grouped.setdefault(stage, []).append(entry)
    return grouped


def get_pipeline_entry(conn: sqlite3.Connection, entry_id: int) -> dict | None:
    """Get a single pipeline entry by ID."""
    row = conn.execute(
        "SELECT * FROM pipeline_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return dict(row) if row else None


def get_pipeline_entry_by_target(
    conn: sqlite3.Connection,
    opportunity_id: int | None = None,
    foundation_id: int | None = None,
) -> dict | None:
    """Get a pipeline entry by opportunity or foundation ID."""
    if opportunity_id:
        row = conn.execute(
            "SELECT * FROM pipeline_entries WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
    elif foundation_id:
        row = conn.execute(
            "SELECT * FROM pipeline_entries WHERE foundation_id = ?",
            (foundation_id,),
        ).fetchone()
    else:
        return None
    return dict(row) if row else None


def get_dashboard_stats(conn: sqlite3.Connection) -> dict:
    """Get extended dashboard statistics."""
    base = get_pipeline_stats(conn)
    pipeline_count = conn.execute("SELECT COUNT(*) FROM pipeline_entries").fetchone()[0]
    base["pipeline_entries"] = pipeline_count

    # Deadline breakdown
    upcoming_30 = conn.execute(
        """SELECT COUNT(*) FROM opportunities
        WHERE deadline != '' AND deadline IS NOT NULL
        AND date(deadline) BETWEEN date('now') AND date('now', '+30 days')"""
    ).fetchone()[0]
    upcoming_60 = conn.execute(
        """SELECT COUNT(*) FROM opportunities
        WHERE deadline != '' AND deadline IS NOT NULL
        AND date(deadline) BETWEEN date('now', '+31 days') AND date('now', '+60 days')"""
    ).fetchone()[0]
    base["deadlines_30"] = upcoming_30
    base["deadlines_60"] = upcoming_60

    return base
