# YouthLink Grant Intelligence Tool

A Python CLI tool that discovers grant opportunities, researches foundation funding patterns, scores each opportunity using AI, and delivers weekly prioritized reports for Youth Link Ministries.

## What It Does

1. **Grant Discovery** - Searches Grants.gov for federal grant opportunities using mission-aligned keywords
2. **Foundation Research** - Analyzes IRS 990 filings of similar organizations via ProPublica to identify foundations already funding pastoral development work
3. **AI Match Scoring** - Uses Claude API to score each opportunity 1-10 against YLM's specific profile
4. **Weekly Delivery** - Generates CSV reports and HTML email digests with the top-scored opportunities

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Initialize database
grant-intel db-init

# Run individual phases
grant-intel search      # Search Grants.gov
grant-intel research    # Research foundations via ProPublica
grant-intel score       # Score with Claude AI
grant-intel report      # Generate CSV reports
grant-intel digest      # Send/preview email digest

# Run full pipeline
grant-intel run

# Check status
grant-intel status
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `grant-intel search` | Search Grants.gov for opportunities matching YLM keywords |
| `grant-intel research` | Research similar orgs and foundations via ProPublica 990 filings |
| `grant-intel score` | Score all unscored items using Claude AI (requires ANTHROPIC_API_KEY) |
| `grant-intel report` | Export CSV reports to `output/` directory |
| `grant-intel digest` | Send weekly email digest (or `--dry-run` to preview) |
| `grant-intel run` | Full pipeline: search + research + score + report + digest |
| `grant-intel db-init` | Initialize/reset the SQLite database |
| `grant-intel status` | Show pipeline statistics |

## Configuration

- `config/org_profile.yaml` - Organization profile, mission, programs, search keywords
- `config/similar_orgs.yaml` - Comparable organizations for 990 research
- `.env` - API keys and SMTP settings (see `.env.example`)

## Data Sources

| Source | Auth | Cost | Purpose |
|--------|------|------|---------|
| Grants.gov REST API | None | Free | Federal grant opportunities |
| ProPublica Nonprofit Explorer | None | Free | 990 filings for similar orgs |
| IRS 990-PF XML (S3) | None | Free | Foundation grant disbursements |
| Claude API | API key | ~$5-15/mo | AI match scoring |

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
src/grant_intel/
├── cli.py              # Click CLI commands
├── config.py           # Configuration loading
├── db.py               # SQLite database layer
├── sources/
│   ├── grants_gov.py   # Grants.gov API client
│   ├── propublica.py   # ProPublica API client
│   └── irs990.py       # IRS 990-PF XML parser
├── scoring/
│   └── matcher.py      # Claude API scoring engine
├── delivery/
│   ├── csv_export.py   # CSV report generation
│   └── email_digest.py # Email digest via SMTP
└── utils/
    └── rate_limiter.py  # Rate limiting + retry logic
```

## Weekly Automation

Add to crontab for automated Monday morning runs:

```
0 6 * * 1 cd /path/to/YouthLink-Grants && grant-intel run >> data/cron.log 2>&1
```
