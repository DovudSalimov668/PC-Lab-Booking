# bookings/models.py (UPDATE EXISTING)
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from labs.models import Lab

User = settings.AUTH_USER_MODEL

BOOKING_STATUS = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
    ("completed", "Completed"),
]

RECURRENCE_FREQUENCY = [
    ("none", "No Recurrence"),
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("biweekly", "Bi-weekly"),
    ("monthly", "Monthly"),
]


class Booking(models.Model):
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings",null=False)
    lab = models.ForeignKey(
        Lab, on_delete=models.CASCADE, related_name="bookings",
        null=True, blank=True
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=20, choices=BOOKING_STATUS, default="pending")
    purpose = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approval_required = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_bookings'
    )
    admin_notes = models.TextField(blank=True, null=True)
    
    # Recurring booking fields
    is_recurring = models.BooleanField(default=False)
    recurrence_frequency = models.CharField(
        max_length=20, 
        choices=RECURRENCE_FREQUENCY, 
        default="none"
    )
    recurrence_end_date = models.DateField(null=True, blank=True)
    parent_booking = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='recurring_instances'
    )
    
    # Policy exception tracking
    is_policy_exception = models.BooleanField(default=False)
    exception_reason = models.TextField(blank=True, null=True)
    exception_approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_exceptions'
    )

    class Meta:
        ordering = ["-start"]
        indexes = [
            models.Index(fields=['start', 'end']),
            models.Index(fields=['status']),
            models.Index(fields=['lab', 'start']),
        ]

    def __str__(self):
        recurring_tag = " (Recurring)" if self.is_recurring else ""
        return f"{self.lab.name if self.lab else 'Unknown Lab'} — {self.start:%Y-%m-%d %H:%M}{recurring_tag}"

    def clean(self):
        """Enhanced validation with policy checks"""
        if self.pk:
            try:
                original = Booking.objects.get(pk=self.pk)
                if original.start == self.start and original.end == self.end:
                    if self.end <= self.start:
                        raise ValidationError("Booking end must be after start.")
                    return
            except Booking.DoesNotExist:
                pass

        if not self.lab:
            raise ValidationError("You must select a lab.")

        if self.end <= self.start:
            raise ValidationError("Booking end must be after start.")

        if self.start < timezone.now():
            raise ValidationError("Booking start must be in the future.")

        # Check for overlaps
        if self.has_conflict():
            raise ValidationError("This booking conflicts with an existing booking.")
        
        # Policy validations
        self._validate_against_policy()

    def _validate_against_policy(self):
        """Check booking against policy rules"""
        # Check duration limits
        duration_hours = (self.end - self.start).total_seconds() / 3600
        
        try:
            policy = Policy.objects.first()
            if policy and duration_hours > policy.max_hours:
                if not self.is_policy_exception:
                    raise ValidationError(
                        f"Booking duration ({duration_hours}h) exceeds maximum allowed ({policy.max_hours}h). "
                        "Request a policy exception."
                    )
        except Policy.DoesNotExist:
            pass

    def has_conflict(self):
        """Check for booking conflicts"""
        qs = Booking.objects.exclude(pk=self.pk)
        qs = qs.exclude(status__in=["cancelled", "rejected"])
        conflicts = qs.filter(
            lab=self.lab,
            start__lt=self.end,
            end__gt=self.start
        )
        return conflicts.exists()

    def save(self, *args, **kwargs):
        if 'update_fields' not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("booking_detail", kwargs={"pk": self.pk})
    
    @property
    def duration_hours(self):
        """Calculate duration in hours"""
        delta = self.end - self.start
        return round(delta.total_seconds() / 3600, 1)
    
    @property
    def duration_minutes(self):
        """Calculate duration in minutes"""
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)
    
    @property
    def can_be_edited_by(self, user):
        """Check if user can edit this booking"""
        if user.can_edit_any_booking:
            return True
        return user == self.requester and self.status == 'pending'
    
    @property
    def can_be_deleted_by(self, user):
        """Check if user can delete this booking"""
        if user.can_delete_any_booking:
            return True
        return user == self.requester and self.status in ['pending', 'approved']


class Policy(models.Model):
    """Booking policies and restrictions"""
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    approval_required_for_students = models.BooleanField(default=False)
    max_hours = models.PositiveIntegerField(default=8)
    advance_notice_days = models.PositiveIntegerField(default=1)
    max_advance_booking_days = models.PositiveIntegerField(default=30)
    allow_recurring = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PolicyException(models.Model):
    """Track policy exception requests"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='policy_exceptions')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exception_requests')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_exceptions'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Exception for Booking #{self.booking.id} - {self.status}"


class AuditLog(models.Model):
    """Track all booking changes"""
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    entity = models.CharField(max_length=100, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} {self.actor} {self.action}"