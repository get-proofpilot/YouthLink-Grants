# Coding Conventions

**Analysis Date:** 2026-02-28

## Naming Patterns

**Files:**
- Modules use `snake_case.py`: `grants_gov.py`, `email_digest.py`, `rate_limiter.py`
- Packages use `snake_case/` directories with `__init__.py`
- Templates use `.html.j2` suffix for Jinja2 templates: `email_digest.html.j2`

**Functions:**
- Public functions use `snake_case`: `discover_grants`, `upsert_opportunity`, `render_digest`
- Private/internal helpers are prefixed with underscore: `_score_title`, `_score_agency`, `_migrate_rule_score`, `_clean_json_response`
- Database mutation functions use verb prefixes: `upsert_*`, `insert_*`, `update_*`, `get_*`, `clear_*`
- Boolean-returning functions named descriptively: `upsert_opportunity` returns `True` if new

**Variables:**
- Local variables use `snake_case`: `all_results`, `opp_id`, `seen_ids`
- Module-level constants use `UPPER_SNAKE_CASE`: `SEARCH_URL`, `STRONG_POSITIVE`, `BOOST_AGENCIES`
- Logger always named `logger` at module level: `logger = logging.getLogger(__name__)`

**Classes:**
- `PascalCase` for dataclasses and Flask view classes: `OrgProfile`, `Config`, `AdminUser`
- Test classes use `TestPascalCase` grouping: `TestPriorityScore`, `TestDashboardRoutes`, `TestDraftDB`

**Database columns / dict keys:**
- `snake_case` throughout: `opportunity_id`, `award_floor`, `rule_explanation`

## Code Style

**Formatting:**
- No formatter config detected (no `.prettierrc`, `pyproject.toml` has no `[tool.ruff.format]` section)
- Standard Python style observed: 4-space indentation, blank lines between functions
- Line length appears to follow PEP 8 ~88-100 character soft limit (long strings sometimes exceed)

**Linting:**
- No `[tool.ruff]` or `[tool.flake8]` section in `pyproject.toml` — linting not configured
- No `.pylintrc` detected

**Type Hints:**
- Used consistently on all public functions: `conn: sqlite3.Connection`, `opp: dict`, `-> list[dict]`
- Return types always annotated on functions with non-trivial return: `-> bool`, `-> dict | None`, `-> tuple[int, str]`
- Python 3.10+ union syntax used: `dict | None`, `int | None`

## Import Organization

**Order (observed pattern):**
1. Standard library: `import os`, `import json`, `import logging`, `from pathlib import Path`
2. Third-party: `import click`, `import flask`, `import anthropic`, `import yaml`
3. Internal package imports: `from grant_intel.config import ...`, `from grant_intel.db import ...`

**Pattern notes:**
- Internal imports from CLI commands are deferred inside function bodies to avoid circular imports at module load time (e.g., all `from grant_intel.sources.*` imports inside `@cli.command` handlers)
- No path aliases used — standard relative package imports via `grant_intel.*`

## Error Handling

**Patterns:**

Exception catching follows two main styles:

**1. Bare `except Exception` with logger.exception (pipeline code):**
```python
try:
    results = discover_grants(config.keywords)
    ...
except Exception:
    logger.exception("Pipeline: Grants.gov search failed")
```
Used in `src/grant_intel/dashboard/app.py` and `src/grant_intel/sources/grants_gov.py` pipeline loops — catches everything, logs full traceback, continues execution.

**2. Specific exception types for DB upsert logic:**
```python
try:
    conn.execute("INSERT INTO ...")
    conn.commit()
    return True
except sqlite3.IntegrityError:
    # Already exists, update instead
    conn.execute("UPDATE ...")
    conn.commit()
    return False
```
Used in `src/grant_intel/db.py` — all `upsert_*` functions use `IntegrityError` for conflict detection.

**3. Silent pass for non-critical parse errors:**
```python
except (json.JSONDecodeError, TypeError):
    pass
```
Used in migration backfill code in `src/grant_intel/db.py`.

**4. ValueError for invalid input at logic boundaries:**
```python
raise ValueError("Must provide opportunity_id or foundation_id")
```
Used in `src/grant_intel/db.py` for `upsert_pipeline_entry`.

**CLI error pattern:**
```python
click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
sys.exit(1)
```
Error messages go to stderr via `err=True`. Fatal errors call `sys.exit(1)`.

## Logging

**Framework:** Python's `logging` module via `logging.getLogger(__name__)`

**Setup:** Configured once in CLI entry point (`src/grant_intel/cli.py`):
```python
logging.basicConfig(
    level=level,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
```

**Patterns:**
- All logs go to `stderr`, not `stdout` (stdout is for user-facing output via `click.echo`)
- `logger.debug` for request-level details: search pagination, API calls
- `logger.info` for pipeline step completion with counts
- `logger.warning` for non-fatal configuration issues (missing recipients)
- `logger.exception` inside bare `except` blocks (automatically captures traceback)
- `%`-style formatting used (not f-strings) for lazy evaluation: `logger.info("Found %d", count)`

## CLI Pattern (Click)

**Structure:** Single `@click.group()` named `cli` with subcommands registered via `@cli.command()`.

**Context object pattern:** Config and db_path are loaded once at the group level and passed down via `ctx.obj`:
```python
@click.group()
@click.pass_context
def cli(ctx, config_path, db_path, verbose):
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(...)
    ctx.obj["db_path"] = db_path
```

Each subcommand receives it with `@click.pass_context` and reads `ctx.obj["config"]`.

**Subcommand imports deferred:** Heavy module imports happen inside the command handler body to keep startup fast:
```python
@cli.command()
@click.pass_context
def search(ctx, tier):
    from grant_intel.sources.grants_gov import discover_grants
    ...
```

**Output conventions:**
- `click.echo(...)` for normal output to stdout
- `click.echo(..., err=True)` for errors/warnings to stderr
- `click.echo(f"Step 1/5: ...")` pattern for pipeline progress
- Summary lines use consistent `Found N items (X new, Y existing)` format

**Entry point:** `grant-intel` CLI command maps to `grant_intel.cli:cli` via `pyproject.toml` `[project.scripts]`.

## Flask Patterns (Dashboard)

**App factory:** `create_app()` function in `src/grant_intel/dashboard/app.py` — no global `app` instance.

**Blueprint organization:** Each resource type gets its own blueprint module under `src/grant_intel/dashboard/routes/`:
- `main_bp` — dashboard home
- `opportunities_bp` — URL prefix `/opportunities`
- `foundations_bp` — URL prefix `/foundations`
- `drafts_bp` — URL prefix `/drafts`
- `pipeline_bp` — URL prefix `/pipeline`
- `actions_bp` — URL prefix `/actions`
- `settings_bp` — URL prefix `/settings`
- `web_opportunities_bp` — URL prefix `/web-opportunities`

**Config storage:** App config stores non-sensitive values:
```python
app.config["DB_PATH"] = db_path
app.config["GRANT_CONFIG"] = grant_config
```

**Jinja2 context processor:** Injects `org_name` globally into all templates:
```python
@app.context_processor
def inject_globals():
    return {"org_name": grant_config.org.name}
```

**Auth:** Flask-Login `LoginManager` with single `AdminUser` class. Credentials sourced from environment variables (`DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`/`DASHBOARD_PASSWORD_HASH`).

**Jinja2 filters:** Custom filters registered via `register_filters(app)` in `src/grant_intel/dashboard/filters.py`.

## Database Access Patterns

**Raw SQL throughout** — no ORM. All queries use `sqlite3.Connection` directly.

**Connection pattern:**
```python
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row   # enables dict-like access by column name
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
```

**Row-to-dict conversion:** Every query result converts `sqlite3.Row` to plain `dict`:
```python
return [dict(row) for row in rows]
return dict(row) if row else None
```

**Upsert pattern:** Try INSERT, catch `IntegrityError`, fallback to UPDATE:
```python
try:
    conn.execute("INSERT INTO ...", values)
    conn.commit()
    return True
except sqlite3.IntegrityError:
    conn.execute("UPDATE ... WHERE ...", values)
    conn.commit()
    return False
```

**Migration pattern:** Additive `ALTER TABLE ADD COLUMN IF NOT EXISTS` migrations run at every `init_db()` call, guarded by `PRAGMA table_info` inspection:
```python
cols = {row[1] for row in conn.execute("PRAGMA table_info(opportunities)").fetchall()}
if "rule_score" not in cols:
    conn.execute("ALTER TABLE opportunities ADD COLUMN rule_score INTEGER")
```

**JSON serialization:** Complex fields (lists, dicts) stored as JSON text: `focus_areas TEXT`, `raw_json TEXT`. Loaded/saved with `json.dumps()` / `json.loads()`.

## Config Loading Patterns

**Load order:**
1. Call `load_dotenv()` to populate environment from `.env` file
2. Read YAML profile: `config/org_profile.yaml` (org identity, keywords)
3. Read YAML similar orgs: `config/similar_orgs.yaml` (optional, Path.exists() guard)
4. Read secrets from `os.getenv()` (API keys, SMTP credentials, EMAIL_TO)

**Config dataclass:**
```python
@dataclass
class Config:
    org: OrgProfile
    keywords: dict[str, list[str]]
    anthropic_api_key: str = ""
    ...
```

**Secrets always from env, never YAML:**
- `ANTHROPIC_API_KEY`, `BRAVE_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`, `SECRET_KEY`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`

**Default values:** All optional config fields default to empty string `""` or `0`, never `None`. Guards in CLI check truthiness: `if not config.anthropic_api_key:`.

## Module Design

**Exports:** No barrel `__init__.py` re-exports — all imports use full module paths: `from grant_intel.sources.grants_gov import discover_grants`.

**Module-level constants:** Scoring keyword lists (`STRONG_POSITIVE`, `BOOST_AGENCIES`, etc.) are defined as module-level lists/dicts in `src/grant_intel/scoring/rules.py`. Module-level `_rate_limiter` instance in `src/grant_intel/sources/grants_gov.py`.

**Separation of concerns:**
- `db.py` — all SQL queries, no business logic
- `scoring/rules.py` — pure functions, no I/O
- `scoring/matcher.py` — Claude API integration, orchestrates rules + AI
- `sources/*.py` — external API clients, no DB access
- `cli.py` — connects everything, imports deferred inside commands
- `dashboard/app.py` — Flask factory only, data pipeline in `_run_data_pipeline`

---

*Convention analysis: 2026-02-28*
