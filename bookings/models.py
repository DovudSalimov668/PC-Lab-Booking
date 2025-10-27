# bookings/models.py
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta, time
from labs.models import Lab

User = settings.AUTH_USER_MODEL

# --------------------------------------------------------------------
# CHOICES
# --------------------------------------------------------------------
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

# --------------------------------------------------------------------
# BOOKING MODEL
# --------------------------------------------------------------------
class Booking(models.Model):
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
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
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_bookings'
    )
    admin_notes = models.TextField(blank=True, null=True)

    # Recurrence
    is_recurring = models.BooleanField(default=False)
    recurrence_frequency = models.CharField(
        max_length=20, choices=RECURRENCE_FREQUENCY, default="none"
    )
    recurrence_end_date = models.DateField(null=True, blank=True)
    parent_booking = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='recurring_instances'
    )

    # Policy exception tracking
    is_policy_exception = models.BooleanField(default=False)
    exception_reason = models.TextField(blank=True, null=True)
    exception_approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
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
        tag = " (Recurring)" if self.is_recurring else ""
        return f"{self.lab.name if self.lab else 'Unknown Lab'} — {self.start:%Y-%m-%d %H:%M}{tag}"

    # ----------------------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------------------
    def clean(self):
        """Perform full booking validation including policy and time rules"""
        if not self.lab:
            raise ValidationError("A lab must be selected.")

        if self.end <= self.start:
            raise ValidationError("Booking end time must be after the start time.")

        if self.start < timezone.now():
            raise ValidationError("You cannot create a booking in the past.")

        # Check for time slot rules (policy)
        self._validate_time_restrictions()

        # Check for overlapping bookings
        if self.has_conflict():
            raise ValidationError("This booking conflicts with an existing booking.")

        # Check for duration and policy exceptions
        self._validate_against_policy()

    def _validate_time_restrictions(self):
        """
        Check that the booking is within allowed time slots and date window.
        Controlled by Policy model (active one).
        """
        try:
            policy = Policy.objects.filter(is_active=True).first()
        except Policy.DoesNotExist:
            return  # no policy defined

        if not policy:
            return

        # ⏰ Time-of-day restrictions (8AM to 8PM for example)
        work_start = time(hour=getattr(policy, "work_start_hour", 8))
        work_end = time(hour=getattr(policy, "work_end_hour", 20))
        if self.start.time() < work_start or self.end.time() > work_end:
            if not self.is_policy_exception:
                raise ValidationError(
                    f"Bookings must be between {work_start.strftime('%H:%M')} and {work_end.strftime('%H:%M')}."
                )

        # 📅 Advance notice rules
        now = timezone.now()
        min_date = now + timedelta(days=policy.advance_notice_days)
        max_date = now + timedelta(days=policy.max_advance_booking_days)

        if self.start < min_date:
            if not self.is_policy_exception:
                raise ValidationError(
                    f"Bookings must be made at least {policy.advance_notice_days} day(s) in advance."
                )

        if self.start.date() > max_date.date():
            if not self.is_policy_exception:
                raise ValidationError(
                    f"You cannot book more than {policy.max_advance_booking_days} days ahead."
                )

    def _validate_against_policy(self):
        """Duration and policy constraints"""
        try:
            policy = Policy.objects.filter(is_active=True).first()
        except Policy.DoesNotExist:
            policy = None

        duration_hours = self.duration_hours

        if policy and duration_hours > policy.max_hours:
            if not self.is_policy_exception:
                raise ValidationError(
                    f"Booking duration ({duration_hours}h) exceeds the maximum allowed ({policy.max_hours}h). "
                    "Request a policy exception."
                )

    def has_conflict(self):
        """Check for overlapping bookings"""
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

    # ----------------------------------------------------------------
    # PROPERTIES
    # ----------------------------------------------------------------
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("booking_detail", kwargs={"pk": self.pk})

    @property
    def duration_hours(self):
        delta = self.end - self.start
        return round(delta.total_seconds() / 3600, 2)

    @property
    def duration_minutes(self):
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)
        # ----------------------------------------------------------------
    # AVAILABLE TIME SLOTS CALCULATOR
    # ----------------------------------------------------------------
    @staticmethod
    def available_time_slots_for_date(lab, date_obj, slot_minutes=30):
        """
        Returns available start-end intervals for a given lab and date,
        respecting policy working hours and excluding overlapping bookings.
        """

        from datetime import datetime, timedelta, time
        from django.utils import timezone

        # ✅ Get active policy
        policy = Policy.objects.filter(is_active=True).first()

        if not policy:
            work_start = time(hour=8)
            work_end = time(hour=20)
        else:
            work_start = time(hour=policy.work_start_hour)
            work_end = time(hour=policy.work_end_hour)

        # ✅ Make aware start/end times for the day
        tz = timezone.get_default_timezone()
        day_start = timezone.make_aware(datetime.combine(date_obj, work_start), tz)
        day_end = timezone.make_aware(datetime.combine(date_obj, work_end), tz)

        # ✅ Get all active bookings for the lab that overlap this date
        booked = Booking.objects.filter(
            lab=lab,
            start__lt=day_end,
            end__gt=day_start,
        ).exclude(status__in=['cancelled', 'rejected']).order_by('start')

        # ✅ Build all possible slots (e.g., 30 min intervals)
        slots = []
        cur = day_start
        step = timedelta(minutes=slot_minutes)
        while cur + step <= day_end:
            slots.append((cur, cur + step))
            cur += step

        # ✅ Mark unavailable slots based on booked times
        available_slots = []
        for start, end in slots:
            overlap = booked.filter(start__lt=end, end__gt=start).exists()
            if not overlap:
                available_slots.append({
                    'start': start.strftime('%H:%M'),
                    'end': end.strftime('%H:%M'),
                })

        return available_slots

    @staticmethod
    def booked_intervals_for_date(lab, date_obj):
        """
        Return a list of already booked intervals for a given lab and date.
        Useful for visualizing on calendar (red or blocked slots).
        """
        from datetime import datetime, time
        from django.utils import timezone

        tz = timezone.get_default_timezone()
        day_start = timezone.make_aware(datetime.combine(date_obj, time.min), tz)
        day_end = timezone.make_aware(datetime.combine(date_obj, time.max), tz)

        booked_qs = Booking.objects.filter(
            lab=lab,
            start__lt=day_end,
            end__gt=day_start,
        ).exclude(status__in=['cancelled', 'rejected']).order_by('start')

        return [
            {
                'start': b.start.strftime('%H:%M'),
                'end': b.end.strftime('%H:%M'),
                'requester': b.requester.username if hasattr(b.requester, 'username') else str(b.requester),
                'status': b.status
            }
            for b in booked_qs
        ]


# --------------------------------------------------------------------
# POLICY MODEL
# --------------------------------------------------------------------
class Policy(models.Model):
    """Booking policies and time restrictions"""
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    approval_required_for_students = models.BooleanField(default=False)
    max_hours = models.PositiveIntegerField(default=8)
    advance_notice_days = models.PositiveIntegerField(default=1)
    max_advance_booking_days = models.PositiveIntegerField(default=30)
    allow_recurring = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    # NEW FIELDS
    work_start_hour = models.PositiveSmallIntegerField(default=8)
    work_end_hour = models.PositiveSmallIntegerField(default=20)

    def __str__(self):
        return self.name

# --------------------------------------------------------------------
# POLICY EXCEPTION MODEL
# --------------------------------------------------------------------
# Add this to bookings/models.py (should already exist, but verify it's complete)

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

# --------------------------------------------------------------------
# AUDIT LOG MODEL
# --------------------------------------------------------------------
class AuditLog(models.Model):
    """Track booking and policy actions"""
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
        return f"{self.timestamp:%Y-%m-%d %H:%M} — {self.actor} — {self.action}"
