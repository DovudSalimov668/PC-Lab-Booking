from django.test import TestCase, Client
from django.urls import reverse
from users.models import User

class RoleAccessTests(TestCase):
    def setUp(self):
        # create users for roles
        self.student = User.objects.create_user(email='s@example.com', username='stud', password='pass', role='student', is_active=True)
        self.lecturer = User.objects.create_user(email='l@example.com', username='lect', password='pass', role='lecturer', is_active=True)
        self.admin = User.objects.create_user(email='a@example.com', username='admin', password='pass', role='program_admin', is_active=True)
        self.client = Client()

    def test_student_redirect_to_student_dashboard(self):
        self.client.login(email='s@example.com', password='pass')
        resp = self.client.get(reverse('dashboard_redirect'))
        self.assertRedirects(resp, reverse('student_dashboard'))

    def test_program_admin_can_access_approve(self):
        self.client.login(email='a@example.com', password='pass')
        # Create a booking as fixture or assume booking pk=1 exists; for example purposes we'll just verify view permission
        resp = self.client.post(reverse('booking_approve', kwargs={'pk': 1}), follow=True)
        # If pk doesn't exist you'd assert 404; primary point is access control — ensure not Forbidden
        # But we check that user is allowed (should get 404 if booking missing, not 403)
        self.assertNotEqual(resp.status_code, 403)

    def test_student_cannot_access_admin_dashboard(self):
        self.client.login(email='s@example.com', password='pass')
        resp = self.client.get(reverse('program_admin_dashboard'))
        # Should redirect to dashboard or login; check not 200
        self.assertNotEqual(resp.status_code, 200)
