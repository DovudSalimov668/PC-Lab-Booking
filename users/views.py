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

class ManagerDashboardView(LoginRequiredMixin, ManagerRequiredMixin, TemplateView):
    template_name = "dashboards/manager_dashboard.html"



from django.contrib.auth import logout

def logout_view(request):
    """Logs out the current user and redirects to the login page."""
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')
