# Codebase Concerns

**Analysis Date:** 2026-02-28

---

## Security Concerns

### Plaintext Password Fallback in Auth

- **Risk:** If `DASHBOARD_PASSWORD_HASH` is not set in env, the app falls back to comparing a raw plaintext password from `DASHBOARD_PASSWORD` (default value: `"changeme"`).
- **Files:** `src/grant_intel/dashboard/auth.py` lines 37-44
- **Current mitigation:** The hash path works correctly when `DASHBOARD_PASSWORD_HASH` is configured. The fallback is documented as "for initial setup."
- **Recommendations:** Remove the plaintext fallback entirely. Require `DASHBOARD_PASSWORD_HASH` at startup; raise a startup error if missing. The current design means a misconfigured deployment silently uses "changeme" as the password.

### Hardcoded Insecure Default Secret Key

- **Risk:** Flask `SECRET_KEY` defaults to the literal string `"change-me-in-production"` if `SECRET_KEY` env var is unset. This makes session cookies trivially forgeable.
- **Files:** `src/grant_intel/dashboard/app.py` line 29
- **Current mitigation:** None; there is no startup check.
- **Recommendations:** Assert `SECRET_KEY` is set and is not the default string at startup. Log a critical warning or refuse to start if the default is detected.

### Unvalidated Open Redirect in Login

- **Risk:** The `next` query parameter in the login flow is passed directly to `redirect()` without validation. An attacker can craft a login URL that redirects to an external malicious site after successful auth.
- **Files:** `src/grant_intel/dashboard/auth.py` lines 55-56
- **Current mitigation:** Single-user tool, low exposure, but the risk exists.
- **Recommendations:** Validate that `next_page` is a relative URL (starts with `/`) before redirecting. Flask's `url_for` + a whitelist check is the standard approach.

### No CSRF Protection on State-Mutating POST Endpoints

- **Risk:** All `POST` routes (trigger search, trigger scoring, change pipeline stage, edit notes, generate drafts, generate LOIs) have no CSRF token validation. Any page that can be visited by the logged-in user can trigger these actions.
- **Files:** `src/grant_intel/dashboard/routes/actions.py`, `src/grant_intel/dashboard/routes/pipeline.py`, `src/grant_intel/dashboard/routes/drafts.py`
- **Current mitigation:** Flask-Login session is required, so the attacker must trick the logged-in user's browser.
- **Recommendations:** Add Flask-WTF or manually validate a CSRF token on all POST endpoints. This is a standard Flask extension that requires minimal integration work.

### No Security Headers (X-Frame-Options, Content-Security-Policy)

- **Risk:** The dashboard has no HTTP security headers. It can be embedded in iframes (clickjacking), and there is no Content-Security-Policy to limit script execution.
- **Files:** `src/grant_intel/dashboard/app.py` (no `after_request` hook for headers)
- **Current mitigation:** None.
- **Recommendations:** Add `flask-talisman` or an `after_request` hook that sets `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and a minimal CSP.

### EIN Exposed Prominently in UI

- **Risk:** Foundation EINs are displayed in the UI and exported in CSVs. For a single-admin tool this is low-risk, but EINs are used to look up sensitive nonprofit financial data.
- **Files:** `src/grant_intel/delivery/csv_export.py` line 100, `templates/dashboard/foundation_detail.html`, `templates/dashboard/foundations.html`
- **Current mitigation:** Dashboard is login-protected.
- **Recommendations:** Low priority, but note for any future multi-user expansion.

---

## Technical Debt

### `db.py` Exceeds 500-Line File Budget

- **Issue:** `src/grant_intel/db.py` is 979 lines — nearly twice the project's stated 500-line limit. It combines schema definition, migrations, CRUD for 8 entity types, and dashboard queries.
- **Files:** `src/grant_intel/db.py`
- **Impact:** Hard to navigate, easy to accidentally break unrelated operations. All tests that touch the DB must import from this single monolith.
- **Fix approach:** Split into `db/schema.py`, `db/opportunities.py`, `db/foundations.py`, `db/pipeline.py`, `db/drafts.py`, etc. Expose a `db/__init__.py` with the public API to preserve import paths.

### Two Redundant Pipeline Tables

- **Issue:** The schema defines both a `pipeline` table (lines 93-100) and a `pipeline_entries` table (lines 102-110). The code uses only `pipeline_entries`. The `pipeline` table appears to be dead code from an earlier design.
- **Files:** `src/grant_intel/db.py` lines 93-110
- **Impact:** Confusion about which table is canonical; migrations and schema reviews must account for both.
- **Fix approach:** Drop the `pipeline` table in a migration. Remove any references.

### `pipeline_entries` UNIQUE Constraints Are Incorrect

- **Issue:** Both `opportunity_id` and `foundation_id` columns in `pipeline_entries` are individually declared `UNIQUE` (lines 104-105). This means a foundation can only ever appear in one pipeline entry and an opportunity can only appear in one pipeline entry — which is correct — but it also means you cannot have a pipeline entry that links both an opportunity AND a foundation simultaneously (the constraint would conflict if those IDs were already used separately). The real uniqueness constraint should be a composite or partial unique, not individual column uniques.
- **Files:** `src/grant_intel/db.py` lines 102-110
- **Impact:** If someone tries to add an opportunity to the pipeline after adding the same opportunity via a different path, SQLite silently rejects the insert. The `upsert_pipeline_entry` function works around this manually, but the schema constraint does not match the intended data model.
- **Fix approach:** Replace individual UNIQUE columns with appropriate partial unique indexes or remove the constraint and enforce uniqueness in application logic.

### `givingtuesday.py` File Name Does Not Match Its Actual Function

- **Issue:** `src/grant_intel/sources/givingtuesday.py` contains a comment at line 6 noting that the GivingTuesday API returns 403 on all endpoints. The file actually calls ProPublica. The module name is therefore misleading.
- **Files:** `src/grant_intel/sources/givingtuesday.py` lines 1-10
- **Impact:** Anyone reading the code will assume GivingTuesday data is flowing through here. The mismatch creates confusion when debugging data quality issues.
- **Fix approach:** Rename to `src/grant_intel/sources/foundation_enrichment.py` and update all imports.

### `total_giving` Is Computed From `totfuncexpns` (Total Functional Expenses), Not Grants Paid

- **Issue:** In `givingtuesday.py` line 73-76, the code maps `totfuncexpns` (total functional expenses from IRS 990) to `total_giving`. Total functional expenses includes administrative costs, program expenses, and fundraising — not just grants disbursed. For operating nonprofits, this over-reports "giving" by 100-500%. For private foundations, `totfuncexpns` is closer but still includes expenses beyond grants.
- **Files:** `src/grant_intel/sources/givingtuesday.py` lines 73-76, `src/grant_intel/sources/propublica.py` line 97
- **Impact:** The "Total Giving" column shown in the dashboard and exported CSVs is systematically wrong for most foundations. Scoring foundations by `total_giving DESC` (db.py lines 464, 489) produces an incorrect ranking.
- **Fix approach:** Use `totgrantspd` (grants paid) from 990-PF filings for private foundations, or clearly label the field as "Total Expenses (Proxy for Giving)" in the UI and CSV.

### `extract_org_info` in `propublica.py` Maps `asset_amount` to `total_expenses`

- **Issue:** `src/grant_intel/sources/propublica.py` line 81 maps `org.get("asset_amount")` to `total_expenses`. Asset amount is total assets (balance sheet), not expenses. This is the wrong field.
- **Files:** `src/grant_intel/sources/propublica.py` line 81
- **Impact:** `similar_orgs.total_expenses` contains asset values, not expenses. This affects any display or scoring that relies on `total_expenses` for similar org comparison.
- **Fix approach:** Use `income_amount` for revenue/income and `asset_amount` for total assets. Rename fields to match.

### Background Pipeline in `app.py` Opens a Second Connection Without `finally`

- **Issue:** In `_run_data_pipeline` (`src/grant_intel/dashboard/app.py` lines 92-177), step 6 (lines 161-165) opens a **new** connection (`conn = get_connection(db_path)`) inside a `try` block but never closes it in a `finally`. If scoring raises an exception, this connection leaks.
- **Files:** `src/grant_intel/dashboard/app.py` lines 161-175
- **Impact:** Under gunicorn with a single worker, SQLite WAL mode handles this gracefully, but it is a resource leak and a code quality issue.
- **Fix approach:** Wrap the second `get_connection` in a `try/finally` and call `conn.close()`.

### CLI `cli.py` Is 628 Lines

- **Issue:** `src/grant_intel/cli.py` is 628 lines — exceeding the 500-line limit. It mixes CLI wiring, pipeline orchestration, and inline business logic.
- **Files:** `src/grant_intel/cli.py`
- **Impact:** Difficult to test individual CLI commands in isolation.
- **Fix approach:** Extract pipeline steps into a `pipeline.py` module and keep `cli.py` as thin wrappers.

---

## Reliability Concerns

### All Weekly Pipeline Steps Are Fire-and-Forget with Bare `except Exception`

- **Issue:** Every step in `_refresh_data` (`src/grant_intel/scoring/weekly.py` lines 68-128) and `_run_data_pipeline` (`src/grant_intel/dashboard/app.py` lines 104-175) catches `except Exception` and logs the exception, then continues silently. If Grants.gov returns garbage data, scoring fails, or a migration throws, the pipeline completes with no user-visible signal of partial failure.
- **Files:** `src/grant_intel/scoring/weekly.py` lines 75-127, `src/grant_intel/dashboard/app.py` lines 111-173
- **Impact:** The dashboard can show "Pipeline complete" while having ingested no new data and no scores. The operator has no indicator beyond log inspection.
- **Fix approach:** Return a per-step status from each pipeline stage and surface failure counts in the flash message or a pipeline health widget.

### AI Scoring Swallows `JSONDecodeError` Silently, Loses Entire Batch

- **Issue:** In `score_opportunities` and `score_foundations` (`src/grant_intel/scoring/matcher.py` lines 183-184, 297-298), a `JSONDecodeError` from Claude returning malformed JSON causes the entire batch of 5 items to be skipped with only a log warning. No retry is attempted; those items remain unscored indefinitely.
- **Files:** `src/grant_intel/scoring/matcher.py` lines 149-185, 271-298
- **Impact:** If Claude returns Markdown fences or truncates its response (common on high-load), up to 5 opportunities per failure quietly disappear from scoring. The `_clean_json_response` function mitigates this but is only a heuristic.
- **Fix approach:** On `JSONDecodeError`, retry the batch with a more explicit "respond with JSON only" reminder prompt before giving up. Log how many items were lost.

### Rate Limiters Are Not Thread-Safe

- **Issue:** Module-level `RateLimiter` instances in all source modules (`src/grant_intel/sources/grants_gov.py` line 13, `src/grant_intel/sources/propublica.py` line 12, etc.) use `time.monotonic()` and `time.sleep()` without a lock. The background pipeline thread and any dashboard action trigger (e.g., `trigger_search`) can share the same rate limiter object concurrently.
- **Files:** `src/grant_intel/utils/rate_limiter.py` lines 11-24, all source modules
- **Impact:** Under concurrent access (background populate + user-triggered action), the limiter's `last_call` check is a race condition and could result in bursting past API rate limits.
- **Fix approach:** Add `threading.Lock` to `RateLimiter.wait()`.

### `gunicorn` Runs With Default Single Worker and 300s Timeout

- **Issue:** `nixpacks.toml` sets `--timeout 300` but no `--workers` flag. Gunicorn defaults to 1 sync worker. A single long-running request (e.g., draft generation via Claude API, which can take 30-60 seconds per section with 7 sections) blocks all other requests.
- **Files:** `nixpacks.toml` line 8, `Procfile` line 1
- **Impact:** During draft generation, the entire dashboard becomes unresponsive. No concurrent dashboard users can load pages.
- **Fix approach:** Use `--workers 2` (or gevent/async worker class) since the workload is I/O-bound. Alternatively, move draft generation to a background thread/task queue.

### No Retry on Claude `APIError` for Individual Sections

- **Issue:** `generate_section` in `src/grant_intel/writer/sections.py` line 80 catches `anthropic.APIError` and returns a `[ERROR: Failed to generate...]` string inline. That string is stored verbatim as the section content and committed to the database. There is no retry.
- **Files:** `src/grant_intel/writer/sections.py` lines 70-82
- **Impact:** A transient API error produces a stored draft with literal error placeholders. The user sees a "Draft generated!" flash message and discovers the failure only when reviewing the content.
- **Fix approach:** Retry section generation 1-2 times on transient API errors before inserting the error string. Distinguish clearly between "draft failed" and "draft complete with errors."

---

## Scalability Concerns

### All Data Is Fetched Into Memory Before Rendering

- **Issue:** `get_all_opportunities`, `get_all_foundations`, `get_all_web_opportunities` (`src/grant_intel/db.py` lines 496-514, 873-879) fetch the entire table into a Python list. `get_all_opportunities` additionally does a JOIN with scores.
- **Files:** `src/grant_intel/db.py` lines 496-514, 873-879; `src/grant_intel/dashboard/routes/opportunities.py` line 29; `src/grant_intel/dashboard/routes/foundations.py` line 23
- **Impact:** With hundreds of opportunities from Grants.gov searches, this already works. At thousands of rows (possible after repeated weekly runs over months), page load time will increase noticeably and memory use will grow. No pagination exists in any list view.
- **Fix approach:** Add `LIMIT`/`OFFSET` pagination to all list queries and corresponding pagination controls in templates.

### Brave Search Quota Is Consumed Entirely on Each Run

- **Issue:** `discover_web_opportunities` in `src/grant_intel/sources/brave_search.py` always runs all 28 queries in `BRAVE_SEARCH_QUERIES` (`src/grant_intel/config.py` lines 228-252). The Brave free tier allows 2,000 requests/month. Each weekly run uses 28 queries. With 4 weekly runs/month that is 112 queries — well within limits — but the monthly `trigger_brave_search` action button can be clicked repeatedly by the user, quickly exhausting the quota.
- **Files:** `src/grant_intel/sources/brave_search.py` line 165, `src/grant_intel/config.py` lines 228-252, `src/grant_intel/dashboard/routes/actions.py` lines 190-214
- **Impact:** If the Brave quota is exhausted, Brave Search silently returns 0 results and web opportunities stop being discovered, with no visible indication in the dashboard.
- **Fix approach:** Track monthly API usage in the `settings` table and warn the user when approaching the quota. Add a cooldown on the Brave Search action button similar to the weekly scoring cooldown.

### SQLite WAL Mode on Railway Volume: Not Configured for Concurrent Access

- **Issue:** WAL mode is enabled (`src/grant_intel/db.py` line 161), which is correct. However, gunicorn single-worker + background threading means all DB access is effectively sequential. If `--workers 2` is added (see reliability concern above), multiple workers would share the same SQLite file on a Railway volume, which SQLite WAL mode supports only for readers. Multiple writers will serialize via locks, potentially causing request timeouts during the weekly pipeline run.
- **Files:** `src/grant_intel/db.py` line 161
- **Impact:** Low risk at current scale; becomes blocking if worker count is increased.
- **Fix approach:** Acceptable at current scale. Note for future: if concurrency becomes an issue, migrate to PostgreSQL (Railway has first-class Postgres support).

### Grants.gov Pagination Has No Hard Cap

- **Issue:** `search_opportunities` in `src/grant_intel/sources/grants_gov.py` lines 16-66 paginates through all results for each keyword. A broad Tier 3 keyword like "nonprofit professional development" could match thousands of opportunities. The rate limiter at 1 req/sec means 100 pages = 100 seconds per keyword.
- **Files:** `src/grant_intel/sources/grants_gov.py` lines 25-66
- **Impact:** A full Tier 3 search with 5 broad keywords could block the background thread for 5+ minutes, slowing the first page load on a cold-start deployment.
- **Fix approach:** Add a `max_pages` or `max_results` parameter, defaulting to a reasonable cap (e.g., 500 results per keyword). Log a warning when the cap is hit.

---

## Data Quality Concerns

### `total_giving` Sort for Foundations Is Meaningless When Data Is Missing

- **Issue:** `get_all_foundations`, `get_unscored_foundations`, `get_foundations_needing_enrichment` all sort by `total_giving DESC NULLS LAST` (`src/grant_intel/db.py` lines 513, 464, 968). For foundations discovered from ProPublica keyword search, `total_giving` is null until enrichment runs. This means newly discovered foundations are always sorted to the bottom, even if they are highly relevant.
- **Files:** `src/grant_intel/db.py` lines 464, 513, 968
- **Impact:** High-priority small foundations from keyword search may never surface to the top of the foundations list until enrichment runs.
- **Fix approach:** Sort by `score DESC NULLS LAST, total_giving DESC NULLS LAST` on the main list view. For unenriched foundations without scores, a secondary sort by `created_at DESC` would surface recently discovered ones.

### Deadline Strings Are Not Validated on Ingest

- **Issue:** Opportunity deadlines are stored as raw strings from the API (`src/grant_intel/db.py` line 22: `deadline TEXT`). No validation occurs at ingest time. The scoring and priority logic in multiple places uses `deadline[:10]` and `datetime.strptime(deadline[:10], "%Y-%m-%d")` with a bare `except (ValueError, TypeError)` fallback.
- **Files:** `src/grant_intel/db.py` line 22; `src/grant_intel/scoring/matcher.py` lines 97-109; `src/grant_intel/dashboard/priority.py` lines 69-82; `src/grant_intel/scoring/rules.py` lines 358-369
- **Impact:** An opportunity with a non-ISO deadline string (e.g., "Rolling" or "See announcement") silently scores as urgency "none" and is never surfaced in the deadline countdown. The user cannot distinguish "no deadline" from "unknown deadline format."
- **Fix approach:** Validate and normalize deadline strings at ingest. Store `NULL` for unparseable deadlines and handle `NULL` explicitly in queries.

### Scores Table Has No Uniqueness Constraint

- **Issue:** `insert_score` (`src/grant_intel/db.py` lines 388-403) does a plain `INSERT` with no `ON CONFLICT` handling and no unique constraint on `(opportunity_id, foundation_id)`. Running scoring twice (e.g., via the "Score" action button on the dashboard) inserts duplicate score rows. `get_top_opportunities` selects `JOIN scores s ON s.opportunity_id = o.id`, which returns the first score row; subsequent scoring runs add silent duplicates.
- **Files:** `src/grant_intel/db.py` lines 388-403, schema lines 82-91
- **Impact:** Over time, the `scores` table accumulates duplicate rows for every re-scored item. Queries that join without `LIMIT 1` or `MAX` could return duplicate opportunities in results.
- **Fix approach:** Add `UNIQUE(opportunity_id, foundation_id)` constraint (with NULL handling for the foundation-only case) and change `insert_score` to `INSERT OR REPLACE`.

### Curated Foundations Have No Enrichment After Initial Seed

- **Issue:** `seed_curated_foundations` (`src/grant_intel/sources/curated.py`) seeds foundations with hardcoded `accepts_applications` and `focus_areas` data from `config.py`. The `last_enriched` column is never set for curated foundations at seed time, so they are immediately eligible for enrichment — but if `total_assets` and `total_giving` are already populated from another source, the enrichment may overwrite curated data with older ProPublica data.
- **Files:** `src/grant_intel/sources/curated.py`, `src/grant_intel/config.py` lines 122-224
- **Impact:** Low immediate risk. Potential for stale data over time.
- **Fix approach:** Set `last_enriched = datetime('now')` when seeding curated foundations that already have `total_giving` from the config data.

---

## Maintenance Concerns

### No Integration Tests for External API Calls

- **Issue:** Tests mock HTTP responses (`responses` library) but only for the happy path. There are no tests for rate-limit (429) responses, network timeouts, or malformed API responses. The `request_with_retry` retry logic has no test coverage.
- **Files:** `tests/test_grants_gov.py`, `tests/test_propublica.py`, `src/grant_intel/utils/rate_limiter.py`
- **Impact:** Regressions in retry/backoff behavior are invisible. Any change to `request_with_retry` could silently break error recovery.
- **Fix approach:** Add tests that mock 429 → 200 sequences to verify exponential backoff. Test connection error handling.

### No Tests for `weekly.py` End-to-End Scoring Cycle

- **Issue:** `src/grant_intel/scoring/weekly.py` has no test file. The cooldown logic, the data refresh pipeline, and the AI scoring gate are all untested.
- **Files:** `src/grant_intel/scoring/weekly.py` (no corresponding test file)
- **Impact:** The most operationally critical code path (the weekly automated job) has zero test coverage. A regression in cooldown logic could cause double-runs and API cost spikes.
- **Fix approach:** Add `tests/test_weekly.py` with mocked sources and scoring. At minimum, test cooldown bypass, dry-run mode, and partial failure recovery.

### No Tests for `nodc_import.py`

- **Issue:** `src/grant_intel/sources/nodc_import.py` has no test file. Column auto-detection, filtering, and foundation auto-discovery are untested.
- **Files:** `src/grant_intel/sources/nodc_import.py` (no corresponding test file)
- **Impact:** CSV import is used to bulk-load historical data. A bug in column mapping would silently import misaligned data.
- **Fix approach:** Add `tests/test_nodc_import.py` using an in-memory database and a small CSV fixture.

### No Tests for `brave_search.py`

- **Issue:** `src/grant_intel/sources/brave_search.py` has no dedicated test file.
- **Files:** `src/grant_intel/sources/brave_search.py` (no corresponding test file)
- **Impact:** The heuristic `is_grant_result` filter and `parse_web_opportunity` parser are the primary source of data quality for web opportunities and have no regression protection.
- **Fix approach:** Add `tests/test_brave_search.py` with fixture search results to test the grant detection heuristic and parser.

### Settings Page Is Read-Only — No Way to Edit Org Profile Without Redeployment

- **Issue:** The settings page (`src/grant_intel/dashboard/routes/settings.py`) renders the org profile YAML but has no edit functionality. Changing the org name, mission, programs, or keywords requires editing `config/org_profile.yaml` and redeploying.
- **Files:** `src/grant_intel/dashboard/routes/settings.py`, `templates/dashboard/settings.html`
- **Impact:** For a tool designed for a single nonprofit operator, editing org config should not require a deployment. This creates friction when the org updates its mission or programs.
- **Fix approach:** Add form-based editing for at minimum the keywords (tier1/tier2/tier3), persisted to a YAML or to the `settings` table.

### `config.py` Is 253 Lines and Contains Both Code and Data

- **Issue:** `src/grant_intel/config.py` contains `CURATED_FOUNDATIONS` (a large list of hardcoded foundation dicts, lines 123-224) and `BRAVE_SEARCH_QUERIES` (lines 228-252) alongside the config loading logic. These are data that should live in YAML config files, not Python source.
- **Files:** `src/grant_intel/config.py` lines 122-252
- **Impact:** Adding a new curated foundation requires editing Python source rather than a config file. Updating search queries requires a code change and redeployment.
- **Fix approach:** Move `CURATED_FOUNDATIONS` to `config/curated_foundations.yaml` and `BRAVE_SEARCH_QUERIES` to `config/search_queries.yaml`. Load them in `load_config`.

### `org_profile.yaml` Has a Missing EIN

- **Issue:** `config/org_profile.yaml` line 3: `ein: ""  # To be provided by YLM`. The EIN is blank. This means any feature that relies on the org's own EIN for self-identification (e.g., filtering out self-references in grant data) silently uses an empty string.
- **Files:** `config/org_profile.yaml` line 3
- **Impact:** Low immediate impact; the EIN field is not used in active code paths today. It will matter if self-exclusion or EIN-based matching is added.
- **Fix approach:** Fill in the actual EIN or add a startup validation that warns if EIN is blank.

---

## UX / Ops Concerns

### Draft Generation Blocks the Dashboard With No Progress Indication

- **Issue:** Clicking "Generate Draft" triggers `trigger_draft` (`src/grant_intel/dashboard/routes/actions.py` lines 89-149), which calls `draft_federal_narrative` synchronously. This makes 7 sequential Claude API calls (one per section), each taking 5-20 seconds. Total generation time is 35-140 seconds. The browser spins with no feedback; the user cannot know if it succeeded or timed out.
- **Files:** `src/grant_intel/dashboard/routes/actions.py` lines 89-149, `src/grant_intel/writer/agent.py` lines 26-72
- **Impact:** High friction for the primary value-generating feature. On Railway with the default 30s request timeout (before the explicit 300s is reached in `nixpacks.toml`), older deployments may time out.
- **Fix approach:** Run draft generation in a background thread, store the draft ID immediately, and poll for completion. Alternatively, show a "generating..." redirect page that auto-refreshes.

### No Monitoring or Alerting for Weekly Job Failures

- **Issue:** The weekly scoring job runs via Railway cron or system cron. Failures are logged to stderr but there is no Slack notification, email alert, or health-check endpoint to indicate whether the last weekly run succeeded.
- **Files:** `src/grant_intel/scoring/weekly.py`, `src/grant_intel/cli.py` lines 254-306
- **Impact:** If the weekly run silently fails (e.g., API key expires, Railway cron misfires), the operator won't notice until they manually check the dashboard and see stale data.
- **Fix approach:** Add a `/health` endpoint that returns the `last_weekly_run` timestamp and flags if it is more than 8 days old. Alternatively, send a short email summary on job completion.

### Brave Search and AI Scoring Triggers Are Unguarded Buttons

- **Issue:** The dashboard's action buttons (Score, Brave Search, Enrich) have no rate limiting or cooldown. Clicking "Score" multiple times in quick succession would fire multiple Claude API scoring runs and create duplicate score rows.
- **Files:** `src/grant_intel/dashboard/routes/actions.py` lines 25-88, `templates/dashboard/home.html`
- **Impact:** Accidental double-clicking could result in significant unexpected API costs (scoring 100 opportunities = multiple Claude Haiku calls per batch).
- **Fix approach:** Disable the button client-side on click (JavaScript). Add a server-side guard that checks `last_scored_at` from the settings table, similar to the weekly cooldown.

### Web Opportunities Have No Scoring or Prioritization

- **Issue:** Web opportunities discovered via Brave Search are stored in `web_opportunities` and displayed in a flat list (`src/grant_intel/dashboard/routes/web_opportunities.py`). Unlike Grants.gov opportunities, they are not scored or prioritized. The only filter is by funder name. The `scores` table has a `web_opportunity_id` column (`src/grant_intel/db.py` line 235-238) but it is never populated.
- **Files:** `src/grant_intel/db.py` lines 929-937, `src/grant_intel/dashboard/routes/web_opportunities.py`
- **Impact:** A user looking at 50+ web opportunities has no signal about which ones to pursue. The feature exists but provides limited actionable value.
- **Fix approach:** Wire `web_opportunity_id` scoring into the existing scoring pipeline. Add a "Score web opportunities" action to the dashboard.

---

## Opportunities (Quick Wins and High-Value Improvements)

1. **Add `/health` endpoint** — Returns JSON with `last_weekly_run`, opportunity count, and foundation count. Very low effort, high operational value.

2. **Fix `total_giving` data quality bug** — Use `totgrantspd` instead of `totfuncexpns` for 990-PF filers. This is a one-line fix in `src/grant_intel/sources/givingtuesday.py` line 74 that would immediately improve foundation scoring accuracy.

3. **Add CSRF tokens** — Flask-WTF integrates in ~20 lines and protects all POST routes. High security value, low effort.

4. **Pagination on list views** — Opportunities and foundations lists load everything into memory. Adding `LIMIT 50 OFFSET ?` to the queries and a "Next/Prev" button in templates would immediately improve performance and UX as the database grows.

5. **Score web opportunities** — The scoring infrastructure is already built; `web_opportunity_id` column already exists in the `scores` table. Connecting web opportunities to the rule scorer would add signal to a currently signal-free list.

6. **Move curated foundations and search queries to YAML** — Move `CURATED_FOUNDATIONS` and `BRAVE_SEARCH_QUERIES` out of `src/grant_intel/config.py` into YAML files. Enables the operator to add foundations and queries without a code change or redeployment.

7. **Add `test_weekly.py` and `test_brave_search.py`** — The two most important untested modules. Adding even basic tests for cooldown logic and grant-result filtering would significantly increase reliability confidence.

8. **Add startup validation for required env vars** — Check for `SECRET_KEY`, `DASHBOARD_PASSWORD_HASH`, and `ANTHROPIC_API_KEY` at startup and print clear error messages rather than defaulting to insecure values silently.

---

*Concerns audit: 2026-02-28*
