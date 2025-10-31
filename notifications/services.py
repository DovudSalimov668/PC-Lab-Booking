# notifications/services.py - COMPLETE REPLACEMENT
import logging
from django.conf import settings
from django.utils import timezone
from .models import Notification
from users.models import User
from .email import send_simple_email_async

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Complete notification service that matches your bookings views
    """

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
        Create DB notification and optionally send email
        """
        try:
            print(f"📧 Creating notification: {title} for {recipient.email if recipient else target_role}")
            
            # Create DB notification records
            if recipient:
                notification = Notification.objects.create(
                    recipient=recipient,
                    sender=sender,
                    title=title,
                    message=message,
                    action_url=link,
                    notification_type=notification_type,
                    target_role=target_role,
                    is_read=False,
                    created_at=timezone.now()
                )
                
                # Send email if requested
                if send_email and recipient.email:
                    try:
                        send_simple_email_async(
                            subject=f"[PC Lab] {title}",
                            message=f"{message}<br><br><a href='{link or 'https://pc-lab-booking.onrender.com'}'>View in Dashboard</a>",
                            recipient_email=recipient.email
                        )
                        print(f"✅ Notification email sent to {recipient.email}")
                    except Exception as e:
                        print(f"❌ Failed to send email to {recipient.email}: {e}")

            elif target_role:
                users = User.objects.filter(role=target_role, is_active=True)
                for user in users:
                    Notification.objects.create(
                        recipient=user,
                        sender=sender,
                        title=title,
                        message=message,
                        action_url=link,
                        notification_type=notification_type,
                        target_role=target_role,
                        is_read=False,
                        created_at=timezone.now()
                    )
                    
                    # Send email to each user in target role
                    if send_email and user.email:
                        try:
                            send_simple_email_async(
                                subject=f"[PC Lab] {title}",
                                message=f"{message}<br><br><a href='{link or 'https://pc-lab-booking.onrender.com'}'>View in Dashboard</a>",
                                recipient_email=user.email
                            )
                            print(f"✅ Notification email sent to {user.email}")
                        except Exception as e:
                            print(f"❌ Failed to send email to {user.email}: {e}")

            else:
                print("❌ No recipient or target_role specified for notification")
                
        except Exception as e:
            logger.error(f"❌ Error creating notification: {str(e)}")
            print(f"❌ Notification creation failed: {e}")

    # ================= BOOKING NOTIFICATIONS =================

    @staticmethod
    def notify_booking_created(booking):
        """Notify admins about new booking request"""
        try:
            print(f"🔔 Notifying admins about new booking #{booking.id}")
            admins = User.objects.filter(role__in=["program_admin", "lab_technician", "manager"], is_active=True)
            
            for admin in admins:
                NotificationService.create_notification(
                    recipient=admin,
                    title=f"New Booking Request - {booking.lab.name if booking.lab else 'Lab'}",
                    message=f"{booking.requester.username} requested booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')}.",
                    link=f"/bookings/{booking.id}/",
                    sender=booking.requester,
                    notification_type="booking_created",
                    send_email=True
                )
            print(f"✅ Booking created notifications sent to {admins.count()} admins")
        except Exception as e:
            print(f"❌ Error sending booking created notifications: {e}")

    @staticmethod
    def notify_booking_approved(booking, approver):
        """Notify requester about booking approval"""
        try:
            print(f"🔔 Notifying {booking.requester.email} about booking approval")
            NotificationService.create_notification(
                recipient=booking.requester,
                title=f"Booking Approved - {booking.lab.name if booking.lab else 'Lab'}",
                message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')} was approved by {approver.username}.",
                link=f"/bookings/{booking.id}/",
                sender=approver,
                notification_type="booking_approved",
                send_email=True
            )
            print(f"✅ Booking approved notification sent to {booking.requester.email}")
        except Exception as e:
            print(f"❌ Error sending booking approved notification: {e}")

    @staticmethod
    def notify_booking_rejected(booking, approver):
        """Notify requester about booking rejection"""
        try:
            print(f"🔔 Notifying {booking.requester.email} about booking rejection")
            NotificationService.create_notification(
                recipient=booking.requester,
                title=f"Booking Rejected - {booking.lab.name if booking.lab else 'Lab'}",
                message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')} was rejected by {approver.username}.",
                link=f"/bookings/{booking.id}/",
                sender=approver,
                notification_type="booking_rejected",
                send_email=True
            )
            print(f"✅ Booking rejected notification sent to {booking.requester.email}")
        except Exception as e:
            print(f"❌ Error sending booking rejected notification: {e}")

    @staticmethod
    def notify_booking_cancelled(booking, actor):
        """Notify about booking cancellation"""
        try:
            print(f"🔔 Notifying {booking.requester.email} about booking cancellation")
            NotificationService.create_notification(
                recipient=booking.requester,
                title=f"Booking Cancelled - {booking.lab.name if booking.lab else 'Lab'}",
                message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start.strftime('%Y-%m-%d %H:%M')} was cancelled by {actor.username}.",
                link=f"/bookings/{booking.id}/",
                sender=actor,
                notification_type="booking_cancelled",
                send_email=True
            )
            print(f"✅ Booking cancelled notification sent to {booking.requester.email}")
        except Exception as e:
            print(f"❌ Error sending booking cancelled notification: {e}")

    @staticmethod
    def notify_booking_completed(booking, user):
        """Notify requester about booking completion"""
        try:
            print(f"🔔 Notifying {booking.requester.email} about booking completion")
            NotificationService.create_notification(
                recipient=booking.requester,
                title=f"Booking #{booking.id} completed",
                message=f"Booking for {booking.lab.name} on {booking.start} completed.",
                link=f"/bookings/{booking.id}/",
                sender=user,
                notification_type="booking_completed",
                send_email=True
            )
            print(f"✅ Booking completed notification sent to {booking.requester.email}")
        except Exception as e:
            print(f"❌ Error sending booking completed notification: {e}")