"""Tailor base resume to a job description via Claude API."""

import argparse
import os
import sys
from pathlib import Path

from config import BASE_RESUME_EXAMPLE, BASE_RESUME_PATH

# Customize: copy templates/base_resume.example.txt → templates/base_resume.txt
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a resume editor. Rules:
1. Do NOT invent experience, skills, or companies.
2. Only rewrite the summary section and reorder existing bullets.
3. Do not add new bullet points.
4. Return plain text only, same structure as input."""


def load_base_resume(path: Path | str | None = None) -> str:
    if path:
        resume_path = Path(path)
    else:
        resume_path = (
            BASE_RESUME_PATH if BASE_RESUME_PATH.is_file() else BASE_RESUME_EXAMPLE
        )
    if not resume_path.is_file():
        raise FileNotFoundError(
            "Base resume not found. Copy templates/base_resume.example.txt "
            "to templates/base_resume.txt"
        )
    return resume_path.read_text(encoding="utf-8").strip()


def load_jd_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from an uploaded job-description PDF."""
    import io

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("Install pdfplumber: pip install pdfplumber") from exc

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
    result = "\n\n".join(parts).strip()
    if not result:
        raise ValueError("Could not extract text from PDF.")
    return result


def tailor_resume(jd_text: str, base_resume: str, api_key: str | None = None) -> str:
    jd_text = jd_text.strip()
    if not jd_text:
        raise ValueError("Job description text is empty.")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("Install anthropic: pip install anthropic") from exc

    user_content = f"""Base resume:

{base_resume}

---

Job description:

{jd_text}

Tailor the base resume per the rules. Output the full resume in plain text."""

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text.strip()


def main():
    parser = argparse.ArgumentParser(description="Tailor resume to a job description")
    parser.add_argument("--jd", required=True, help="Job description text")
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help="Path to base resume text file",
    )
    parser.add_argument("--job-title", default=None, help="Optional title for DB log")
    parser.add_argument("--company", default=None, help="Optional company for DB log")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write to resume_outputs table",
    )
    args = parser.parse_args()

    from database import init_db, save_resume_output

    init_db()
    base = load_base_resume(args.template)
    tailored = tailor_resume(args.jd, base)

    pdf_path = None
    if not args.no_save:
        from pdf_generator import default_output_path, resume_to_pdf

        pdf_path = default_output_path(args.company, args.job_title)
        resume_to_pdf(tailored, pdf_path)

    if not args.no_save:
        row_id = save_resume_output(
            jd_text=args.jd,
            tailored_resume_text=tailored,
            job_title=args.job_title,
            company=args.company,
            tailored_resume_path=str(pdf_path),
        )
        print(f"# Saved to resume_outputs id={row_id}", file=sys.stderr)
        print(f"# PDF saved to {pdf_path}", file=sys.stderr)

    print(tailored)


if __name__ == "__main__":
    main()
