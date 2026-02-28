# External Integrations

**Analysis Date:** 2026-02-28

---

## APIs & External Services

### Anthropic Claude API

- **Purpose:** (1) Grant/foundation scoring — ranks 1-10 by mission alignment; (2) Grant narrative writing — generates full federal grant narratives section-by-section and foundation LOIs
- **SDK:** `anthropic==0.84.0` (official Python SDK)
- **Auth:** API key via `ANTHROPIC_API_KEY` env var; passed as `anthropic.Anthropic(api_key=...)`
- **Models used:**
  - `claude-haiku-4-5-20251001` — bulk opportunity and foundation scoring (batches of 5, `max_tokens=1024`) — `src/grant_intel/scoring/matcher.py`
  - `claude-sonnet-4-6` — grant narrative writing and LOI generation (`max_tokens=4096`) — `src/grant_intel/writer/sections.py` (`WRITING_MODEL` constant)
- **Usage pattern:** Scoring uses batch JSON prompts (5 items/call); narrative writing makes one call per section with all prior sections threaded as context
- **Rate limiting:** No explicit rate limiter on Anthropic calls; relies on SDK retry behavior
- **Cost notes:** Haiku used for high-volume scoring (cheaper); Sonnet used only for draft writing (less frequent). Scoring is gated behind a rule-engine funnel — only opportunities with `rule_score >= 6` (configurable via `--ai-threshold`) are sent to Claude AI
- **Error handling:** Catches `anthropic.AuthenticationError` (aborts scoring), `anthropic.APIError` (logs, continues with next batch)
- **Config files:** `src/grant_intel/scoring/matcher.py`, `src/grant_intel/writer/sections.py`, `src/grant_intel/writer/agent.py`

---

### Grants.gov REST API

- **Purpose:** Federal grant opportunity discovery — searches by keyword, fetches full opportunity details
- **Endpoints:**
  - `POST https://api.grants.gov/v1/api/search2` — keyword search with pagination
  - `POST https://api.grants.gov/v1/api/fetchOpportunity` — fetch single opportunity by ID
- **Auth:** None — public API, no key required
- **Rate limiting:** Conservative self-imposed limit of 1 request/second (`RateLimiter(calls_per_second=1.0)`) in `src/grant_intel/sources/grants_gov.py`
- **Retry logic:** Exponential backoff (2s, 4s, 8s) on HTTP 429 and 5xx via `request_with_retry()` in `src/grant_intel/utils/rate_limiter.py`
- **Pagination:** Auto-paginates via `startRecordNum` + `rows=100` until `start >= hitCount`
- **Search keywords:** Tiered keyword system defined in `config/org_profile.yaml` under `search_keywords.tier1/2/3`
- **Result parsing:** `parse_opportunity()` normalizes hits into standard dict; deduped by `opportunity_id`
- **Config files:** `src/grant_intel/sources/grants_gov.py`

---

### ProPublica Nonprofit Explorer API

- **Purpose:** (1) Research peer organizations by EIN to understand funding landscape; (2) Search for foundation prospects by keyword; (3) Enrich foundation records with financial data (assets, revenue, NTEE code)
- **Base URL:** `https://projects.propublica.org/nonprofits/api/v2`
- **Endpoints used:**
  - `GET /search.json?q={query}&state[id]={state}&page={page}` — keyword search
  - `GET /organizations/{ein}.json` — detailed org lookup by EIN including filings
- **Auth:** None — public API, no key required
- **Rate limiting:** Conservative self-imposed 0.5 requests/second (`RateLimiter(calls_per_second=0.5)`) — 1 req per 2 seconds
- **Pagination:** Loops pages until `len(all_orgs) >= total_results`, capped at 10 pages max
- **404 handling:** Returns `None` / empty list gracefully; ProPublica returns 404 for no-results state-filtered queries
- **Note on GivingTuesday:** `src/grant_intel/sources/givingtuesday.py` is named after the original planned integration (GivingTuesday 990 Infrastructure API) but actually uses ProPublica internally — the GivingTuesday API returns 403 on all endpoints as of Feb 2026
- **Config files:** `src/grant_intel/sources/propublica.py`, `src/grant_intel/sources/givingtuesday.py`

---

### IRS 990-PF XML (AWS S3)

- **Purpose:** Parse grant disbursements from foundation 990-PF tax filings to identify which foundations have funded ministry/youth/pastoral work
- **Endpoint:** `GET https://s3.amazonaws.com/irs-form-990/{object_id}_public.xml`
- **Auth:** None — public S3 bucket
- **Rate limiting:** 2.0 requests/second (`RateLimiter(calls_per_second=2.0)`)
- **XML parsing:** Uses `lxml.etree` to parse IRS e-file XML schema; handles namespace variations across 990-PF schema versions
- **Elements parsed:** `GrantOrContributionPdDurYrGrp` / `GrantOrContributionPdDuringYr` — extracts recipient name, EIN, amount, purpose
- **Relevance filter:** Matches against `MATCH_KEYWORDS` list (youth ministry, pastoral, christian, church, etc.) in `src/grant_intel/sources/irs990.py`
- **Usage note:** Requires `object_id` values from ProPublica filings data; no-op if `object_ids` not provided
- **Config files:** `src/grant_intel/sources/irs990.py`

---

### Brave Search API

- **Purpose:** Web discovery of active grant opportunities from foundation websites that are not in Grants.gov or ProPublica
- **Endpoint:** `GET https://api.search.brave.com/res/v1/web/search`
- **Auth:** `X-Subscription-Token: {BRAVE_API_KEY}` header
- **Env var:** `BRAVE_API_KEY`
- **Rate limiting:** 1.0 requests/second self-imposed
- **Free tier:** 2,000 requests/month (documented in source file header)
- **Query set:** 18 pre-configured queries in `BRAVE_SEARCH_QUERIES` list in `src/grant_intel/config.py` targeting known funders (Lilly Endowment, Chatlos, Kern, etc.) and faith-based grant discovery
- **Result filtering:** `is_grant_result()` heuristic requires 2+ grant indicator words (apply, deadline, rfp, loi, etc.) in title+description; skips CDN/file URLs
- **Data extracted:** title, funder name (from URL domain/title), URL, description, deadline (regex), award amounts (regex)
- **Storage:** Results saved to `web_opportunities` table in SQLite
- **Config files:** `src/grant_intel/sources/brave_search.py`, `src/grant_intel/config.py`

---

### Simpler Grants API (Unused/Future)

- **Purpose:** Planned integration, key stored in config but no source file implements it
- **Env var:** `SIMPLER_GRANTS_API_KEY`
- **Status:** Key is accepted in `Config` dataclass (`src/grant_intel/config.py`) but no corresponding source module exists
- **Config files:** `src/grant_intel/config.py`

---

## Data Storage

**Databases:**
- SQLite — file at `data/grants.db`
  - Connection: configured via `--db` CLI flag or hardcoded default `data/grants.db`
  - Client: Python stdlib `sqlite3`, accessed via functions in `src/grant_intel/db.py`
  - No ORM — raw SQL with `sqlite3.Row` row factory
  - WAL journal mode for concurrent read performance

**File Storage:**
- Local filesystem only
- Output CSVs: `output/` directory (created on demand)
- Grant draft Markdown files: `output/drafts/` directory
- Email digest HTML: `output/` directory

**Caching:**
- None — each pipeline run re-fetches from external APIs; SQLite upserts prevent duplicates via `UNIQUE` constraints

---

## Authentication & Identity

**Dashboard Auth:**
- Flask-Login with a single hardcoded admin user (`AdminUser` with `id="admin"`)
- Credentials verified against env vars: `DASHBOARD_USERNAME` (default: `"admin"`) and either `DASHBOARD_PASSWORD_HASH` (bcrypt via werkzeug) or `DASHBOARD_PASSWORD` (plain text fallback for initial setup)
- Session secret: `SECRET_KEY` env var (defaults to `"change-me-in-production"`)
- Password hashing: werkzeug `generate_password_hash` / `check_password_hash`
- Implementation: `src/grant_intel/dashboard/auth.py`

**External API Auth:**
- Anthropic: Bearer-style API key (`ANTHROPIC_API_KEY`)
- Brave: `X-Subscription-Token` header (`BRAVE_API_KEY`)
- Grants.gov: No auth
- ProPublica: No auth
- IRS S3: No auth

---

## Email / SMTP

**Purpose:** Weekly grant intelligence digest email with top-scored opportunities and foundations
- **Transport:** Python stdlib `smtplib` with STARTTLS
- **Auth:** Username/password login (`SMTP_USER`, `SMTP_PASS`)
- **Env vars:** `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO` (comma-separated list)
- **Format:** Multipart MIME with HTML (`templates/email_digest.html.j2`) and plain text fallback
- **Trigger:** CLI `grant-intel digest` command; `--dry-run` renders HTML to file without sending
- **Implementation:** `src/grant_intel/delivery/email_digest.py`

---

## Monitoring & Observability

**Error Tracking:** None — no Sentry, Datadog, or similar
**Logs:** Python stdlib `logging` module; all modules use `logger = logging.getLogger(__name__)`; CLI configures `basicConfig` to stderr with timestamp format; no structured logging or log aggregation

---

## CI/CD & Deployment

**Hosting:** Railway (Procfile + nixpacks.toml present)
**CI Pipeline:** None detected — no GitHub Actions, CircleCI, or similar config files

---

## Environment Variables Reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | For AI scoring/drafting | None | Claude API authentication |
| `BRAVE_API_KEY` | For web discovery | None | Brave Search API authentication |
| `SMTP_HOST` | For email digest | None | SMTP server hostname |
| `SMTP_PORT` | No | `587` | SMTP server port |
| `SMTP_USER` | For email digest | None | SMTP login username |
| `SMTP_PASS` | For email digest | None | SMTP login password |
| `EMAIL_TO` | For email digest | None | Comma-separated recipient list |
| `SIMPLER_GRANTS_API_KEY` | No | None | Future use — not yet implemented |
| `DASHBOARD_USERNAME` | No | `admin` | Dashboard login username |
| `DASHBOARD_PASSWORD_HASH` | Recommended | None | Bcrypt hash of dashboard password |
| `DASHBOARD_PASSWORD` | No | `changeme` | Plain text fallback (initial setup only) |
| `SECRET_KEY` | Yes (production) | `change-me-in-production` | Flask session signing key |
| `AUTO_POPULATE` | No | `true` | Trigger background pipeline on empty DB |
| `PORT` | Railway sets this | `8000` | gunicorn bind port |

**Loading mechanism:** `python-dotenv` `load_dotenv()` called in `src/grant_intel/config.py:load_config()`; all vars read via `os.getenv()`

**Secrets location:** `.env` file in project root (not committed — in `.gitignore`)

---

## Webhooks & Callbacks

**Incoming:** None — no webhook endpoints
**Outgoing:** None — no webhook dispatching

---

*Integration audit: 2026-02-28*
