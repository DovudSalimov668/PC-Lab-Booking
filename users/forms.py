
# users/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class RegistrationForm(UserCreationForm):
    
    class Meta:
        model = User
        fields = ["email", "username",  "password1", "password2"]


class OTPVerificationForm(forms.Form):
    email = forms.EmailField()
    otp_code = forms.CharField(max_length=6)
