"""CRUD for companies table (used by Streamlit and shares jobs.db with main.py)."""

import sqlite3
from datetime import datetime

from database import _conn, get_company_health_map, init_db

ATS_TYPES = ("greenhouse", "lever", "ashby", "custom")


def ensure_companies_seeded():
    """Empty DB → run idempotent seed (Streamlit Cloud / fresh clone)."""
    init_db()
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    if count == 0:
        from db_seed import apply_fixes, seed_companies

        seed_companies()
        apply_fixes()


def list_all_companies() -> list[dict]:
    health = get_company_health_map()
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, ats_type, slug, careers_url, active, notes
            FROM companies
            ORDER BY name
            """
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        h = health.get(item["name"]) or {}
        item["last_checked"] = h.get("last_checked")
        item["last_job_count"] = h.get("last_job_count")
        result.append(item)
    return result


def format_last_checked(iso_ts: str | None) -> str:
    if not iso_ts or not isinstance(iso_ts, str):
        return "Never"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso_ts


def add_company(
    name: str,
    ats_type: str,
    slug: str,
    careers_url: str | None = None,
    notes: str | None = None,
) -> int:
    name = name.strip()
    slug = slug.strip()
    ats_type = ats_type.strip().lower()
    careers_url = (careers_url or "").strip() or None
    notes = (notes or "").strip() or None

    if not name or not slug:
        raise ValueError("Name and slug are required.")
    if ats_type not in ATS_TYPES:
        raise ValueError(f"ATS type must be one of: {', '.join(ATS_TYPES)}")
    if ats_type == "custom" and not careers_url:
        raise ValueError("Careers URL is required for custom ATS companies.")

    with _conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO companies (name, ats_type, slug, careers_url, active, notes)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (name, ats_type, slug, careers_url, notes or "added via UI"),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Company '{name}' already exists.") from exc
        return int(cur.lastrowid)


def set_active(company_id: int, active: bool) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE companies SET active = ? WHERE id = ?",
            (1 if active else 0, company_id),
        )


def sync_active_from_rows(rows: list[dict]) -> int:
    """Apply active flags from data_editor rows; returns number of updates."""
    updated = 0
    for row in rows:
        company_id = int(row["id"])
        new_active = bool(row["active"])
        with _conn() as conn:
            old = conn.execute(
                "SELECT active FROM companies WHERE id = ?", (company_id,)
            ).fetchone()
        if old and bool(old[0]) != new_active:
            set_active(company_id, new_active)
            updated += 1
    return updated
