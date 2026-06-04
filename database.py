import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_id TEXT PRIMARY KEY,
                company TEXT,
                title TEXT,
                url TEXT,
                matched_keywords TEXT,
                first_seen TEXT,
                location TEXT,
                verdict_label TEXT,
                verdict_reason TEXT,
                is_us INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_health (
                company TEXT PRIMARY KEY,
                last_job_count INTEGER,
                last_checked TEXT,
                consecutive_zeros INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                ats_type TEXT NOT NULL,
                slug TEXT NOT NULL,
                careers_url TEXT,
                active INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title TEXT,
                company TEXT,
                jd_text TEXT,
                tailored_resume_text TEXT,
                tailored_resume_path TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        _migrate_companies(conn)
        _migrate_seen_jobs(conn)


def _migrate_seen_jobs(conn: sqlite3.Connection):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
    if "location" not in cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN location TEXT")
    if "verdict_label" not in cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN verdict_label TEXT")
    if "verdict_reason" not in cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN verdict_reason TEXT")
    if "is_us" not in cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN is_us INTEGER DEFAULT 1")
    conn.execute("UPDATE seen_jobs SET is_us = 1 WHERE is_us IS NULL")


def save_resume_output(
    jd_text: str,
    tailored_resume_text: str,
    job_title: str | None = None,
    company: str | None = None,
    tailored_resume_path: str | None = None,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO resume_outputs
                (job_title, company, jd_text, tailored_resume_text, tailored_resume_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_title, company, jd_text, tailored_resume_text, tailored_resume_path),
        )
        return int(cur.lastrowid)


def _migrate_companies(conn: sqlite3.Connection):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(companies)")}
    if "notes" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN notes TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_name ON companies(name)"
    )


def get_active_companies() -> list[dict]:
    """Active scrapable companies (excludes custom/manual ATS)."""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT name, ats_type, slug, careers_url
            FROM companies
            WHERE active = 1 AND ats_type != 'custom'
            ORDER BY name
            """
        ).fetchall()
    return [
        {
            "name": row["name"],
            "ats": row["ats_type"],
            "slug": row["slug"],
            "careers_url": row["careers_url"],
        }
        for row in rows
    ]


def is_new(job_id: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row is None


def mark_seen(
    job: dict,
    company: str,
    matched_keywords: list[str],
    *,
    verdict_label: str | None = None,
    verdict_reason: str | None = None,
    is_us: int = 1,
):
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO seen_jobs
                (job_id, company, title, url, matched_keywords, first_seen,
                 location, verdict_label, verdict_reason, is_us)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["job_id"],
                company,
                job["title"],
                job["url"],
                json.dumps(matched_keywords),
                datetime.now(timezone.utc).isoformat(),
                job.get("location") or "",
                verdict_label or "",
                verdict_reason or "",
                is_us,
            ),
        )


def list_seen_jobs(
    *,
    verdict_label: str | None = None,
    company: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_us: int | None = None,
) -> list[dict]:
    """Match history rows, newest first."""
    clauses: list[str] = []
    params: list[object] = []

    if verdict_label and verdict_label != "All":
        clauses.append("verdict_label = ?")
        params.append(verdict_label)
    if company and company != "All":
        clauses.append("company = ?")
        params.append(company)
    if date_from:
        clauses.append("date(first_seen) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append("date(first_seen) <= date(?)")
        params.append(date_to)
    if is_us is not None:
        clauses.append("is_us = ?")
        params.append(is_us)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT job_id, title, company, location, verdict_label, verdict_reason,
               first_seen, url, is_us
        FROM seen_jobs
        {where}
        ORDER BY first_seen DESC
    """
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_fit_jobs_excluding(job_ids: list[str]) -> list[dict]:
    """FIT / APPLY_LATER rows not in job_ids (for email 'Previously Seen' section)."""
    if job_ids:
        placeholders = ",".join("?" * len(job_ids))
        exclude_clause = f"AND job_id NOT IN ({placeholders})"
        params: list[object] = list(job_ids)
    else:
        exclude_clause = ""
        params = []
    sql = f"""
        SELECT job_id, title, company, location, verdict_label, verdict_reason,
               first_seen, url, is_us, matched_keywords
        FROM seen_jobs
        WHERE verdict_label IN ('FIT', 'APPLY_LATER')
        {exclude_clause}
        ORDER BY first_seen DESC
    """
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_seen_job_row_to_dict(row) for row in rows]


def _seen_job_row_to_dict(row: sqlite3.Row) -> dict:
    keywords_raw = row["matched_keywords"] or "[]"
    try:
        matched_keywords = json.loads(keywords_raw)
    except json.JSONDecodeError:
        matched_keywords = []
    return {
        "job_id": row["job_id"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"] or "",
        "verdict_label": row["verdict_label"] or "",
        "verdict_reason": row["verdict_reason"] or "",
        "first_seen": row["first_seen"],
        "url": row["url"],
        "is_us": row["is_us"] if row["is_us"] is not None else 1,
        "matched_keywords": matched_keywords,
    }


def get_company_health_map() -> dict[str, dict]:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT company, last_job_count, last_checked, consecutive_zeros
            FROM company_health
            """
        ).fetchall()
    return {row["company"]: dict(row) for row in rows}


def list_match_companies() -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT company FROM seen_jobs
            WHERE company IS NOT NULL AND company != ''
            ORDER BY company
            """
        ).fetchall()
    return [row[0] for row in rows]


def update_health(company: str, job_count: int) -> dict | None:
    """Returns a health alert dict if scraper looks broken, else None."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT consecutive_zeros FROM company_health WHERE company = ?",
            (company,),
        ).fetchone()

        consecutive_zeros = ((row[0] if row else 0) + 1) if job_count == 0 else 0

        conn.execute(
            """
            INSERT INTO company_health
                (company, last_job_count, last_checked, consecutive_zeros)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(company) DO UPDATE SET
                last_job_count = excluded.last_job_count,
                last_checked   = excluded.last_checked,
                consecutive_zeros = excluded.consecutive_zeros
            """,
            (company, job_count, now, consecutive_zeros),
        )

    if consecutive_zeros >= 2:
        return {
            "company": company,
            "message": f"0 jobs returned for {consecutive_zeros} consecutive runs",
        }
    return None
