import os
from datetime import timedelta
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import authenticate, login as django_login, logout
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.db.models.functions import TruncDate

from .models import User, EmailOTP
from .forms import RegistrationForm
from .mixins import (
    StudentRequiredMixin, LecturerRequiredMixin, ProgrammeAdminRequiredMixin,
    LabTechnicianRequiredMixin, ITSupportRequiredMixin, ManagerRequiredMixin,
)
from notifications.models import Notification

# =====================================================
# Register user + send OTP (WITH FALLBACK)
# =====================================================
def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            otp = EmailOTP.generate_otp()
            EmailOTP.objects.create(
                user=user,
                otp_code=otp,
                purpose="registration",
                expires_at=timezone.now() + timedelta(minutes=5),
            )

            # Try to send email with fallback
            email_sent = False
            try:
                from notifications.email import send_simple_email_async
                send_simple_email_async(
                    subject="Your OTP Code – PC Lab Booking",
                    message=f"Your verification code is: <div class='otp'>{otp}</div>This code expires in 5 minutes.",
                    recipient_email=user.email
                )
                email_sent = True
                messages.info(request, "An OTP has been sent to your email.")
            except Exception as e:
                # FALLBACK: Show OTP on screen
                messages.warning(request, f"Email service configuring. Your OTP is: <strong>{otp}</strong>")
                print(f"🚨 OTP for {user.email}: {otp}")  # Log for debugging

            request.session["pending_email"] = user.email
            request.session["otp_purpose"] = "registration"
            request.session["otp_code"] = otp  # Store for fallback
            return redirect("verify_email")
    else:
        form = RegistrationForm()
    return render(request, "users/register.html", {"form": form})

# =====================================================
# Login + OTP (WITH FALLBACK)
# =====================================================
def login_with_otp(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, email=email, password=password)
        if not user:
            messages.error(request, "Invalid credentials.")
            return render(request, "users/login.html")

        otp = EmailOTP.generate_otp()
        EmailOTP.objects.create(
            user=user,
            otp_code=otp,
            purpose="login",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        # Try to send email with fallback
        try:
            from notifications.email import send_simple_email_async
            send_simple_email_async(
                subject="Your Login OTP – PC Lab Booking",
                message=f"Your login OTP is: <div class='otp'>{otp}</div>Expires in 5 minutes.",
                recipient_email=user.email
            )
            messages.info(request, "OTP sent to your email.")
        except Exception as e:
            # FALLBACK: Show OTP on screen
            messages.warning(request, f"Email service configuring. Your OTP is: <strong>{otp}</strong>")
            print(f"🚨 Login OTP for {user.email}: {otp}")

        request.session["pending_email"] = user.email
        request.session["otp_purpose"] = "login"
        request.session["otp_code"] = otp  # Store for fallback
        return redirect("verify_email")
    return render(request, "users/login.html")

# =====================================================
# Resend OTP (WITH FALLBACK)
# =====================================================
def resend_otp(request):
    email = request.session.get("pending_email")
    purpose = request.session.get("otp_purpose")

    if not email or not purpose:
        return JsonResponse({"success": False, "error": "Session expired."}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found."}, status=404)

    otp = EmailOTP.generate_otp()
    EmailOTP.objects.create(
        user=user,
        otp_code=otp,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    # Try to send email with fallback
    try:
        from notifications.email import send_simple_email_async
        send_simple_email_async(
            subject="Your New OTP Code – PC Lab Booking",
            message=f"Your new OTP code is: <div class='otp'>{otp}</div>Expires in 5 minutes.",
            recipient_email=user.email
        )
        return JsonResponse({"success": True, "message": "A new OTP has been sent."})
    except Exception as e:
        # Fallback response
        return JsonResponse({
            "success": True, 
            "message": f"Email service configuring. Your new OTP is: {otp}",
            "otp_fallback": otp
        })

# ==========================================================
# ================= VERIFY EMAIL OTP =======================
# ==========================================================
def verify_email(request):
    """Handle OTP verification for registration."""
    pending_email = request.session.get('pending_email')
    purpose = request.session.get('otp_purpose', 'registration')
    fallback_otp = request.session.get('otp_code')

    if not pending_email:
        messages.error(request, "Session expired. Please log in or register again.")
        return redirect('login')

    if request.method == 'POST':
        otp_code = request.POST.get('otp_code')
        try:
            user = User.objects.get(email=pending_email)
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect('login')

        # Check OTP in database first
        otp_entry = EmailOTP.objects.filter(
            user=user, otp_code=otp_code, purpose=purpose, is_used=False
        ).order_by('-created_at').first()

        # Fallback: check session OTP if database OTP not found
        if not otp_entry and fallback_otp and otp_code == fallback_otp:
            # Create a temporary OTP entry for fallback
            otp_entry = EmailOTP.objects.create(
                user=user,
                otp_code=fallback_otp,
                purpose=purpose,
                expires_at=timezone.now() + timedelta(minutes=5),
                is_used=True
            )
        
        if not otp_entry:
            messages.error(request, "Invalid OTP.")
            return redirect('verify_email')

        if otp_entry.is_expired():
            otp_entry.is_used = True
            otp_entry.save()
            messages.error(request, "OTP expired. Please try again.")
            request.session.pop('pending_email', None)
            request.session.pop('otp_purpose', None)
            request.session.pop('otp_code', None)
            return redirect('login')

        otp_entry.is_used = True
        otp_entry.save()

        if purpose == 'registration':
            user.is_active = True
            user.is_verified = True
            user.save()

        django_login(request, user)
        request.session.pop('pending_email', None)
        request.session.pop('otp_purpose', None)
        request.session.pop('otp_code', None)

        messages.success(request, f"Welcome, {user.username}!")
        return redirect('dashboard_redirect')

    return render(request, 'users/verify_email.html', {
        'email': pending_email,
        'purpose': purpose,
    })

# ==========================================================
# ================= LOGOUT =================================
# ==========================================================
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')

# ==========================================================
# ================= DASHBOARD REDIRECT =====================
# ==========================================================
def dashboard_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login_with_otp')

    user = request.user
    role_redirects = {
        "student": 'student_dashboard',
        "lecturer": 'lecturer_dashboard',
        "program_admin": 'program_admin_dashboard',
        "lab_technician": 'lab_technician_dashboard',
        "it_support": 'it_support_dashboard',
        "manager": 'manager_dashboard'
    }
    return redirect(role_redirects.get(user.role, '/'))

# ==========================================================
# =================== DASHBOARD VIEWS ======================
# ==========================================================
class StudentDashboardView(LoginRequiredMixin, StudentRequiredMixin, TemplateView):
    template_name = "dashboards/student_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notifications"] = Notification.objects.filter(
            recipient=self.request.user
        ).order_by("-created_at")[:10]
        return context

class LecturerDashboardView(LoginRequiredMixin, LecturerRequiredMixin, TemplateView):
    template_name = "dashboards/lecturer_dashboard.html"

class ProgramAdminDashboardView(LoginRequiredMixin, ProgrammeAdminRequiredMixin, TemplateView):
    template_name = "dashboards/program_admin_dashboard.html"

class LabTechnicianDashboardView(LoginRequiredMixin, LabTechnicianRequiredMixin, TemplateView):
    template_name = "dashboards/lab_technician_dashboard.html"

class ITSupportDashboardView(LoginRequiredMixin, ITSupportRequiredMixin, TemplateView):
    template_name = "dashboards/it_support_dashboard.html"

class ManagerDashboardView(LoginRequiredMixin, ManagerRequiredMixin, TemplateView):
    template_name = "dashboards/manager_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from bookings.models import Booking, PolicyException
        from labs.models import Lab

        days_back = int(self.request.GET.get("days", 30))
        start_date = timezone.now() - timedelta(days=days_back)

        ctx["total_bookings"] = Booking.objects.count()
        ctx["pending_bookings"] = Booking.objects.filter(status="pending").count()
        ctx["approved_bookings"] = Booking.objects.filter(status="approved").count()
        ctx["completed_bookings"] = Booking.objects.filter(status="completed").count()
        ctx["rejected_bookings"] = Booking.objects.filter(status="rejected").count()
        ctx["cancelled_bookings"] = Booking.objects.filter(status="cancelled").count()
        ctx["recent_bookings"] = Booking.objects.filter(created_at__gte=start_date).count()
        ctx["approved_today"] = Booking.objects.filter(
            status="approved",
            created_at__date=timezone.now().date()
        ).count()

        ctx["pending_exceptions_count"] = PolicyException.objects.filter(status="pending").count()
        ctx["total_exceptions"] = PolicyException.objects.count()
        ctx["approved_exceptions"] = PolicyException.objects.filter(status="approved").count()
        ctx["rejected_exceptions"] = PolicyException.objects.filter(status="rejected").count()

        labs = Lab.objects.all()
        lab_stats = []
        WORK_START_HOUR = 8
        WORK_END_HOUR = 20

        for lab in labs:
            bookings = Booking.objects.filter(
                lab=lab, start__gte=start_date, status__in=["approved", "completed"]
            )
            total_seconds = sum([(b.end - b.start).total_seconds() for b in bookings])
            total_hours = round(total_seconds / 3600.0, 2)
            available_hours = (WORK_END_HOUR - WORK_START_HOUR) * days_back
            utilization = round((total_hours / available_hours * 100) if available_hours > 0 else 0.0, 1)

            lab_stats.append({
                "lab": lab,
                "booking_count": bookings.count(),
                "total_hours": total_hours,
                "utilization": utilization
            })

        lab_stats.sort(key=lambda x: x["utilization"], reverse=True)
        ctx["lab_stats"] = lab_stats[:5]

        ctx["bookings_by_day"] = list(
            Booking.objects.filter(start__gte=start_date)
            .annotate(date=TruncDate("start"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        ctx["status_stats"] = list(
            Booking.objects.filter(created_at__gte=start_date)
            .values("status")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        ctx["top_requesters"] = list(
            Booking.objects.filter(created_at__gte=start_date)
            .values("requester__username", "requester__email")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        ctx["peak_hours"] = list(
            Booking.objects.filter(start__gte=start_date, status__in=["approved", "completed"])
            .extra(select={"hour": "EXTRACT(hour FROM start)"})
            .values("hour")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        ctx["days_back"] = days_back
        ctx["start_date"] = start_date
        return ctx