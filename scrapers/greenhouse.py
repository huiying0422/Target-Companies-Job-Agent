import requests

_LIST_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
_JOB_URL  = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"


def _normalize(job: dict, slug: str, company_name: str) -> dict:
    departments = job.get("departments") or []
    dept = departments[0]["name"] if departments else ""
    return {
        "job_id":            f"greenhouse_{slug}_{job['id']}",
        "title":             job.get("title", ""),
        "department":        dept,
        "location":          (job.get("location") or {}).get("name", ""),
        "url":               job.get("absolute_url", ""),
        "description":       "",
        "description_plain": "",
        # internal fields for enrichment — not part of the public schema
        "_raw_id":  job["id"],
        "_slug":    slug,
        "_company": company_name,
    }


def fetch(slug: str, company_name: str) -> list[dict]:
    resp = requests.get(_LIST_URL.format(slug=slug), timeout=15)
    resp.raise_for_status()
    return [_normalize(j, slug, company_name) for j in resp.json().get("jobs", [])]


def enrich_description(job: dict) -> dict:
    """Fetch the full job description for a job that passed the pre-filter."""
    resp = requests.get(
        _JOB_URL.format(slug=job["_slug"], job_id=job["_raw_id"]),
        timeout=15,
    )
    if resp.status_code != 200:
        return job
    data = resp.json()
    return {**job, "description": data.get("content", "")}
