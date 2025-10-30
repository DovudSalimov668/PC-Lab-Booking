# notifications/services.py
from threading import Thread
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

class NotificationService:
    """
    NotificationService:
    - create_notification: saves DB entry, optionally sends email (async)
    - notify_booking_* helpers for booking lifecycle events
    """

    @staticmethod
    def _send_email_background(subject, message, recipient_list, html_message=None):
        """Send email in background thread (non-blocking)."""
        def _send():
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
                    recipient_list=recipient_list,
                    html_message=html_message,
                    fail_silently=False
                )
            except Exception as e:
                # In production, replace print with proper logging
                print("[NotificationService] Failed to send email:", e)

        Thread(target=_send, daemon=True).start()

    @staticmethod
    def create_notification(
        recipient=None,
        title="",
        message="",
        link=None,
        sender=None,
        target_role=None,
        notification_type="general",
        send_email=True
    ):
        """
        Create DB notification and optionally email recipient(s).
        - recipient: single User instance (preferred)
        - target_role: string role to broadcast to (recipient omitted)
        """

        # Create DB notification records
        if recipient:
            Notification.objects.create(
                recipient=recipient,
                sender=sender,
                title=title,
                message=message,
                action_url=link,
                notification_type=notification_type,
                target_role=target_role or None,
                is_read=False,
                created_at=timezone.now()
            )
        elif target_role:
            users = User.objects.filter(role=target_role, is_active=True)
            for u in users:
                Notification.objects.create(
                    recipient=u,
                    sender=sender,
                    title=title,
                    message=message,
                    action_url=link,
                    notification_type=notification_type,
                    target_role=target_role,
                    is_read=False,
                    created_at=timezone.now()
                )
        else:
            # No recipient and no role -> do nothing (or write a system-wide notification if you have such a model)
            pass

        # Send email if requested
        if send_email:
            if recipient and recipient.email:
                NotificationService._send_email_background(
                    subject=f"[PC Lab Booking] {title}",
                    message=message,
                    recipient_list=[recipient.email],
                    html_message=None
                )
            elif target_role:
                recipients = list(User.objects.filter(role=target_role, is_active=True).exclude(email__isnull=True).exclude(email__exact="").values_list("email", flat=True))
                if recipients:
                    # split recipients into smaller lists if necessary — most SMTP servers limit recipients per email
                    NotificationService._send_email_background(
                        subject=f"[PC Lab Booking] {title}",
                        message=message,
                        recipient_list=list(recipients),
                        html_message=None
                    )

    # Booking-specific helpers
    @staticmethod
    def notify_booking_created(booking):
        admins = User.objects.filter(role="program_admin", is_active=True)
        for admin in admins:
            NotificationService.create_notification(
                recipient=admin,
                title=f"New Booking Request: {booking.lab.name if booking.lab else 'Lab'}",
                message=(f"{booking.requester.username} requested booking for {booking.lab.name if booking.lab else 'lab'} "
                         f"on {booking.start.strftime('%Y-%m-%d %H:%M')}."),
                link=f"/bookings/{booking.id}/",
                sender=booking.requester,
                notification_type="booking_created",
                send_email=True
            )

    @staticmethod
    def notify_booking_approved(booking, approver):
        NotificationService.create_notification(
            recipient=booking.requester,
            title=f"Booking Approved: {booking.lab.name if booking.lab else 'Lab'}",
            message=(f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
                     f"was approved by {approver.username}."),
            link=f"/bookings/{booking.id}/",
            sender=approver,
            notification_type="booking_approved",
            send_email=True
        )

    @staticmethod
    def notify_booking_rejected(booking, approver):
        NotificationService.create_notification(
            recipient=booking.requester,
            title=f"Booking Rejected: {booking.lab.name if booking.lab else 'Lab'}",
            message=(f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
                     f"was rejected by {approver.username}."),
            link=f"/bookings/{booking.id}/",
            sender=approver,
            notification_type="booking_rejected",
            send_email=True
        )

    @staticmethod
    def notify_booking_cancelled(booking, actor):
        NotificationService.create_notification(
            recipient=booking.requester,
            title=f"Booking Cancelled: {booking.lab.name if booking.lab else 'Lab'}",
            message=(f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
                     f"was cancelled by {actor.username}."),
            link=f"/bookings/{booking.id}/",
            sender=actor,
            notification_type="booking_cancelled",
            send_email=True
        )
