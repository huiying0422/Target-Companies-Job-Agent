"""Plain-text resume → PDF via WeasyPrint."""

import os

os.environ["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib:" + os.environ.get(
    "DYLD_LIBRARY_PATH", ""
)

import html
import re
from pathlib import Path

_CSS = """
@page {
    size: letter;
    margin: 0.6in 0.65in;
}
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 9.5pt;
    line-height: 1.25;
    color: #1a1a1a;
    margin: 0;
}
h1 {
    font-size: 16pt;
    font-weight: bold;
    text-align: center;
    margin: 0 0 0.3em 0;
    letter-spacing: 0.02em;
}
.contact {
    text-align: center;
    font-size: 9pt;
    color: #444;
    margin: 0;
}
h2 {
    font-size: 11pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 0.05em solid #333;
    margin: 0.7em 0 4pt 0;
    padding-bottom: 0.1em;
}
h2:first-of-type {
    margin-top: 0.7em;
}
p {
    margin: 0 0 0.25em 0;
}
.summary {
    margin-bottom: 0;
}
.skills-line {
    margin: 0 0 0.25em 0;
    line-height: 1.25;
}
.job-block + .job-block {
    margin-top: 0.5em;
}
.role {
    font-weight: bold;
    margin: 0 0 0.15em 0;
}
.role-sub {
    font-weight: normal;
    font-style: normal;
}
.education-line {
    margin: 0 0 0.15em 0;
    line-height: 1.2;
}
ul {
    margin: 0 0 0.15em 0;
    padding: 0;
    list-style-type: disc;
    list-style-position: outside;
}
li {
    margin-left: 1em;
    margin-bottom: 0.2em;
    line-height: 1.25;
}
li:last-child {
    margin-bottom: 0;
}
"""

_SECTION_ORDER = (
    "PROFESSIONAL SUMMARY",
    "TECHNICAL SKILLS",
    "WORK EXPERIENCE",
    "ML & AI PROJECTS",
    "EDUCATION",
)
_SKIP_SKILL_PREFIXES: tuple[str, ...] = ()
# Customize: cap bullets per employer substring, e.g. (("Acme Corp", 3),)
_ROLE_BULLET_LIMITS: tuple[tuple[str, int], ...] = ()


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("- "):
        return False
    if len(stripped) > 80:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False
    return stripped.upper() == stripped


def _is_subtitle_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("- "):
        return False
    if _is_section_header(line):
        return False
    if " — " in line and len(line) < 120:
        return False
    if len(stripped) > 100:
        return False
    if "|" in stripped:
        return True
    if re.search(r"\b(19|20)\d{2}\b", stripped):
        return True
    return stripped.startswith(("Summer ", "Winter ", "Spring ", "Fall "))


def _strip_parens(text: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


def _format_role_header(line: str, section: str = "") -> str:
    """Render as 'Job Title — Company' with sub-descriptors and parentheticals removed."""
    if " — " not in line:
        return _strip_parens(line)

    parts = [_strip_parens(part.strip()) for part in line.split(" — ")]
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return parts[0] if parts else line.strip()
    if len(parts) == 2:
        return f"{parts[0]} — {parts[1]}"

    first = parts[0]
    if section == "ML & AI PROJECTS" and any(
        token in first for token in ("Platform", "Agent", "Project")
    ):
        return f"{parts[-2]} — {parts[-1]}"
    return f"{parts[0]} — {parts[-1]}"


def _truncate_summary(text: str, max_sentences: int = 2) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    parts = re.split(r"(?<=[.!?])\s+", stripped)
    return " ".join(parts[:max_sentences]).strip()


def _build_contact_line(header_lines: list[str]) -> str:
    blob = " ".join(header_lines)
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", blob)
    email = email_match.group(0) if email_match else "your.email@example.com"

    web = "yourwebsite.com"
    web_match = re.search(r"[\w.-]+\.(dev|com|io)", blob, re.I)
    if web_match:
        web = web_match.group(0)
    else:
        url_match = re.search(r"https?://[\w./-]+", blob)
        if url_match:
            web = url_match.group(0).replace("https://", "").replace("http://", "")

    city = "City ST"
    city_match = re.search(r"[A-Za-z .]+,\s*[A-Z]{2}", blob)
    if city_match:
        city = re.sub(r",\s*", " ", city_match.group(0).strip())

    return f"US Citizen | {city} | {email} | {web}"


def _parse_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                sections.setdefault(current, []).append("")
            elif not sections:
                header.append("")
            continue

        if _is_section_header(line):
            current = stripped
            sections.setdefault(current, [])
            continue

        if current is None:
            header.append(stripped)
        else:
            sections.setdefault(current, []).append(stripped)

    return header, sections


def _condense_skills(lines: list[str]) -> list[str]:
    kept = [
        line
        for line in lines
        if line.strip()
        and not any(line.strip().startswith(prefix) for prefix in _SKIP_SKILL_PREFIXES)
    ]
    if len(kept) <= 3:
        return kept
    if len(kept) == 4:
        return [kept[0], kept[1], f"{kept[2]} | {kept[3]}"]
    merged: list[str] = []
    chunk = 2
    for i in range(0, len(kept), chunk):
        merged.append(" | ".join(kept[i : i + chunk]))
    return merged[:3]


def _bullet_limit_for_role(role_line: str) -> int | None:
    for needle, limit in _ROLE_BULLET_LIMITS:
        if needle.lower() in role_line.lower():
            return limit
    return None


def _apply_bullet_limits(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.strip().startswith("- "):
            i += 1
            continue

        is_role = " — " in line and len(line) < 120 and not line.strip().startswith("- ")
        if not is_role:
            i += 1
            continue

        limit = _bullet_limit_for_role(line)
        i += 1
        if limit is None:
            continue

        if i < len(lines) and _is_subtitle_line(lines[i]):
            out.append(lines[i])
            i += 1

        bullets_kept = 0
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                out.append(nxt)
                i += 1
                break
            if _is_section_header(nxt):
                break
            if " — " in nxt and len(nxt) < 120 and not nxt.strip().startswith("- "):
                break
            if nxt.strip().startswith("- "):
                if bullets_kept < limit:
                    out.append(nxt)
                    bullets_kept += 1
                i += 1
                continue
            out.append(nxt)
            i += 1

    return out


def _format_education(lines: list[str]) -> list[str]:
    entries: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if not (" — " in line and len(line) < 120):
            i += 1
            continue

        degree, _, school = line.partition(" — ")
        year = ""
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                continue
            if _is_section_header(nxt) or (" — " in nxt and len(nxt) < 120):
                break
            if nxt.lower().startswith("coursework:"):
                j += 1
                continue
            # detect continuation lines in education section
            year_match = re.search(
                r"(Expected\s+\d{4}|Graduated\s+\d{4}|\d{4})", nxt, re.I
            )
            if year_match and not year:
                year = year_match.group(1)
            j += 1
            if year:
                break

        if year:
            entries.append(f"{degree.strip()}, {school.strip()}, {year}")
        else:
            entries.append(f"{degree.strip()}, {school.strip()}")
        i = j

    return entries


def _strip_section(lines: list[str]) -> list[str]:
    trimmed = [ln for ln in lines]
    while trimmed and not trimmed[0].strip():
        trimmed.pop(0)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _prepare_resume_text(text: str) -> list[str]:
    raw_lines = [ln.rstrip() for ln in text.strip().splitlines()]
    header, sections = _parse_sections(raw_lines)

    name = header[0].strip() if header else "YOUR NAME"
    contact = _build_contact_line(header)

    out: list[str] = [name, contact, ""]

    if "PROFESSIONAL SUMMARY" in sections:
        summary = " ".join(ln for ln in sections["PROFESSIONAL SUMMARY"] if ln.strip())
        out.extend(["PROFESSIONAL SUMMARY", _truncate_summary(summary), ""])

    if "TECHNICAL SKILLS" in sections:
        skills = _condense_skills(sections["TECHNICAL SKILLS"])
        out.append("TECHNICAL SKILLS")
        out.extend(skills)
        out.append("")

    work = _strip_section(sections.get("WORK EXPERIENCE", []))
    if work:
        out.append("WORK EXPERIENCE")
        out.extend(_apply_bullet_limits(work))
        out.append("")

    projects = _strip_section(sections.get("ML & AI PROJECTS", []))
    if projects:
        out.append("ML & AI PROJECTS")
        out.extend(_apply_bullet_limits(projects))
        out.append("")

    if "EDUCATION" in sections:
        education = _format_education(sections["EDUCATION"])
        if education:
            out.append("EDUCATION")
            out.extend(education)

    while out and not out[-1].strip():
        out.pop()
    return out


def _plain_text_to_html(text: str) -> str:
    lines = _prepare_resume_text(text)
    parts: list[str] = []
    in_list = False
    in_job_block = False
    name_done = False
    contact_done = False
    current_section = ""

    def close_list():
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    def close_job_block():
        nonlocal in_job_block
        if in_job_block:
            parts.append("</div>")
            in_job_block = False

    def open_job_block():
        nonlocal in_job_block
        if not in_job_block:
            parts.append('<div class="job-block">')
            in_job_block = True

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            close_list()
            i += 1
            continue

        escaped = html.escape(line.strip())

        if not name_done:
            parts.append(f"<h1>{escaped}</h1>")
            name_done = True
            i += 1
            continue

        if not contact_done:
            parts.append(f'<p class="contact">{escaped}</p>')
            contact_done = True
            i += 1
            continue

        if _is_section_header(line):
            close_list()
            close_job_block()
            current_section = line.strip()
            parts.append(f"<h2>{escaped}</h2>")
            i += 1
            continue

        if line.strip().startswith("- "):
            open_job_block()
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(line.strip()[2:])}</li>")
            i += 1
            continue

        close_list()

        if current_section == "EDUCATION":
            close_job_block()
            parts.append(f'<p class="education-line">{escaped}</p>')
            i += 1
            continue

        is_role = " — " in line and len(line) < 120
        if is_role and current_section in ("WORK EXPERIENCE", "ML & AI PROJECTS"):
            close_job_block()
            open_job_block()
            role_text = html.escape(_format_role_header(line.strip(), current_section))
            subtitle = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _is_subtitle_line(lines[j]):
                subtitle = html.escape(lines[j].strip())
                i = j + 1
            else:
                i += 1
            if subtitle:
                parts.append(
                    f'<p class="role">{role_text}<br><span class="role-sub">{subtitle}</span></p>'
                )
            else:
                parts.append(f'<p class="role">{role_text}</p>')
            continue

        if is_role:
            role_text = html.escape(_format_role_header(line.strip(), current_section))
            subtitle = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _is_subtitle_line(lines[j]):
                subtitle = html.escape(lines[j].strip())
                i = j + 1
            else:
                i += 1
            if subtitle:
                parts.append(
                    f'<p class="role">{role_text}<br><span class="role-sub">{subtitle}</span></p>'
                )
            else:
                parts.append(f'<p class="role">{role_text}</p>')
            continue

        if current_section == "TECHNICAL SKILLS":
            parts.append(f'<p class="skills-line">{escaped}</p>')
        elif current_section == "PROFESSIONAL SUMMARY":
            parts.append(f'<p class="summary">{escaped}</p>')
        else:
            parts.append(f"<p>{escaped}</p>")
        i += 1

    close_list()
    close_job_block()
    body = "\n".join(parts)
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{body}</body></html>"


def default_output_path(
    company: str | None = None,
    job_title: str | None = None,
    output_dir: Path | str | None = None,
) -> Path:
    from datetime import datetime, timezone

    root = Path(output_dir) if output_dir else Path(__file__).parent / "resume_outputs"
    root.mkdir(parents=True, exist_ok=True)

    slug_parts: list[str] = []
    for part in (company, job_title):
        if part:
            slug = re.sub(r"[^\w\s-]", "", part.strip())
            slug = re.sub(r"\s+", "_", slug)[:40]
            if slug:
                slug_parts.append(slug)
    if not slug_parts:
        slug_parts.append("resume")
    slug_parts.append(datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    return root / f"{'_'.join(slug_parts)}.pdf"


def resume_to_pdf(text: str, output_path: Path | str) -> Path:
    """Render plain-text resume to PDF at output_path."""
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError(
            "Install weasyprint: pip install weasyprint "
            "(Mac system deps: brew install pango)"
        ) from exc

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html_doc = _plain_text_to_html(text)
    HTML(string=html_doc).write_pdf(str(path))
    return path
