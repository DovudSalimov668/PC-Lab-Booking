from rest_framework import serializers
from .models import Lab
from .models import Lab, EquipmentProfile

class EquipmentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentProfile
        fields = ['id', 'name', 'get_name_display']


class LabSerializer(serializers.ModelSerializer):
    equipment_profiles = EquipmentProfileSerializer(many=True, read_only=True)

    class Meta:
        model = Lab
        fields = ['id', 'name', 'campus', 'capacity', 'equipment_profiles']

