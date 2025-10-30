# notifications/email.py
"""
Email helper utilities (SMTP version).

Uses Django's configured EMAIL_BACKEND (e.g. Brevo, SendGrid, etc.).
"""

import logging
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from threading import Thread

logger = logging.getLogger(__name__)

def _send_async(email_obj):
    """Send email in a background thread (non-blocking)."""
    def _send():
        try:
            email_obj.send(fail_silently=False)
            logger.info(f"Email sent successfully to: {email_obj.to}")
        except Exception as e:
            logger.exception(f"Email send failed: {e}")
    Thread(target=_send, daemon=True).start()


def send_simple_email(subject, message, recipient_email, template_name=None, context=None):
    """
    Sends an email using the configured Django email backend.
    If template_name is provided, renders HTML and attaches it.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "PC Lab Booking <noreply@pclab.app>")

    # prepare plain text and html body
    if template_name:
        html_body = render_to_string(template_name, context or {})
    else:
        html_body = f"<p>{message}</p>"

    email = EmailMultiAlternatives(
        subject=subject,
        body=message,
        from_email=from_email,
        to=[recipient_email],
    )
    email.attach_alternative(html_body, "text/html")

    _send_async(email)
    return True
