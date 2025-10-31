# notifications/services.py
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from threading import Thread
from users.models import User
from .models import Notification
from .utils import send_simple_email_async  # ✅ Import the working Brevo function


class NotificationService:
    """Handles creation and email delivery of notifications."""

    # -----------------------------
    # 1️⃣ Base notification creator
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
        """
        Create a notification record and optionally send an email.
        """
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

        # Email sending - NOW USING BREVO ✅
        if send_email:
            if recipient and recipient.email:
                NotificationService._send_email_async(
                    subject=f"[PC Lab Booking] {title}",
                    message=message,
                    recipient_email=recipient.email,  # ✅ Single email parameter
                )
            elif target_role:
                users = User.objects.filter(role=target_role, is_active=True)
                for user in users:
                    if user.email:
                        NotificationService._send_email_async(
                            subject=f"[PC Lab Booking] {title}",
                            message=message,
                            recipient_email=user.email,  # ✅ Single email parameter
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
    # 3️⃣ UPDATED Email Helper - NOW USING BREVO ✅
    # -----------------------------
    @staticmethod
    def _send_email_async(subject, message, recipient_email):
        """Send email using the same Brevo system that works for OTP"""
        try:
            # Use the same function that works for OTP emails
            send_simple_email_async(
                subject=subject,
                message=message,
                recipient_email=recipient_email
            )
            print(f"✅ Notification email queued for: {recipient_email}")
        except Exception as e:
            print(f"❌ Notification email error: {e}")