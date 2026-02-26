"""Weekly email digest delivery."""

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


def render_digest(
    opportunities: list[dict],
    foundations: list[dict],
    stats: dict,
) -> str:
    """Render the email digest HTML from template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("email_digest.html.j2")

    return template.render(
        report_date=date.today().strftime("%B %d, %Y"),
        opportunities=opportunities,
        foundations=foundations,
        stats=stats,
    )


def send_digest(
    html_content: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    recipients: list[str],
    subject: str | None = None,
) -> bool:
    """Send the digest email via SMTP.

    Returns True if sent successfully.
    """
    if not recipients:
        logger.warning("No email recipients configured")
        return False

    if not smtp_host or not smtp_user:
        logger.warning("SMTP not configured, skipping email")
        return False

    if subject is None:
        subject = f"YLM Grant Intelligence Report - {date.today().strftime('%B %d, %Y')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    text_part = MIMEText(
        "Your weekly grant intelligence report is ready. "
        "Please view this email in an HTML-capable client.",
        "plain",
    )
    html_part = MIMEText(html_content, "html")

    msg.attach(text_part)
    msg.attach(html_part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())

        logger.info("Digest email sent to %s", ", ".join(recipients))
        return True
    except Exception:
        logger.exception("Failed to send digest email")
        return False


def dry_run_digest(
    opportunities: list[dict],
    foundations: list[dict],
    stats: dict,
    output_dir: str = "output",
) -> str:
    """Render the digest and save to file without sending.

    Returns path to the saved HTML file.
    """
    html = render_digest(opportunities, foundations, stats)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filepath = Path(output_dir) / f"digest_{date.today().isoformat()}.html"
    filepath.write_text(html)

    logger.info("Digest rendered to %s", filepath)
    return str(filepath)
