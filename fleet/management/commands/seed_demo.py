from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from fleet.models import Driver, Trip, Vehicle


class Command(BaseCommand):
    help = "Create a small, repeatable FleetPulse demo dataset."

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username="fleet-manager",
            defaults={"email": "manager@example.com", "is_staff": True},
        )
        if created:
            user.set_password("FleetPulseDemo!ChangeMe")
            user.save(update_fields=["password"])

        vehicles = []
        for vin, label, make, model, year in [
            ("DEMO0000000000001", "Van 01", "Ford", "Transit", 2022),
            ("DEMO0000000000002", "Car 02", "Toyota", "Corolla", 2023),
        ]:
            vehicle, _ = Vehicle.objects.get_or_create(
                vin=vin,
                defaults={"label": label, "make": make, "model": model, "year": year, "odometer_km": 12000},
            )
            vehicles.append(vehicle)

        driver, _ = Driver.objects.get_or_create(
            license_number="DEMO-LICENSE-001", defaults={"name": "Alex Morgan", "user": user}
        )
        Trip.objects.get_or_create(
            vehicle=vehicles[0], driver=driver, status=Trip.Status.SCHEDULED,
            origin="San Francisco Depot", destination="Oakland Service Hub",
            defaults={},
        )
        self.stdout.write(self.style.SUCCESS("Demo data is ready. Sign in as fleet-manager with FleetPulseDemo!ChangeMe."))
