# notifications/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone
from .models import Notification


@login_required
def all_notifications(request):
    """
    Display all notifications related to the logged-in user.
    - Normal users: see their own notifications.
    - Programme admins: see all system notifications.
    """

    user = request.user

    # Programme Admins or Managers can view all notifications
    if user.role in ["program_admin", "manager", "it_support", "lab_technician"]:
        notifications = Notification.objects.select_related("recipient").order_by("-created_at")
    else:
        # Students, Lecturers, etc. see only their own
        notifications = Notification.objects.filter(recipient=user).order_by("-created_at")

    # Count unread notifications for badge display
    unread_count = notifications.filter(is_read=False).count()

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
    }

    return render(request, "notifications/all.html", context)


@login_required
@require_POST
def mark_read(request):
    """
    Mark a specific notification as read via AJAX or form post.
    """
    notif_id = request.POST.get("id")

    # Ensure notification exists
    notif = get_object_or_404(Notification, pk=notif_id)

    # Only the recipient can mark it as read
    if notif.recipient == request.user:
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return JsonResponse({"success": True, "message": "Notification marked as read."})

    return JsonResponse({"success": False, "error": "Permission denied."})
