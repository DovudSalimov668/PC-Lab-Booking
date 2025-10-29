# notifications/views.py (FIXED)
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone

from .models import Notification
from .services import NotificationService


@login_required
def all_notifications(request):
    """
    Render notifications page for the current user.
    Shows notifications where recipient == user OR target_role == user's role.
    Latest notifications first.
    """
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role)
    ).order_by('-created_at')
    return render(request, 'notifications/all.html', {'notifications': qs})


@login_required
@require_POST
def mark_read(request):
    """
    Mark a single notification as read.
    Expects POST data: {'id': <notification_id>}
    Returns JSON (AJAX friendly) and DOES NOT redirect.
    """
    notif_id = request.POST.get('id') or request.POST.get('notification_id')
    if not notif_id:
        return JsonResponse({'success': False, 'error': 'Missing notification ID'}, status=400)

    notif = get_object_or_404(Notification, pk=notif_id)

    # permission: user must be explicit recipient OR user's role equals target_role
    if notif.recipient_id == request.user.id or (notif.target_role and notif.target_role == request.user.role):
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'read_at'])
        return JsonResponse({'success': True, 'message': 'Notification marked as read.'})
    return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)


@login_required
@require_POST
def mark_all_read(request):
    """
    Mark all visible notifications as read for the current user (no redirect).
    This will mark both notifications explicitly addressed to the user and those targeted by role.
    """
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role),
        is_read=False
    )
    updated = qs.update(is_read=True, read_at=timezone.now())
    return JsonResponse({'success': True, 'updated': updated, 'message': 'All notifications marked as read.'})


@login_required
@require_POST
def delete_notification(request):
    """
    (Optional) Delete a notification. Only owner or admin may delete.
    Expects POST data: {'id': <notification_id>}
    """
    notif_id = request.POST.get('id')
    if not notif_id:
        return JsonResponse({'success': False, 'error': 'Missing notification ID'}, status=400)
    notif = get_object_or_404(Notification, pk=notif_id)
    if notif.recipient_id == request.user.id or request.user.is_superuser:
        notif.delete()
        return JsonResponse({'success': True, 'message': 'Deleted.'})
    return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
