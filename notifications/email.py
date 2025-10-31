import logging
import requests
import os
from django.conf import settings
from threading import Thread

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
    Simple email wrapper for OTP
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
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>PC Lab Booking System</h1>
            </div>
            <div class="content">
                {message}
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
    # notifications/email.py - MAKE SURE THIS EXISTS
import logging
from django.core.mail import send_mail
from django.conf import settings
from threading import Thread

logger = logging.getLogger(__name__)

def send_email_smtp(subject, html_content, text_content, recipients):
    """
    Send email using Django's SMTP backend
    """
    try:
        result = send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f"✅ Email sent via SMTP to {recipients}")
        return True
    except Exception as e:
        logger.error(f"❌ SMTP email failed: {str(e)}")
        # Fallback to console
        print(f"📧 [EMAIL FALLBACK] To: {recipients}, Subject: {subject}")
        print(f"📧 [EMAIL CONTENT]: {text_content}")
        return False

def send_email_async(subject, html, text, recipients):
    """
    Send email asynchronously using SMTP
    """
    def send():
        send_email_smtp(subject, html, text, recipients)
    
    thread = Thread(target=send)
    thread.daemon = True
    thread.start()

def send_simple_email_async(subject, message, recipient_email):
    """
    Simple email wrapper for OTP - THIS IS WHAT NotificationService CALLS
    """
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
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>PC Lab Booking System</h1>
            </div>
            <div class="content">
                {message}
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
        text=message,
        recipients=[recipient_email]
    )