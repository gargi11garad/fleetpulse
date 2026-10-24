from django.db import transaction
from django.db.models import Count, F
from django.shortcuts import render
from django.utils import timezone
from rest_framework import decorators, response, status, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Driver, LocationUpdate, MaintenanceRecord, Trip, Vehicle
from .permissions import FleetRolePermission
from .serializers import DriverSerializer, LocationUpdateSerializer, MaintenanceRecordSerializer, TripSerializer, VehicleSerializer


def dashboard_page(request):
    return render(request, "fleet/dashboard.html")


class FleetViewSet(viewsets.ModelViewSet):
    permission_classes = [FleetRolePermission]


class VehicleViewSet(FleetViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_fields = ["status", "make", "year"]
    search_fields = ["label", "vin", "make", "model"]
    ordering_fields = ["label", "year", "odometer_km", "created_at"]

    @decorators.action(detail=True, methods=["get"])
    def latest_location(self, request, pk=None):
        vehicle = self.get_object()
        location = vehicle.locations.first()
        if not location:
            return response.Response({"detail": "No location has been recorded."}, status=status.HTTP_404_NOT_FOUND)
        return response.Response(LocationUpdateSerializer(location).data)


class DriverViewSet(FleetViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    filterset_fields = ["active"]
    search_fields = ["name", "license_number"]
    ordering_fields = ["name", "created_at"]


class TripViewSet(FleetViewSet):
    queryset = Trip.objects.select_related("vehicle", "driver").all()
    serializer_class = TripSerializer
    filterset_fields = ["status", "vehicle", "driver"]
    search_fields = ["origin", "destination", "vehicle__label", "driver__name"]
    ordering_fields = ["created_at", "started_at", "status"]

    @decorators.action(detail=True, methods=["post"])
    @transaction.atomic
    def start(self, request, pk=None):
        trip = Trip.objects.select_for_update().select_related("vehicle").get(pk=pk)
        if trip.status != Trip.Status.SCHEDULED:
            return response.Response({"detail": "Only scheduled trips can be started."}, status=400)
        vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle_id)
        if vehicle.status != Vehicle.Status.AVAILABLE:
            return response.Response({"detail": "Vehicle is not available."}, status=400)
        trip.status = Trip.Status.ACTIVE
        trip.started_at = timezone.now()
        trip.start_odometer_km = vehicle.odometer_km
        trip.save(update_fields=["status", "started_at", "start_odometer_km"])
        vehicle.status = Vehicle.Status.IN_USE
        vehicle.save(update_fields=["status", "updated_at"])
        return response.Response(self.get_serializer(trip).data)

    @decorators.action(detail=True, methods=["post"])
    @transaction.atomic
    def complete(self, request, pk=None):
        trip = Trip.objects.select_for_update().select_related("vehicle").get(pk=pk)
        if trip.status != Trip.Status.ACTIVE:
            return response.Response({"detail": "Only active trips can be completed."}, status=400)
        try:
            end_odometer = int(request.data["end_odometer_km"])
            if end_odometer < trip.start_odometer_km:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return response.Response({"end_odometer_km": "Provide a valid value greater than or equal to the start odometer."}, status=400)
        vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle_id)
        trip.status = Trip.Status.COMPLETED
        trip.completed_at = timezone.now()
        trip.end_odometer_km = end_odometer
        trip.save(update_fields=["status", "completed_at", "end_odometer_km"])
        vehicle.odometer_km = end_odometer
        vehicle.status = (
            Vehicle.Status.MAINTENANCE
            if end_odometer >= vehicle.last_service_odometer_km + vehicle.service_interval_km
            else Vehicle.Status.AVAILABLE
        )
        vehicle.save(update_fields=["odometer_km", "status", "updated_at"])
        return response.Response(self.get_serializer(trip).data)


class LocationUpdateViewSet(viewsets.ModelViewSet):
    queryset = LocationUpdate.objects.select_related("vehicle", "trip").all()
    serializer_class = LocationUpdateSerializer
    permission_classes = [IsAuthenticated, FleetRolePermission]
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["vehicle", "trip"]
    ordering_fields = ["recorded_at", "received_at"]


class MaintenanceRecordViewSet(FleetViewSet):
    queryset = MaintenanceRecord.objects.select_related("vehicle").all()
    serializer_class = MaintenanceRecordSerializer
    filterset_fields = ["vehicle"]
    search_fields = ["description", "vehicle__label"]
    ordering_fields = ["service_date", "cost"]


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        by_status = {item["status"]: item["count"] for item in Vehicle.objects.values("status").annotate(count=Count("id"))}
        return response.Response({
            "vehicles": {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "service_due": Vehicle.objects.filter(
                    odometer_km__gte=F("last_service_odometer_km") + F("service_interval_km")
                ).count(),
            },
            "trips": {"active": Trip.objects.filter(status=Trip.Status.ACTIVE).count(), "scheduled": Trip.objects.filter(status=Trip.Status.SCHEDULED).count(), "completed": Trip.objects.filter(status=Trip.Status.COMPLETED).count()},
            "active_drivers": Driver.objects.filter(active=True).count(),
        })
