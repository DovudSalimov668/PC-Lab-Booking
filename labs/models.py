# labs/models.py
from django.db import models


class EquipmentProfile(models.Model):
    EQUIPMENT_CHOICES = [
        ("keyboard", "Keyboard"),
        ("printer", "Printer"),
        ("projector", "Projector"),
        ("headset", "Headset / Audio Device"),
        ("webcam", "Webcam"),
        ("other", "Other Equipment"),
        ("mouse", "Mouse"),
        ("laptop", "Laptop / Notebook"),
        ("monitor", "Monitor / Display"),
    ]

    name = models.CharField(
        max_length=20,
        choices=EQUIPMENT_CHOICES,
        unique=True,
    )

    def __str__(self):
        return self.get_name_display()


class Lab(models.Model):
    name = models.CharField(max_length=120)
    campus = models.CharField(max_length=120)
    capacity = models.PositiveIntegerField(default=20)
    equipment_profiles = models.ManyToManyField(
        EquipmentProfile,
        related_name="labs",
        blank=True,
        help_text="Select all equipment available in this lab",
    )

    def __str__(self):
        return f"{self.name} ({self.campus})" if self.campus else self.name


