from datetime import datetime, timedelta, time
from django.utils import timezone
from .models import Booking, Policy

WORK_START_HOUR = 8     # Lab opens at 8 AM
WORK_END_HOUR = 20      # Lab closes at 8 PM
SLOT_INTERVAL_MINUTES = 30  # Each slot is 30 minutes

def get_available_time_slots(lab, date):
    """
    Generate a list of available (start, end) times for the given lab and date.
    Respects existing bookings, working hours, and policy.
    """
    tz = timezone.get_default_timezone()
    start_of_day = timezone.make_aware(datetime.combine(date, time(WORK_START_HOUR, 0)), tz)
    end_of_day = timezone.make_aware(datetime.combine(date, time(WORK_END_HOUR, 0)), tz)
    step = timedelta(minutes=SLOT_INTERVAL_MINUTES)

    # 1️⃣ Get all active bookings for that lab & day
    existing_bookings = Booking.objects.filter(
        lab=lab,
        start__lt=end_of_day,
        end__gt=start_of_day,
    ).exclude(status__in=['cancelled', 'rejected']).order_by('start')

    # 2️⃣ Generate time slots across working hours
    slots = []
    current = start_of_day
    while current + step <= end_of_day:
        slot_start = current
        slot_end = current + step
        # Check if slot overlaps with existing bookings
        overlap = any(
            b.start < slot_end and b.end > slot_start
            for b in existing_bookings
        )
        if not overlap:
            slots.append((slot_start, slot_end))
        current += step

    # 3️⃣ Filter by Policy (e.g., advance notice, future dates)
    try:
        policy = Policy.objects.filter(is_active=True).first()
        if policy:
            now = timezone.now()
            min_date = now + timedelta(days=policy.advance_notice_days)
            max_date = now + timedelta(days=policy.max_advance_booking_days)
            if date < min_date.date() or date > max_date.date():
                return []
    except Policy.DoesNotExist:
        pass

    return slots
