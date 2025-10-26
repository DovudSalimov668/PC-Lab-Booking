# users/mixins.py
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect

class RoleRequiredMixin(UserPassesTestMixin):
    """
    Generic mixin to require that request.user.role is one of allowed roles.
    Set `allowed_roles = ['student', 'lecturer']` on the view or subclass.
    """

    allowed_roles = None  # override in subclass or view

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if self.allowed_roles is None:
            return True  # no restriction
        return user.role in self.allowed_roles

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            # Let LoginRequiredMixin handle redirect if used. Otherwise redirect to login.
            return redirect('login')
        messages.error(self.request, "You do not have permission to view this page.")
        return redirect('dashboard_redirect')  # safe landing page for unauthorized users


# Convenience specific mixins:

class StudentRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['student']


class LecturerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['lecturer']


class ProgrammeAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['program_admin']


class LabTechnicianRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['lab_technician']


class ITSupportRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['it_support']


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['manager']
