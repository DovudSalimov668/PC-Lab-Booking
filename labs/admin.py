from django.contrib import admin
from .models import Lab

@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ("name", "campus", "capacity")
    search_fields = ("name", "campus")
