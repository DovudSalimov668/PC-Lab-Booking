# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, EmailOTP


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    Admin configuration for the custom User model.
    Uses email for login and includes extra fields like 'role' and 'is_verified'.
    """

    # Display columns in admin list
    list_display = ("email", "username", "role", "is_verified", "is_active", "is_staff", "is_superuser")
    list_filter = ("role", "is_verified", "is_staff", "is_superuser")
    search_fields = ("email", "username")
    ordering = ("email",)

    # Fields to be read-only in admin
    readonly_fields = ("last_login", "date_joined")

    # Custom field groups in user detail view
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("username",)}),
        (_("Role and Verification"), {"fields": ("role", "is_verified")}),
        (_("Permissions"), {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # Fields to display when creating a new user manually
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "role", "password1", "password2"),
        }),
    )

    filter_horizontal = ("groups", "user_permissions",)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    """
    Admin configuration for OTPs used in email verification.
    These are read-only for safety and audit transparency.
    """
    list_display = ("user", "otp_code", "created_at", "expires_at")
    readonly_fields = ("otp_code", "created_at", "expires_at")
    search_fields = ("user__email", "otp_code")
    list_filter = ("created_at",)
    ordering = ("-created_at",)
