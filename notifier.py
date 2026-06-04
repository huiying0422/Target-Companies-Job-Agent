import html
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_BADGE_STYLES = {
    "FIT": ("background:#dcfce7;color:#166534;", "FIT"),
    "APPLY_LATER": ("background:#fef9c3;color:#854d0e;", "APPLY LATER"),
    "NOT_FIT": ("background:#fee2e2;color:#991b1b;", "NOT FIT"),
}


def _send(subject: str, html_body: str, text: str):
    gmail_from = os.environ["GMAIL_FROM"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]
    notify_email = os.environ["NOTIFY_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_from
    msg["To"] = notify_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_from, app_password)
        server.sendmail(gmail_from, notify_email, msg.as_string())


def _sort_jobs(jobs: list[dict]) -> list[dict]:
    return sorted(jobs, key=lambda j: j.get("first_seen") or "", reverse=True)


def _bucket_jobs(
    new_jobs: list[dict],
    seen_fit_jobs: list[dict],
) -> dict[str, list[dict]]:
    new_fit = _sort_jobs([
        j for j in new_jobs
        if j.get("is_new") and j.get("verdict_label") in ("FIT", "APPLY_LATER")
    ])
    seen_fit = _sort_jobs([
        {**j, "is_new": False} for j in seen_fit_jobs
        if j.get("verdict_label") in ("FIT", "APPLY_LATER")
    ])
    not_fit_us = _sort_jobs([
        j for j in new_jobs
        if j.get("verdict_label") == "NOT_FIT" and int(j.get("is_us", 1)) == 1
    ])
    not_fit_intl = _sort_jobs([
        j for j in new_jobs
        if j.get("verdict_label") == "NOT_FIT" and int(j.get("is_us", 1)) == 0
    ])
    return {
        "new_fit": new_fit,
        "seen_fit": seen_fit,
        "not_fit_us": not_fit_us,
        "not_fit_intl": not_fit_intl,
    }


def _badge_html(label: str) -> str:
    style, text = _BADGE_STYLES.get(label, ("background:#f3f4f6;color:#374151;", label))
    return (
        f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;'
        f'font-size:14px;font-weight:600;{style}">{html.escape(text)}</span>'
    )


def _job_card_html(job: dict) -> str:
    label = job.get("verdict_label") or ""
    reason = html.escape(job.get("verdict_reason") or "")
    title = html.escape(job.get("title") or "")
    company = html.escape(job.get("company") or "")
    location = html.escape(job.get("location") or "")
    url = html.escape(job.get("url") or "#")
    keywords = html.escape(", ".join(job.get("matched_keywords") or []))

    return f"""
<div style="border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:0 0 14px;background:#ffffff;">
  <p style="margin:0 0 8px;font-size:16px;line-height:1.4;">
    <a href="{url}" style="color:#1a73e8;text-decoration:none;font-weight:600;">{title}</a>
    <span style="color:#6b7280;"> — {company}</span>
  </p>
  <p style="margin:0 0 10px;color:#4b5563;font-size:14px;line-height:1.5;">{location}</p>
  <p style="margin:0 0 10px;font-size:14px;line-height:1.5;"><strong>Keywords:</strong> {keywords}</p>
  <p style="margin:0 0 10px;">{_badge_html(label) if label else ""}</p>
  <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">{reason}</p>
</div>"""


def _job_card_text(job: dict) -> str:
    label = job.get("verdict_label") or ""
    reason = job.get("verdict_reason") or ""
    keywords = ", ".join(job.get("matched_keywords") or [])
    lines = [
        f"{job.get('title')} — {job.get('company')}",
        job.get("location") or "",
        job.get("url") or "",
        f"Keywords: {keywords}",
    ]
    if label:
        lines.append(f"Verdict: {label}")
    if reason:
        lines.append(reason)
    return "\n".join(lines)


def _section_html(title: str, jobs: list[dict], collapsed: bool = False) -> str:
    if not jobs:
        return ""
    cards = "".join(_job_card_html(j) for j in jobs)
    inner = f"""
<div style="padding:8px 0 4px;">
  {cards}
</div>"""
    if collapsed:
        return f"""
<details style="margin:0 0 18px;border:1px solid #e5e7eb;border-radius:10px;padding:8px 12px;background:#fafafa;">
  <summary style="cursor:pointer;font-size:16px;font-weight:600;line-height:1.5;padding:6px 0;">
    {html.escape(title)} ({len(jobs)})
  </summary>
  {inner}
</details>"""
    return f"""
<section style="margin:0 0 22px;">
  <h2 style="margin:0 0 12px;font-size:18px;line-height:1.4;">{html.escape(title)}</h2>
  {inner}
</section>"""


def _section_text(title: str, jobs: list[dict]) -> str:
    if not jobs:
        return ""
    blocks = "\n---\n".join(_job_card_text(j) for j in jobs)
    return f"\n{title}\n{'=' * len(title)}\n{blocks}\n"


def send_job_matches(new_jobs: list[dict], seen_fit_jobs: list[dict] | None = None):
    """
    new_jobs: jobs evaluated this run (is_new=True), all verdict labels.
    seen_fit_jobs: existing FIT/APPLY_LATER from DB for 'Previously Seen' section.
    Skips send when new_fit + seen_fit is empty.
    """
    buckets = _bucket_jobs(new_jobs, seen_fit_jobs or [])
    if not buckets["new_fit"] and not buckets["seen_fit"]:
        return False

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n_new = len(buckets["new_fit"])
    subject = f"🎯 {n_new} new match{'es' if n_new != 1 else ''} — {date_str}"

    html_sections = (
        _section_html("🆕 New Matches", buckets["new_fit"])
        + _section_html("📋 Previously Seen", buckets["seen_fit"])
        + _section_html("📦 Not a Fit (US)", buckets["not_fit_us"], collapsed=True)
        + _section_html("🌏 Not a Fit (Outside US)", buckets["not_fit_intl"], collapsed=True)
    )

    text_sections = (
        _section_text("New Matches", buckets["new_fit"])
        + _section_text("Previously Seen", buckets["seen_fit"])
        + _section_text("Not a Fit (US)", buckets["not_fit_us"])
        + _section_text("Not a Fit (Outside US)", buckets["not_fit_intl"])
    )

    html_body = f"""<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;padding:16px;font-size:14px;line-height:1.5;color:#111827;">
<h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;">{html.escape(subject)}</h1>
{html_sections}
</body></html>"""
    text = f"{subject}\n{text_sections}"
    _send(subject, html_body, text)
    return True


def send_no_matches(companies_checked: list[str]):
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    subject = f"✅ Agent ran — no new matches ({timestamp})"

    companies_html = "".join(f"<li>{html.escape(c)}</li>" for c in companies_checked)
    companies_text = "\n".join(f"  · {c}" for c in companies_checked)

    html_body = f"""<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:16px;font-size:14px;">
<h1 style="font-size:22px;">✅ Agent ran — no new matches</h1>
<p><strong>Run time:</strong> {html.escape(timestamp)}</p>
<p>Companies checked:</p>
<ul style="line-height:1.8;">{companies_html}</ul>
</body></html>"""
    text = f"{subject}\n\nCompanies checked:\n{companies_text}"

    _send(subject, html_body, text)


def send_health_alerts(alerts: list[dict]):
    """alerts: list of {company, message}"""
    n = len(alerts)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"⚠️ Scraper health alert — {n} issue{'s' if n != 1 else ''} ({date_str})"

    rows_html = "".join(
        f"<tr>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;'><strong>{html.escape(a['company'])}</strong></td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;color:#c0392b;'>{html.escape(a['message'])}</td>"
        f"</tr>"
        for a in alerts
    )
    rows_text = "\n".join(f"  · {a['company']}: {a['message']}" for a in alerts)

    html_body = f"""<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:16px;font-size:14px;">
<h1 style="font-size:22px;">⚠️ Scraper health alert</h1>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
  <thead>
    <tr>
      <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Company</th>
      <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Issue</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
</body></html>"""
    text = f"{subject}\n\n{rows_text}"

    _send(subject, html_body, text)
