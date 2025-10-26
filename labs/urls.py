from django.urls import path
from . import views

app_name = 'labs'

urlpatterns = [

    # Template-based URLs
    path('lab_list/', views.LabListView.as_view(), name='lab_list'),
]
