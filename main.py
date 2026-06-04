import sys
from datetime import datetime, timezone

from database import (
    get_active_companies,
    init_db,
    is_new,
    list_fit_jobs_excluding,
    mark_seen,
    update_health,
)
from filters import match_keywords
from notifier import send_health_alerts, send_job_matches, send_no_matches
from ranker import get_verdict
from scrapers import ashby, greenhouse, lever

_US_MARKERS = (
    "United States",
    "US",
    "USA",
    "Remote",
    "San Francisco",
    "New York",
    "Chicago",
    "Seattle",
    "Austin",
    "Boston",
    "Los Angeles",
    "Philadelphia",
    "Denver",
    "Atlanta",
)

_NON_US_MARKERS = (
    "China",
    "India",
    "Bangalore",
    "London",
    "Canada",
    "UK",
    "Germany",
    "Singapore",
    "Australia",
    "Japan",
    "Europe",
    "EMEA",
    "Toronto",
    "Vancouver",
)


def parse_is_us(location: str | None) -> int:
    if not location:
        return 1
    loc = location.casefold()
    if any(marker.casefold() in loc for marker in _NON_US_MARKERS):
        return 0
    if any(marker.casefold() in loc for marker in _US_MARKERS):
        return 1
    return 1


def run() -> dict:
    init_db()

    new_jobs: list[dict] = []
    new_job_ids: list[str] = []
    health_alerts: list[dict] = []
    companies_checked: list[str] = []

    for company in get_active_companies():
        name = company["name"]
        ats = company["ats"]
        slug = company["slug"]
        companies_checked.append(name)

        try:
            if ats == "greenhouse":
                jobs = greenhouse.fetch(slug, name)
            elif ats == "lever":
                jobs = lever.fetch(slug, name)
            elif ats == "ashby":
                jobs = ashby.fetch(slug, name)
            else:
                print(f"Unknown ATS '{ats}' for {name}", file=sys.stderr)
                continue
        except Exception as exc:
            print(f"Error fetching {name}: {exc}", file=sys.stderr)
            alert = update_health(name, 0)
            if alert:
                health_alerts.append(alert)
            continue

        alert = update_health(name, len(jobs))
        if alert:
            health_alerts.append(alert)

        for job in jobs:
            pre_match = match_keywords({**job, "description": "", "description_plain": ""})
            if not pre_match:
                continue

            if ats == "greenhouse":
                job = greenhouse.enrich_description(job)

            matched = match_keywords(job)
            if not matched:
                continue

            if not is_new(job["job_id"]):
                continue

            job["company"] = name
            location = job.get("location", "")
            is_us_flag = parse_is_us(location)
            verdict = get_verdict(job, matched)
            first_seen = datetime.now(timezone.utc).isoformat()
            mark_seen(
                job,
                name,
                matched,
                verdict_label=verdict.get("label"),
                verdict_reason=verdict.get("reason"),
                is_us=is_us_flag,
            )

            new_job_ids.append(job["job_id"])
            new_jobs.append({
                "job_id": job["job_id"],
                "title": job["title"],
                "company": name,
                "location": location,
                "url": job["url"],
                "matched_keywords": matched,
                "verdict_label": verdict.get("label", ""),
                "verdict_reason": verdict.get("reason", ""),
                "is_us": is_us_flag,
                "is_new": True,
                "first_seen": first_seen,
            })

    if health_alerts:
        send_health_alerts(health_alerts)

    seen_fit_jobs = list_fit_jobs_excluding(new_job_ids)
    email_sent = send_job_matches(new_jobs, seen_fit_jobs)
    if not email_sent:
        send_no_matches(companies_checked)

    new_fit_count = sum(
        1 for j in new_jobs
        if j.get("verdict_label") in ("FIT", "APPLY_LATER")
    )
    return {
        "new_jobs": len(new_jobs),
        "new_fit": new_fit_count,
        "companies_checked": len(companies_checked),
        "email_sent": email_sent,
    }


if __name__ == "__main__":
    run()
