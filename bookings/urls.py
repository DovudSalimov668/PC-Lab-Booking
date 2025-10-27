# bookings/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # === Main lists ===
    path("", views.BookingListView.as_view(), name="booking_list"),
    path("my-bookings/", views.MyBookingsView.as_view(), name="my_bookings"),
    path("pending-approvals/", views.PendingApprovalsView.as_view(), name="pending_approvals"),

    # === Booking CRUD ===
    path("create/", views.BookingCreateWithCalendarView.as_view(), name="booking_create"),
    path("<int:pk>/", views.BookingDetailView.as_view(), name="booking_detail"),
    path("<int:pk>/edit/", views.BookingUpdateView.as_view(), name="booking_edit"),
    path("<int:pk>/delete/", views.BookingDeleteView.as_view(), name="booking_delete"),

    # === Booking creation alternative (function-based) ===
    path("new/", views.create_booking, name="create_booking_fbv"),

    # === Admin / Status Actions ===
    path("status-action/", views.booking_status_action, name="booking_status_action"),
    path("bulk-action/", views.bulk_booking_action, name="bulk_booking_action"),

    # === Calendar & availability endpoints ===
    path("calendar/", views.LabCalendarView.as_view(), name="lab_calendar"),
    path("calendar/data/", views.lab_bookings_json, name="lab_bookings_json"),
    path("events/", views.booking_events, name="booking_events"),
    path("availability/", views.availability_for_date, name="availability_for_date"),
    path("month-availability/", views.lab_month_availability, name="lab_month_availability"),

    # === JSON helpers ===
    path("labs/json/", views.get_lab_list_json, name="get_lab_list_json"),
    path("pending-for-lab/", views.pending_bookings_for_lab, name="pending_bookings_for_lab"),
    # path("lab_availability_json/", views.lab_availability_json, name="lab_availability_json"),
    
    


    # === Quick approve/reject ===
    path("<int:pk>/quick-approve/", views.quick_approve_page, name="quick_approve_page"),

    # === Policy exceptions (optional) ===
    path("<int:booking_id>/request-exception/", views.PolicyExceptionRequestView.as_view(), name="request_policy_exception"),
    path("exception/<int:pk>/review/", views.PolicyExceptionApprovalView.as_view(), name="policy_exception_review"),   
    path("policy-exceptions/", views.PolicyExceptionListView.as_view(), name="policy_exception_list"),
    
    
    

    # === Reports and analytics ===
    path("utilization/", views.UtilizationDashboardView.as_view(), name="utilization_dashboard"),
    path("export-csv/", views.export_bookings_csv, name="export_bookings_csv"),




    # Add these URLs to bookings/urls.py





    
    # Policy Exception URLs
    path("policy-exception/<int:booking_id>/request/", 
         views.PolicyExceptionRequestView.as_view(), 
         name="policy_exception_request"),
    
    path("policy-exception/<int:pk>/review/", 
         views.PolicyExceptionApprovalView.as_view(), 
         name="policy_exception_review"),
    
    path("policy-exceptions/", 
         views.PolicyExceptionListView.as_view(), 
         name="policy_exception_list"),
]

