# bookings/services.py
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import Booking, RECURRENCE_FREQUENCY
import logging

logger = logging.getLogger(__name__)


class RecurringBookingService:
    """Service to handle recurring bookings"""
    
    @staticmethod
    def create_recurring_bookings(parent_booking, frequency, end_date):
        """
        Create recurring bookings based on parent booking
        
        Args:
            parent_booking: The original booking
            frequency: 'daily', 'weekly', 'biweekly', or 'monthly'
            end_date: When to stop creating recurring bookings
        
        Returns:
            List of created booking instances
        """
        created_bookings = []
        
        # Calculate interval
        if frequency == 'daily':
            delta = timedelta(days=1)
        elif frequency == 'weekly':
            delta = timedelta(weeks=1)
        elif frequency == 'biweekly':
            delta = timedelta(weeks=2)
        elif frequency == 'monthly':
            delta = timedelta(days=30)  # Approximate
        else:
            return []
        
        current_start = parent_booking.start + delta
        current_end = parent_booking.end + delta
        duration = parent_booking.end - parent_booking.start
        
        # Limit to prevent infinite loops
        max_instances = 52  # Max 1 year of weekly bookings
        instance_count = 0
        
        while current_start.date() <= end_date and instance_count < max_instances:
            # Check if this slot is available
            conflicts = Booking.objects.filter(
                lab=parent_booking.lab,
                start__lt=current_end,
                end__gt=current_start
            ).exclude(status__in=['cancelled', 'rejected'])
            
            if not conflicts.exists():
                try:
                    with transaction.atomic():
                        recurring_booking = Booking.objects.create(
                            requester=parent_booking.requester,
                            lab=parent_booking.lab,
                            start=current_start,
                            end=current_end,
                            purpose=parent_booking.purpose,
                            status='approved' if parent_booking.status == 'approved' else 'pending',
                            is_recurring=True,
                            recurrence_frequency=frequency,
                            parent_booking=parent_booking,
                            admin_notes=f"Part of recurring series starting {parent_booking.start.date()}"
                        )
                        created_bookings.append(recurring_booking)
                        logger.info(f"Created recurring booking #{recurring_booking.id}")
                except Exception as e:
                    logger.error(f"Failed to create recurring booking: {str(e)}")
            else:
                logger.warning(f"Skipped {current_start} - slot already booked")
            
            # Move to next occurrence
            current_start += delta
            current_end += delta
            instance_count += 1
        
        return created_bookings
    
    @staticmethod
    def cancel_recurring_series(parent_booking):
        """Cancel all future instances of a recurring series"""
        now = timezone.now()
        future_instances = Booking.objects.filter(
            parent_booking=parent_booking,
            start__gte=now
        ).exclude(status='cancelled')
        
        count = future_instances.update(status='cancelled')
        logger.info(f"Cancelled {count} future instances of booking #{parent_booking.id}")
        return count
    
    @staticmethod
    def update_recurring_series(parent_booking, update_future=True, **update_fields):
        """Update recurring series"""
        if not update_future:
            return 0
        
        now = timezone.now()
        future_instances = Booking.objects.filter(
            parent_booking=parent_booking,
            start__gte=now,
            status='pending'
        )
        
        count = future_instances.update(**update_fields)
        logger.info(f"Updated {count} future instances of booking #{parent_booking.id}")
        return count