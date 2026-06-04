import re
import requests

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _normalize(job: dict, slug: str, company_name: str) -> dict:
    desc_html  = job.get("descriptionHtml", "")
    desc_plain = job.get("descriptionPlain") or _strip_html(desc_html)
    return {
        "job_id":            f"ashby_{slug}_{job['id']}",
        "title":             job.get("title", ""),
        "department":        job.get("department", ""),
        "location":          job.get("location", ""),
        "url":               job.get("jobUrl", ""),
        "description":       desc_html,
        "description_plain": desc_plain,
        "_company":          company_name,
    }


def fetch(slug: str, company_name: str) -> list[dict]:
    resp = requests.get(_BASE.format(slug=slug), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [_normalize(j, slug, company_name) for j in data.get("jobPostings", [])]
