from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('verify/', views.verify_email, name='verify_email'),
    path('verify/resend/', views.resend_otp, name='resend_otp'),

    # IMPORTANT: this must point to your custom view
    path('login/', views.login_with_otp, name='login'),
    # path('verify-login-otp/', views.verify_login_otp, name='verify_login_otp'),

    # other URLs...
    path('logout/', views.logout_view, name='logout'),   # implement logout_view or use auth.logout
    

    # dashboard redirect + role dashboards
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('dashboard/student/', views.StudentDashboardView.as_view(), name='student_dashboard'),
    path('dashboard/lecturer/', views.LecturerDashboardView.as_view(), name='lecturer_dashboard'),
    path('dashboard/program-admin/', views.ProgramAdminDashboardView.as_view(), name='program_admin_dashboard'),
    path('dashboard/lab-tech/', views.LabTechnicianDashboardView.as_view(), name='lab_technician_dashboard'),
    path('dashboard/it-support/', views.ITSupportDashboardView.as_view(), name='it_support_dashboard'),
    path('dashboard/manager/', views.ManagerDashboardView.as_view(), name='manager_dashboard'),
    
    
    
]
