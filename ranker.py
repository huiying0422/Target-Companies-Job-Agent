import json
import os
import re

from config import CANDIDATE_PROFILE_EXAMPLE, CANDIDATE_PROFILE_PATH

# Customize: edit config/candidate_profile.txt (copy from candidate_profile.example.txt).
# Used when ANTHROPIC_API_KEY is set — Claude labels jobs FIT / APPLY_LATER / NOT_FIT.

_VERDICT_SYSTEM = """Respond ONLY with valid JSON. No preamble, no markdown.
label must be exactly one of: FIT, APPLY_LATER, NOT_FIT
FIT = apply now. APPLY_LATER = apply in 3-6 months. NOT_FIT = do not apply."""

_VALID_LABELS = frozenset({"FIT", "APPLY_LATER", "NOT_FIT"})

_CANDIDATE_NAME = os.environ.get("CANDIDATE_NAME", "the candidate").strip() or "the candidate"


def load_candidate_profile() -> str:
    """Load profile text from config/candidate_profile.txt or the example file."""
    path = CANDIDATE_PROFILE_PATH if CANDIDATE_PROFILE_PATH.is_file() else CANDIDATE_PROFILE_EXAMPLE
    if not path.is_file():
        raise FileNotFoundError(
            "Candidate profile not found. Copy config/candidate_profile.example.txt "
            "to config/candidate_profile.txt"
        )
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _parse_verdict_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    label = str(data.get("label", "")).strip()
    reason = str(data.get("reason", "")).strip()
    if label not in _VALID_LABELS:
        raise ValueError(f"invalid verdict label: {label!r}")
    return {"label": label, "reason": reason}


def get_verdict(job: dict, matched_keywords: list[str]) -> dict:
    """Return structured verdict: {"label": str, "reason": str}. Empty strings if unavailable."""
    empty = {"label": "", "reason": ""}
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return empty

    try:
        import anthropic
    except ImportError:
        return empty

    try:
        profile = load_candidate_profile()
    except FileNotFoundError:
        return empty

    description_excerpt = (
        job.get("description_plain") or job.get("description") or ""
    )[:1500]

    prompt = f"""You are evaluating a job posting for {_CANDIDATE_NAME}. Here is their profile:

{profile}

Job details:
- Title: {job['title']}
- Company: {job.get('company', '')}
- Location: {job.get('location', '')}
- Matched keywords: {', '.join(matched_keywords)}
- Description (first 1500 chars):
{description_excerpt}

Respond with JSON only:
{{
  "label": "FIT" | "APPLY_LATER" | "NOT_FIT",
  "reason": "2-3 sentence explanation"
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=_VERDICT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_verdict_json(message.content[0].text)
    except Exception:
        return empty
