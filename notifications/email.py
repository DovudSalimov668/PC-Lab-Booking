import logging
import requests
from django.conf import settings
from threading import Thread

logger = logging.getLogger(__name__)

def send_email_via_brevo(subject, html_content, text_content, recipients):
    """
    Send email via Brevo API
    """
    try:
        api_key = getattr(settings, 'BREVO_API_KEY')
        if not api_key:
            logger.error("Brevo API key not configured")
            return False

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json'
        }
        
        sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', 'noreply@example.com')
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

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
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
    # Extract OTP from message for clean text version
    import re
    otp_match = re.search(r'<div class=\'otp\'>(.*?)</div>', message)
    if otp_match:
        otp_code = otp_match.group(1)
        text_message = f"Your OTP code is: {otp_code}. This code expires in 5 minutes."
    else:
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