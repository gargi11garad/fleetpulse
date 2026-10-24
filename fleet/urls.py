from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DashboardViewSet, DriverViewSet, LocationUpdateViewSet, MaintenanceRecordViewSet, TripViewSet, VehicleViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet)
router.register("drivers", DriverViewSet)
router.register("trips", TripViewSet)
router.register("locations", LocationUpdateViewSet)
router.register("maintenance", MaintenanceRecordViewSet)
router.register("dashboard", DashboardViewSet, basename="dashboard")

urlpatterns = [path("", include(router.urls))]
