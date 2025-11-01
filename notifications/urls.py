# notifications/urls.py
from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.all_notifications, name='all_notifications'),
    path('mark-read/', views.mark_read, name='mark_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('delete/', views.delete_notification, name='delete_notification'),
    path('delete-all-read/', views.delete_all_read, name='delete_all_read'),
]