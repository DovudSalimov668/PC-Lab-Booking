# notifications/email.py
from resend import Resend
from django.conf import settings
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

_resend = None
def get_resend_client():
    global _resend
    if _resend is None:
        api_key = getattr(settings, "RESEND_API_KEY", None)
        if not api_key:
            raise RuntimeError("RESEND_API_KEY not set in settings")
        _resend = Resend(api_key)
    return _resend

def send_email_via_resend(subject: str, plaintext: str, html: str, recipients: list[str], from_email: str = None):
    """
    Recipients: list of emails
    html: rendered html body (string)
    plaintext: fallback text body
    """
    if not from_email:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    try:
        client = get_resend_client()
        resp = client.emails.send({
            "from": from_email,
            "to": recipients,
            "subject": subject,
            "text": plaintext,
            "html": html
        })
        logger.info("Resend email sent: %s", resp)
        return resp
    except Exception as e:
        logger.exception("Failed to send email via Resend: %s", e)
        return None

def send_simple_email(subject, message, recipient_email, template_name=None, context=None):
    # convenience helper: if template_name provided, render html
    if template_name:
        html = render_to_string(template_name, context or {})
    else:
        html = f"<p>{message}</p>"

    return send_email_via_resend(
        subject=subject,
        plaintext=message,
        html=html,
        recipients=[recipient_email]
    )
