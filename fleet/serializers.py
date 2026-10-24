from django.db import transaction
from rest_framework import serializers

from .models import Driver, LocationUpdate, MaintenanceRecord, Trip, Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    service_due = serializers.BooleanField(read_only=True)

    class Meta:
        model = Vehicle
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class TripSerializer(serializers.ModelSerializer):
    vehicle_label = serializers.CharField(source="vehicle.label", read_only=True)
    driver_name = serializers.CharField(source="driver.name", read_only=True)

    class Meta:
        model = Trip
        fields = "__all__"
        read_only_fields = ("id", "created_at", "status", "started_at", "completed_at", "start_odometer_km", "end_odometer_km")

    def validate(self, attrs):
        vehicle = attrs.get("vehicle", getattr(self.instance, "vehicle", None))
        driver = attrs.get("driver", getattr(self.instance, "driver", None))
        if vehicle and vehicle.status in (Vehicle.Status.MAINTENANCE, Vehicle.Status.INACTIVE):
            raise serializers.ValidationError({"vehicle": "Vehicle is unavailable for trips."})
        if driver and not driver.active:
            raise serializers.ValidationError({"driver": "Driver is inactive."})
        return attrs


class LocationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationUpdate
        fields = ("id", "vehicle", "trip", "latitude", "longitude", "recorded_at", "received_at")
        read_only_fields = ("id", "received_at")

    def validate(self, attrs):
        trip = attrs.get("trip")
        vehicle = attrs.get("vehicle")
        if trip and vehicle and trip.vehicle_id != vehicle.id:
            raise serializers.ValidationError({"trip": "Trip must belong to the specified vehicle."})
        if trip and trip.status != Trip.Status.ACTIVE:
            raise serializers.ValidationError({"trip": "Location updates can only be attached to an active trip."})
        return attrs


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceRecord
        fields = "__all__"
        read_only_fields = ("id", "created_at")

    @transaction.atomic
    def create(self, validated_data):
        record = super().create(validated_data)
        vehicle = record.vehicle
        vehicle.last_service_odometer_km = record.odometer_km
        if vehicle.status == Vehicle.Status.MAINTENANCE:
            vehicle.status = Vehicle.Status.AVAILABLE
        vehicle.save(update_fields=["last_service_odometer_km", "status", "updated_at"])
        return record
