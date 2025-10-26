from rest_framework import serializers
from .models import Booking
from django.utils import timezone

class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = "__all__"
        read_only_fields = ("requester", "created_at", "updated_at")

    def validate(self, data):
        # Ensure end > start
        start = data.get("start")
        end = data.get("end")
        if end <= start:
            raise serializers.ValidationError("End must be after start.")
        if start < timezone.now():
            raise serializers.ValidationError("Start must be in the future.")
        # If pc and lab both present, ensure consistency
        pc = data.get("pc")
        lab = data.get("lab")
        if pc and lab and pc.lab_id != lab.id:
            raise serializers.ValidationError("Selected PC doesn't belong to the lab.")
        # Temporarily create a Booking instance for conflict check.
        # Use requester if available in context.
        requester = self.context["request"].user if "request" in self.context else None
        tmp = Booking(requester=requester, **data)
        if tmp.has_conflict():
            raise serializers.ValidationError("This booking conflicts with an existing one.")
        return data
