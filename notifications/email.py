import logging
import threading
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def send_email_via_brevo(subject, html_content, text_content, recipients):
    """
    Send email via Brevo API
    """
    try:
        api_key = getattr(settings, 'EMAIL_HOST_PASSWORD')
        if not api_key:
            logger.error("Brevo API key not configured")
            return False

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json'
        }
        
        sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'))
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
            logger.info(f"Email sent successfully to {recipients}")
            return True
        else:
            logger.error(f"Brevo API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending email via Brevo: {str(e)}")
        return False

def send_email_async(subject, html, text, recipients):
    """
    Send email asynchronously using Brevo API
    """
    def send():
        send_email_via_brevo(subject, html, text, recipients)
    
    thread = threading.Thread(target=send)
    thread.daemon = True
    thread.start()

def send_simple_email_async(subject, message, recipient_email):
    """
    Simple email wrapper
    """
    send_email_async(
        subject=subject,
        html=f"<p>{message}</p>",
        text=message,
        recipients=[recipient_email]
    )