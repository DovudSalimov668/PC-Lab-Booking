from rest_framework import viewsets
from .models import Lab
from .serializers import LabSerializer


class LabViewSet(viewsets.ModelViewSet):
    queryset = Lab.objects.all()
    serializer_class = LabSerializer


# template based 

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView

class LabListView(LoginRequiredMixin, ListView):
    model = Lab
    template_name = 'templates\labs\lab_list.html'
    context_object_name = 'labs'

