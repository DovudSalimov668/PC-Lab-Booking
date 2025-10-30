import os
import django
from django.core.mail import send_mail

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Test SMTP connection
try:
    send_mail(
        'Test SMTP from Render',
        'This is a test email using your new SMTP key.',
        'PC Lab Booking <noreply@yourdomain.com>',
        ['your-email@example.com'],  # Change to your email
        fail_silently=False,
    )
    print("✅ SMTP test email sent successfully!")
except Exception as e:
    print(f"❌ SMTP test failed: {e}")