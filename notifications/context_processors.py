from .models import Notification
from django.db.models import Q

def notifications_context(request):
    if not request.user.is_authenticated:
        return {}
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role)
    ).order_by('-created_at')
    unread_count = qs.filter(is_read=False).count()
    latest = qs[:10]
    return {
        'notifications': latest,
        'unread_notifications_count': unread_count,
    }
