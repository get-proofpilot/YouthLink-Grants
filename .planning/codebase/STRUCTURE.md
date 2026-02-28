# Codebase Structure

**Analysis Date:** 2026-02-28

## Directory Layout

```
YouthLink-Grants/
├── src/
│   └── grant_intel/                 # Main Python package (installed as 'grant_intel')
│       ├── __init__.py
│       ├── cli.py                   # CLI entry point — all Click commands
│       ├── config.py                # Config loading, OrgProfile, curated data constants
│       ├── db.py                    # All SQLite schema + CRUD operations
│       ├── dashboard/               # Flask web application
│       │   ├── app.py               # Application factory (create_app)
│       │   ├── auth.py              # Flask-Login single-admin auth
│       │   ├── filters.py           # Jinja2 custom template filters
│       │   ├── priority.py          # Priority Score + requirement match analysis
│       │   └── routes/              # Flask Blueprints (one per domain)
│       │       ├── main.py          # / — home/overview page
│       │       ├── opportunities.py # /opportunities/ and /opportunities/<id>
│       │       ├── foundations.py   # /foundations/ and /foundations/<id>
│       │       ├── web_opportunities.py  # /web-opportunities/
│       │       ├── drafts.py        # /drafts/ and /drafts/<id>
│       │       ├── pipeline.py      # /pipeline/ — kanban stage management
│       │       ├── actions.py       # /actions/* — POST-only trigger endpoints
│       │       └── settings.py      # /settings/ — org profile viewer
│       ├── sources/                 # External data source clients
│       │   ├── grants_gov.py        # Grants.gov REST API (federal opps)
│       │   ├── propublica.py        # ProPublica 990 API (foundations + similar orgs)
│       │   ├── brave_search.py      # Brave Search API (web grant discovery)
│       │   ├── curated.py           # Hard-coded curated foundation list seeder
│       │   ├── givingtuesday.py     # GivingTuesday 990 API (foundation enrichment)
│       │   ├── irs990.py            # IRS 990 data source
│       │   └── nodc_import.py       # NODC CSV import for historical grant data
│       ├── scoring/                 # Grant scoring engine
│       │   ├── rules.py             # Keyword/CFDA/agency rule engine (Tier 1, free)
│       │   ├── matcher.py           # Claude AI scoring funnel (Tier 2) + foundation scoring
│       │   └── weekly.py            # Weekly scheduled scoring agent with cooldown
│       ├── writer/                  # AI grant narrative generation
│       │   ├── agent.py             # Orchestrator for federal narrative + LOI drafting
│       │   ├── sections.py          # Section-by-section generation with context threading
│       │   ├── prompts.py           # System prompt, section prompts, LOI prompt, banned words
│       │   └── extractor.py         # NOFA/RFP requirement extraction (Haiku)
│       ├── delivery/                # Output delivery
│       │   ├── csv_export.py        # CSV export of scored opportunities + foundations
│       │   └── email_digest.py      # HTML email digest via SMTP + Jinja2 template
│       └── utils/
│           └── rate_limiter.py      # RateLimiter class + request_with_retry() wrapper
├── templates/                       # Jinja2 templates
│   ├── dashboard/                   # Flask HTML templates
│   │   ├── base.html                # Base layout with nav, flash messages
│   │   ├── home.html                # Dashboard overview / home page
│   │   ├── login.html               # Login form
│   │   ├── opportunities.html       # Opportunities list with filters
│   │   ├── opportunity_detail.html  # Single opportunity + priority score + drafts
│   │   ├── foundations.html         # Foundations list
│   │   ├── foundation_detail.html   # Single foundation + grant history + drafts
│   │   ├── web_opportunities.html   # Brave Search discoveries list
│   │   ├── drafts.html              # All drafts list
│   │   ├── draft_detail.html        # Single draft with section tabs
│   │   ├── pipeline.html            # Kanban pipeline view
│   │   └── settings.html            # Org profile read-only view
│   ├── email_digest.html.j2         # Weekly email digest HTML template
│   └── grant_draft.md.j2            # Grant narrative Markdown output template
├── static/
│   ├── css/
│   │   └── dashboard.css            # Dashboard styles
│   └── js/
│       └── dashboard.js             # Dashboard interactivity
├── config/
│   ├── org_profile.yaml             # Org identity, search keywords (3 tiers), NTEE codes
│   └── similar_orgs.yaml            # Known peer organizations for 990 research
├── data/
│   └── grants.db                    # SQLite database (gitignored in production)
├── tests/
│   ├── conftest.py                  # Shared pytest fixtures
│   ├── test_db.py                   # Database CRUD tests
│   ├── test_dashboard.py            # Flask route tests
│   ├── test_matcher.py              # Scoring engine tests
│   ├── test_writer.py               # Grant writer tests
│   ├── test_csv_export.py           # CSV export tests
│   ├── test_email_digest.py         # Email digest tests
│   ├── test_grants_gov.py           # Grants.gov client tests
│   ├── test_irs990.py               # IRS 990 client tests
│   └── test_propublica.py           # ProPublica client tests
├── pyproject.toml                   # Package config, dependencies, entry point
├── requirements.txt                 # Pinned requirements for deployment
├── Procfile                         # Railway/Heroku: gunicorn create_app()
├── nixpacks.toml                    # Railway build config: pip install + PYTHONPATH
├── startup.sh                       # Startup helper script
├── .env.example                     # Template for required env vars (never commit .env)
└── .gitignore
```

---

## Directory Purposes

**`src/grant_intel/`:**
- Purpose: The entire application as an installable Python package
- Key files: `cli.py` (all commands), `db.py` (all data), `config.py` (all config)
- Installed editably via `pyproject.toml`; the `grant-intel` CLI script maps to `grant_intel.cli:cli`

**`src/grant_intel/dashboard/`:**
- Purpose: Flask web application sub-package
- Contains: Factory, auth, template filters, priority scoring logic, and all Blueprint route modules
- Key design: `create_app()` in `app.py` is the only entry point; `app.config["DB_PATH"]` and `app.config["GRANT_CONFIG"]` are set at factory time and accessed by all routes via `current_app.config`

**`src/grant_intel/dashboard/routes/`:**
- Purpose: One Flask Blueprint per domain entity
- Pattern: Each module defines a Blueprint, registers `@login_required` on all views, gets a DB connection using `get_connection(current_app.config["DB_PATH"])`, and closes it in a `finally` block
- `actions.py` is special — it contains only POST-only trigger endpoints that invoke business logic and redirect

**`src/grant_intel/sources/`:**
- Purpose: External API integrations for grant and foundation discovery
- Pattern: Each module is a standalone client; returns normalized plain dicts; uses `utils/rate_limiter.py` for polite API access
- `curated.py` is the only non-API source — it reads the `CURATED_FOUNDATIONS` constant from `config.py` and seeds them into the DB

**`src/grant_intel/scoring/`:**
- Purpose: Two-tier scoring pipeline for ranking opportunities and foundations
- `rules.py`: Pure function scoring, no external calls. `score_opportunity(opp: dict) -> (int, str)` is the core function.
- `matcher.py`: Claude Haiku calls. `score_with_funnel()` runs rules then AI; `score_foundations()` is AI-only.
- `weekly.py`: Orchestrates a full cycle (data refresh + both scoring tiers) with a 6-day cooldown guard

**`src/grant_intel/writer/`:**
- Purpose: AI grant narrative and LOI drafting using Claude Sonnet
- `agent.py`: Top-level orchestrator for `draft_federal_narrative()` and `draft_foundation_loi()`
- `sections.py`: Core loop — iterates over `determine_sections()` result, calls `generate_section()` for each, passes all prior sections as context
- `prompts.py`: All prompt strings as module-level constants + builder functions. The `GRANT_WRITER_SYSTEM` persona prompt and all `SECTION_PROMPTS` live here.
- `extractor.py`: Claude Haiku call to parse a NOFA/RFP document into a structured `requirements` dict

**`templates/dashboard/`:**
- Purpose: Jinja2 HTML templates for the Flask dashboard
- `base.html` is the shared layout inherited by all pages
- Templates are resolved by Flask from the absolute path set in `app.py`: `_PROJECT_ROOT / "templates" / "dashboard"`
- Static assets resolved from `_PROJECT_ROOT / "static"`

**`templates/` (root-level):**
- `email_digest.html.j2`: Rendered by `delivery/email_digest.py` via `FileSystemLoader`
- `grant_draft.md.j2`: Rendered by `writer/agent.py` via `FileSystemLoader` to produce Markdown output files

**`config/`:**
- `org_profile.yaml`: Organization identity (name, EIN, mission, location, NTEE codes), and tiered search keyword lists (`tier1`/`tier2`/`tier3`). Read by `load_config()`.
- `similar_orgs.yaml`: List of peer nonprofits with EINs used by `sources/propublica.py` for competitive landscape research

**`data/`:**
- `grants.db`: SQLite database file. Created automatically by `init_db()`. Not committed to git in production deployments.

---

## Key File Locations

**Entry Points:**
- `src/grant_intel/cli.py`: All CLI commands. The `@cli.group()` decorator is the root Click group.
- `src/grant_intel/dashboard/app.py`: `create_app()` function — the Flask application factory.

**Configuration:**
- `config/org_profile.yaml`: Org profile, mission, programs, budget, NTEE codes, search keywords
- `config/similar_orgs.yaml`: Peer org EINs for ProPublica research
- `.env` (local only): `ANTHROPIC_API_KEY`, `BRAVE_API_KEY`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD_HASH`, `SECRET_KEY`, SMTP config, `EMAIL_TO`
- `pyproject.toml`: Package metadata, dependencies, CLI entry point definition
- `nixpacks.toml`: Railway deployment build config

**Core Logic:**
- `src/grant_intel/db.py`: Every table definition and every query. Adding new DB operations means adding functions here.
- `src/grant_intel/scoring/rules.py`: All rule-based scoring signals (keyword lists, CFDA codes, agency names). Add new keyword signals here.
- `src/grant_intel/scoring/matcher.py`: Claude scoring prompts and batch logic
- `src/grant_intel/writer/prompts.py`: All grant writing prompts, persona, banned words list

**Testing:**
- `tests/`: All test files. Run with `pytest` from project root.
- `tests/conftest.py`: Shared fixtures (in-memory DB, mock config, etc.)

---

## Naming Conventions

**Files:**
- Python modules: `snake_case.py`
- HTML templates: `snake_case.html`
- Jinja2 templates with explicit extension: `name.html.j2`, `name.md.j2`
- Config files: `snake_case.yaml`

**Python:**
- Functions: `snake_case` (e.g., `score_with_funnel`, `draft_federal_narrative`)
- Classes: `PascalCase` (e.g., `OrgProfile`, `Config`, `AdminUser`, `RateLimiter`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `SCORING_SYSTEM_PROMPT`, `DEFAULT_SECTIONS`, `WRITING_MODEL`)
- Flask Blueprints: `snake_case_bp` (e.g., `main_bp`, `opportunities_bp`, `actions_bp`)

---

## Where to Add New Code

**New CLI command:**
- Add a `@cli.command()` function to `src/grant_intel/cli.py`
- Import domain logic lazily inside the function body (following existing pattern)

**New dashboard page:**
- Create a new Blueprint file in `src/grant_intel/dashboard/routes/new_module.py`
- Register it in `src/grant_intel/dashboard/app.py` `create_app()` with `app.register_blueprint()`
- Add a template to `templates/dashboard/new_page.html` extending `base.html`

**New data source:**
- Add a new module to `src/grant_intel/sources/new_source.py`
- Return normalized plain dicts matching the schema expected by `db.py` upsert functions
- Use `utils/rate_limiter.py` for any HTTP calls

**New DB table or column:**
- Add to `SCHEMA_SQL` in `src/grant_intel/db.py`
- Add a `_migrate_*()` function for the column/table and call it from `init_db()`
- Add corresponding query functions to `db.py`

**New scoring signal:**
- For rule-based signals: Add keywords to relevant lists in `src/grant_intel/scoring/rules.py`
- For AI signals: Modify the prompt constants in `src/grant_intel/scoring/matcher.py`

**New grant writing section:**
- Add section name to `DEFAULT_SECTIONS` in `src/grant_intel/writer/sections.py`
- Add section prompt to `SECTION_PROMPTS` dict in `src/grant_intel/writer/prompts.py`
- Add mapping entry in `determine_sections()` in `sections.py`

**Utilities:**
- Shared HTTP/rate-limiting: `src/grant_intel/utils/rate_limiter.py`
- New utilities: Add to `src/grant_intel/utils/new_util.py`

---

## Special Directories

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (by `python -m venv .venv`)
- Committed: No (in `.gitignore`)

**`data/`:**
- Purpose: SQLite database storage
- Generated: Yes (auto-created by `init_db()`)
- Committed: No (database file is runtime state)

**`output/`:**
- Purpose: Generated CSV reports and grant draft Markdown files
- Generated: Yes (created by CLI `report` and `draft` commands)
- Committed: No

**`.planning/`:**
- Purpose: GSD planning documents and codebase analysis
- Generated: Yes (by GSD tooling)
- Committed: Yes

**`src/grant_intel.egg-info/`:**
- Purpose: Python package metadata generated by `pip install -e .`
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-02-28*
