import requests

_BASE = "https://api.lever.co/v0/postings/{slug}?mode=json"


def _normalize(job: dict, slug: str, company_name: str) -> dict:
    lists_text = " ".join(
        f"{item.get('text', '')} {item.get('content', '')}"
        for item in (job.get("lists") or [])
    )
    description_plain = " ".join(
        filter(None, [
            job.get("descriptionPlain", ""),
            job.get("additionalPlain", ""),
            lists_text,
        ])
    ).strip()

    categories = job.get("categories") or {}
    return {
        "job_id":            f"lever_{slug}_{job['id']}",
        "title":             job.get("text", ""),   # Lever uses "text" not "title"
        "department":        categories.get("department", ""),
        "location":          categories.get("location", ""),
        "url":               job.get("hostedUrl", ""),
        "description":       "",
        "description_plain": description_plain,
        "_company":          company_name,
    }


def fetch(slug: str, company_name: str) -> list[dict]:
    resp = requests.get(_BASE.format(slug=slug), timeout=15)
    resp.raise_for_status()
    return [_normalize(j, slug, company_name) for j in resp.json()]
