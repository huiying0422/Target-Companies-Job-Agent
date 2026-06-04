"""Idempotent company seed. Safe to re-run; does not touch seen_jobs."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"

# Customize: replace with your target companies, or add via Streamlit Company Manager.
# Format: (name, ats_type, slug, active, notes, careers_url)
# ats_type: greenhouse | lever | ashby | custom (custom rows are not scraped automatically)
SEED_COMPANIES = [
    ("Acme Corp", "greenhouse", "acme", 0, "demo — set active=1 and fix slug", None),
    ("Example Lever Co", "lever", "exampleco", 0, "demo — replace slug with real lever slug", None),
    ("Example Ashby Co", "ashby", "example-ashby", 0, "demo — replace slug with real ashby slug", None),
]

REMOVED_COMPANIES: list[str] = []

# (name, ats_type, slug, notes) — applied to existing DB rows
COMPANY_UPDATES: list[tuple[str, str, str, str]] = []


def apply_fixes(db_path: Path | str | None = None) -> None:
    """Update slugs/ATS and remove deprecated companies in jobs.db."""
    from database import init_db

    init_db()
    path = Path(db_path) if db_path else DB_PATH
    with sqlite3.connect(path) as conn:
        for name in REMOVED_COMPANIES:
            conn.execute("DELETE FROM companies WHERE name = ?", (name,))
        for name, ats_type, slug, notes in COMPANY_UPDATES:
            conn.execute(
                """
                UPDATE companies
                SET ats_type = ?, slug = ?, notes = ?, active = 1
                WHERE name = ?
                """,
                (ats_type, slug, notes, name),
            )
    print(f"Applied {len(COMPANY_UPDATES)} updates, removed {len(REMOVED_COMPANIES)} companies.")


def seed_companies(db_path: Path | str | None = None) -> int:
    """Insert seed rows; skip existing names. Returns number of rows in SEED_COMPANIES."""
    from database import init_db

    init_db()
    path = Path(db_path) if db_path else DB_PATH
    with sqlite3.connect(path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        for name, ats_type, slug, active, notes, careers_url in SEED_COMPANIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO companies
                    (name, ats_type, slug, careers_url, active, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, ats_type, slug, careers_url, active, notes),
            )
        after = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    added = after - before
    print(f"Seed list: {len(SEED_COMPANIES)} companies. DB total: {after} (+{added} new).")
    return len(SEED_COMPANIES)


def verify_all(db_path: Path | str | None = None):
    """Check live job-board URLs for rows marked 'verify slug'."""
    import requests

    path = Path(db_path) if db_path else DB_PATH
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name, ats_type, slug FROM companies WHERE notes LIKE '%verify%slug%'"
        ).fetchall()

    def check(ats_type: str, slug: str) -> bool | None:
        if ats_type == "greenhouse":
            url = f"https://boards.greenhouse.io/{slug}"
        elif ats_type == "lever":
            url = f"https://jobs.lever.co/{slug}"
        elif ats_type == "ashby":
            url = f"https://jobs.ashbyhq.com/{slug}"
        else:
            return None
        try:
            return requests.get(url, timeout=5).status_code == 200
        except requests.RequestException:
            return False

    for name, ats_type, slug in rows:
        ok = check(ats_type, slug)
        status = "OK" if ok else "DEAD" if ok is False else "SKIP"
        print(f"{status:6} | {ats_type:12} | {name:30} | {slug}")


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd == "verify":
        verify_all()
    elif cmd == "apply":
        apply_fixes()
    elif cmd == "seed":
        seed_companies()
        apply_fixes()
    else:
        print("Usage: python db_seed.py [seed|apply|verify]")
        raise SystemExit(1)
