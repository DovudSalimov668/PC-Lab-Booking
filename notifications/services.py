# notifications/services.py
import os
import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from threading import Thread
from users.models import User
from .models import Notification


class NotificationService:
    """Handles creation and email delivery of notifications."""

    # -----------------------------
    # 1️⃣ Create and optionally send email
    # -----------------------------
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
        notif = Notification.objects.create(
            recipient=recipient,
            sender=sender,
            title=title,
            message=message,
            action_url=link,
            target_role=target_role,
            notification_type=notification_type,
            created_at=timezone.now(),
            is_read=False,
        )

        if send_email:
            if recipient and recipient.email:
                NotificationService._send_email_async(
                    subject=f"[PC Lab Booking] {title}",
                    message=message,
                    recipient_email=recipient.email,
                )
            elif target_role:
                users = User.objects.filter(role=target_role, is_active=True)
                for user in users:
                    if user.email:
                        NotificationService._send_email_async(
                            subject=f"[PC Lab Booking] {title}",
                            message=message,
                            recipient_email=user.email,
                        )

        return notif

    # -----------------------------
    # 2️⃣ Specific notification types
    # -----------------------------
    @staticmethod
    def notify_booking_created(booking):
        admins = User.objects.filter(role="program_admin", is_active=True)
        for admin in admins:
            NotificationService.create_notification(
                recipient=admin,
                title=f"New Booking Request: {booking.lab.name}",
                message=(
                    f"{booking.requester.username} requested to book {booking.lab.name} "
                    f"on {booking.start.strftime('%Y-%m-%d %H:%M')}."
                ),
                link=f"/bookings/{booking.id}/",
                sender=booking.requester,
                notification_type="booking_created",
            )

    @staticmethod
    def notify_booking_approved(booking, approver):
        NotificationService.create_notification(
            recipient=booking.requester,
            title=f"Booking Approved: {booking.lab.name}",
            message=(
                f"Your booking for {booking.lab.name} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
                f"has been approved by {approver.username}."
            ),
            link=f"/bookings/{booking.id}/",
            sender=approver,
            notification_type="booking_approved",
        )

    @staticmethod
    def notify_booking_rejected(booking, approver):
        NotificationService.create_notification(
            recipient=booking.requester,
            title=f"Booking Rejected: {booking.lab.name}",
            message=(
                f"Your booking for {booking.lab.name} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
                f"was rejected by {approver.username}."
            ),
            link=f"/bookings/{booking.id}/",
            sender=approver,
            notification_type="booking_rejected",
        )

    @staticmethod
    def notify_booking_cancelled(booking, actor):
        NotificationService.create_notification(
            recipient=booking.requester,
            title=f"Booking Cancelled: {booking.lab.name}",
            message=(
                f"Your booking for {booking.lab.name} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
                f"was cancelled by {actor.username}."
            ),
            link=f"/bookings/{booking.id}/",
            sender=actor,
            notification_type="booking_cancelled",
        )

    # -----------------------------
    # 3️⃣ Async email helper using Resend
    # -----------------------------
    @staticmethod
    def _send_email_async(subject, message, recipient_email):
        """Send an email using Resend API in background thread."""
        def _send():
            try:
                api_key = os.getenv("RESEND_API_KEY")
                if not api_key:
                    print("[NotificationService] Missing RESEND_API_KEY")
                    return

                sender = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@yourdomain.com")
                data = {
                    "from": sender,
                    "to": [recipient_email],
                    "subject": subject,
                    "text": message,
                }

                response = requests.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=data,
                    timeout=10,
                )

                if response.status_code not in (200, 201):
                    print(f"[Resend] Failed to send email: {response.text}")

            except Exception as e:
                print("[NotificationService] Email send error:", e)

        Thread(target=_send, daemon=True).start()
