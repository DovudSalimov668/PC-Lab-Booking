# notifications/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone
from django.contrib import messages

from .models import Notification


@login_required
def all_notifications(request):
    """
    Render notifications page for the current user.
    """
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    notification_type = request.GET.get('type', 'all')
    
    # Base queryset
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role)
    ).order_by('-created_at')
    
    # Apply filters
    if status_filter == 'unread':
        qs = qs.filter(is_read=False)
    elif status_filter == 'read':
        qs = qs.filter(is_read=True)
    
    if notification_type != 'all':
        qs = qs.filter(notification_type=notification_type)
    
    # Get filter counts for UI
    total_count = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role)
    ).count()
    
    unread_count = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role),
        is_read=False
    ).count()
    
    read_count = total_count - unread_count
    
    context = {
        'notifications': qs,
        'total_count': total_count,
        'unread_count': unread_count,
        'read_count': read_count,
        'current_status_filter': status_filter,
        'current_type_filter': notification_type,
    }
    
    return render(request, 'notifications/all.html', context)


@login_required
@require_POST
def mark_read(request):
    """
    Mark a single notification as read.
    """
    notif_id = request.POST.get('id')
    if not notif_id:
        return JsonResponse({'success': False, 'error': 'Missing notification ID'}, status=400)

    try:
        notif = Notification.objects.get(pk=notif_id)
        
        # Check permission
        if notif.recipient_id == request.user.id or (notif.target_role and notif.target_role == request.user.role):
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save()
            return JsonResponse({'success': True, 'message': 'Notification marked as read.'})
        else:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)


@login_required
@require_POST
def mark_all_read(request):
    """
    Mark all notifications as read for the current user.
    """
    try:
        qs = Notification.objects.filter(
            Q(recipient=request.user) | Q(target_role=request.user.role),
            is_read=False
        )
        updated_count = qs.update(is_read=True, read_at=timezone.now())
        
        return JsonResponse({
            'success': True, 
            'updated': updated_count, 
            'message': f'{updated_count} notifications marked as read.'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def delete_notification(request):
    """
    Delete a single notification.
    """
    notif_id = request.POST.get('id')
    if not notif_id:
        return JsonResponse({'success': False, 'error': 'Missing notification ID'}, status=400)

    try:
        notif = Notification.objects.get(pk=notif_id)
        
        # Check permission
        if notif.recipient_id == request.user.id or request.user.is_superuser:
            notif.delete()
            return JsonResponse({'success': True, 'message': 'Notification deleted.'})
        else:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)


@login_required
def delete_all_read(request):
    """
    Delete all read notifications for the current user.
    """
    if request.method == 'POST':
        try:
            deleted_count = Notification.objects.filter(
                Q(recipient=request.user) | Q(target_role=request.user.role),
                is_read=True
            ).delete()[0]
            
            messages.success(request, f'Deleted {deleted_count} read notifications.')
            
        except Exception as e:
            messages.error(request, f'Error deleting notifications: {str(e)}')
    
    return redirect('notifications:all_notifications')