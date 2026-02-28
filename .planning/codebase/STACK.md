# Technology Stack

**Analysis Date:** 2026-02-28

## Languages

**Primary:**
- Python 3.11+ — all backend logic, CLI, and web application
- HTML/Jinja2 — server-side rendered templates in `templates/`
- CSS — dashboard styling in `static/css/dashboard.css`
- JavaScript — dashboard interactivity in `static/js/dashboard.js`

## Runtime

**Environment:**
- Python 3.11+ (declared in `pyproject.toml`: `requires-python = ">=3.11"`)
- Uses Python 3.10+ union type syntax (`str | None`, `list[dict]`) throughout source

**Package Manager:**
- pip with `requirements.txt` (pinned versions)
- `pyproject.toml` used for project metadata, build config, and dev deps
- Lockfile: `requirements.txt` serves as pinned lockfile (11 lines, all exact versions)

## Frameworks

**Core Web:**
- Flask 3.1.3 — web application framework (`src/grant_intel/dashboard/app.py`)
- Flask-Login 0.6.3 — session-based auth for the admin dashboard (`src/grant_intel/dashboard/auth.py`)

**CLI:**
- Click 8.3.1 — command-line interface (`src/grant_intel/cli.py`)

**Templating:**
- Jinja2 3.1.6 — HTML dashboard templates and email/draft rendering

**HTTP:**
- Requests 2.32.5 — all outbound HTTP calls to external APIs

**XML Parsing:**
- lxml 6.0.2 — IRS 990-PF XML parsing in `src/grant_intel/sources/irs990.py`

**Configuration:**
- PyYAML 6.0.3 — org profile and similar orgs config from `config/*.yaml`
- python-dotenv 1.2.1 — `.env` loading via `load_dotenv()` in `src/grant_intel/config.py`

**Production Server:**
- gunicorn 25.1.0 — WSGI server, binds to `0.0.0.0:${PORT:-8000}`

**Testing:**
- pytest 8.0+ — test runner, config in `pyproject.toml` (`testpaths = ["tests"]`)
- responses 0.25+ — HTTP request mocking for API client tests

## Key Dependencies

**Critical:**
- `anthropic==0.84.0` — Claude API SDK; used for grant scoring (`claude-haiku-4-5-20251001`) and narrative writing (`claude-sonnet-4-6`)
- `requests==2.32.5` — all external API calls (Grants.gov, ProPublica, Brave, IRS S3)
- `Flask==3.1.3` — web dashboard

**Infrastructure:**
- `gunicorn==25.1.0` — production WSGI server
- `lxml==6.0.2` — IRS XML parsing (would break without it)
- `Flask-Login==0.6.3` — authentication guard on all dashboard routes

## Database

**Type:** SQLite (embedded, file-based)
- Path: `data/grants.db` (default, configurable via `--db` CLI flag or `DB_PATH` env)
- Client: Python stdlib `sqlite3` module — no ORM
- WAL mode enabled: `PRAGMA journal_mode=WAL`
- Foreign keys enabled: `PRAGMA foreign_keys=ON`
- Schema defined in `src/grant_intel/db.py` (`SCHEMA_SQL` constant)
- Tables: `opportunities`, `foundations`, `foundation_grants`, `similar_orgs`, `scores`, `pipeline`, `pipeline_entries`, `grant_drafts`, `web_opportunities`, `settings`
- Migrations: additive `ALTER TABLE` migrations run on every `init_db()` call (safe to re-run)

## Configuration

**Environment Variables (loaded via python-dotenv):**
- Read from `.env` in working directory via `load_dotenv()` in `src/grant_intel/config.py`
- Key vars: `ANTHROPIC_API_KEY`, `BRAVE_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`, `SIMPLER_GRANTS_API_KEY`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD_HASH`, `DASHBOARD_PASSWORD`, `SECRET_KEY`, `AUTO_POPULATE`

**YAML Config Files:**
- `config/org_profile.yaml` — org identity, mission, NTEE codes, search keywords by tier
- `config/similar_orgs.yaml` — peer organizations to research via ProPublica

**Build Config:**
- `pyproject.toml` — project metadata, dependencies, pytest config, setuptools build
- `nixpacks.toml` — Railway/Nixpacks deployment config; sets `PYTHONPATH=/app/src`, install via `pip install -r requirements.txt`

## Deployment / Infrastructure

**Platform:** Railway (indicated by `Procfile`, `nixpacks.toml`, `PORT` env var pattern)

**Web Process (Procfile):**
```
web: gunicorn "grant_intel.dashboard.app:create_app()" --bind 0.0.0.0:$PORT
```

**Startup Script (`startup.sh`):**
- Checks if `data/grants.db` is empty; if so, runs `db-init` → `search` → `research` pipeline
- Then starts gunicorn on `${PORT:-8000}`
- Used for Railway volume persistence: `data/` directory must be a mounted volume

**Nixpacks (`nixpacks.toml`):**
- Install: `pip install -r requirements.txt`
- PYTHONPATH: `/app/src`
- Start: `mkdir -p data && PYTHONPATH=/app/src gunicorn ... --timeout 300`

**Auto-population:**
- `AUTO_POPULATE=true` (default) triggers background thread in `create_app()` to run data pipeline when DB is empty
- Background thread: `threading.Thread(target=_populate, daemon=True).start()`

**Data Persistence:**
- SQLite DB at `data/grants.db` — must be on a persistent volume in Railway
- Output files (CSV reports, draft Markdown) written to `output/` directory

## Package Entry Points

**CLI:**
- Command: `grant-intel` → `grant_intel.cli:cli`
- Defined in `pyproject.toml` under `[project.scripts]`

**Web:**
- App factory: `grant_intel.dashboard.app:create_app()`
- Invoked by gunicorn directly

## Build System

- `setuptools>=68` with `setuptools.build_meta`
- Source layout: `src/` layout, packages found via `tool.setuptools.packages.find` with `where = ["src"]`
- Installed editable for development: implied by `src/grant_intel.egg-info/` presence

---

*Stack analysis: 2026-02-28*
