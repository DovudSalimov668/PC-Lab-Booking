# notifications/admin.py
from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Admin interface for managing notifications.
    Only includes real model fields, no phantom ones.
    """
    list_display = ('id', 'recipient', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__email', 'recipient__username')
    readonly_fields = ('created_at', 'updated_at', 'sender')

    fieldsets = (
        (None, {
            'fields': ('recipient', 'sender', 'notification_type', 'title', 'message')
        }),
        ('Metadata', {
            'fields': ('is_read', 'action_url', 'created_at', 'updated_at')
        }),
    )

    ordering = ('-created_at',)
