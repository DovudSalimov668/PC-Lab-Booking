from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from django.contrib.auth import authenticate, login, logout
from .models import User, EmailOTP
from .forms import RegistrationForm, OTPVerificationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from .mixins import (
    StudentRequiredMixin, LecturerRequiredMixin, ProgrammeAdminRequiredMixin,
    LabTechnicianRequiredMixin, ITSupportRequiredMixin, ManagerRequiredMixin
)

#from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from .models import User, EmailOTP
from .forms import RegistrationForm, OTPVerificationForm

# ---------- REGISTER ----------
def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            otp = EmailOTP.generate_otp()
            EmailOTP.objects.create(
                user=user,
                otp_code=otp,
                purpose='registration',
                expires_at=timezone.now() + timedelta(minutes=5)
            )

            send_mail(
                'Your OTP Code – PC Lab Booking',
                f'Your verification code is: {otp}',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )

            messages.info(request, "An OTP has been sent to your email for verification.")
            request.session['pending_email'] = user.email
            request.session['otp_purpose'] = 'registration'
            return redirect('verify_email')
    else:
        form = RegistrationForm()
    return render(request, 'users/register.html', {'form': form})


# ---------- LOGIN (ASK FOR OTP) ----------
# users/views.py (snippet)
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from .models import EmailOTP, User

def login_with_otp(request):
    """
    Step 1: authenticate credentials (no login()), generate OTP and redirect to verify page.
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(request, email=email, password=password)
        if not user:
            messages.error(request, "Invalid email or password.")
            return render(request, 'users/login.html')

        # generate OTP record (purpose=login)
        otp = EmailOTP.generate_otp()
        EmailOTP.objects.create(
            user=user,
            otp_code=otp,
            purpose='login',
            expires_at=timezone.now() + timedelta(minutes=5)
        )

        # send OTP email (synchronous; ok for now)
        send_mail(
            subject='Your Login OTP – PC Lab Booking',
            message=f'Your login OTP is: {otp}\nThis code expires in 5 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        # save session info so verify view knows context
        request.session['pending_email'] = user.email
        request.session['otp_purpose'] = 'login'

        messages.info(request, "A verification code was sent to your email.")
        return redirect('verify_email')   # reuse unified verify page
    return render(request, 'users/login.html')
from django.contrib.auth import login as django_login

def verify_login_otp(request):
    """Handle login-time OTP verification"""
    pending_email = request.session.get('pending_email')

    if not pending_email:
        messages.error(request, "Session expired. Please login again.")
        return redirect('login')

    if request.method == 'POST':
        otp_code = request.POST.get('otp_code')

        try:
            user = User.objects.get(email=pending_email)
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect('login')

        otp_entry = EmailOTP.objects.filter(
            user=user, otp_code=otp_code, purpose='login', is_used=False
        ).order_by('-created_at').first()

        if not otp_entry:
            messages.error(request, "Invalid OTP.")
            return redirect('verify_email')

        if otp_entry.is_expired():
            otp_entry.is_used = True
            otp_entry.save()
            messages.error(request, "OTP expired. Please login again.")
            return redirect('login')

        # ✅ OTP is valid
        otp_entry.is_used = True
        otp_entry.save()

        django_login(request, user)

        # Clean up session
        request.session.pop('pending_email', None)

        messages.success(request, f"Welcome back, {user.username}!")
        return redirect('dashboard_redirect')

    # For GET request → show OTP entry form (reuse verify page)
    return render(request, 'users/verify_email.html', {
        'email': pending_email,
        'purpose': 'login'
    })


# ---------- UNIFIED VERIFY ----------
# users/views.py (verify part)
from django.contrib.auth import login as django_login

def verify_email(request):
    pending_email = request.session.get('pending_email')
    purpose = request.session.get('otp_purpose', 'registration')

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

        otp_entry = EmailOTP.objects.filter(
            user=user, otp_code=otp_code, purpose=purpose, is_used=False
        ).order_by('-created_at').first()

        if not otp_entry:
            messages.error(request, "Invalid OTP.")
            return redirect('verify_email')

        if otp_entry.is_expired():
            otp_entry.is_used = True
            otp_entry.save()
            messages.error(request, "OTP expired. Please log in again.")
            # cleanup session then redirect to login
            request.session.pop('pending_email', None)
            request.session.pop('otp_purpose', None)
            return redirect('login')

        # OTP valid -> mark used and log in
        otp_entry.is_used = True
        otp_entry.save()

        # activate user if registration
        if purpose == 'registration':
            user.is_active = True
            user.is_verified = True
            user.save()

        # Final login (this is the only place login() is called)
        django_login(request, user)

        # cleanup
        request.session.pop('pending_email', None)
        request.session.pop('otp_purpose', None)

        messages.success(request, f"Welcome, {user.username}!")
        return redirect('dashboard_redirect')

    # GET: render unified verify template
    return render(request, 'users/verify_email.html', {'email': pending_email, 'purpose': purpose})


from django.http import JsonResponse
from datetime import timedelta

def resend_otp(request):
    """
    Re-sends a fresh OTP for the current session's email & purpose.
    Works for both registration and login OTPs.
    """
    email = request.session.get('pending_email')
    purpose = request.session.get('otp_purpose')

    if not email or not purpose:
        return JsonResponse({'success': False, 'error': 'Session expired. Please login or register again.'}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'}, status=404)

    # Create and send new OTP
    otp = EmailOTP.generate_otp()
    EmailOTP.objects.create(
        user=user,
        otp_code=otp,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=5)
    )

    send_mail(
        subject='Your New OTP Code – PC Lab Booking',
        message=f'Your new verification code is: {otp}\nThis code expires in 5 minutes.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )

    return JsonResponse({'success': True, 'message': 'A new OTP has been sent to your email.'})



# --------------------- DASHBOARD REDIRECT ---------------------
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


# --------------------- DASHBOARD VIEWS ---------------------
from notifications.models import Notification

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

# Replace or update the ManagerDashboardView in users/views.py

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Avg, Sum
from django.db.models.functions import TruncDate
from .mixins import ManagerRequiredMixin

class ManagerDashboardView(LoginRequiredMixin, ManagerRequiredMixin, TemplateView):
    template_name = "dashboards/manager_dashboard.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Import here to avoid circular imports
        from bookings.models import Booking, PolicyException
        from labs.models import Lab
        
        # Date range for analytics (last 30 days by default)
        days_back = int(self.request.GET.get("days", 30))
        start_date = timezone.now() - timedelta(days=days_back)
        
        # ===== BOOKING STATISTICS =====
        ctx["total_bookings"] = Booking.objects.count()
        ctx["pending_bookings"] = Booking.objects.filter(status="pending").count()
        ctx["approved_bookings"] = Booking.objects.filter(status="approved").count()
        ctx["completed_bookings"] = Booking.objects.filter(status="completed").count()
        ctx["rejected_bookings"] = Booking.objects.filter(status="rejected").count()
        ctx["cancelled_bookings"] = Booking.objects.filter(status="cancelled").count()
        
        # Recent bookings (last 30 days)
        ctx["recent_bookings"] = Booking.objects.filter(
            created_at__gte=start_date
        ).count()
        
        ctx["approved_today"] = Booking.objects.filter(
            status="approved",
            created_at__date=timezone.now().date()
        ).count()
        
        # ===== POLICY EXCEPTION STATISTICS =====
        ctx["pending_exceptions_count"] = PolicyException.objects.filter(status="pending").count()
        ctx["total_exceptions"] = PolicyException.objects.count()
        ctx["approved_exceptions"] = PolicyException.objects.filter(status="approved").count()
        ctx["rejected_exceptions"] = PolicyException.objects.filter(status="rejected").count()
        
        # Recent pending exceptions (for quick view)
        ctx["recent_exceptions"] = PolicyException.objects.filter(
            status="pending"
        ).select_related("booking", "booking__lab", "requested_by").order_by("-created_at")[:5]
        
        # ===== LAB UTILIZATION =====
        labs = Lab.objects.all()
        lab_stats = []
        WORK_START_HOUR = 8
        WORK_END_HOUR = 20
        
        for lab in labs:
            bookings = Booking.objects.filter(
                lab=lab, 
                start__gte=start_date, 
                status__in=["approved", "completed"]
            )
            
            # Calculate total booked hours
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
            
            lab_stats.append({
                "lab": lab,
                "booking_count": booking_count,
                "total_hours": total_hours,
                "utilization": utilization
            })
        
        # Sort by utilization (highest first)
        lab_stats.sort(key=lambda x: x["utilization"], reverse=True)
        ctx["lab_stats"] = lab_stats[:5]  # Top 5 labs
        
        # ===== BOOKING TRENDS =====
        bookings_by_day = Booking.objects.filter(
            start__gte=start_date
        ).annotate(
            date=TruncDate("start")
        ).values("date").annotate(count=Count("id")).order_by("date")
        
        ctx["bookings_by_day"] = list(bookings_by_day)
        
        # ===== STATUS BREAKDOWN =====
        status_stats = Booking.objects.filter(
            created_at__gte=start_date
        ).values("status").annotate(count=Count("id")).order_by("-count")
        
        ctx["status_stats"] = list(status_stats)
        
        # ===== TOP REQUESTERS =====
        top_requesters = Booking.objects.filter(
            created_at__gte=start_date
        ).values(
            "requester__username", 
            "requester__email"
        ).annotate(count=Count("id")).order_by("-count")[:5]
        
        ctx["top_requesters"] = list(top_requesters)
        
        # # ===== AVERAGE DURATION =====
        # avg_duration = Booking.objects.filter(
        #     created_at__gte=start_date
        # ).aggregate(
        #     avg_hours=Avg("duration_hours" if hasattr(Booking, "duration_hours") else None)
        # )
        
        # ctx["avg_duration"] = avg_duration.get("avg_hours") if avg_duration else 0
        
        # ===== PEAK HOURS =====
        peak_hours = Booking.objects.filter(
            start__gte=start_date,
            status__in=["approved", "completed"]
        ).extra(
            select={"hour": "EXTRACT(hour FROM start)"}
        ).values("hour").annotate(count=Count("id")).order_by("-count")[:5]
        
        ctx["peak_hours"] = list(peak_hours)
        
        # ===== OTHER CONTEXT =====
        ctx["days_back"] = days_back
        ctx["start_date"] = start_date
        
        return ctx


from django.contrib.auth import logout

def logout_view(request):
    """Logs out the current user and redirects to the login page."""
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')
