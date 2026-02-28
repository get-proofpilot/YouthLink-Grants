# Architecture

**Analysis Date:** 2026-02-28

## Pattern Overview

**Overall:** Dual-mode CLI pipeline + Flask web dashboard over a single SQLite store

The system operates as two complementary modes sharing the same codebase and database:
1. **CLI pipeline** — `grant-intel` command-line tool for scheduled/automated runs
2. **Flask dashboard** — Admin web UI for interactive exploration, scoring, and draft generation

Both modes share `src/grant_intel/db.py` as the sole data layer and `src/grant_intel/config.py` for org profile configuration.

**Key Characteristics:**
- No ORM — all SQL is handwritten in `db.py` using `sqlite3` with `Row` factory
- All business logic lives in domain submodules (`sources/`, `scoring/`, `writer/`, `delivery/`)
- Flask app uses an application factory (`create_app()`) with Blueprint-per-domain routing
- Claude AI (Anthropic SDK) is used for scoring (Haiku) and grant writing (Sonnet)
- The scoring funnel is 2-tier: rule engine first (free/instant), Claude AI second (threshold-gated)

---

## Layers

**Configuration Layer:**
- Purpose: Load org profile from YAML + credentials from `.env`
- Location: `src/grant_intel/config.py`
- Contains: `OrgProfile` dataclass, `Config` dataclass, `load_config()`, curated foundation lists, Brave Search queries
- Depends on: `yaml`, `python-dotenv`
- Used by: CLI (`cli.py`), Flask app factory (`dashboard/app.py`), all scoring/writing modules

**Data Layer:**
- Purpose: All SQLite read/write operations — single source of truth for all persistence
- Location: `src/grant_intel/db.py`
- Contains: `SCHEMA_SQL` (all table definitions), upsert/insert/query functions for every entity, migration helpers
- Depends on: `sqlite3` stdlib only
- Used by: CLI commands, Flask routes, scoring modules, weekly agent

**Sources Layer (Discovery):**
- Purpose: Fetch and normalize external grant/foundation data into standard dicts
- Location: `src/grant_intel/sources/`
- Contains: `grants_gov.py`, `propublica.py`, `brave_search.py`, `curated.py`, `givingtuesday.py`, `irs990.py`, `nodc_import.py`
- Depends on: `requests`, `grant_intel.utils.rate_limiter`, external APIs
- Used by: CLI commands, Flask `actions_bp`, weekly scoring agent

**Scoring Layer:**
- Purpose: Evaluate and rank opportunities and foundations for mission fit
- Location: `src/grant_intel/scoring/`
- Contains: `rules.py` (keyword/CFDA/agency rule engine), `matcher.py` (Claude AI scoring + funnel orchestration), `weekly.py` (scheduled weekly scoring cycle with cooldown)
- Depends on: `anthropic`, `grant_intel.db`, `grant_intel.config.OrgProfile`
- Used by: CLI `score` and `weekly` commands, Flask `actions_bp`, dashboard startup pipeline

**Writer Layer (AI Grant Drafting):**
- Purpose: AI-assisted grant narrative and LOI generation
- Location: `src/grant_intel/writer/`
- Contains: `agent.py` (orchestrator), `sections.py` (section-by-section generation with context threading), `prompts.py` (system prompt, section prompts, LOI prompt, banned-words list), `extractor.py` (NOFA/RFP requirement extraction from text or URL)
- Depends on: `anthropic`, `jinja2`, `lxml`, `requests`
- Used by: CLI `draft` and `loi` commands, Flask `actions_bp`

**Delivery Layer:**
- Purpose: Export pipeline output to CSV and email digest
- Location: `src/grant_intel/delivery/`
- Contains: `csv_export.py`, `email_digest.py`
- Depends on: `jinja2`, `smtplib` stdlib
- Used by: CLI `report` and `digest` commands

**Dashboard Layer:**
- Purpose: Flask web application for interactive grant management
- Location: `src/grant_intel/dashboard/`
- Contains: `app.py` (factory), `auth.py` (Flask-Login single admin user), `filters.py` (Jinja2 template filters), `priority.py` (composite Priority Score + requirement match analysis), `routes/` (one Blueprint per domain)
- Depends on: `flask`, `flask-login`, `grant_intel.db`, all business logic layers
- Used by: Directly — this is the web entry point

---

## Data Flow

**Full Pipeline (CLI `run` command):**

1. `grant-intel run` invokes `search` → `research` → `weekly` → `report` → `digest` in sequence
2. `search`: `sources/grants_gov.py` calls Grants.gov REST API with tiered keywords → `upsert_opportunity()` into `opportunities` table
3. `research`: `sources/propublica.py` fetches 990 filings for similar orgs and keyword-searches for foundation prospects → `upsert_foundation()` and `upsert_similar_org()`
4. `weekly`: `scoring/weekly.py` orchestrates: re-runs search/research, then rule-scores all unscored opps via `scoring/rules.py`, then AI-scores candidates with `rule_score >= 6` via `scoring/matcher.py` using Claude Haiku
5. `report`: `delivery/csv_export.py` reads all scored records and writes CSV files to `output/`
6. `digest`: `delivery/email_digest.py` renders `templates/email_digest.html.j2` and sends via SMTP

**Scoring Funnel (2-tier):**

1. **Tier 1 — Rule engine** (`scoring/rules.py`): Every opportunity receives a `rule_score` (1–10) computed from title keywords, description content, agency name, CFDA codes, award range, deadline proximity, and eligibility text. Base score is 5; deltas are applied from each signal. Kill overrides cap score at 2 for science/defense/medical agencies. Runs instantly, free, no API calls.
2. **Tier 2 — Claude AI** (`scoring/matcher.py`): Only opportunities with `rule_score >= threshold` (default 6) are sent to Claude Haiku in batches of 5. Returns per-opportunity `score` (1–10), `explanation`, and `urgency`. Results stored in `scores` table with `opportunity_id` or `foundation_id` FK.

**Dashboard Startup Pipeline (on empty DB):**

When `AUTO_POPULATE=true` (default) and the `opportunities` table is empty, `dashboard/app.py` fires `_run_data_pipeline()` in a background thread that runs: Grants.gov search → similar org research → foundation keyword search → curated foundation seeding → GivingTuesday 990 enrichment → rule-only scoring.

**Grant Draft Generation Flow:**

1. User triggers `draft` or `loi` (CLI or dashboard)
2. Optional: `writer/extractor.py` fetches and parses NOFA/RFP text using Claude Haiku → structured `requirements` dict
3. `writer/agent.py` calls `writer/sections.py` once per section in order; each call passes all previously-written sections as context for consistency
4. Sections are rendered via `templates/grant_draft.md.j2` into a Markdown file in `output/drafts/`
5. Draft record stored in `grant_drafts` table with `sections_json`, `requirements_json`, and full text

**State Management:**
- All persistent state is in SQLite at `data/grants.db`
- Scheduling state (last weekly run) is stored in the `settings` table as key-value pairs
- Flask session state is managed by Flask-Login (single `AdminUser` session)
- Config state is loaded once at app startup and stored in `app.config["GRANT_CONFIG"]`

---

## Key Abstractions

**OrgProfile:**
- Purpose: Typed representation of the nonprofit's identity, mission, and metadata
- Examples: `src/grant_intel/config.py` (lines 11–24)
- Pattern: Python `@dataclass`; passed to scoring prompts, writer prompts, priority calculator, eligibility checker

**Opportunity:**
- Purpose: A federal grant opportunity from Grants.gov or a web-discovered grant
- Tables: `opportunities` (Grants.gov), `web_opportunities` (Brave Search)
- Pattern: Raw dict from DB query; augmented with `score`/`urgency` from `scores` table via LEFT JOIN; further enriched with `priority_score` by `dashboard/priority.py`

**Foundation:**
- Purpose: A private foundation or potential funder, sourced from ProPublica, curated list, or GivingTuesday 990 API
- Table: `foundations`, with related `foundation_grants` for past giving history
- Pattern: Raw dict with JSON-serialized `focus_areas`; enriched with `score` via LEFT JOIN

**Score:**
- Purpose: Links a scoring result to either an opportunity or a foundation
- Table: `scores` with nullable `opportunity_id`, `foundation_id`, `web_opportunity_id` FKs
- Pattern: Either AI-generated (Haiku) or unused for rule scores (rule scores live inline on `opportunities.rule_score`)

**Draft:**
- Purpose: An AI-generated grant narrative or Letter of Inquiry
- Table: `grant_drafts`
- Pattern: Stores `requirements_json` (what the funder wants), `sections_json` (dict of section name → text), `full_draft` (assembled Markdown), and `status` (draft/review/submitted)

**Pipeline Entry:**
- Purpose: Tracks the relationship management stage of a grant opportunity or foundation
- Table: `pipeline_entries`
- Stages: `discovered` → `drafting` → `submitted` → `awarded` / `declined`
- Pattern: One entry per opportunity or foundation; stage updated via dashboard UI

---

## Entry Points

**CLI Tool (`grant-intel`):**
- Location: `src/grant_intel/cli.py`
- Triggers: Installed as console script via `pyproject.toml` entry point `grant-intel = "grant_intel.cli:cli"`
- Commands: `db-init`, `search`, `research`, `score`, `report`, `digest`, `weekly`, `run`, `draft`, `loi`, `seed-foundations`, `enrich`, `brave-search`, `import-grants`, `dashboard`, `status`
- Responsibilities: Each command loads config via `--config` flag, gets a SQLite connection, invokes the relevant module, reports results to stdout

**Flask Application Factory:**
- Location: `src/grant_intel/dashboard/app.py` → `create_app()`
- Triggers: `gunicorn 'grant_intel.dashboard.app:create_app()'` (production) or `grant-intel dashboard` (dev)
- Responsibilities: Initialize DB, trigger background data pipeline if empty, register Flask-Login, register all Blueprints, register Jinja2 filters, inject org name into template context

**Weekly Scheduling Entry Point:**
- Location: `src/grant_intel/scoring/weekly.py` → `run_weekly_scoring()`
- Triggers: CLI `grant-intel weekly` command; intended for cron or Railway scheduled job
- Responsibilities: Cooldown check (6-day guard), data refresh, rule scoring, AI scoring, foundation scoring, record run timestamp

---

## Error Handling

**Strategy:** Catch-and-log at module boundaries; let outer orchestrators (CLI, weekly agent) report summary counts. Flask routes use `try/finally` to ensure DB connections are closed.

**Patterns:**
- All `anthropic.APIError` and `json.JSONDecodeError` are caught in scoring/writer loops; failed batches are logged and skipped without aborting the run
- `sqlite3.IntegrityError` on upserts is the deduplification mechanism — caught and converted to an update
- Flask route errors flash a danger message and redirect rather than raising 500s
- External API calls use `request_with_retry` from `utils/rate_limiter.py` with exponential backoff
- Dashboard startup pipeline wraps each step in individual `try/except` so one failing step doesn't abort subsequent steps

---

## Cross-Cutting Concerns

**Logging:** Python stdlib `logging` throughout; format `"%(asctime)s | %(name)s | %(levelname)s | %(message)s"` set in `cli.py`. Each module uses `logger = logging.getLogger(__name__)`. Flask app uses `logging.getLogger(__name__)`.

**Validation:** Input validation is minimal — mainly type coercion at CLI option level (Click) and Jinja2 filter level. No Pydantic or schema validation on external API responses; missing fields fall back to empty strings/None.

**Authentication:** Flask-Login with a single `AdminUser` (hardcoded id `"admin"`). Credentials verified against `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD_HASH` (preferred), or `DASHBOARD_PASSWORD` (fallback) env vars. All dashboard routes are `@login_required`.

**Rate Limiting:** `src/grant_intel/utils/rate_limiter.py` provides a `RateLimiter` class and `request_with_retry()` wrapper used by all external API clients (`grants_gov.py` at 1 req/sec, `propublica.py` at 0.5 req/sec).

**AI Models Used:**
- Scoring (opportunities and foundations): `claude-haiku-4-5-20251001` — cheap, fast, batch of 5
- Requirement extraction from NOFA/RFP: `claude-haiku-4-5-20251001`
- Grant narrative writing: `claude-sonnet-4-6` (constant `WRITING_MODEL` in `writer/sections.py`)

---

*Architecture analysis: 2026-02-28*
