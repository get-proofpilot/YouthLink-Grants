# Testing Patterns

**Analysis Date:** 2026-02-28

## Test Framework

**Runner:**
- pytest 9.0.2 (confirmed via compiled cache filenames: `cpython-314-pytest-9.0.2.pyc`)
- Python 3.14
- Config in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  ```

**Assertion Library:**
- pytest's built-in `assert` (no additional assertion library)

**Mocking Libraries:**
- `unittest.mock` (stdlib) — `MagicMock`, `patch` for Claude API calls
- `responses` library (PyPI) — HTTP response mocking for external API calls (Grants.gov, ProPublica)

**Run Commands:**
```bash
# Activate venv first
source .venv/bin/activate

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific file
pytest tests/test_db.py

# Run a specific class
pytest tests/test_dashboard.py::TestPriorityScore

# Run a specific test
pytest tests/test_matcher.py::test_calculate_urgency_30_day

# Coverage (not configured — requires pytest-cov install)
# pytest --cov=src/grant_intel --cov-report=term-missing
```

## Test File Inventory

**`tests/conftest.py`** — shared fixtures used across all test files
- `test_db` — in-memory SQLite connection with schema applied
- `sample_opportunity` — realistic Grants.gov opportunity dict
- `sample_foundation` — ProPublica foundation dict
- `grants_gov_search_response` — mock Grants.gov search2 API JSON
- `propublica_org_response` — mock ProPublica organization API JSON
- `sample_org_profile` — full `OrgProfile` instance for Youth Link Ministries
- `sample_nofa_text` — realistic 200-word NOFA/RFP text block
- `mock_claude_section_response` — realistic Claude narrative section text
- `mock_claude_loi_response` — realistic Claude LOI text
- `sample_requirements` — structured parsed NOFA requirements dict
- `sample_990pf_xml` — sample IRS 990-PF XML bytes with 3 grant records

**`tests/test_db.py`** — database CRUD operations (`src/grant_intel/db.py`)
- Schema creation and table existence
- `upsert_opportunity` — insert new, detect duplicate, return bool
- `upsert_foundation` — insert new, detect duplicate
- `insert_score` — score insertion and retrieval
- `get_unscored_opportunities` — filtering by score join
- `get_unscored_foundations` — filtering by score join
- `get_pipeline_stats` — aggregate counts
- `upsert_similar_org` — insert and dedup

**`tests/test_matcher.py`** — scoring engine (`src/grant_intel/scoring/matcher.py`)
- `build_system_prompt` — verifies all org profile fields appear in Claude prompt
- `_calculate_urgency` — 30-day, 60-day, 90-day, none, empty/None deadline cases

**`tests/test_grants_gov.py`** — Grants.gov API client (`src/grant_intel/sources/grants_gov.py`)
- `search_opportunities` — basic search, pagination, empty results (uses `responses` mock)
- `parse_opportunity` — standardized dict output from raw API hit
- `discover_grants` — deduplication across keywords, multi-tier discovery

**`tests/test_propublica.py`** — ProPublica API client (`src/grant_intel/sources/propublica.py`)
- `search_orgs` — keyword org search (uses `responses` mock)
- `get_organization` — fetch by EIN, 404 handling
- `extract_org_info` — org data parsing
- `extract_filings` — 990 filing data parsing
- `research_similar_orgs` — end-to-end org research

**`tests/test_irs990.py`** — IRS 990-PF XML parser (`src/grant_intel/sources/irs990.py`)
- `parse_990pf_grants` — parse grants from valid XML, invalid XML, empty XML
- `filter_relevant_grants` — keyword-based relevance filtering of grant recipients

**`tests/test_csv_export.py`** — CSV delivery (`src/grant_intel/delivery/csv_export.py`)
- `export_opportunities_csv` — file creation, column headers, value formatting (`$25,000`)
- `export_foundations_csv` — file creation, column headers, value formatting
- Empty list export — no crash on zero rows

**`tests/test_email_digest.py`** — Email digest rendering (`src/grant_intel/delivery/email_digest.py`)
- `render_digest` — HTML template rendering with real data
- `render_digest` empty — renders with no opportunities/foundations
- `dry_run_digest` — saves `.html` file to temp directory

**`tests/test_writer.py`** — Grant writer agent (`src/grant_intel/writer/`)
- 8 test classes covering all writer submodules:
  - `TestPrompts` — system prompt, section prompt, LOI prompt construction
  - `TestPostProcessing` — markdown stripping, banned word flagging, clean text passthrough
  - `TestDetermineSections` — default sections, funder name mapping, core section enforcement
  - `TestExtractor` — empty requirements structure, Claude API parse (mocked), empty input handling
  - `TestSectionGeneration` — single section generation (mocked Claude), prior sections threading
  - `TestDraftDB` — draft insert/retrieve, not-found case, drafts-by-opportunity, status update, pipeline stats
  - `TestAgent` — full narrative draft (mocked section generator), LOI draft (mocked Claude), draft record builder

**`tests/test_dashboard.py`** — Flask dashboard (`src/grant_intel/dashboard/`)
- 7 test classes:
  - `TestPriorityScore` — `calculate_priority_score`, labels (High/Low), factor scoring
  - `TestRequirementMatching` — `analyze_requirements`, 6-check structure, pass/fail logic
  - `TestAuth` — login page, login success/failure, login-required redirect, logout
  - `TestDashboardRoutes` — all main routes (home, opportunities, foundations, drafts, pipeline, settings)
  - `TestPipelineAndStatus` — stage change, invalid stage, notes edit, draft status, invalid draft status
  - `TestOpportunityFilters` — filter by min_score, urgency, tier
  - `TestDashboardDB` — pipeline entry lookup by target ID

## Test File Organization

**Location:** All tests in a top-level `tests/` directory, separate from source.

**Naming:**
- Test files: `test_{module_name}.py` matching source module: `test_db.py` → `src/grant_intel/db.py`
- Test functions: `test_{what_is_tested}_{condition}`: `test_upsert_opportunity_new`, `test_calculate_urgency_30_day`
- Test classes: `Test{Feature}` grouping related scenarios: `TestAuth`, `TestDashboardRoutes`

**Structure:**
```
tests/
├── __init__.py
├── conftest.py          # all shared fixtures
├── test_csv_export.py
├── test_dashboard.py    # largest file — Flask integration + unit tests
├── test_db.py
├── test_email_digest.py
├── test_grants_gov.py
├── test_irs990.py
├── test_matcher.py
├── test_propublica.py
└── test_writer.py       # second largest — 8 test classes
```

## Test Structure

**Function-style (most test files):**
```python
def test_upsert_opportunity_new(test_db, sample_opportunity):
    """Test inserting a new opportunity."""
    is_new = upsert_opportunity(test_db, sample_opportunity)
    assert is_new is True

    row = test_db.execute(
        "SELECT * FROM opportunities WHERE opportunity_id = ?",
        (sample_opportunity["opportunity_id"],),
    ).fetchone()
    assert row is not None
    assert row["title"] == sample_opportunity["title"]
```

**Class-style (writer and dashboard tests):**
```python
class TestPrompts:
    def test_system_prompt_includes_org_profile(self, sample_org_profile):
        """System prompt should contain all org profile fields."""
        prompt = build_system_prompt(sample_org_profile)
        assert "Youth Link Ministries" in prompt
```

**Docstring pattern:** Every test has a one-line docstring describing what is being tested.

**Assertion style:** Simple `assert value`, `assert x == y`, `assert x in y`. No `pytest.approx` or custom matchers.

## Mocking

**Two mocking approaches:**

**1. `responses` library for HTTP (external API tests):**
```python
import responses

@responses.activate
def test_search_opportunities_basic(grants_gov_search_response):
    responses.post(SEARCH_URL, json=grants_gov_search_response)
    results = search_opportunities("faith-based")
    assert len(results) == 2
```
Used in: `test_grants_gov.py`, `test_propublica.py`

**2. `unittest.mock.patch` for Claude API (writer tests):**
```python
from unittest.mock import MagicMock, patch

@patch("grant_intel.writer.extractor.anthropic.Anthropic")
def test_extract_requirements_from_text(self, mock_anthropic, sample_nofa_text):
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({...})

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic.return_value = mock_client

    result = extract_requirements_from_text(sample_nofa_text, "fake-key")
    mock_client.messages.create.assert_called_once()
```
Patch target is always the import path where the class is used, not where it is defined.

**3. `unittest.mock.patch` for function-level mocking (agent tests):**
```python
@patch("grant_intel.writer.agent.generate_section")
def test_draft_federal_narrative(self, mock_gen_section, ...):
    mock_gen_section.return_value = "Section content here."
```

**What gets mocked:**
- All Claude `anthropic.Anthropic` client instantiation
- All external HTTP calls (Grants.gov, ProPublica APIs)
- Individual functions when testing orchestrators (`generate_section` when testing agent)

**What is NOT mocked:**
- SQLite database (uses real in-memory SQLite via `test_db` fixture)
- Jinja2 template rendering (uses real templates from `templates/`)
- File system (uses `tempfile.TemporaryDirectory()` for real temp files)
- Python stdlib: `json`, `csv`, `xml`, `datetime`

## Fixtures and Factories

**Shared fixtures in `tests/conftest.py`** (available to all test files automatically):

```python
@pytest.fixture
def test_db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def sample_opportunity():
    """A sample Grants.gov opportunity dict."""
    return { ... }  # Full realistic dict with all fields populated
```

**Local fixtures in `tests/test_dashboard.py`** (scoped to dashboard tests):
```python
@pytest.fixture
def db_path():
    """Temporary SQLite database file (on disk, not in-memory)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    init_db(conn)
    conn.close()
    yield path
    os.unlink(path)

@pytest.fixture
def seeded_db(db_path):
    """Database seeded with one opportunity, one foundation, one draft, one pipeline entry."""
    ...
    return db_path

@pytest.fixture
def app(seeded_db):
    """Flask test application with test config."""
    os.environ["DASHBOARD_USERNAME"] = "admin"
    os.environ["DASHBOARD_PASSWORD"] = "testpass"
    application = create_app(config_path="config/org_profile.yaml", db_path=seeded_db)
    application.config["TESTING"] = True
    return application

@pytest.fixture
def authed_client(client):
    """Pre-authenticated Flask test client."""
    client.post("/login", data={"username": "admin", "password": "testpass"})
    return client
```

**Fixture for temp files (inline in test functions):**
```python
with tempfile.TemporaryDirectory() as tmpdir:
    path = export_opportunities_csv(opportunities, tmpdir)
    assert os.path.exists(path)
```

## Coverage

**Requirements:** None enforced — no `--cov` flag in pytest config.

**Install coverage tool:**
```bash
pip install pytest-cov
pytest --cov=src/grant_intel --cov-report=term-missing
```

**Observed gaps** (see CONCERNS.md for full list):
- `src/grant_intel/scoring/rules.py` — rule scoring engine has no dedicated unit tests; covered only indirectly through integration
- `src/grant_intel/scoring/weekly.py` — weekly scheduler entirely untested
- `src/grant_intel/sources/brave_search.py` — not tested
- `src/grant_intel/sources/curated.py` — not tested
- `src/grant_intel/sources/givingtuesday.py` — not tested
- `src/grant_intel/sources/nodc_import.py` — not tested
- `src/grant_intel/utils/rate_limiter.py` — not tested
- `src/grant_intel/cli.py` — CLI commands not tested via Click test runner
- `src/grant_intel/delivery/email_digest.py` — `send_digest` (SMTP sending) not tested; only `render_digest` and `dry_run_digest` are covered
- `src/grant_intel/dashboard/routes/*.py` — route handlers tested via Flask test client (integration level), no unit-level handler tests

## Test Types

**Unit Tests:**
- Pure function tests with no I/O: `test_matcher.py`, `test_irs990.py`, `test_csv_export.py`
- Pattern: call function, assert return value
- No setup/teardown beyond fixture injection

**Integration Tests:**
- Database-backed tests using real SQLite in-memory: `test_db.py`, parts of `test_writer.py`
- Flask route tests using real app + test client: `test_dashboard.py`
- Pattern: seed data → call function/route → assert DB state or response

**HTTP-mocked Tests:**
- External API tests using `responses` library: `test_grants_gov.py`, `test_propublica.py`
- Behave like unit tests but exercise full HTTP client code paths

**E2E Tests:**
- Not present. No browser automation, Playwright, or Selenium.

## Common Patterns

**Testing HTTP APIs with `responses`:**
```python
@responses.activate
def test_get_organization_not_found():
    responses.get(f"{BASE_URL}/organizations/000000000.json", status=404)
    data = get_organization("000000000")
    assert data is None
```

**Testing file output:**
```python
with tempfile.TemporaryDirectory() as tmpdir:
    filepath, sections = draft_federal_narrative(
        api_key="fake-key",
        org=sample_org_profile,
        requirements=sample_requirements,
        output_dir=tmpdir,
    )
    assert os.path.exists(filepath)
    assert filepath.endswith(".md")
    content = open(filepath).read()
    assert "Federal Grant Narrative" in content
```

**Testing Claude API call arguments:**
```python
call_kwargs = mock_client.messages.create.call_args
messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
assert len(messages) == 3
assert "Burnout is a real problem" in messages[0]["content"]
```

**Testing DB state after mutation:**
```python
def test_upsert_opportunity_duplicate(test_db, sample_opportunity):
    upsert_opportunity(test_db, sample_opportunity)
    is_new = upsert_opportunity(test_db, sample_opportunity)
    assert is_new is False
    count = test_db.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    assert count == 1
```

**Testing Flask routes (authenticated):**
```python
def test_opportunity_detail(self, authed_client):
    resp = authed_client.get("/opportunities/1")
    assert resp.status_code == 200
    assert b"Faith-Based" in resp.data

def test_opportunity_not_found(self, authed_client):
    resp = authed_client.get("/opportunities/9999")
    assert resp.status_code == 404
```

## CI/CD Test Automation

**No CI pipeline detected.** No `.github/workflows/`, `.circleci/`, or `Jenkinsfile` present.

**Deployment target:** Railway (see `nixpacks.toml`, `Procfile`). Railway does not run tests automatically based on current config.

**Manual test run before deploy:**
```bash
cd /Users/matthewanderson/YouthLink-Grants
source .venv/bin/activate
pytest -v
```

---

*Testing analysis: 2026-02-28*
