# bookings/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Booking
from notifications.services import NotificationService  # ✅ Import the correct service

@receiver(post_save, sender=Booking)
def booking_created(sender, instance, created, **kwargs):
    """
    Signal when a new booking is created
    """
    if created:
        print(f"🎯 Booking created signal triggered for booking #{instance.id}")
        NotificationService.notify_booking_created(instance)

@receiver(pre_save, sender=Booking)
def booking_status_updated(sender, instance, **kwargs):
    """
    Signal when booking status changes
    """
    if not instance.pk:
        return
    
    try:
        old_booking = Booking.objects.get(pk=instance.pk)
    except Booking.DoesNotExist:
        return
        
    # Check if status changed
    if old_booking.status != instance.status:
        print(f"🎯 Booking status changed from {old_booking.status} to {instance.status}")
        
        if instance.status == 'approved':
            NotificationService.notify_booking_approved(
                booking=instance, 
                approver=instance.approved_by
            )
        elif instance.status == 'rejected':
            NotificationService.notify_booking_rejected(
                booking=instance, 
                approver=instance.approved_by
            )
        elif instance.status == 'cancelled':
            # Determine who cancelled - could be requester or admin
            actor = instance.requester  # default to requester
            if hasattr(instance, 'cancelled_by') and instance.cancelled_by:
                actor = instance.cancelled_by
            NotificationService.notify_booking_cancelled(
                booking=instance,
                actor=actor
            )