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
