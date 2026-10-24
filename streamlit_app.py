"""Self-contained Streamlit console backed by FleetPulse's Django models."""

import os
from datetime import date
from pathlib import Path

import streamlit as st


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "fleetpulse-streamlit-demo-key-change-for-real-deployments")
os.environ.setdefault("DJANGO_DEBUG", "false")
os.environ.setdefault("DATABASE_URL", "")

import django


django.setup()

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import authenticate
from fleet.models import Driver, LocationUpdate, MaintenanceRecord, Trip, Vehicle


st.set_page_config(page_title="FleetPulse", page_icon="🚙", layout="wide")


@st.cache_resource
def initialize_database():
    """Prepare an ephemeral SQLite demo database on first app startup."""
    from django.conf import settings

    db_name = settings.DATABASES["default"]["NAME"]
    if str(db_name) != ":memory:":
        Path(db_name).parent.mkdir(parents=True, exist_ok=True)
    call_command("migrate", interactive=False, verbosity=0)
    call_command("seed_demo", verbosity=0)
    return True


initialize_database()


def label(value):
    return str(value or "").replace("_", " ").title()


def vehicle_name(vehicle_id):
    vehicle = Vehicle.objects.filter(pk=vehicle_id).first()
    return vehicle.label if vehicle else str(vehicle_id)


def dashboard():
    vehicles = list(Vehicle.objects.all())
    statuses = {key: sum(v.status == key for v in vehicles) for key, _ in Vehicle.Status.choices}
    return vehicles, statuses


def overview():
    vehicles, statuses = dashboard()
    trips = list(Trip.objects.select_related("vehicle", "driver"))
    st.title("Fleet overview")
    st.caption("Fleet activity and health at a glance.")
    metrics = st.columns(4)
    metrics[0].metric("Vehicles", len(vehicles))
    metrics[1].metric("On the road", statuses[Vehicle.Status.IN_USE])
    metrics[2].metric("Available", statuses[Vehicle.Status.AVAILABLE])
    metrics[3].metric("Service due", sum(v.service_due for v in vehicles))
    trip_metrics = st.columns(3)
    for col, status in zip(trip_metrics, (Trip.Status.ACTIVE, Trip.Status.SCHEDULED, Trip.Status.COMPLETED)):
        col.metric(label(status), sum(t.status == status for t in trips))
    st.subheader("Fleet availability")
    st.bar_chart([{"Status": label(k), "Vehicles": v} for k, v in statuses.items()], x="Status", y="Vehicles")
    st.subheader("Recent trips")
    st.dataframe([{"Trip": str(t.id)[:8].upper(), "Vehicle": t.vehicle.label, "Driver": t.driver.name,
                   "Route": f"{t.origin} → {t.destination}", "Status": label(t.status),
                   "Created": t.created_at.strftime("%Y-%m-%d")} for t in trips[:10]],
                 use_container_width=True, hide_index=True)


def vehicles_page():
    st.title("Vehicles")
    query = st.text_input("Search vehicles", placeholder="Label, VIN, make, model")
    rows = list(Vehicle.objects.all())
    if query:
        rows = [v for v in rows if query.casefold() in f"{v.label} {v.vin} {v.make} {v.model}".casefold()]
    st.dataframe([{"Vehicle": v.label, "Make / model": f"{v.make} {v.model}", "VIN": v.vin,
                   "Status": label(v.status), "Odometer (km)": v.odometer_km,
                   "Service due": "Due" if v.service_due else "On schedule", "Year": v.year} for v in rows],
                 use_container_width=True, hide_index=True)
    with st.expander("Add a vehicle"):
        with st.form("add_vehicle"):
            name = st.text_input("Label")
            make, model = st.columns(2)
            make_value, model_value = make.text_input("Make"), model.text_input("Model")
            year, vin = st.columns(2)
            year_value = year.number_input("Year", 1900, 2100, 2024)
            vin_value = vin.text_input("VIN", max_chars=17)
            odometer = st.number_input("Odometer (km)", min_value=0)
            if st.form_submit_button("Add vehicle", type="primary"):
                try:
                    Vehicle.objects.create(label=name, make=make_value, model=model_value, year=year_value,
                                           vin=vin_value, odometer_km=odometer)
                    st.success("Vehicle added.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def drivers_page():
    st.title("Drivers")
    drivers = list(Driver.objects.all())
    st.dataframe([{"Driver": d.name, "License": d.license_number,
                   "Status": "Active" if d.active else "Inactive"} for d in drivers],
                 use_container_width=True, hide_index=True)
    with st.expander("Add a driver"):
        with st.form("add_driver"):
            name, license_number = st.text_input("Full name"), st.text_input("License number")
            if st.form_submit_button("Add driver", type="primary"):
                try:
                    Driver.objects.create(name=name, license_number=license_number, active=True)
                    st.success("Driver added.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def trips_page():
    st.title("Trips")
    trips = list(Trip.objects.select_related("vehicle", "driver"))
    for trip in trips:
        with st.container(border=True):
            info, action = st.columns([4, 1])
            info.markdown(f"**{trip.vehicle.label}** · {label(trip.status)}")
            info.caption(f"{trip.origin} → {trip.destination} · {trip.driver.name}")
            if trip.status == Trip.Status.SCHEDULED and action.button("Start", key=f"start-{trip.id}"):
                with transaction.atomic():
                    vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle_id)
                    if vehicle.status != Vehicle.Status.AVAILABLE:
                        st.error("Vehicle is not available.")
                    else:
                        trip.status, trip.started_at = Trip.Status.ACTIVE, timezone.now()
                        trip.start_odometer_km = vehicle.odometer_km
                        trip.save(update_fields=["status", "started_at", "start_odometer_km"])
                        vehicle.status = Vehicle.Status.IN_USE
                        vehicle.save(update_fields=["status", "updated_at"])
                        st.rerun()
            elif trip.status == Trip.Status.ACTIVE:
                with st.form(f"complete-{trip.id}"):
                    end_km = st.number_input("Final odometer (km)", min_value=trip.start_odometer_km or 0,
                                             value=max(trip.vehicle.odometer_km, trip.start_odometer_km or 0), key=f"km-{trip.id}")
                    if st.form_submit_button("Complete trip"):
                        with transaction.atomic():
                            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle_id)
                            trip.status, trip.completed_at, trip.end_odometer_km = Trip.Status.COMPLETED, timezone.now(), end_km
                            trip.save(update_fields=["status", "completed_at", "end_odometer_km"])
                            vehicle.odometer_km = end_km
                            vehicle.status = Vehicle.Status.MAINTENANCE if vehicle.service_due else Vehicle.Status.AVAILABLE
                            vehicle.save(update_fields=["odometer_km", "status", "updated_at"])
                        st.success("Trip completed.")
                        st.rerun()
    with st.expander("Schedule a trip"):
        available = list(Vehicle.objects.filter(status=Vehicle.Status.AVAILABLE))
        drivers = list(Driver.objects.filter(active=True))
        with st.form("schedule_trip"):
            vehicle = st.selectbox("Vehicle", available, format_func=lambda v: f"{v.label} · {v.make} {v.model}") if available else None
            driver = st.selectbox("Driver", drivers, format_func=lambda d: d.name) if drivers else None
            origin, destination = st.text_input("Origin"), st.text_input("Destination")
            if st.form_submit_button("Schedule trip", type="primary"):
                if not vehicle or not driver or not origin or not destination:
                    st.error("Add an available vehicle and active driver, then enter both locations.")
                else:
                    Trip.objects.create(vehicle=vehicle, driver=driver, origin=origin, destination=destination)
                    st.success("Trip scheduled.")
                    st.rerun()


def maintenance_page():
    st.title("Maintenance")
    records = list(MaintenanceRecord.objects.select_related("vehicle"))
    st.dataframe([{"Vehicle": r.vehicle.label, "Service": r.description, "Date": str(r.service_date),
                   "Odometer (km)": r.odometer_km, "Cost": str(r.cost) if r.cost else "—"} for r in records],
                 use_container_width=True, hide_index=True)
    vehicles = list(Vehicle.objects.all())
    if not vehicles:
        st.info("Add a vehicle before recording maintenance.")
        return
    with st.expander("Log service"):
        with st.form("log_service"):
            vehicle = st.selectbox("Vehicle", vehicles, format_func=lambda v: v.label)
            description = st.text_input("Service description")
            service_date = st.date_input("Service date", value=date.today())
            odometer = st.number_input("Odometer (km)", min_value=0, value=vehicle.odometer_km)
            cost = st.number_input("Cost", min_value=0.0, step=10.0)
            if st.form_submit_button("Save service record", type="primary"):
                with transaction.atomic():
                    MaintenanceRecord.objects.create(vehicle=vehicle, description=description,
                        service_date=service_date, odometer_km=odometer, cost=cost or None)
                    vehicle.last_service_odometer_km = odometer
                    if vehicle.status == Vehicle.Status.MAINTENANCE:
                        vehicle.status = Vehicle.Status.AVAILABLE
                    vehicle.save(update_fields=["last_service_odometer_km", "status", "updated_at"])
                st.success("Service record saved.")
                st.rerun()


def locations_page():
    st.title("Live locations")
    locations = list(LocationUpdate.objects.select_related("vehicle", "trip")[:100])
    st.dataframe([{"Vehicle": r.vehicle.label, "Trip": str(r.trip_id)[:8] if r.trip_id else "—",
                   "Latitude": float(r.latitude), "Longitude": float(r.longitude),
                   "Recorded at": r.recorded_at.strftime("%Y-%m-%d %H:%M:%S")} for r in locations],
                 use_container_width=True, hide_index=True)
    vehicles = list(Vehicle.objects.all())
    if not vehicles:
        return
    active_trips = list(Trip.objects.filter(status=Trip.Status.ACTIVE).select_related("vehicle"))
    with st.expander("Submit a location update"):
        with st.form("location_update"):
            vehicle = st.selectbox("Vehicle", vehicles, format_func=lambda v: v.label)
            trip = st.selectbox("Active trip (optional)", [None] + active_trips,
                format_func=lambda t: "No trip" if t is None else f"{t.origin} → {t.destination}")
            lat = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=37.7749, format="%.6f")
            lon = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-122.4194, format="%.6f")
            if st.form_submit_button("Send update", type="primary"):
                if trip and trip.vehicle_id != vehicle.id:
                    st.error("The selected trip belongs to a different vehicle.")
                else:
                    LocationUpdate.objects.create(vehicle=vehicle, trip=trip, latitude=lat, longitude=lon)
                    st.success("Location update received.")
                    st.rerun()


def main():
    st.sidebar.markdown("# 🚙 FleetPulse")
    st.sidebar.caption("Fleet operations command center")
    if not st.session_state.get("username"):
        _, center, _ = st.columns([1, 1.1, 1])
        with center:
            st.title("FleetPulse")
            st.caption("Sign in to manage the demo fleet.")
            st.info("Demo login: `fleet-manager` / `FleetPulseDemo!ChangeMe`")
            with st.form("login"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submitted:
                user = authenticate(username=username.strip(), password=password)
                if user and user.is_staff:
                    st.session_state.username = user.username
                    st.rerun()
                st.error("Invalid username or password.")
        return

    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.username}**")
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("username", None)
            st.rerun()
        st.divider()
        page = st.radio("Workspace", ["Overview", "Vehicles", "Trips", "Drivers", "Maintenance", "Locations"], label_visibility="collapsed")
        if st.button("↻ Refresh data", use_container_width=True):
            st.rerun()
        st.caption("Portfolio demo · SQLite data may reset when the app restarts.")
    {"Overview": overview, "Vehicles": vehicles_page, "Trips": trips_page,
     "Drivers": drivers_page, "Maintenance": maintenance_page, "Locations": locations_page}[page]()


main()
