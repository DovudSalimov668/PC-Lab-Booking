# notifications/models.py
from django.db import models
from django.utils import timezone
from users.models import User


class Notification(models.Model):
    """
    Represents both system and email notifications for users.
    """

    # ---------------------------------------------------------------
    # Core Relationships
    # ---------------------------------------------------------------
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="The user who receives this notification."
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
        help_text="The user or system that triggered the notification."
    )

    # ---------------------------------------------------------------
    # Notification Content
    # ---------------------------------------------------------------
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Type of notification (e.g., booking_created, booking_approved)."
    )

    # Allow both absolute and relative paths (e.g., /bookings/5/)
    action_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional link to the related action or page."
    )

    # Optional field for broadcasting notifications to a user role (e.g., 'program_admin')
    target_role = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Target role if notification is broadcast to a group."
    )

    # ---------------------------------------------------------------
    # Read Status
    # ---------------------------------------------------------------
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # ---------------------------------------------------------------
    # Utility Methods
    # ---------------------------------------------------------------
    def __str__(self):
        """
        Display a meaningful summary in admin and shell.
        """
        if self.recipient:
            return f"[{self.title}] → {self.recipient.username}"
        elif self.target_role:
            return f"[{self.title}] → Role: {self.target_role}"
        return f"Notification: {self.title}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
