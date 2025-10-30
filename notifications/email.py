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
    Simple email wrapper - ONLY USES SMTP
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
            .otp {{ font-size: 24px; font-weight: bold; color: #007cba; text-align: center; margin: 20px 0; padding: 10px; border: 2px dashed #007cba; }}
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