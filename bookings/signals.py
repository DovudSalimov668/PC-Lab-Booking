from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Booking
from notifications.utils import create_notification

@receiver(post_save, sender=Booking)
def booking_created(sender, instance, created, **kwargs):
    if created:
        create_notification(
            actor=instance.requester,
            target_role='program_admin',
            verb='requested a booking',
            description=f'{instance.requester.username} requested booking #{instance.id} for {instance.lab.name}.',
            obj=instance
        )

@receiver(pre_save, sender=Booking)
def booking_status_updated(sender, instance, **kwargs):
    if not instance.pk:
        return
    old = Booking.objects.get(pk=instance.pk)
    if old.status != instance.status:
        create_notification(
            actor=instance.approved_by if hasattr(instance, 'approved_by') else None,
            recipient=instance.requester,
            verb=f'booking {instance.status}',
            description=f'Your booking #{instance.id} for {instance.lab.name} was {instance.status}.',
            obj=instance
        )
