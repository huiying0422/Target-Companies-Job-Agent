import re

from config import KEYWORDS_EXAMPLE, KEYWORDS_PATH

# Customize: copy keywords.example.txt → keywords.txt (one keyword per line).


def _load_keywords() -> list[str]:
    path = KEYWORDS_PATH if KEYWORDS_PATH.is_file() else KEYWORDS_EXAMPLE
    keywords = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keywords.append(line.lower())
    return keywords


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _normalize(text: str) -> str:
    text = _strip_html(text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text


def match_keywords(job: dict) -> list[str]:
    keywords = _load_keywords()
    combined = _normalize(
        f"{job.get('title', '')} "
        f"{job.get('department', '')} "
        f"{job.get('description', '')} "
        f"{job.get('description_plain', '')}"
    )
    return [kw for kw in keywords if kw in combined]
