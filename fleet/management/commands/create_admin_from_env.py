import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial staff account from BOOTSTRAP_ADMIN_* environment variables."

    def handle(self, *args, **options):
        username = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
        if not username or not password:
            raise CommandError("Set BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD before deployment.")

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={"email": os.getenv("BOOTSTRAP_ADMIN_EMAIL", ""), "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Created deployment administrator '{username}'."))
        elif not user.is_staff:
            raise CommandError(f"'{username}' already exists but is not a staff account; resolve this account manually.")
        else:
            self.stdout.write(f"Deployment administrator '{username}' already exists.")
