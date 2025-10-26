from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task
def send_verification_email(email, otp_code):
    subject = "Verify Your PC Lab Account"
    message = f"Your verification code is: {otp_code}"
    sender = settings.DEFAULT_FROM_EMAIL
    recipient = [email]

    send_mail(subject, message, sender, recipient)
    return f"Verification email sent to {email}"

@shared_task
def send_booking_confirmation(email, lab_name, start, end):
    subject = "Booking Confirmation"
    message = (
        f"Your booking for {lab_name} has been confirmed.\n"
        f"Start: {start}\nEnd: {end}\nThank you for using our system!"
    )
    sender = settings.DEFAULT_FROM_EMAIL
    recipient = [email]

    send_mail(subject, message, sender, recipient)
    return f"Booking confirmation sent to {email}"
