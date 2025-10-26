# bookings/views.py
"""
Comprehensive views for the bookings app - FULLY FIXED VERSION

Key Fixes:
- Conflict checking only considers ACTIVE bookings (approved/pending)
- Permission functions check is_superuser first
- All admin actions work for superusers
- Proper status filtering everywhere
"""

import logging
import csv
from datetime import datetime, date, time as _time, timedelta
from typing import List, Tuple, Dict, Any, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncDate
from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages

# REST imports (if DRF installed)
try:
    from rest_framework import viewsets, permissions
    from rest_framework.decorators import action
    from rest_framework.response import Response
    DRF_AVAILABLE = True
except Exception:
    DRF_AVAILABLE = False

# Local imports
from .models import Booking
from .forms import BookingForm
from labs.models import Lab

# Optional imports with safe fallbacks
try:
    from notifications.services import NotificationService as ExternalNotificationService
    HAVE_EXTERNAL_NOTIFICATION = True
except Exception:
    ExternalNotificationService = None
    HAVE_EXTERNAL_NOTIFICATION = False

# Optional AuditLog, PolicyException, RecurringBookingService imports
try:
    from .models import AuditLog
except Exception:
    AuditLog = None

try:
    from .models import PolicyException
except Exception:
    PolicyException = None

try:
    from .services import RecurringBookingService
except Exception:
    RecurringBookingService = None

# Set up logger
logger = logging.getLogger(__name__)


# ----------------------------
# Helper utilities & fallbacks
# ----------------------------
def safe_get_username(user):
    """Return a human-readable username/email for user-like objects."""
    if not user:
        return "system"
    try:
        return getattr(user, "username", None) or getattr(user, "email", None) or str(user)
    except Exception:
        return str(user)


def booking_duration_hours(booking: Booking) -> float:
    """Calculate booking duration in hours safely."""
    try:
        delta = booking.end - booking.start
        return round(delta.total_seconds() / 3600.0, 2)
    except Exception:
        return 0.0


# Notification fallback service
class FallbackNotificationService:
    """Fallback notification service when external service not available."""

    def __init__(self):
        try:
            from notifications.models import Notification as NotificationModel
            self.NotificationModel = NotificationModel
        except Exception:
            self.NotificationModel = None

    def _send_email(self, subject: str, message: str, recipient_email: str):
        if not recipient_email:
            logger.warning("No recipient email provided for notification: %s", subject)
            return
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            logger.info("Sent notification email to %s: %s", recipient_email, subject)
        except Exception as exc:
            logger.exception("Failed to send notification email to %s: %s", recipient_email, exc)

    def create(self, recipient, title: str, message: str, link: Optional[str] = None, sender=None, extra=None):
        # Try to create DB object if model available
        if self.NotificationModel and hasattr(recipient, "id"):
            try:
                n = self.NotificationModel.objects.create(
                    recipient=recipient,
                    title=title[:255],
                    message=message,
                    link=link or "",
                    actor=sender if hasattr(sender, "pk") else None,
                )
                logger.info("Created DB notification id=%s for %s", getattr(n, "id", "?"), safe_get_username(recipient))
            except Exception as exc:
                logger.exception("Failed to create DB notification: %s", exc)

        # Send email too
        recipient_email = getattr(recipient, "email", None)
        subject = title
        body = message
        if link:
            body += "\n\nLink: " + link
        self._send_email(subject=subject, message=body, recipient_email=recipient_email)

    def notify_booking_created(self, booking: Booking, admins: Optional[List] = None):
        title = f"New booking request: {booking.lab.name if booking.lab else 'Lab'}"
        message = (
            f"{safe_get_username(booking.requester)} requested a booking for {booking.lab.name if booking.lab else 'N/A'}\n"
            f"Start: {booking.start}\nEnd: {booking.end}\nPurpose: {booking.purpose or '—'}\n"
            f"Booking ID: {booking.id}"
        )
        link = f"/bookings/{booking.id}/"

        if admins:
            for admin in admins:
                self.create(admin, title, message, link=link, sender=booking.requester)
        else:
            try:
                from users.models import User as UserModel
                managers = UserModel.objects.filter(role__in=["program_admin", "manager"])
                for m in managers:
                    self.create(m, title, message, link=link, sender=booking.requester)
            except Exception:
                logger.exception("Could not load managers to notify")


# Choose effective NotificationService
if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
    NotificationService = ExternalNotificationService
else:
    NotificationService = FallbackNotificationService()


# ----------------------------
# FIXED: Permission helpers - NOW CHECK is_superuser FIRST
# ----------------------------
def user_is_admin_role(user):
    """Return True if user is superuser or belongs to any admin-like role."""
    try:
        # CRITICAL: Check superuser first!
        if user.is_superuser:
            return True
        # ADD 'lecturer' to this list
        return hasattr(user, "role") and user.role in ["program_admin", "lab_technician", "it_support", "it_admin", "manager", "lecturer"]
    except Exception:
        return False


def user_can_approve(user):
    """Permission gate for approving bookings. Superuser or specific roles allowed."""
    try:
        # CRITICAL: Check superuser first!
        if user.is_superuser:
            return True
        # ADD 'lecturer' to this list
        return hasattr(user, "role") and user.role in ["program_admin", "manager", "lecturer"]
    except Exception:
        return False


# ----------------------------
# Helper: Check for ACTIVE booking conflicts
# ----------------------------
def has_booking_conflict(booking, exclude_self=True):
    """
    Check if booking conflicts with ACTIVE bookings only.
    CRITICAL: Only checks against approved/pending bookings.
    Excluded statuses: cancelled, rejected, completed
    """
    qs = Booking.objects.filter(
        lab=booking.lab,
        start__lt=booking.end,
        end__gt=booking.start,
        status__in=["approved", "pending"]  # ONLY active bookings!
    )
    
    if exclude_self and booking.pk:
        qs = qs.exclude(pk=booking.pk)
    
    return qs.exists()


# ----------------------------
# REST API (DRF) viewset
# ----------------------------
if DRF_AVAILABLE:
    class IsAuthenticatedOrReadOnlyPermission(permissions.BasePermission):
        def has_permission(self, request, view):
            return request.method in permissions.SAFE_METHODS or request.user and request.user.is_authenticated

    class BookingViewSet(viewsets.ModelViewSet):
        queryset = Booking.objects.all().order_by("-start")
        try:
            from .serializers import BookingSerializer
            serializer_class = BookingSerializer
        except Exception:
            serializer_class = None
            logger.warning("BookingSerializer not found")

        permission_classes = [IsAuthenticatedOrReadOnlyPermission]

        def perform_create(self, serializer):
            serializer.save(requester=self.request.user)

        @action(detail=False, methods=["get"])
        def availability(self, request):
            lab_id = request.query_params.get("lab_id")
            days = int(request.query_params.get("days") or 30)
            now = timezone.now()
            horizon = now + timedelta(days=days)

            # FIXED: Only check active bookings
            qs = Booking.objects.filter(status__in=["approved", "pending"])
            if lab_id:
                qs = qs.filter(lab_id=lab_id)
            qs = qs.filter(start__lt=horizon, end__gt=now)
            data = [{"start": b.start.isoformat(), "end": b.end.isoformat()} for b in qs]
            return Response(data)
else:
    BookingViewSet = None


# ----------------------------
# Template-based views
# ----------------------------

# General constants
SLOT_MINUTES = 30
DEFAULT_DURATION_OPTIONS = [30, 60, 90]
WORK_START_HOUR = 8
WORK_END_HOUR = 20


class BookingListView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = "bookings/booking_list.html"
    context_object_name = "bookings"
    paginate_by = 40

    def get_queryset(self):
        user = self.request.user
        qs = Booking.objects.select_related("lab", "requester", "approved_by").order_by("-start")
        
        # Superuser or admin roles see ALL bookings
        if user.is_superuser or user_is_admin_role(user):
            return qs
        
        # Regular users see only their own bookings
        return qs.filter(requester=user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        
        is_admin = user.is_superuser or user_is_admin_role(user)
        
        qs = self.get_queryset()
        ctx["total"] = qs.count()
        ctx["pending_count"] = qs.filter(status="pending").count()
        ctx["approved_count"] = qs.filter(status="approved").count()
        ctx["completed_count"] = qs.filter(status="completed").count()
        ctx["rejected_count"] = qs.filter(status="rejected").count()
        ctx["cancelled_count"] = qs.filter(status="cancelled").count()
        ctx["labs"] = Lab.objects.all()
        ctx["is_admin"] = is_admin
        
        if is_admin:
            from users.models import User
            ctx["total_users"] = User.objects.filter(is_active=True).count()
            ctx["total_requesters"] = Booking.objects.values('requester').distinct().count()
        
        return ctx


@login_required
def create_booking(request):
    """FIXED: Only checks conflicts with active bookings"""
    if request.method == "POST":
        form = BookingForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    booking = form.save(commit=False)
                    booking.requester = request.user
                    
                    # Auto-approve for admins
                    if user_is_admin_role(request.user) or request.user.is_superuser:
                        booking.status = "approved"
                        booking.approved_by = request.user
                    else:
                        booking.status = "pending"

                    # FIXED: Conflict check only against ACTIVE bookings
                    if has_booking_conflict(booking, exclude_self=False):
                        messages.error(request, "Selected time conflicts with another active booking. Please choose a different slot.")
                        return render(request, "bookings/booking_form.html", {"form": form})

                    booking.save()
                    
                    # Notify admins if pending
                    if booking.status == "pending":
                        try:
                            NotificationService.notify_booking_created(booking)
                        except Exception:
                            try:
                                fallback = FallbackNotificationService()
                                fallback.notify_booking_created(booking)
                            except Exception:
                                logger.exception("Failed to notify about booking creation")

                    messages.success(request, "Booking created successfully.")
                    return redirect("booking_list")
            except Exception as e:
                logger.exception("Error creating booking: %s", e)
                messages.error(request, f"Error creating booking: {str(e)}")
        else:
            messages.error(request, "Form validation failed. Check the fields and try again.")
    else:
        form = BookingForm(user=request.user)

    return render(request, "bookings/booking_form.html", {
        "form": form, 
        "labs": Lab.objects.all(), 
        "duration_options": DEFAULT_DURATION_OPTIONS
    })


class BookingDetailView(LoginRequiredMixin, DetailView):
    model = Booking
    template_name = "bookings/booking_detail.html"
    context_object_name = "booking"

    def post(self, request, *args, **kwargs):
        """Handle action forms submitted from detail page"""
        booking = self.get_object()
        action = request.POST.get("action")
        admin_notes = request.POST.get("admin_notes", "").strip()
        user = request.user

        if not action:
            messages.error(request, "No action specified")
            return redirect("booking_detail", pk=booking.pk)

        # Cancel - Allow both requester and admin
        if action == "cancel":
            if not (user == booking.requester or user.is_superuser or user_is_admin_role(user)):
                messages.error(request, "You don't have permission to cancel this booking")
                return redirect("booking_detail", pk=booking.pk)
            
            if booking.status in ["cancelled", "completed"]:
                messages.error(request, f"Cannot cancel booking with status {booking.status}")
                return redirect("booking_detail", pk=booking.pk)
            
            booking.status = "cancelled"
            booking.save(update_fields=["status"])
            
            # Notify about cancellation
            try:
                if user != booking.requester:
                    if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                        ExternalNotificationService.notify_booking_cancelled(booking, user)
                    else:
                        fallback = FallbackNotificationService()
                        fallback.create(
                            recipient=booking.requester,
                            title=f"Booking #{booking.id} cancelled",
                            message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was cancelled by {safe_get_username(user)}.",
                            link=f"/bookings/{booking.id}/",
                            sender=user
                        )
            except Exception:
                logger.exception("Error notifying booking cancellation")
            
            messages.success(request, "Booking cancelled successfully")
            return redirect("booking_list")

        # Approve - Admin only
        if action == "approve":
            if not user_can_approve(user):
                messages.error(request, "Permission denied")
                return redirect("booking_detail", pk=booking.pk)
            
            if booking.status != "pending":
                messages.error(request, "Only pending bookings can be approved")
                return redirect("booking_detail", pk=booking.pk)
            
            booking.status = "approved"
            booking.approved_by = user
            if admin_notes:
                booking.admin_notes = admin_notes
            booking.save(update_fields=["status", "approved_by", "admin_notes"])
            
            # Notify requester
            try:
                if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                    ExternalNotificationService.notify_booking_approved(booking, user)
                else:
                    fallback = FallbackNotificationService()
                    fallback.create(
                        recipient=booking.requester,
                        title=f"Booking #{booking.id} approved",
                        message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was approved.",
                        link=f"/bookings/{booking.id}/",
                        sender=user
                    )
            except Exception:
                logger.exception("Error notifying booking approval")
            
            messages.success(request, "Booking approved successfully")
            return redirect("booking_detail", pk=booking.pk)

        # Reject - Admin only
        if action == "reject":
            if not user_can_approve(user):
                messages.error(request, "Permission denied")
                return redirect("booking_detail", pk=booking.pk)
            
            if booking.status != "pending":
                messages.error(request, "Only pending bookings can be rejected")
                return redirect("booking_detail", pk=booking.pk)
            
            if not admin_notes:
                messages.error(request, "Reason for rejection is required")
                return redirect("booking_detail", pk=booking.pk)
            
            booking.status = "rejected"
            booking.approved_by = user
            booking.admin_notes = admin_notes
            booking.save(update_fields=["status", "approved_by", "admin_notes"])
            
            # Notify requester
            try:
                if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                    ExternalNotificationService.notify_booking_rejected(booking, user)
                else:
                    fallback = FallbackNotificationService()
                    fallback.create(
                        recipient=booking.requester,
                        title=f"Booking #{booking.id} rejected",
                        message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was rejected.\nReason: {admin_notes}",
                        link=f"/bookings/{booking.id}/",
                        sender=user
                    )
            except Exception:
                logger.exception("Error notifying booking rejection")
            
            messages.success(request, "Booking rejected")
            return redirect("booking_detail", pk=booking.pk)

        # Complete - Admin only
        if action == "complete":
            if not user_can_approve(user):
                messages.error(request, "Permission denied")
                return redirect("booking_detail", pk=booking.pk)
            
            if booking.status != "approved":
                messages.error(request, "Only approved bookings can be marked completed")
                return redirect("booking_detail", pk=booking.pk)
            
            booking.status = "completed"
            if admin_notes:
                booking.admin_notes = admin_notes
            booking.save(update_fields=["status", "admin_notes"])
            
            # Notify requester
            try:
                if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                    ExternalNotificationService.notify_booking_completed(booking, user)
                else:
                    fallback = FallbackNotificationService()
                    fallback.create(
                        recipient=booking.requester,
                        title=f"Booking #{booking.id} marked complete",
                        message=f"Booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} has been marked complete.",
                        link=f"/bookings/{booking.id}/",
                        sender=user
                    )
            except Exception:
                logger.exception("Error notifying booking completed")
            
            messages.success(request, "Booking marked as complete")
            return redirect("booking_detail", pk=booking.pk)

        messages.error(request, "Invalid action")
        return redirect("booking_detail", pk=booking.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking = self.get_object()
        ctx["duration_hours"] = booking_duration_hours(booking)
        ctx["can_edit"] = (self.request.user == booking.requester and booking.status == "pending") or self.request.user.is_superuser or user_is_admin_role(self.request.user)
        ctx["can_approve"] = user_can_approve(self.request.user)
        return ctx


class BookingUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Booking
    form_class = BookingForm
    template_name = "bookings/booking_form.html"
    success_url = reverse_lazy("booking_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def test_func(self):
        """Superuser or admin can edit ANY booking. Regular users can edit own pending bookings."""
        booking = self.get_object()
        user = self.request.user
        
        if user.is_superuser or user_is_admin_role(user):
            return True
        
        return user == booking.requester and booking.status == "pending"

    def form_valid(self, form):
        try:
            booking = form.save(commit=False)
            
            # FIXED: Conflict check only against ACTIVE bookings
            if has_booking_conflict(booking, exclude_self=True):
                form.add_error(None, "Time conflict detected with another active booking.")
                messages.error(self.request, "This time slot conflicts with another active booking.")
                return super().form_invalid(form)
            
            booking.save()
            messages.success(self.request, "Booking updated successfully.")
            
            # Log the update if AuditLog exists
            try:
                if AuditLog:
                    create_audit_log(
                        actor=self.request.user,
                        action="booking_updated",
                        entity=f"Booking #{booking.id}",
                        details=f"Updated booking for {booking.lab.name if booking.lab else 'N/A'}"
                    )
            except Exception:
                logger.exception("Failed to create audit log for booking update")
            
            return super().form_valid(form)
        except Exception as exc:
            logger.exception("Error updating booking: %s", exc)
            messages.error(self.request, "An error occurred updating the booking.")
            return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_edit"] = True
        ctx["booking"] = self.get_object()
        return ctx


class BookingDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Booking
    template_name = "bookings/booking_confirm_delete.html"
    success_url = reverse_lazy("booking_list")

    def test_func(self):
        """Superuser or admin can delete ANY booking. Regular users can delete own pending/approved."""
        booking = self.get_object()
        user = self.request.user
        
        if user.is_superuser or user_is_admin_role(user):
            return True
        
        return booking.requester == user and booking.status in ["pending", "approved"]

    def delete(self, request, *args, **kwargs):
        booking = self.get_object()
        
        try:
            with transaction.atomic():
                # Notify about deletion
                try:
                    if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                        ExternalNotificationService.notify_booking_cancelled(booking, request.user)
                    else:
                        fallback = FallbackNotificationService()
                        if request.user != booking.requester:
                            fallback.create(
                                recipient=booking.requester,
                                title=f"Your booking #{booking.id} has been deleted",
                                message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} has been deleted by {safe_get_username(request.user)}.",
                                link=f"/bookings/",
                                sender=request.user
                            )
                except Exception:
                    logger.exception("Failed to send deletion notification")
                
                # Log the deletion
                try:
                    if AuditLog:
                        create_audit_log(
                            actor=request.user,
                            action="booking_deleted",
                            entity=f"Booking #{booking.id}",
                            details=f"Deleted booking for {booking.lab.name if booking.lab else 'N/A'} on {booking.start}"
                        )
                except Exception:
                    logger.exception("Failed to create audit log for booking deletion")
                
                messages.success(request, f"Booking #{booking.id} has been deleted successfully.")
                return super().delete(request, *args, **kwargs)
                
        except Exception as exc:
            logger.exception("Error deleting booking: %s", exc)
            messages.error(request, "Failed to delete booking.")
            return redirect("booking_detail", pk=booking.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["booking"] = self.get_object()
        return ctx


@method_decorator(login_required, name="dispatch")
class BookingCreateWithCalendarView(LoginRequiredMixin, CreateView):
    model = Booking
    form_class = BookingForm
    template_name = "bookings/booking_create_with_calendar.html"
    success_url = reverse_lazy("booking_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["labs"] = Lab.objects.all()
        ctx["duration_options"] = DEFAULT_DURATION_OPTIONS
        ctx["work_start_hour"] = WORK_START_HOUR
        ctx["work_end_hour"] = WORK_END_HOUR
        ctx["slot_minutes"] = SLOT_MINUTES
        ctx["is_admin"] = user_is_admin_role(self.request.user) or self.request.user.is_superuser
        return ctx

    def form_valid(self, form):
        booking = form.save(commit=False)
        booking.requester = self.request.user
        
        if not (booking.start and booking.end):
            form.add_error(None, "Start and end times are required.")
            return self.form_invalid(form)
        
        # FIXED: Only check active bookings
        if has_booking_conflict(booking, exclude_self=False):
            form.add_error(None, "Selected time overlaps another active booking.")
            return self.form_invalid(form)
        
        # Auto-approve for admins
        if user_is_admin_role(self.request.user) or self.request.user.is_superuser:
            booking.status = "approved"
            booking.approved_by = self.request.user
        else:
            booking.status = "pending"

        booking.save()

        # Send notification
        try:
            if booking.status == "pending":
                NotificationService.notify_booking_created(booking)
        except Exception:
            logger.exception("Failed to call NotificationService for booking creation")

        messages.success(self.request, "Booking created successfully.")
        return super().form_valid(form)


@login_required
def booking_events(request):
    """Returns JSON array of events for FullCalendar - FIXED to exclude inactive bookings from display"""
    lab_id = request.GET.get("lab_id")
    campus = request.GET.get("campus")

    # FIXED: Exclude cancelled/rejected bookings from calendar
    qs = Booking.objects.filter(status__in=["approved", "pending", "completed"])
    if lab_id:
        qs = qs.filter(lab_id=lab_id)
    if campus:
        qs = qs.filter(lab__campus__iexact=campus)

    events = []
    for b in qs:
        color = {
            "pending": "#facc15",
            "approved": "#22c55e",
            "rejected": "#ef4444",
            "completed": "#3b82f6",
        }.get(b.status, "#6b7280")
        events.append({
            "id": b.id,
            "title": f"{b.lab.name if b.lab else 'Lab'} — {safe_get_username(b.requester)}",
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "color": color,
            "extendedProps": {
                "status": b.status,
                "lab": b.lab.name if b.lab else "N/A",
                "purpose": b.purpose or "",
                "requester": safe_get_username(b.requester)
            }
        })
    return JsonResponse(events, safe=False)


@login_required
def lab_bookings_json(request):
    """FIXED: Only return active bookings for calendar"""
    start = request.GET.get("start")
    end = request.GET.get("end")
    lab_id = request.GET.get("lab_id")
    campus = request.GET.get("campus")

    # FIXED: Only show active bookings
    qs = Booking.objects.filter(status__in=["approved", "pending"])
    if lab_id:
        qs = qs.filter(lab_id=lab_id)
    if campus:
        qs = qs.filter(lab__campus__iexact=campus)

    try:
        if start:
            start_dt = datetime.fromisoformat(start)
            qs = qs.filter(end__gt=start_dt)
        if end:
            end_dt = datetime.fromisoformat(end)
            qs = qs.filter(start__lt=end_dt)
    except Exception:
        pass

    events = []
    for b in qs:
        color = {
            "pending": "#facc15",
            "approved": "#22c55e",
        }.get(b.status, "#6b7280")
        events.append({
            "id": b.id,
            "title": f"{b.lab.name if b.lab else 'Lab'} ({b.status})",
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "color": color,
            "extendedProps": {
                "status": b.status,
                "lab": b.lab.name if b.lab else "N/A",
                "purpose": b.purpose or ""
            }
        })
    return JsonResponse(events, safe=False)


@login_required
def availability_for_date(request):
    """
    FIXED: Returns availability checking only ACTIVE bookings (approved/pending)
    """
    lab_id = request.GET.get("lab_id")
    date_str = request.GET.get("date")
    duration = int(request.GET.get("duration") or SLOT_MINUTES)
    
    if not lab_id or not date_str:
        return HttpResponseBadRequest("lab_id and date are required")

    try:
        lab = Lab.objects.get(pk=lab_id)
    except Lab.DoesNotExist:
        return HttpResponseBadRequest("Invalid lab_id")

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponseBadRequest("Invalid date format (expected YYYY-MM-DD)")

    tz = timezone.get_default_timezone()
    start_of_day = timezone.make_aware(datetime.combine(date_obj, _time(hour=WORK_START_HOUR)), tz)
    end_of_day = timezone.make_aware(datetime.combine(date_obj, _time(hour=WORK_END_HOUR)), tz)

    # FIXED: Only check ACTIVE bookings
    booked_qs = Booking.objects.filter(
        lab=lab,
        start__lt=end_of_day,
        end__gt=start_of_day,
        status__in=["approved", "pending"]
    ).order_by("start")

    booked_intervals = [{"start": b.start.isoformat(), "end": b.end.isoformat()} for b in booked_qs]

    # Build slot slices
    slots: List[Tuple[datetime, datetime]] = []
    cur = start_of_day
    step = timedelta(minutes=SLOT_MINUTES)
    while cur + step <= end_of_day:
        slots.append((cur, cur + step))
        cur += step

    free_indices = []
    for i, (s_start, s_end) in enumerate(slots):
        overlap = booked_qs.filter(start__lt=s_end, end__gt=s_start).exists()
        if not overlap:
            free_indices.append(i)

    slots_needed = max(1, duration // SLOT_MINUTES)
    available_slots = []
    for i in range(len(slots) - slots_needed + 1):
        window = range(i, i + slots_needed)
        if all(idx in free_indices for idx in window):
            slot_start = slots[i][0]
            slot_end = slots[i + slots_needed - 1][1]
            available_slots.append({"start": slot_start.strftime("%H:%M"), "end": slot_end.strftime("%H:%M")})

    return JsonResponse({"booked": booked_intervals, "available_slots": available_slots})


# ----------------------------
# Admin actions: approve / reject / cancel / complete
# ----------------------------
@login_required
@require_POST
def booking_status_action(request):
    """
    FIXED: All permission checks include is_superuser
    """
    booking_id = request.POST.get("booking_id")
    action = request.POST.get("action")
    admin_notes = request.POST.get("admin_notes", "").strip()

    if not booking_id or not action:
        return JsonResponse({"error": "booking_id and action are required"}, status=400)

    booking = get_object_or_404(Booking, pk=booking_id)
    user = request.user

    # Approve
    if action == "approve":
        if not user_can_approve(user):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status != "pending":
            return JsonResponse({"error": "only pending bookings can be approved"}, status=400)
        
        booking.status = "approved"
        booking.approved_by = user
        if admin_notes:
            booking.admin_notes = admin_notes
        booking.save(update_fields=["status", "approved_by", "admin_notes"])
        
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_approved(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} approved",
                    message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was approved.",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking approval")
        
        return JsonResponse({"ok": True, "id": booking.id})

    # Reject
    if action == "reject":
        if not user_can_approve(user):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status != "pending":
            return JsonResponse({"error": "only pending bookings can be rejected"}, status=400)
        if not admin_notes:
            return JsonResponse({"error": "admin_notes required for rejection"}, status=400)
        
        booking.status = "rejected"
        booking.approved_by = user
        booking.admin_notes = admin_notes
        booking.save(update_fields=["status", "approved_by", "admin_notes"])
        
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_rejected(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} rejected",
                    message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was rejected.\nReason: {admin_notes}",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking rejection")
        
        return JsonResponse({"ok": True, "id": booking.id})

    # Cancel
    if action == "cancel":
        if not (user == booking.requester or user.is_superuser or user_is_admin_role(user)):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status in ["cancelled", "completed"]:
            return JsonResponse({"error": f"cannot cancel booking with status {booking.status}"}, status=400)
        
        booking.status = "cancelled"
        booking.save(update_fields=["status"])
        
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_cancelled(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} cancelled",
                    message=f"Booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was cancelled.",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking cancelled")
        
        return JsonResponse({"ok": True, "id": booking.id})

    # Complete
    if action == "complete":
        if not user_can_approve(user):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status != "approved":
            return JsonResponse({"error": "only approved bookings can be marked completed"}, status=400)
        
        booking.status = "completed"
        if admin_notes:
            booking.admin_notes = admin_notes
        booking.save(update_fields=["status", "admin_notes"])
        
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_completed(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} marked complete",
                    message=f"Booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} has been marked complete by {safe_get_username(user)}.",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking completed")
        
        return JsonResponse({"ok": True, "id": booking.id})

    return JsonResponse({"error": "invalid action"}, status=400)


@login_required
def pending_bookings_for_lab(request):
    """Return pending bookings for a lab (admin view)"""
    if not (request.user.is_superuser or user_is_admin_role(request.user)):
        return HttpResponseForbidden("Forbidden")

    lab_id = request.GET.get("lab_id")
    if not lab_id:
        return HttpResponseBadRequest("lab_id required")
    
    try:
        lab = Lab.objects.get(pk=lab_id)
    except Lab.DoesNotExist:
        return HttpResponseBadRequest("Invalid lab_id")

    qs = Booking.objects.filter(lab=lab, status="pending").order_by("start")
    out = []
    for b in qs:
        out.append({
            "id": b.id,
            "requester": safe_get_username(b.requester),
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "purpose": b.purpose or "",
        })
    return JsonResponse(out, safe=False)


@login_required
@require_POST
def bulk_booking_action(request):
    """FIXED: Permission check includes superuser"""
    if not (request.user.is_superuser or user_can_approve(request.user)):
        return JsonResponse({"error": "permission denied"}, status=403)

    booking_ids = request.POST.getlist("booking_ids[]")
    action = request.POST.get("action")
    notes = request.POST.get("notes", "")

    if not booking_ids or not action:
        return JsonResponse({"error": "booking_ids and action required"}, status=400)

    try:
        with transaction.atomic():
            bookings = Booking.objects.filter(pk__in=booking_ids)
            
            if action == "approve":
                count = 0
                for b in bookings:
                    if b.status == "pending":
                        b.status = "approved"
                        b.approved_by = request.user
                        b.save(update_fields=["status", "approved_by"])
                        count += 1
                        try:
                            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                                ExternalNotificationService.notify_booking_approved(b, request.user)
                            else:
                                fallback = FallbackNotificationService()
                                fallback.create(
                                    recipient=b.requester,
                                    title=f"Your booking #{b.id} was approved",
                                    message=f"Booking for {b.lab.name if b.lab else 'lab'} on {b.start} was approved.",
                                    link=f"/bookings/{b.id}/",
                                    sender=request.user
                                )
                        except Exception:
                            logger.exception("Error notifying bulk approval for booking %s", b.id)
                return JsonResponse({"success": True, "action": "approve", "count": count})

            if action == "reject":
                if not notes:
                    return JsonResponse({"error": "notes required for rejection"}, status=400)
                count = 0
                for b in bookings:
                    if b.status == "pending":
                        b.status = "rejected"
                        b.approved_by = request.user
                        b.admin_notes = notes
                        b.save(update_fields=["status", "approved_by", "admin_notes"])
                        count += 1
                        try:
                            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                                ExternalNotificationService.notify_booking_rejected(b, request.user)
                            else:
                                fallback = FallbackNotificationService()
                                fallback.create(
                                    recipient=b.requester,
                                    title=f"Your booking #{b.id} was rejected",
                                    message=f"Booking for {b.lab.name if b.lab else 'lab'} on {b.start} was rejected.\nReason: {notes}",
                                    link=f"/bookings/{b.id}/",
                                    sender=request.user
                                )
                        except Exception:
                            logger.exception("Error notifying bulk rejection for booking %s", b.id)
                return JsonResponse({"success": True, "action": "reject", "count": count})

            if action == "delete":
                count = bookings.count()
                bookings.delete()
                return JsonResponse({"success": True, "action": "delete", "count": count})

            return JsonResponse({"error": "invalid action"}, status=400)
    except Exception as exc:
        logger.exception("bulk_booking_action error: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
def export_bookings_csv(request):
    """FIXED: Permission check includes superuser"""
    if not (request.user.is_superuser or user_is_admin_role(request.user)):
        return HttpResponseForbidden("You don't have permission to export data")

    days_back = int(request.GET.get("days", 30))
    start_date = timezone.now() - timedelta(days=days_back)

    bookings = Booking.objects.filter(created_at__gte=start_date).select_related("requester", "lab", "approved_by").order_by("-start")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bookings_export.csv"'
    writer = csv.writer(response)
    writer.writerow(["ID", "Requester", "Role", "Lab", "Start", "End", "Duration (hours)", "Status", "Purpose", "Created At", "Approved By"])
    for b in bookings:
        writer.writerow([
            b.id,
            safe_get_username(b.requester),
            getattr(b.requester, "role", ""),
            b.lab.name if b.lab else "N/A",
            b.start.strftime("%Y-%m-%d %H:%M"),
            b.end.strftime("%Y-%m-%d %H:%M"),
            booking_duration_hours(b),
            b.status,
            b.purpose or "",
            b.created_at.strftime("%Y-%m-%d %H:%M"),
            safe_get_username(b.approved_by) if getattr(b, "approved_by", None) else "N/A",
        ])
    return response


class UtilizationDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "bookings/utilization_dashboard.html"

    def test_func(self):
        return self.request.user.is_superuser or user_is_admin_role(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        days_back = int(self.request.GET.get("days", 30))
        start_date = timezone.now() - timedelta(days=days_back)

        total_bookings = Booking.objects.filter(created_at__gte=start_date).count()
        approved_bookings = Booking.objects.filter(created_at__gte=start_date, status="approved").count()
        pending_bookings = Booking.objects.filter(status="pending").count()

        labs = Lab.objects.all()
        lab_stats = []
        for lab in labs:
            bookings = Booking.objects.filter(lab=lab, start__gte=start_date, status__in=["approved", "completed"])
            total_seconds = 0.0
            for b in bookings:
                try:
                    total_seconds += (b.end - b.start).total_seconds()
                except Exception:
                    pass
            total_hours = round(total_seconds / 3600.0, 2)
            booking_count = bookings.count()
            available_hours = (WORK_END_HOUR - WORK_START_HOUR) * days_back
            utilization = round((total_hours / available_hours * 100) if available_hours > 0 else 0.0, 1)
            lab_stats.append({"lab": lab, "booking_count": booking_count, "total_hours": total_hours, "utilization": utilization})

        bookings_by_day = Booking.objects.filter(start__gte=start_date).annotate(date=TruncDate("start")).values("date").annotate(count=Count("id")).order_by("date")
        status_stats = Booking.objects.filter(created_at__gte=start_date).values("status").annotate(count=Count("id")).order_by("-count")
        peak_hours = Booking.objects.filter(start__gte=start_date, status__in=["approved", "completed"]).extra(select={"hour": "EXTRACT(hour FROM start)"}).values("hour").annotate(count=Count("id")).order_by("-count")[:10]
        avg_duration = Booking.objects.filter(created_at__gte=start_date).aggregate(avg_minutes=Avg("duration_minutes" if hasattr(Booking, "duration_minutes") else None))

        ctx.update({
            "total_bookings": total_bookings,
            "approved_bookings": approved_bookings,
            "pending_bookings": pending_bookings,
            "lab_stats": lab_stats,
            "bookings_by_day": list(bookings_by_day),
            "status_stats": list(status_stats),
            "peak_hours": list(peak_hours),
            "avg_duration": avg_duration.get("avg_minutes") if isinstance(avg_duration, dict) else None,
            "days_back": days_back,
        })
        return ctx


class MyBookingsView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = "bookings/my_bookings.html"
    context_object_name = "bookings"
    paginate_by = 30

    def get_queryset(self):
        user = self.request.user
        f = self.request.GET.get("filter", "all")
        qs = Booking.objects.filter(requester=user).select_related("lab", "approved_by").order_by("-start")
        if f == "upcoming":
            qs = qs.filter(start__gte=timezone.now(), status="approved")
        elif f == "past":
            qs = qs.filter(end__lt=timezone.now())
        elif f == "pending":
            qs = qs.filter(status="pending")
        elif f == "recurring":
            qs = qs.filter(is_recurring=True) if hasattr(Booking, "is_recurring") else qs.none()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["total_bookings"] = Booking.objects.filter(requester=user).count()
        ctx["upcoming_bookings"] = Booking.objects.filter(requester=user, start__gte=timezone.now(), status="approved").count()
        ctx["pending_bookings"] = Booking.objects.filter(requester=user, status="pending").count()
        return ctx


@login_required
def lab_month_availability(request):
    """FIXED: Only check active bookings for availability"""
    lab_id = request.GET.get("lab_id")
    year = int(request.GET.get("year") or timezone.now().year)
    month = int(request.GET.get("month") or timezone.now().month)
    
    if not lab_id:
        return HttpResponseBadRequest("lab_id required")
    
    try:
        lab = Lab.objects.get(pk=lab_id)
    except Lab.DoesNotExist:
        return HttpResponseBadRequest("Invalid lab_id")

    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    out = {}
    day = first_day
    while day <= last_day:
        start_of_day = timezone.make_aware(datetime.combine(day, _time(hour=WORK_START_HOUR)), timezone.get_default_timezone())
        end_of_day = timezone.make_aware(datetime.combine(day, _time(hour=WORK_END_HOUR)), timezone.get_default_timezone())
        
        # FIXED: Only check active bookings
        booked_qs = Booking.objects.filter(
            lab=lab, 
            start__lt=end_of_day, 
            end__gt=start_of_day, 
            status__in=["approved", "pending"]
        )
        
        total_slots = int(((WORK_END_HOUR - WORK_START_HOUR) * 60) // SLOT_MINUTES)
        slots_free = 0
        cur = start_of_day
        step = timedelta(minutes=SLOT_MINUTES)
        while cur + step <= end_of_day:
            if not booked_qs.filter(start__lt=cur + step, end__gt=cur).exists():
                slots_free += 1
            cur += step
        out[day.isoformat()] = {"free_slots": slots_free, "total_slots": total_slots, "booked_count": booked_qs.count()}
        day = day + timedelta(days=1)
    
    return JsonResponse({"days": out})


class LabCalendarView(LoginRequiredMixin, TemplateView):
    template_name = "bookings/lab_calendar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["labs"] = Lab.objects.all()
        ctx["campuses"] = Lab.objects.values_list("campus", flat=True).distinct()
        ctx["default_view"] = "dayGridMonth"
        return ctx


class PendingApprovalsView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Booking
    template_name = "bookings/pending_approvals.html"
    context_object_name = "bookings"
    paginate_by = 40

    def test_func(self):
        return self.request.user.is_superuser or user_can_approve(self.request.user)

    def get_queryset(self):
        qs = Booking.objects.filter(status="pending").select_related("lab", "requester").order_by("start")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["pending_count"] = self.get_queryset().count()
        return ctx


@login_required
def get_lab_list_json(request):
    """Return a simple JSON list of labs for UI dropdowns."""
    labs = Lab.objects.all().values("id", "name", "campus")
    return JsonResponse(list(labs), safe=False)


def create_audit_log(actor, action, entity, details="", ip_address=None):
    """Create an AuditLog entry if AuditLog model is present."""
    if AuditLog is None:
        logger.debug("AuditLog model not defined; skipping audit log for action %s", action)
        return None
    try:
        return AuditLog.objects.create(actor=actor, action=action, entity=entity, details=details[:2000], ip_address=ip_address)
    except Exception:
        logger.exception("Failed to create AuditLog entry")
        return None

# JSON endpoint for bookings filtered by calendar date range (FullCalendar calls with start/end)
@login_required
def lab_bookings_json(request):
    """
    FullCalendar recommended endpoint returning events between 'start' and 'end' (query params).
    If missing, returns active bookings.
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    lab_id = request.GET.get("lab_id")
    campus = request.GET.get("campus")

    qs = Booking.objects.exclude(status__in=["cancelled", "rejected"])
    if lab_id:
        qs = qs.filter(lab_id=lab_id)
    if campus:
        qs = qs.filter(lab__campus__iexact=campus)

    # Filter by start/end if provided
    try:
        if start:
            start_dt = datetime.fromisoformat(start)
            qs = qs.filter(end__gt=start_dt)
        if end:
            end_dt = datetime.fromisoformat(end)
            qs = qs.filter(start__lt=end_dt)
    except Exception:
        # ignore parse errors
        pass

    events = []
    for b in qs:
        color = {
            "pending": "#facc15",
            "approved": "#22c55e",
            "rejected": "#ef4444",
            "completed": "#3b82f6",
        }.get(b.status, "#6b7280")
        events.append({
            "id": b.id,
            "title": f"{b.lab.name if b.lab else 'Lab'} ({b.status})",
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "color": color,
            "extendedProps": {
                "status": b.status,
                "lab": b.lab.name if b.lab else "N/A",
                "purpose": b.purpose or ""
            }
        })
    return JsonResponse(events, safe=False)


# Availability checker for a specific date & lab
@login_required
def availability_for_date(request):
    """
    Returns JSON with 'booked' intervals and 'available_slots' for a given lab and date.
    Query params:
      - lab_id (required)
      - date YYYY-MM-DD (required)
      - duration in minutes (optional)
    Response:
      { "booked": [{"start":"ISO", "end":"ISO"}...], "available_slots": [{"start":"HH:MM","end":"HH:MM"}, ...] }
    """
    lab_id = request.GET.get("lab_id")
    date_str = request.GET.get("date")
    duration = int(request.GET.get("duration") or SLOT_MINUTES)
    if not lab_id or not date_str:
        return HttpResponseBadRequest("lab_id and date are required")

    try:
        lab = Lab.objects.get(pk=lab_id)
    except Lab.DoesNotExist:
        return HttpResponseBadRequest("Invalid lab_id")

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponseBadRequest("Invalid date format (expected YYYY-MM-DD)")

    tz = timezone.get_default_timezone()
    start_of_day = timezone.make_aware(datetime.combine(date_obj, _time(hour=WORK_START_HOUR)), tz)
    end_of_day = timezone.make_aware(datetime.combine(date_obj, _time(hour=WORK_END_HOUR)), tz)

    booked_qs = Booking.objects.filter(
        lab=lab,
        start__lt=end_of_day,
        end__gt=start_of_day,
        status__in=["approved", "pending"]
    ).order_by("start")

    booked_intervals = [{"start": b.start.isoformat(), "end": b.end.isoformat()} for b in booked_qs]

    # Build slot slices
    slots: List[Tuple[datetime, datetime]] = []
    cur = start_of_day
    step = timedelta(minutes=SLOT_MINUTES)
    while cur + step <= end_of_day:
        slots.append((cur, cur + step))
        cur += step

    free_indices = []
    for i, (s_start, s_end) in enumerate(slots):
        # If any booked overlaps this slot, mark as occupied
        overlap = booked_qs.filter(start__lt=s_end, end__gt=s_start).exists()
        if not overlap:
            free_indices.append(i)

    slots_needed = max(1, duration // SLOT_MINUTES)
    available_slots = []
    for i in range(len(slots) - slots_needed + 1):
        window = range(i, i + slots_needed)
        if all(idx in free_indices for idx in window):
            slot_start = slots[i][0]
            slot_end = slots[i + slots_needed - 1][1]
            available_slots.append({"start": slot_start.strftime("%H:%M"), "end": slot_end.strftime("%H:%M")})

    return JsonResponse({"booked": booked_intervals, "available_slots": available_slots})


# ----------------------------
# Admin actions: approve / reject / cancel / complete
# ----------------------------
@login_required
@require_POST
def booking_status_action(request):
    """
    Generic action endpoint for approve/reject/cancel/complete.
    POST params:
      - booking_id
      - action (approve|reject|cancel|complete)
      - admin_notes optional
    Returns JSON {ok: True, id: booking_id} or appropriate error
    """
    booking_id = request.POST.get("booking_id")
    action = request.POST.get("action")
    admin_notes = request.POST.get("admin_notes", "").strip()

    if not booking_id or not action:
        return JsonResponse({"error": "booking_id and action are required"}, status=400)

    booking = get_object_or_404(Booking, pk=booking_id)
    user = request.user

    # Approve
    if action == "approve":
        if not user_can_approve(user):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status != "pending":
            return JsonResponse({"error": "only pending bookings can be approved"}, status=400)
        booking.status = "approved"
        booking.approved_by = user
        if admin_notes:
            booking.admin_notes = admin_notes
        booking.save(update_fields=["status", "approved_by", "admin_notes"])
        # Notify requester
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_approved(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} approved",
                    message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was approved.",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking approval")
        return JsonResponse({"ok": True, "id": booking.id})

    # Reject
    if action == "reject":
        if not user_can_approve(user):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status != "pending":
            return JsonResponse({"error": "only pending bookings can be rejected"}, status=400)
        if not admin_notes:
            return JsonResponse({"error": "admin_notes required for rejection"}, status=400)
        booking.status = "rejected"
        booking.approved_by = user
        booking.admin_notes = admin_notes
        booking.save(update_fields=["status", "approved_by", "admin_notes"])
        # Notify requester
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_rejected(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} rejected",
                    message=f"Your booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was rejected.\nReason: {admin_notes}",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking rejection")
        return JsonResponse({"ok": True, "id": booking.id})

    # Cancel
    if action == "cancel":
        # requester or admin can cancel
        if not (user == booking.requester or user_is_admin_role(user)):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status in ["cancelled", "completed"]:
            return JsonResponse({"error": f"cannot cancel booking with status {booking.status}"}, status=400)
        booking.status = "cancelled"
        booking.save(update_fields=["status"])
        # Notify requester (if not the one who canceled)
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_cancelled(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} cancelled",
                    message=f"Booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} was cancelled.",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking cancelled")
        return JsonResponse({"ok": True, "id": booking.id})

    # Complete
    if action == "complete":
        if not user_can_approve(user):
            return JsonResponse({"error": "permission denied"}, status=403)
        if booking.status != "approved":
            return JsonResponse({"error": "only approved bookings can be marked completed"}, status=400)
        booking.status = "completed"
        if admin_notes:
            booking.admin_notes = admin_notes
        booking.save(update_fields=["status", "admin_notes"])
        # Notify requester
        try:
            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                ExternalNotificationService.notify_booking_completed(booking, user)
            else:
                fallback = FallbackNotificationService()
                fallback.create(
                    recipient=booking.requester,
                    title=f"Booking #{booking.id} marked complete",
                    message=f"Booking for {booking.lab.name if booking.lab else 'lab'} on {booking.start} has been marked complete by {safe_get_username(user)}.",
                    link=f"/bookings/{booking.id}/",
                    sender=user
                )
        except Exception:
            logger.exception("Error notifying booking completed")
        return JsonResponse({"ok": True, "id": booking.id})

    return JsonResponse({"error": "invalid action"}, status=400)


# ----------------------------
# Pending bookings for a lab (admin)
# ----------------------------
@login_required
def pending_bookings_for_lab(request):
    """
    Return pending bookings for a lab (admin view).
    Query param: lab_id
    """
    if not user_is_admin_role(request.user):
        return HttpResponseForbidden("Forbidden")

    lab_id = request.GET.get("lab_id")
    if not lab_id:
        return HttpResponseBadRequest("lab_id required")
    try:
        lab = Lab.objects.get(pk=lab_id)
    except Lab.DoesNotExist:
        return HttpResponseBadRequest("Invalid lab_id")

    qs = Booking.objects.filter(lab=lab, status="pending").order_by("start")
    out = []
    for b in qs:
        out.append({
            "id": b.id,
            "requester": safe_get_username(b.requester),
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "purpose": b.purpose or "",
        })
    return JsonResponse(out, safe=False)


# ----------------------------
# Bulk admin actions (approve/reject/delete)
# ----------------------------
@login_required
@require_POST
def bulk_booking_action(request):
    """
    Accepts POST:
      - booking_ids[] multiple values
      - action ('approve'|'reject'|'delete')
      - notes optional
    Returns JSON success/failure.
    """
    if not user_can_approve(request.user):
        return JsonResponse({"error": "permission denied"}, status=403)

    booking_ids = request.POST.getlist("booking_ids[]")
    action = request.POST.get("action")
    notes = request.POST.get("notes", "")

    if not booking_ids or not action:
        return JsonResponse({"error": "booking_ids and action required"}, status=400)

    try:
        with transaction.atomic():
            bookings = Booking.objects.filter(pk__in=booking_ids)
            if action == "approve":
                count = 0
                for b in bookings:
                    if b.status == "pending":
                        b.status = "approved"
                        b.approved_by = request.user
                        b.save(update_fields=["status", "approved_by"])
                        count += 1
                        # notify
                        try:
                            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                                ExternalNotificationService.notify_booking_approved(b, request.user)
                            else:
                                fallback = FallbackNotificationService()
                                fallback.create(
                                    recipient=b.requester,
                                    title=f"Your booking #{b.id} was approved",
                                    message=f"Booking for {b.lab.name if b.lab else 'lab'} on {b.start} was approved.",
                                    link=f"/bookings/{b.id}/",
                                    sender=request.user
                                )
                        except Exception:
                            logger.exception("Error notifying bulk approval for booking %s", b.id)
                return JsonResponse({"success": True, "action": "approve", "count": count})

            if action == "reject":
                if not notes:
                    return JsonResponse({"error": "notes required for rejection"}, status=400)
                count = 0
                for b in bookings:
                    if b.status == "pending":
                        b.status = "rejected"
                        b.approved_by = request.user
                        b.admin_notes = notes
                        b.save(update_fields=["status", "approved_by", "admin_notes"])
                        count += 1
                        # notify
                        try:
                            if HAVE_EXTERNAL_NOTIFICATION and ExternalNotificationService:
                                ExternalNotificationService.notify_booking_rejected(b, request.user)
                            else:
                                fallback = FallbackNotificationService()
                                fallback.create(
                                    recipient=b.requester,
                                    title=f"Your booking #{b.id} was rejected",
                                    message=f"Booking for {b.lab.name if b.lab else 'lab'} on {b.start} was rejected.\nReason: {notes}",
                                    link=f"/bookings/{b.id}/",
                                    sender=request.user
                                )
                        except Exception:
                            logger.exception("Error notifying bulk rejection for booking %s", b.id)
                return JsonResponse({"success": True, "action": "reject", "count": count})

            if action == "delete":
                # only allow deletion by admins
                count = bookings.count()
                bookings.delete()
                return JsonResponse({"success": True, "action": "delete", "count": count})

            return JsonResponse({"error": "invalid action"}, status=400)
    except Exception as exc:
        logger.exception("bulk_booking_action error: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


# ----------------------------
# Export bookings to CSV (admins)
# ----------------------------
@login_required
def export_bookings_csv(request):
    if not user_is_admin_role(request.user):
        return HttpResponseForbidden("You don't have permission to export data")

    days_back = int(request.GET.get("days", 30))
    start_date = timezone.now() - timedelta(days=days_back)

    bookings = Booking.objects.filter(created_at__gte=start_date).select_related("requester", "lab", "approved_by").order_by("-start")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bookings_export.csv"'
    writer = csv.writer(response)
    writer.writerow(["ID", "Requester", "Role", "Lab", "Start", "End", "Duration (hours)", "Status", "Purpose", "Created At", "Approved By"])
    for b in bookings:
        writer.writerow([
            b.id,
            safe_get_username(b.requester),
            getattr(b.requester, "role", ""),
            b.lab.name if b.lab else "N/A",
            b.start.strftime("%Y-%m-%d %H:%M"),
            b.end.strftime("%Y-%m-%d %H:%M"),
            booking_duration_hours(b),
            b.status,
            b.purpose or "",
            b.created_at.strftime("%Y-%m-%d %H:%M"),
            safe_get_username(b.approved_by) if getattr(b, "approved_by", None) else "N/A",
        ])
    return response


# ----------------------------
# Utilization dashboard
# ----------------------------
class UtilizationDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "bookings/utilization_dashboard.html"

    def test_func(self):
        # allow program admins / managers / superusers
        try:
            user = self.request.user
            return user_is_admin_role(user) or user.is_superuser
        except Exception:
            return False

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        days_back = int(self.request.GET.get("days", 30))
        start_date = timezone.now() - timedelta(days=days_back)

        total_bookings = Booking.objects.filter(created_at__gte=start_date).count()
        approved_bookings = Booking.objects.filter(created_at__gte=start_date, status="approved").count()
        pending_bookings = Booking.objects.filter(status="pending").count()

        # Lab utilization
        labs = Lab.objects.all()
        lab_stats = []
        for lab in labs:
            bookings = Booking.objects.filter(lab=lab, start__gte=start_date, status__in=["approved", "completed"])
            # compute total booked hours
            total_seconds = 0.0
            for b in bookings:
                try:
                    total_seconds += (b.end - b.start).total_seconds()
                except Exception:
                    pass
            total_hours = round(total_seconds / 3600.0, 2)
            booking_count = bookings.count()
            available_hours = (WORK_END_HOUR - WORK_START_HOUR) * days_back  # approximate
            utilization = round((total_hours / available_hours * 100) if available_hours > 0 else 0.0, 1)
            lab_stats.append({"lab": lab, "booking_count": booking_count, "total_hours": total_hours, "utilization": utilization})

        # bookings by day
        bookings_by_day = Booking.objects.filter(start__gte=start_date).annotate(date=TruncDate("start")).values("date").annotate(count=Count("id")).order_by("date")
        status_stats = Booking.objects.filter(created_at__gte=start_date).values("status").annotate(count=Count("id")).order_by("-count")

        # peak hours
        peak_hours = Booking.objects.filter(start__gte=start_date, status__in=["approved", "completed"]).extra(select={"hour": "EXTRACT(hour FROM start)"}).values("hour").annotate(count=Count("id")).order_by("-count")[:10]

        avg_duration = Booking.objects.filter(created_at__gte=start_date).aggregate(avg_minutes=Avg("duration_minutes" if hasattr(Booking, "duration_minutes") else None))

        ctx.update({
            "total_bookings": total_bookings,
            "approved_bookings": approved_bookings,
            "pending_bookings": pending_bookings,
            "lab_stats": lab_stats,
            "bookings_by_day": list(bookings_by_day),
            "status_stats": list(status_stats),
            "peak_hours": list(peak_hours),
            "avg_duration": avg_duration.get("avg_minutes") if isinstance(avg_duration, dict) else None,
            "days_back": days_back,
        })
        return ctx


# ----------------------------
# My Bookings view (user's booking list with filters)
# ----------------------------
class MyBookingsView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = "bookings/my_bookings.html"
    context_object_name = "bookings"
    paginate_by = 30

    def get_queryset(self):
        user = self.request.user
        f = self.request.GET.get("filter", "all")
        qs = Booking.objects.filter(requester=user).select_related("lab", "approved_by").order_by("-start")
        if f == "upcoming":
            qs = qs.filter(start__gte=timezone.now(), status="approved")
        elif f == "past":
            qs = qs.filter(end__lt=timezone.now())
        elif f == "pending":
            qs = qs.filter(status="pending")
        elif f == "recurring":
            qs = qs.filter(is_recurring=True) if hasattr(Booking, "is_recurring") else qs.none()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["total_bookings"] = Booking.objects.filter(requester=user).count()
        ctx["upcoming_bookings"] = Booking.objects.filter(requester=user, start__gte=timezone.now(), status="approved").count()
        ctx["pending_bookings"] = Booking.objects.filter(requester=user, status="pending").count()
        return ctx


# ----------------------------
# Policy exception request flow (optional)
# ----------------------------
@method_decorator(login_required, name="dispatch")
class PolicyExceptionRequestView(LoginRequiredMixin, CreateView):
    """
    If you have a PolicyException model, this view allows a requester to submit an exception for a booking.
    """
    model = PolicyException if PolicyException is not None else None
    # If the model not present, render an informative message
    template_name = "bookings/policy_exception_form.html"
    # form_class must be defined if PolicyException model exists
    form_class = None
    success_url = reverse_lazy("booking_list")

    def dispatch(self, request, *args, **kwargs):
        if PolicyException is None:
            messages.error(request, "PolicyException feature is not enabled on this installation.")
            return redirect("booking_list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking_id = self.kwargs.get("booking_id")
        ctx["booking"] = get_object_or_404(Booking, pk=booking_id)
        return ctx

    def form_valid(self, form):
        booking_id = self.kwargs.get("booking_id")
        booking = get_object_or_404(Booking, pk=booking_id)
        if self.request.user != booking.requester:
            messages.error(self.request, "You can only request exceptions for your own bookings.")
            return redirect("booking_detail", pk=booking_id)
        exception = form.save(commit=False)
        exception.booking = booking
        exception.requested_by = self.request.user
        exception.status = "pending"
        exception.save()
        booking.is_policy_exception = True
        booking.exception_reason = exception.reason
        booking.save(update_fields=["is_policy_exception", "exception_reason"])
        # notify managers
        try:
            from users.models import User as UserModel  # type: ignore
            managers = UserModel.objects.filter(role="manager")
            for m in managers:
                NotificationService.create(m, f"Policy exception requested for booking {booking.id}", f"{self.request.user.username} requested exception: {exception.reason}", link=f"/bookings/{booking.id}/")
        except Exception:
            logger.exception("Failed to notify managers for policy exception")
        messages.success(self.request, "Policy exception request submitted.")
        return redirect("booking_detail", pk=booking_id)


# ----------------------------
# Policy exception approve/reject
# ----------------------------
@method_decorator(login_required, name="dispatch")
class PolicyExceptionApprovalView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = PolicyException if PolicyException is not None else None
    fields = ["review_notes"] if PolicyException is not None else []
    template_name = "bookings/policy_exception_review.html"

    def test_func(self):
        # only managers / admins
        return user_is_admin_role(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["booking"] = self.object.booking
        return ctx

    def post(self, request, *args, **kwargs):
        if PolicyException is None:
            messages.error(request, "PolicyException model not available.")
            return redirect("booking_list")
        exception = self.get_object()
        action = request.POST.get("action")
        review_notes = request.POST.get("review_notes", "")
        if action not in ["approve", "reject"]:
            messages.error(request, "Invalid action.")
            return redirect("policy_exception_review", pk=exception.pk)
        try:
            with transaction.atomic():
                exception.status = "approved" if action == "approve" else "rejected"
                exception.reviewed_by = request.user
                exception.reviewed_at = timezone.now()
                exception.review_notes = review_notes
                exception.save()
                booking = exception.booking
                if action == "approve":
                    booking.is_policy_exception = False
                    booking.status = "approved"
                    booking.approved_by = request.user
                else:
                    booking.is_policy_exception = False
                    booking.exception_reason = None
                    booking.status = "rejected"
                booking.save()
                # notify requester
                try:
                    NotificationService.create(
                        recipient=booking.requester,
                        title=f"Policy exception {exception.status}: booking #{booking.id}",
                        message=f"Your policy exception request has been {exception.status}. Notes: {review_notes}",
                        link=f"/bookings/{booking.id}/",
                        sender=request.user
                    )
                except Exception:
                    logger.exception("Failed to notify requester about policy exception decision")
                messages.success(request, f"Policy exception {exception.status}.")
                return redirect("booking_detail", pk=booking.pk)
        except Exception as exc:
            logger.exception("Error processing policy exception: %s", exc)
            messages.error(request, "An error occurred while processing exception.")
            return redirect("policy_exception_review", pk=exception.pk)


# ----------------------------
# Utility: get upcoming availability for one lab for full month (helper for calendar)
# ----------------------------
@login_required
def lab_month_availability(request):
    """
    Returns availability per day for a given month.
    Query params:
      - lab_id (required)
      - year
      - month
    Returns JSON:
      { "days": {"YYYY-MM-DD": {"free_slots": n, "booked": [...]}} }
    This is useful for a monthly availability overview.
    """
    lab_id = request.GET.get("lab_id")
    year = int(request.GET.get("year") or timezone.now().year)
    month = int(request.GET.get("month") or timezone.now().month)
    if not lab_id:
        return HttpResponseBadRequest("lab_id required")
    try:
        lab = Lab.objects.get(pk=lab_id)
    except Lab.DoesNotExist:
        return HttpResponseBadRequest("Invalid lab_id")

    # compute first and last day of month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    out = {}
    day = first_day
    while day <= last_day:
        # for each day compute available slots count
        start_of_day = timezone.make_aware(datetime.combine(day, _time(hour=WORK_START_HOUR)), timezone.get_default_timezone())
        end_of_day = timezone.make_aware(datetime.combine(day, _time(hour=WORK_END_HOUR)), timezone.get_default_timezone())
        booked_qs = Booking.objects.filter(lab=lab, start__lt=end_of_day, end__gt=start_of_day, status__in=["approved", "pending"])
        total_slots = int(((WORK_END_HOUR - WORK_START_HOUR) * 60) // SLOT_MINUTES)
        # mark free slots
        slots_free = 0
        cur = start_of_day
        step = timedelta(minutes=SLOT_MINUTES)
        while cur + step <= end_of_day:
            if not booked_qs.filter(start__lt=cur + step, end__gt=cur).exists():
                slots_free += 1
            cur += step
        out[day.isoformat()] = {"free_slots": slots_free, "total_slots": total_slots, "booked_count": booked_qs.count()}
        day = day + timedelta(days=1)
    return JsonResponse({"days": out})


# ----------------------------
# Small helper endpoints for UI: quick approve/reject page (GET renders small confirm form)
# ----------------------------
@login_required
def quick_approve_page(request, pk):
    """Render a simple approve/reject form for a booking (admins only)"""
    booking = get_object_or_404(Booking, pk=pk)
    if not user_can_approve(request.user):
        messages.error(request, "Permission denied.")
        return redirect("booking_detail", pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        notes = request.POST.get("notes", "")
        # delegate to booking_status_action
        resp = booking_status_action(request._request)  # low-level fallback, might not be ideal
        return resp
    return render(request, "bookings/quick_approve.html", {"booking": booking})


# ----------------------------
# Auditing helper (if AuditLog model exists)
# ----------------------------
def create_audit_log(actor, action, entity, details="", ip_address=None):
    """Create an AuditLog entry if AuditLog model is present."""
    if AuditLog is None:
        logger.debug("AuditLog model not defined; skipping audit log for action %s", action)
        return None
    try:
        return AuditLog.objects.create(actor=actor, action=action, entity=entity, details=details[:2000], ip_address=ip_address)
    except Exception:
        logger.exception("Failed to create AuditLog entry")
        return None


# ----------------------------
# Convenience view: booking calendar page (template)
# ----------------------------
class LabCalendarView(LoginRequiredMixin, TemplateView):
    template_name = "bookings/lab_calendar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["labs"] = Lab.objects.all()
        ctx["campuses"] = Lab.objects.values_list("campus", flat=True).distinct()
        ctx["default_view"] = "dayGridMonth"
        return ctx


# ----------------------------
# Admin pending approvals list
# ----------------------------
class PendingApprovalsView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Booking
    template_name = "bookings/pending_approvals.html"
    context_object_name = "bookings"
    paginate_by = 40

    def test_func(self):
        return user_can_approve(self.request.user)

    def get_queryset(self):
        qs = Booking.objects.filter(status="pending").select_related("lab", "requester").order_by("start")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["pending_count"] = self.get_queryset().count()
        return ctx


# ----------------------------
# Minimal helpers for API compatibility (used by some templates)
# ----------------------------
@login_required
def get_lab_list_json(request):
    """Return a simple JSON list of labs for UI dropdowns."""
    labs = Lab.objects.all().values("id", "name", "campus")
    return JsonResponse(list(labs), safe=False)


# ----------------------------
# Final catch-all error handling for common mistakes
# ----------------------------
def handle_known_migrations_issues(request, exc):
    """
    If you saw errors like 'column notifications_notification.target_role does not exist'
    that means DB schema out-of-sync. This helper can be used temporarily to render a friendly page.
    (Not wired into URLs by default.)
    """
    if "notifications_notification" in str(exc) or "does not exist" in str(exc):
        return render(request, "errors/db_schema_out_of_sync.html", {"error": str(exc)})
    return None


# ----------------------------
# End of file
# ----------------------------
# Notes:
# 1. If you have an external notifications app, adapt the NotificationService wrapper above
#    to import and use its exact function names.
# 2. If you have different roles or permission flags on User (can_approve_bookings, can_delete_any_booking),
#    you can add methods on your User model or adapt user_is_admin_role / user_can_approve accordingly.
# 3. Ensure the templates referenced exist and their form names match (booking_form.html, booking_detail.html, lab_calendar.html, etc).
