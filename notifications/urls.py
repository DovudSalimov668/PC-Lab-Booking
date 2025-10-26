
# notifications/urls.py
from django.urls import path
from . import views

app_name = 'notifications'  # <-- REQUIRED line!

urlpatterns = [
    path('all/', views.all_notifications, name='all'),
    path('mark-read/', views.mark_read, name='mark_read'),
]
