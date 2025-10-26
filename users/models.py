# users/models.py (add to existing User model)
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import random

class User(AbstractUser):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("lecturer", "Lecturer"),
        ("program_admin", "Programme Administrator"),
        ("lab_technician", "Lab Technician"),
        ("it_support", "IT Support"),
        ("manager", "Manager / Director"),
    ]

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="student")
    is_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # ========== PERMISSION HELPERS ==========
    
    @property
    def is_student(self):
        return self.role == 'student'
    
    @property
    def is_lecturer(self):
        return self.role == 'lecturer'
    
    @property
    def is_program_admin(self):
        return self.role == 'program_admin'
    
    @property
    def is_lab_technician(self):
        return self.role == 'lab_technician'
    
    @property
    def is_it_support(self):
        return self.role == 'it_support'
    
    @property
    def is_manager(self):
        return self.role == 'manager'
    
    @property
    def can_approve_bookings(self):
        """Can approve/reject booking requests"""
        return self.role in ['program_admin', 'lab_technician', 'it_support', 'manager', 'lecturer']    
    
    @property
    def can_create_recurring(self):
        """Can create recurring bookings"""
        return self.role in ['lecturer', 'program_admin', 'manager']
    
    @property
    def can_edit_any_booking(self):
        """Can edit any booking (not just own)"""
        return self.role in ['program_admin', 'lab_technician', 'manager', 'lecturer']
    
    @property
    def can_delete_any_booking(self):
        """Can delete any booking"""
        return self.role in ['program_admin', 'manager', 'lecturer']

    
    @property
    def can_view_analytics(self):
        """Can view utilization dashboards"""
        return self.role in ['program_admin', 'lab_technician', 'manager']
    
    @property
    def can_approve_policy_exceptions(self):
        """Can approve policy exceptions"""
        return self.role in ['manager']


class EmailOTP(models.Model):
    PURPOSE_CHOICES = [
        ("registration", "Registration"),
        ("login", "Login"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    @staticmethod
    def generate_otp():
        return f"{random.randint(100000, 999999)}"

    def __str__(self):
        return f"OTP for {self.user.email} ({self.purpose})"