# notifications/services.py
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Notification
from users.models import User

class NotificationService:
    """Handles creation and emailing of system notifications."""

    @staticmethod
    def create_notification(recipient, title, message, link=None):
        """
        Save notification in DB and optionally send an email.
        """
        # 1️⃣ Save to database
        Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            link=link,
            created_at=timezone.now(),
            is_read=False
        )

        # 2️⃣ Send email notification
        try:
            send_mail(
                subject=f"[PC Lab Booking] {title}",
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@pclab.com"),
                recipient_list=[recipient.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"[NotificationService] Error sending email to {recipient.email}: {e}")

    # -------------------- Booking Notifications --------------------

    @staticmethod
    def notify_booking_created(booking):
        """
        Notify Programme Administrators when a student creates a booking.
        """
        admins = User.objects.filter(role="program_admin", is_active=True)
        for admin in admins:
            NotificationService.create_notification(
                recipient=admin,
                title=f"New Booking Request: {booking.lab.name}",
                message=(
                    f"{booking.requester.username} requested to book "
                    f"{booking.lab.name} on {booking.start.strftime('%Y-%m-%d %H:%M')}."
                ),
                link=f"/bookings/{booking.id}/"
            )

    @staticmethod
    def notify_booking_status_changed(booking):
        """
        Notify the requester when the admin approves/rejects the booking.
        """
        status_word = booking.status.title()
        title = f"Booking {status_word}"
        message = (
            f"Your booking for {booking.lab.name} on {booking.start.strftime('%Y-%m-%d %H:%M')} "
            f"was {booking.status}."
        )
        NotificationService.create_notification(
            recipient=booking.requester,
            title=title,
            message=message,
            link=f"/bookings/{booking.id}/"
        )
