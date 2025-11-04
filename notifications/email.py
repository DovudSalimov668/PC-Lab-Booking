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
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 40px 20px;
            }}
            
            .email-wrapper {{
                max-width: 600px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }}
            
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px 30px;
                text-align: center;
                position: relative;
                overflow: hidden;
            }}
            
            .header::before {{
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
                animation: pulse 3s ease-in-out infinite;
            }}
            
            @keyframes pulse {{
                0%, 100% {{ transform: scale(1); opacity: 0.5; }}
                50% {{ transform: scale(1.1); opacity: 0.8; }}
            }}
            
            .logo {{
                font-size: 48px;
                margin-bottom: 10px;
                display: inline-block;
                animation: float 3s ease-in-out infinite;
            }}
            
            @keyframes float {{
                0%, 100% {{ transform: translateY(0px); }}
                50% {{ transform: translateY(-10px); }}
            }}
            
            .header h1 {{
                font-size: 28px;
                font-weight: 700;
                margin: 0;
                position: relative;
                z-index: 1;
                text-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }}
            
            .content {{
                padding: 40px 30px;
                background: #ffffff;
            }}
            
            .content p {{
                margin-bottom: 20px;
                font-size: 16px;
                color: #555;
            }}
            
            .otp-container {{
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                border-radius: 12px;
                padding: 30px;
                text-align: center;
                margin: 30px 0;
                position: relative;
                overflow: hidden;
            }}
            
            .otp-container::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.3) 50%, transparent 70%);
                animation: shine 3s infinite;
            }}
            
            @keyframes shine {{
                0% {{ transform: translateX(-100%); }}
                100% {{ transform: translateX(100%); }}
            }}
            
            .otp-label {{
                font-size: 14px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin-bottom: 15px;
                font-weight: 600;
            }}
            
            .otp {{
                font-size: 42px;
                font-weight: 800;
                color: #667eea;
                letter-spacing: 12px;
                margin: 20px 0;
                font-family: 'Courier New', monospace;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
                position: relative;
                z-index: 1;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .expiry-notice {{
                display: inline-block;
                background: #fff3cd;
                color: #856404;
                padding: 10px 20px;
                border-radius: 20px;
                font-size: 13px;
                margin-top: 15px;
                border: 1px solid #ffeaa7;
            }}
            
            .info-box {{
                background: #e8f4fd;
                border-left: 4px solid #2196F3;
                padding: 20px;
                border-radius: 8px;
                margin: 25px 0;
            }}
            
            .info-box p {{
                margin: 0;
                color: #0d47a1;
                font-size: 14px;
            }}
            
            .warning-box {{
                background: #fff3e0;
                border-left: 4px solid #ff9800;
                padding: 20px;
                border-radius: 8px;
                margin: 25px 0;
            }}
            
            .warning-box p {{
                margin: 0;
                color: #e65100;
                font-size: 14px;
            }}
            
            .footer {{
                background: #f8f9fa;
                padding: 30px;
                text-align: center;
                border-top: 1px solid #e9ecef;
            }}
            
            .footer p {{
                margin: 5px 0;
                font-size: 13px;
                color: #6c757d;
            }}
            
            .footer-links {{
                margin-top: 15px;
            }}
            
            .footer-links a {{
                color: #667eea;
                text-decoration: none;
                margin: 0 10px;
                font-size: 12px;
                transition: color 0.3s ease;
            }}
            
            .footer-links a:hover {{
                color: #764ba2;
            }}
            
            .divider {{
                height: 3px;
                background: linear-gradient(90deg, transparent, #667eea, transparent);
                margin: 30px 0;
            }}
            
            @media only screen and (max-width: 600px) {{
                .email-wrapper {{
                    border-radius: 0;
                    margin: -40px -20px;
                }}
                
                .header {{
                    padding: 30px 20px;
                }}
                
                .header h1 {{
                    font-size: 24px;
                }}
                
                .content {{
                    padding: 30px 20px;
                }}
                
                .otp {{
                    font-size: 36px;
                    letter-spacing: 8px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="email-wrapper">
            <div class="header">
                <div class="logo">💻</div>
                <h1>PC Lab Booking System</h1>
            </div>
            
            <div class="content">
                {message}
            </div>
            
            <div class="footer">
                <p><strong>PC Lab Booking System</strong></p>
                <p>This is an automated message. Please do not reply to this email.</p>
                <div class="footer-links">
                    <a href="#">Help Center</a> • 
                    <a href="#">Contact Support</a> • 
                    <a href="#">Privacy Policy</a>
                </div>
                <p style="margin-top: 20px; font-size: 11px; color: #999;">
                    © 2024 PC Lab Booking System. All rights reserved.
                </p>
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