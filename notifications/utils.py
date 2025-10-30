# notifications/utils.py
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from threading import Thread
from django.contrib.contenttypes.models import ContentType
from .models import Notification
from users.models import User

def _send_email_background(subject, message, recipients, html_message=None):
    """Send emails in a background thread."""
    def _send():
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                html_message=html_message,
                fail_silently=False
            )
        except Exception as e:
            print("Email failed:", e)
    Thread(target=_send, daemon=True).start()

def create_notification(actor=None, recipient=None, target_role=None, verb="", description="", obj=None, level="info"):
    """
    Create a notification entry and send email.
    - actor: user performing the action
    - recipient: target user (if direct)
    - target_role: target role (if broadcast)
    - verb: what happened
    - description: details
    - obj: related object (optional)
    """
    content_type = ContentType.objects.get_for_model(obj.__class__) if obj else None
    notif = Notification.objects.create(
        actor=actor,
        recipient=recipient,
        target_role=target_role,
        verb=verb,
        description=description,
        content_type=content_type,
        object_id=obj.id if obj else None,
        level=level,
    )

    # Send email
    if recipient:
        _send_notification_email(recipient, notif)
    elif target_role:
        for user in User.objects.filter(role=target_role, is_active=True):
            _send_notification_email(user, notif)
    return notif

def _send_notification_email(user, notif):
    """Send notification via email."""
    context = {'user': user, 'notification': notif}
    subject = render_to_string('emails/notification_subject.txt', context).strip()
    body = render_to_string('emails/notification_body.txt', context)
    html_body = render_to_string('emails/notification_body.html', context)
    _send_email_background(subject, body, [user.email], html_message=html_body)
