# notifications/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone
from .models import Notification


@login_required
def all_notifications(request):
    """
    Renders the full-page list of all notifications for the logged-in user.
    """
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role)
    ).order_by('-created_at')
    return render(request, 'notifications/all.html', {'notifications': qs})


@login_required
@require_POST
def mark_read(request):
    """
    Marks a single notification as read via AJAX (no redirect, JSON response).
    """
    notif_id = request.POST.get('id')
    if not notif_id:
        return HttpResponseBadRequest("Missing notification ID")

    notif = get_object_or_404(Notification, pk=notif_id)

    # Security: Only recipient or same-role users can mark it
    if notif.recipient == request.user or notif.target_role == request.user.role:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'updated_at'])
        return JsonResponse({"success": True, "message": "Notification marked as read."})
    return JsonResponse({"success": False, "error": "Permission denied."}, status=403)


@login_required
@require_POST
def mark_all_read(request):
    """
    Marks all notifications for the logged-in user as read (no redirect, JSON response).
    """
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role),
        is_read=False
    )
    count = qs.count()
    qs.update(is_read=True, updated_at=timezone.now())
    return JsonResponse({"success": True, "message": f"{count} notifications marked as read."})
