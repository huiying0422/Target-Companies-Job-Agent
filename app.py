"""Job searching Agent (v2) — Streamlit dashboard."""

import concurrent.futures
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from company_manager import (
    ATS_TYPES,
    add_company,
    ensure_companies_seeded,
    format_last_checked,
    list_all_companies,
    sync_active_from_rows,
)
from database import init_db, list_match_companies, list_seen_jobs, save_resume_output
from main import run as run_scraper
from pdf_generator import default_output_path, resume_to_pdf
from resume_engine import load_base_resume, load_jd_from_pdf, tailor_resume

_ROOT = Path(__file__).parent
_SCRAPE_TIMEOUT_SEC = 120


def _load_local_env():
    """Load .env into os.environ (does not override existing vars)."""
    env_path = _ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _anthropic_api_key() -> str | None:
    """Return API key from .env, os.environ, or Streamlit secrets (never from shell rc)."""
    _load_local_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and key.strip():
        return key.strip()
    try:
        secret = st.secrets["ANTHROPIC_API_KEY"]
        if secret and str(secret).strip():
            return str(secret).strip()
    except Exception:
        pass
    return None


def _clear_resume_form():
    st.session_state.jd_text = ""
    st.session_state.resume_job_title = ""
    st.session_state.resume_company = ""
    st.session_state.pop("_jd_upload_id", None)
    st.session_state["_resume_uploader_gen"] = (
        st.session_state.get("_resume_uploader_gen", 0) + 1
    )


def _run_scrape_with_timeout() -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_scraper)
        return future.result(timeout=_SCRAPE_TIMEOUT_SEC)


def _render_scrape_sidebar():
    st.sidebar.divider()
    st.sidebar.subheader("Scraper")
    running = st.session_state.get("scrape_running", False)

    if st.sidebar.button(
        "Run Scrape Now",
        type="primary",
        disabled=running,
        key="run_scrape_btn",
    ):
        st.session_state.scrape_running = True
        st.session_state.pop("scrape_result", None)
        st.session_state.pop("scrape_error", None)
        st.rerun()

    if running:
        with st.sidebar.spinner("Scraping…"):
            try:
                result = _run_scrape_with_timeout()
                st.session_state.scrape_result = result
                st.session_state.scrape_error = None
            except concurrent.futures.TimeoutError:
                st.session_state.scrape_error = (
                    f"Scraper timed out after {_SCRAPE_TIMEOUT_SEC} seconds."
                )
                st.session_state.scrape_result = None
            except Exception as exc:
                st.session_state.scrape_error = f"Scraper failed: {exc}"
                st.session_state.scrape_result = None
            finally:
                st.session_state.scrape_running = False
        st.rerun()

    if st.session_state.get("scrape_error"):
        st.sidebar.error(st.session_state.scrape_error)
    elif result := st.session_state.get("scrape_result"):
        st.sidebar.success(
            f"{result['new_jobs']} new job(s) found "
            f"({result['new_fit']} FIT/APPLY_LATER). "
            f"{result['companies_checked']} companies checked."
        )


def _render_company_manager():
    st.title("Company Manager")
    st.caption(
        "Changes save to `jobs.db` locally. "
        "GitHub Actions uses its own artifact DB; Streamlit Cloud has a separate DB unless you sync via `db_seed.py`."
    )

    companies = list_all_companies()
    st.subheader(f"Companies ({len(companies)})")

    if companies:
        df = pd.DataFrame(companies)
        df["last_checked_display"] = df["last_checked"].apply(format_last_checked)
        display_cols = [
            "id",
            "name",
            "ats_type",
            "slug",
            "last_checked_display",
            "last_job_count",
            "active",
            "careers_url",
            "notes",
        ]
        edited = st.data_editor(
            df[display_cols],
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "name": st.column_config.TextColumn("Name", disabled=True),
                "ats_type": st.column_config.TextColumn("ATS", disabled=True),
                "slug": st.column_config.TextColumn("Slug", disabled=True),
                "last_checked_display": st.column_config.TextColumn(
                    "Last checked", disabled=True
                ),
                "last_job_count": st.column_config.NumberColumn(
                    "Jobs last run", disabled=True
                ),
                "careers_url": st.column_config.TextColumn("Careers URL", disabled=True),
                "notes": st.column_config.TextColumn("Notes", disabled=True),
                "active": st.column_config.CheckboxColumn("Active"),
            },
            hide_index=True,
            width="stretch",
            key="companies_table",
        )
        if (edited["ats_type"] == "custom").any():
            st.caption(
                "Custom ATS rows are not scraped automatically — use careers URL for manual checks."
            )
        if st.button("Save active toggles", type="primary"):
            try:
                n = sync_active_from_rows(edited.to_dict("records"))
                st.success(f"Saved {n} change(s).")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to save toggles: {exc}")
    else:
        st.error("No companies in database. Add one below or run `python db_seed.py`.")

    st.divider()
    st.subheader("Add company")

    with st.form("add_company_form", clear_on_submit=True):
        name = st.text_input("Company name *")
        ats_type = st.selectbox("ATS type *", ATS_TYPES)
        slug = st.text_input(
            "Slug *",
            help="Greenhouse/Lever/Ashby board slug. For custom, use a short id (e.g. spotify).",
        )
        careers_url = st.text_input(
            "Careers URL",
            help="Required for custom ATS. Optional for Greenhouse/Lever/Ashby.",
        )
        submitted = st.form_submit_button("Add company")

    if submitted:
        try:
            row_id = add_company(name, ats_type, slug, careers_url or None)
            st.success(f"Added company (id={row_id}). Run scrape to fetch jobs.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _render_resume_tailor():
    st.title("Resume Tailor")
    st.caption(
        "Tailors `templates/base_resume.txt` to a job description. Requires `ANTHROPIC_API_KEY`."
    )

    if "tailored_resume" not in st.session_state:
        st.session_state.tailored_resume = ""
    if "pdf_bytes" not in st.session_state:
        st.session_state.pdf_bytes = None
    if "pdf_filename" not in st.session_state:
        st.session_state.pdf_filename = "tailored_resume.pdf"
    if "_resume_uploader_gen" not in st.session_state:
        st.session_state._resume_uploader_gen = 0

    uploaded = st.file_uploader(
        "Upload JD (PDF, optional)",
        type=["pdf"],
        key=f"jd_uploader_{st.session_state._resume_uploader_gen}",
    )
    if uploaded is not None:
        upload_id = f"{uploaded.name}:{uploaded.size}"
        if st.session_state.get("_jd_upload_id") != upload_id:
            try:
                st.session_state.jd_text = load_jd_from_pdf(uploaded.read())
                st.session_state._jd_upload_id = upload_id
                st.success(f"Loaded text from {uploaded.name}")
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    if "jd_text" not in st.session_state:
        st.session_state.jd_text = ""

    jd_text = st.text_area(
        "Job description",
        height=280,
        placeholder="Paste the full job description here…",
        key="jd_text",
    )

    col1, col2 = st.columns(2)
    with col1:
        job_title = st.text_input("Job title (optional)", key="resume_job_title")
    with col2:
        company = st.text_input("Company (optional)", key="resume_company")

    has_jd = bool((jd_text or "").strip())
    if not has_jd and not st.session_state.tailored_resume:
        st.error("Paste a job description or upload a PDF to get started.")

    if st.button("Tailor Resume", type="primary", disabled=not has_jd):
        api_key = _anthropic_api_key()
        if not api_key:
            st.error(
                "Set ANTHROPIC_API_KEY in your shell, `.env`, or `.streamlit/secrets.toml`."
            )
        else:
            try:
                with st.spinner("Tailoring resume with Claude…"):
                    base = load_base_resume()
                    tailored = tailor_resume(jd_text.strip(), base, api_key=api_key)
                    pdf_path = default_output_path(company or None, job_title or None)
                    resume_to_pdf(tailored, pdf_path)
                    row_id = save_resume_output(
                        jd_text=jd_text.strip(),
                        tailored_resume_text=tailored,
                        job_title=job_title or None,
                        company=company or None,
                        tailored_resume_path=str(pdf_path),
                    )
                st.session_state.tailored_resume = tailored
                st.session_state.pdf_bytes = pdf_path.read_bytes()
                st.session_state.pdf_filename = pdf_path.name
                st.session_state.last_resume_row_id = row_id
                st.success(f"Resume tailored (saved as row #{row_id}).")
                _clear_resume_form()
                st.rerun()
            except (ValueError, RuntimeError, FileNotFoundError) as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Tailoring failed: {exc}")

    if st.session_state.tailored_resume:
        st.subheader("Preview")
        st.text_area(
            "Tailored resume",
            value=st.session_state.tailored_resume,
            height=420,
            disabled=True,
            label_visibility="collapsed",
        )
        if st.session_state.pdf_bytes:
            st.download_button(
                label="Download PDF",
                data=st.session_state.pdf_bytes,
                file_name=st.session_state.pdf_filename,
                mime="application/pdf",
                type="primary",
            )


def _render_match_history():
    st.title("Match History")
    st.caption("Scraped job matches with structured verdict labels from scraper runs.")

    companies = list_match_companies()
    filter_cols = st.columns([1, 1, 1, 1, 1])

    with filter_cols[0]:
        verdict_filter = st.selectbox(
            "Verdict",
            ["All", "FIT", "APPLY_LATER", "NOT_FIT"],
            key="mh_verdict",
        )
    with filter_cols[1]:
        company_filter = st.selectbox(
            "Company",
            ["All", *companies],
            key="mh_company",
        )
    with filter_cols[2]:
        date_from = st.date_input("From", value=None, key="mh_date_from")
    with filter_cols[3]:
        date_to = st.date_input("To", value=None, key="mh_date_to")
    with filter_cols[4]:
        us_only = st.toggle("US jobs only", value=False, key="mh_us_only")

    rows = list_seen_jobs(
        verdict_label=verdict_filter,
        company=company_filter,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        is_us=1 if us_only else None,
    )

    if not rows:
        st.error(
            "No matches found for these filters. Run **Run Scrape Now** in the sidebar, "
            "or widen your filters."
        )
        return

    df = pd.DataFrame(rows)
    display = df[
        [
            "title",
            "company",
            "location",
            "verdict_label",
            "verdict_reason",
            "first_seen",
            "url",
        ]
    ].copy()
    display["first_seen"] = pd.to_datetime(display["first_seen"], errors="coerce")
    display = display.sort_values("first_seen", ascending=False)
    display["first_seen"] = display["first_seen"].dt.strftime("%Y-%m-%d %H:%M UTC")

    export_csv = display.to_csv(index=False).encode("utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    st.download_button(
        label="Export CSV",
        data=export_csv,
        file_name=f"match_history_{stamp}.csv",
        mime="text/csv",
    )

    st.dataframe(
        display,
        column_config={
            "title": st.column_config.TextColumn("Title"),
            "company": st.column_config.TextColumn("Company"),
            "location": st.column_config.TextColumn("Location"),
            "verdict_label": st.column_config.TextColumn("Verdict"),
            "verdict_reason": st.column_config.TextColumn("Reason", width="large"),
            "first_seen": st.column_config.TextColumn("First seen"),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        },
        hide_index=True,
        width="stretch",
    )
    st.caption(f"Showing {len(display)} job(s), sorted by first seen (newest first).")


st.set_page_config(page_title="Job searching Agent", page_icon="🎯", layout="wide")

_load_local_env()
_load_shell_rc_exports()
init_db()
ensure_companies_seeded()

if "scrape_running" not in st.session_state:
    st.session_state.scrape_running = False

page = st.sidebar.radio(
    "Navigation",
    ["Company Manager", "Resume Tailor", "Match History"],
    label_visibility="collapsed",
)

_render_scrape_sidebar()

if page == "Resume Tailor":
    _render_resume_tailor()
elif page == "Match History":
    _render_match_history()
else:
    _render_company_manager()
