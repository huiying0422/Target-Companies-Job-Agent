# Target Companies Job Agent

## Why I built this

I got tired of manually checking 60+ company career pages every week.
LinkedIn and Indeed are noisy — they show you irrelevant roles and you
still miss new postings from the companies you actually care about.

This tool checks your target companies daily, filters for roles matching
your keywords, uses Claude AI to score your fit, and generates a tailored
PDF resume for each application — automatically.

If you already know which companies you want to work at, this is for you.

## What you need to get started

Before running anything, prepare these 5 things:

1. **Your resume** — plain text format (copy from your Word doc)
2. **Your target companies** — just the names, the tool handles the rest
3. **Your notification email** — where job alerts get sent
4. **Your skills + target role** — used by AI to score your fit
5. **Your search keywords** — e.g. `machine learning, AI engineer, python`

---

A template for scraping jobs from company career boards (Greenhouse, Lever, Ashby), filtering by your keywords, optional Claude-powered fit scoring, email alerts, and a Streamlit dashboard with resume tailoring.

**No API keys or personal data belong in this repository.** Secrets live in `.env`, GitHub Actions secrets, Streamlit/Railway environment variables, or your machine only.

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USER/Target-Companies-Job-Agent.git
cd Target-Companies-Job-Agent
pip install -r requirements.txt
```

### 2. Copy example config (required)

```bash
cp config/candidate_profile.example.txt config/candidate_profile.txt
cp keywords.example.txt keywords.txt
cp templates/base_resume.example.txt templates/base_resume.txt
cp .env.example .env
```

Edit each file with **your** profile, keywords, resume, and secrets.

### 3. Initialize the database

```bash
python db_seed.py
```

Demo companies are inactive by default. Activate and add real companies in the Streamlit **Company Manager**, or edit `db_seed.py`.

### 4. Run locally

**Dashboard:**

```bash
streamlit run app.py
```

**One-off scrape + email (optional):**

```bash
# .env must include GMAIL_* and NOTIFY_EMAIL for email; ANTHROPIC_API_KEY optional for verdicts
python main.py
```

**Resume tailor (CLI):**

```bash
brew install pango   # Mac — WeasyPrint system dependency
export ANTHROPIC_API_KEY="sk-ant-..."
python resume_engine.py --jd "Paste job description" --job-title "MLE" --company "Acme"
```

## What to customize

| File | Purpose |
|------|---------|
| `config/candidate_profile.txt` | Background for Claude job verdicts (`ranker.py`) |
| `keywords.txt` | Title/description keyword filter (`filters.py`) |
| `templates/base_resume.txt` | Base resume for tailoring (`resume_engine.py`) |
| `db_seed.py` | Starter company list (`SEED_COMPANIES`) |
| `.env` | API keys and email (see `.env.example`) |
| `CANDIDATE_NAME` in `.env` | Name used in verdict prompts (optional) |
| `pdf_generator.py` | `_ROLE_BULLET_LIMITS` if you want per-employer bullet caps |

All user-specific paths above are **gitignored**.

## Secrets (never commit)

| Secret | Where to set |
|--------|----------------|
| `ANTHROPIC_API_KEY` | `.env`, Streamlit secrets, GitHub Actions secret |
| `GMAIL_FROM`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL` | `.env`, GitHub Actions secrets |
| Railway | Railway project **Variables** (not in repo) — deploy uses `railway.toml` only for the start command |

`railway.toml` and `.github/workflows/job-check.yml` reference secret **names** only, not values.

## GitHub Actions

Scheduled workflow: download `jobs.db` artifact → seed companies → `main.py` → re-upload artifact.

Add repository secrets: `GMAIL_FROM`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL`, and optionally `ANTHROPIC_API_KEY`.

## Deploy (Streamlit / Railway)

- **Streamlit Cloud:** main file `app.py`; set `ANTHROPIC_API_KEY` in app secrets for Resume Tailor.
- **Railway:** connect repo; set environment variables in the Railway dashboard (no keys in git).

## Project layout

```
app.py              Streamlit UI
main.py             Batch scraper + notifier
db_seed.py          Company seed data
ranker.py           Optional Claude verdicts
resume_engine.py    Resume tailoring CLI
scrapers/           Greenhouse, Lever, Ashby
```

## License

MIT — see [LICENSE](LICENSE).
