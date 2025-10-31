import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from notifications.email import send_simple_email_async

# Test the email system
send_simple_email_async(
    subject="Test Brevo API",
    message="Your test OTP is: <div class='otp'>123456</div>This is a test.",
    recipient_email="ggvpby6996@gmail.com"
)
print("Test email sent!")