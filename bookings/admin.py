# bookings/admin.py
from django.contrib import admin
from .models import Booking, Policy, AuditLog


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Booking model.
    Displays key booking details, adds filtering, and search capabilities.
    """
    list_display = ("id", "requester", "lab",  "start", "end", "status")
    list_filter = ("status", "lab", "start")
    search_fields = ("requester__username", "requester__email", "purpose")
    date_hierarchy = "start"
    ordering = ("-start",)
    list_per_page = 25

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Booking Information", {
            "fields": ("lab",  "start", "end", "status")
        }),
        ("Requester", {
            "fields": ("requester", "purpose")
        }),
        ("Audit Data", {
            "fields": ("created_at", "updated_at")
        }),
    )


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    """
    Admin for Policy — defines lab booking rules and constraints.
    """
    list_display = ("name", "approval_required_for_students", "max_hours", "advance_notice_days")
    list_filter = ("approval_required_for_students",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin for AuditLog — tracks changes and actions on bookings.
    Read-only for security and compliance.
    """
    list_display = ("timestamp", "actor", "action", "entity", "details")
    readonly_fields = ("timestamp", "actor", "action", "entity", "details")
    search_fields = ("actor__username", "action", "entity")
    ordering = ("-timestamp",)
    list_per_page = 50
