# notifications/utils.py
import logging
import requests
import os
from django.conf import settings
from threading import Thread
from .models import Notification
from django.db.models import Q

logger = logging.getLogger(__name__)

def send_email_via_brevo(subject, html_content, text_content, recipients):
    """
    Send email via Brevo API
    """
    try:
        # Get API key from settings
        api_key = getattr(settings, 'BREVO_API_KEY', None)
        
        # Debug output
        print(f"🔑 DEBUG: API Key exists: {bool(api_key)}")
        if api_key:
            print(f"🔑 DEBUG: API Key length: {len(api_key)}")
        
        if not api_key:
            logger.error("❌ Brevo API key not configured")
            print("❌ Brevo API key not found - check Render environment variables")
            return False

        # Check if we're in development mode
        if os.getenv("DJANGO_DEVELOPMENT", "0") == "1":
            print(f"📧 DEVELOPMENT MODE - Email would be sent to: {recipients}")
            print(f"📧 SUBJECT: {subject}")
            print(f"📧 CONTENT: {text_content}")
            return True

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json'
        }
        
        sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', 'ggvpby6996@gmail.com')
        sender_name = getattr(settings, 'BREVO_SENDER_NAME', 'PC Lab Booking')
        
        payload = {
            "sender": {
                "name": sender_name,
                "email": sender_email
            },
            "to": [{"email": email} for email in recipients],
            "subject": subject,
            "htmlContent": html_content,
            "textContent": text_content
        }

        print(f"📧 Sending email to: {recipients}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        print(f"📧 Brevo API response: {response.status_code}")
        
        if response.status_code in [200, 201]:
            logger.info(f"✅ Email sent successfully to {recipients}")
            return True
        else:
            logger.error(f"❌ Brevo API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error sending email: {str(e)}")
        return False

def send_email_async(subject, html, text, recipients):
    """
    Send email asynchronously
    """
    def send():
        result = send_email_via_brevo(subject, html, text, recipients)
        if not result:
            # Fallback to console
            print(f"📧 [FALLBACK] To: {recipients}")
            print(f"📧 [SUBJECT]: {subject}")
            print(f"📧 [CONTENT]: {text}")
    
    thread = Thread(target=send)
    thread.daemon = True
    thread.start()

def send_simple_email_async(subject, message, recipient_email):
    """
    Simple email wrapper for OTP and Notifications
    """
    # Create clean text version
    text_message = message.replace('<div class=\'otp\'>', '').replace('</div>', '')
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #007cba; color: white; padding: 20px; text-align: center; }}
            .content {{ background: #f9f9f9; padding: 20px; }}
            .otp {{ font-size: 24px; font-weight: bold; color: #007cba; text-align: center; margin: 20px 0; padding: 10px; border: 2px dashed #007cba; background: #f0f8ff; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
            .notification-message {{ background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #007cba; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>PC Lab Booking System</h1>
            </div>
            <div class="content">
                <div class="notification-message">
                    {message}
                </div>
            </div>
            <div class="footer">
                <p>This is an automated message from PC Lab Booking System</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email_async(
        subject=subject,
        html=html_content,
        text=text_message,
        recipients=[recipient_email]
    )

def send_notification_email_async(subject, message, recipient_email):
    """
    Dedicated function for notification emails with better formatting
    """
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #007cba; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9f9f9; padding: 25px; border-radius: 0 0 8px 8px; }}
            .notification-title {{ color: #007cba; font-size: 18px; margin-bottom: 15px; }}
            .notification-message {{ background: white; padding: 20px; border-radius: 5px; border-left: 4px solid #28a745; line-height: 1.8; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
            .action-button {{ display: inline-block; padding: 12px 24px; background: #007cba; color: white; text-decoration: none; border-radius: 4px; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔔 PC Lab Booking Notification</h1>
            </div>
            <div class="content">
                <div class="notification-title">
                    <strong>{subject}</strong>
                </div>
                <div class="notification-message">
                    {message}
                </div>
            </div>
            <div class="footer">
                <p>This is an automated notification from PC Lab Booking System</p>
                <p>You can manage your notification preferences in your account settings.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Create plain text version
    text_content = f"PC Lab Booking Notification\n\n{subject}\n\n{message}\n\n— PC Lab Booking System"
    
    send_email_async(
        subject=subject,
        html=html_content,
        text=text_content,
        recipients=[recipient_email]
    )

def notifications_context(request):
    """
    Context processor for notifications
    """
    if not request.user.is_authenticated:
        return {}
    
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(target_role=request.user.role)
    ).order_by('-created_at')
    
    unread_count = qs.filter(is_read=False).count()
    latest = qs[:10]
    
    return {
        'notifications': latest,
        'unread_notifications_count': unread_count,
        'global_notifications': latest,  # ensures dropdown uses the same data
    }