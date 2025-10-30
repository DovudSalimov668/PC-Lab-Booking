# notifications/email.py
import os
import logging
import requests
from threading import Thread
from typing import List, Optional

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY") or getattr(settings, "BREVO_API_KEY", None)
DEFAULT_FROM = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
BREVO_SEND_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _send_via_brevo_http(subject: str, html: str, text: str, recipients: List[str], from_email: Optional[str] = None):
    """Send using Brevo HTTP API (safe on Render)."""
    if not BREVO_API_KEY:
        return False, "Missing BREVO_API_KEY"

    payload = {
        "sender": {"name": None, "email": from_email or DEFAULT_FROM},
        "to": [{"email": r} for r in recipients],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    try:
        resp = requests.post(BREVO_SEND_ENDPOINT, headers=headers, json=payload, timeout=10)
        if resp.status_code // 100 != 2:
            logger.error("[Brevo HTTP] %s %s", resp.status_code, resp.text)
            return False, resp.text
        logger.info("[Brevo HTTP] Email sent to %s", recipients)
        return True, None
    except Exception as e:
        logger.exception("[Brevo HTTP] Exception: %s", e)
        return False, str(e)


def _send_via_smtp(subject: str, html: str, text: str, recipients: List[str], from_email: Optional[str] = None):
    """Send via Django SMTP backend."""
    try:
        email = EmailMessage(
            subject=subject,
            body=html,
            from_email=from_email or DEFAULT_FROM,
            to=recipients,
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        logger.info("[SMTP] Sent to %s", recipients)
        return True, None
    except Exception as e:
        logger.exception("[SMTP] Exception: %s", e)
        return False, str(e)


def send_email_async(subject: str, html: str, text: str, recipients: List[str], from_email: Optional[str] = None):
    """Public async helper – prefers HTTP API, falls back to SMTP."""
    def worker():
        if BREVO_API_KEY:
            ok, err = _send_via_brevo_http(subject, html, text, recipients, from_email)
            if ok:
                return
            logger.warning("[Email] Brevo HTTP failed, trying SMTP fallback: %s", err)
        ok, err = _send_via_smtp(subject, html, text, recipients, from_email)
        if not ok:
            logger.error("[Email] Both HTTP and SMTP failed: %s", err)

    Thread(target=worker, daemon=True).start()


def send_template_email(subject: str, template_html: str, context: dict, recipients: List[str], from_email: Optional[str] = None):
    """Render template and send asynchronously."""
    html = render_to_string(template_html, context or {})
    text = context.get("plain_text", "PC Lab Booking notification.")
    send_email_async(subject, html, text, recipients, from_email)
