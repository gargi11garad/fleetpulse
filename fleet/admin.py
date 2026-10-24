from django.contrib import admin

from .models import Driver, LocationUpdate, MaintenanceRecord, Trip, Vehicle

admin.site.register(Vehicle)
admin.site.register(Driver)
admin.site.register(Trip)
admin.site.register(LocationUpdate)
admin.site.register(MaintenanceRecord)
