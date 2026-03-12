# Aptos Developer Monthly Newsletter

Automated system that scrapes Aptos GitHub repositories and community sources weekly, aggregates monthly, and generates a polished developer newsletter with Markdown and HTML output.

## How It Works

1. **Weekly scrape** (Sunday 02:00 UTC) — GitHub Actions runs scrapers against configured repos and sources, saving JSON to `data/weekly/`
2. **Monthly generation** (1st of month) — Aggregates the month's weekly data, categorizes items, generates Claude-powered summaries, renders Markdown + HTML, and opens a PR for review

## Setup

### Prerequisites

- Python 3.11+
- GitHub Personal Access Token with `repo` read scope
- Anthropic API key (for Claude summarization)

### Installation

```bash
git clone <repo-url>
cd monthly-dev-newsletter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your tokens:

```bash
cp .env.example .env
```

Set these GitHub Actions secrets:

| Secret | Purpose |
|--------|---------|
| `GH_SCRAPE_TOKEN` | GitHub PAT with repo read scope |
| `ANTHROPIC_API_KEY` | Claude API key for summarization |

Set this repository variable:

| Variable | Purpose |
|----------|---------|
| `NEWSLETTER_REVIEWERS` | Comma-separated GitHub handles for PR auto-assignment |

### Customizing Sources

Edit the YAML files in `config/`:

- **`repos.yaml`** — GitHub repos to track (releases, PRs, commits)
- **`sources.yaml`** — Blog RSS, Discourse forum, AIP repo
- **`newsletter.yaml`** — Newsletter sections, categorization rules, Claude prompts, branding

## Local Usage

### Run a weekly scrape

```bash
export GH_SCRAPE_TOKEN=ghp_...
python scripts/run_weekly_scrape.py
```

Override the week:

```bash
WEEK_OVERRIDE=2026-W09 python scripts/run_weekly_scrape.py
```

### Generate a newsletter

By default, the generator targets the previous month. Use `MONTH_OVERRIDE` to specify a different month.

#### Full generation

Aggregates scraped data, categorizes items, calls Claude for summaries, and renders Markdown + HTML output.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
MONTH_OVERRIDE=2026-02 python scripts/run_monthly_generate.py
```

#### Dry run

Prints a categorized summary of items to the console without calling Claude or writing any files. Useful for checking what the scraper found before spending API credits.

```bash
DRY_RUN=true MONTH_OVERRIDE=2026-02 python scripts/run_monthly_generate.py
```

#### Skip summarization

Runs the full pipeline but skips the Claude summarization step. Outputs raw categorized items into the rendered templates.

```bash
SKIP_SUMMARIZE=true MONTH_OVERRIDE=2026-02 python scripts/run_monthly_generate.py
```

#### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONTH_OVERRIDE` | Previous month | Target month in `YYYY-MM` format |
| `DRY_RUN` | `false` | Print categorized items to console and exit |
| `SKIP_SUMMARIZE` | `false` | Skip Claude summarization (render raw items) |
| `ANTHROPIC_API_KEY` | — | Required for full generation |

#### Output

Files appear in `output/newsletters/`:
- `YYYY-MM.md` — Markdown version
- `YYYY-MM.html` — HTML email version (CSS inlined)

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

## Project Structure

```
├── .github/workflows/       # GitHub Actions (weekly scrape + monthly generation)
├── config/                  # YAML configuration files
├── src/
│   ├── scrapers/            # Data collection (GitHub, RSS, Discourse)
│   ├── processor/           # Aggregation and categorization
│   ├── generator/           # Claude summarization and Jinja2 rendering
│   └── utils/               # Config loader, date helpers, GitHub client
├── scripts/                 # CLI entry points
├── data/weekly/             # Weekly scrape JSON files (auto-committed)
├── output/newsletters/      # Generated newsletter files
├── templates/               # Jinja2 templates (Markdown + HTML)
└── tests/                   # Unit tests
```

## Newsletter Sections

1. **Breaking Changes** — highest priority, items here don't appear elsewhere
2. **Protocol Updates** — core node releases, consensus/execution/storage
3. **SDK & Tooling** — SDK releases, CLI, wallet adapter, indexer
4. **New Features** — feat: prefix commits/PRs, enhancement labels
5. **Governance & AIPs** — new/updated Aptos Improvement Proposals
6. **Community Highlights** — blog posts, forum discussions (catch-all)
