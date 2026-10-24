"""Streamlit operations console for the FleetPulse Django REST API."""

import os
from datetime import date

import requests
import streamlit as st


st.set_page_config(page_title="FleetPulse", page_icon="🚙", layout="wide")


def configured_api_url():
    value = os.getenv("FLEETPULSE_API_URL", "http://127.0.0.1:8000/api/v1")
    try:
        value = st.secrets.get("API_BASE_URL", value)
    except Exception:
        pass
    return value.strip().rstrip("/")


API_BASE_URL = configured_api_url()


def api_request(path, method="GET", payload=None, authenticated=True):
    headers = {}
    if authenticated and st.session_state.get("access_token"):
        headers["Authorization"] = f"Bearer {st.session_state.access_token}"
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            json=payload,
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not connect to the FleetPulse API at {API_BASE_URL}: {exc}") from exc
    if response.status_code == 401 and authenticated and st.session_state.get("refresh_token"):
        try:
            refreshed = requests.post(
                f"{API_BASE_URL}/auth/token/refresh/",
                json={"refresh": st.session_state.refresh_token},
                timeout=20,
            )
            if refreshed.ok:
                st.session_state.access_token = refreshed.json()["access"]
                headers["Authorization"] = f"Bearer {st.session_state.access_token}"
                response = requests.request(method, f"{API_BASE_URL}{path}", json=payload, headers=headers, timeout=20)
        except (requests.RequestException, ValueError):
            pass
    if response.status_code == 204:
        return None
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text or f"HTTP {response.status_code}"}
    if response.status_code >= 400:
        detail = body.get("detail", body) if isinstance(body, dict) else body
        raise RuntimeError(f"API returned {response.status_code}: {detail}")
    return body


def sign_in(username, password):
    result = api_request(
        "/auth/token/",
        method="POST",
        payload={"username": username, "password": password},
        authenticated=False,
    )
    st.session_state.access_token = result["access"]
    st.session_state.refresh_token = result["refresh"]
    st.session_state.username = username


def load_data():
    dashboard = api_request("/dashboard/")
    vehicles = api_request("/vehicles/?page_size=100")
    drivers = api_request("/drivers/?page_size=100")
    trips = api_request("/trips/?page_size=100")
    maintenance = api_request("/maintenance/?page_size=100")
    locations = api_request("/locations/?page_size=100&ordering=-recorded_at")
    return {
        "dashboard": dashboard,
        "vehicles": vehicles.get("results", []),
        "drivers": drivers.get("results", []),
        "trips": trips.get("results", []),
        "maintenance": maintenance.get("results", []),
        "locations": locations.get("results", []),
    }


def display_error(action):
    st.error(str(action))


def display_login():
    left, center, right = st.columns([1, 1.1, 1])
    with center:
        st.markdown("# 🚙 FleetPulse")
        st.caption("Fleet operations command center")
        st.info(f"API endpoint: `{API_BASE_URL}`")
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            try:
                sign_in(username.strip(), password)
                st.rerun()
            except Exception as exc:  # Surface API validation and connectivity issues in the UI.
                st.error(str(exc))


def status_label(value):
    return str(value or "").replace("_", " ").title()


def vehicle_label(vehicles, vehicle_id):
    match = next((item for item in vehicles if item["id"] == vehicle_id), None)
    return match["label"] if match else str(vehicle_id)


def render_overview(data):
    dashboard = data["dashboard"]
    vehicles = dashboard.get("vehicles", {})
    statuses = vehicles.get("by_status", {})
    trips = dashboard.get("trips", {})
    st.title(f"Welcome, {st.session_state.get('username', 'Fleet manager')}")
    st.caption("Fleet activity and health at a glance.")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Vehicles", vehicles.get("total", 0))
    metric_columns[1].metric("On the road", statuses.get("in_use", 0))
    metric_columns[2].metric("Available", statuses.get("available", 0))
    metric_columns[3].metric("Service due", vehicles.get("service_due", 0))
    st.subheader("Trip activity")
    trip_columns = st.columns(3)
    trip_columns[0].metric("Active", trips.get("active", 0))
    trip_columns[1].metric("Scheduled", trips.get("scheduled", 0))
    trip_columns[2].metric("Completed", trips.get("completed", 0))
    st.subheader("Fleet availability")
    status_frame = [{"Status": status_label(key), "Vehicles": value} for key, value in statuses.items()]
    if status_frame:
        st.bar_chart(status_frame, x="Status", y="Vehicles", color="#3465e8")
    st.subheader("Recent trips")
    trip_rows = sorted(data["trips"], key=lambda trip: trip.get("created_at") or "", reverse=True)[:10]
    st.dataframe([
        {
            "Trip": trip["id"][:8].upper(),
            "Vehicle": trip.get("vehicle_label") or vehicle_label(data["vehicles"], trip["vehicle"]),
            "Driver": trip.get("driver_name", ""),
            "Route": f"{trip['origin']} → {trip['destination']}",
            "Status": status_label(trip["status"]),
            "Created": trip.get("created_at", "")[:10],
        }
        for trip in trip_rows
    ], use_container_width=True, hide_index=True)


def render_vehicles(data):
    st.title("Vehicles")
    search = st.text_input("Search vehicles", placeholder="Label, VIN, make, model")
    status_filter = st.selectbox("Filter by status", ["All", "Available", "In use", "Maintenance", "Inactive"])
    items = data["vehicles"]
    if search:
        query = search.casefold()
        items = [item for item in items if query in " ".join(str(item.get(key, "")) for key in ("label", "vin", "make", "model")).casefold()]
    if status_filter != "All":
        expected = status_filter.casefold().replace(" ", "_")
        items = [item for item in items if item["status"] == expected]
    st.dataframe([
        {"Vehicle": v["label"], "Make / model": f"{v['make']} {v['model']}", "VIN": v["vin"], "Status": status_label(v["status"]), "Odometer (km)": v["odometer_km"], "Service due": "Due" if v["service_due"] else "On schedule", "Year": v["year"]}
        for v in items
    ], use_container_width=True, hide_index=True)
    with st.expander("Add a vehicle"):
        with st.form("add_vehicle"):
            label = st.text_input("Label")
            make, model = st.columns(2)
            make_value = make.text_input("Make")
            model_value = model.text_input("Model")
            year, vin = st.columns(2)
            year_value = year.number_input("Year", min_value=1900, max_value=2100, value=2024)
            vin_value = vin.text_input("VIN", max_chars=17)
            odometer = st.number_input("Odometer (km)", min_value=0, value=0)
            if st.form_submit_button("Add vehicle", type="primary"):
                try:
                    api_request("/vehicles/", "POST", {"label": label, "make": make_value, "model": model_value, "year": year_value, "vin": vin_value, "odometer_km": odometer})
                    st.success("Vehicle added.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)


def render_drivers(data):
    st.title("Drivers")
    st.dataframe([
        {"Driver": driver["name"], "License": driver["license_number"], "Status": "Active" if driver["active"] else "Inactive"}
        for driver in data["drivers"]
    ], use_container_width=True, hide_index=True)
    with st.expander("Add a driver"):
        with st.form("add_driver"):
            name = st.text_input("Full name")
            license_number = st.text_input("License number")
            if st.form_submit_button("Add driver", type="primary"):
                try:
                    api_request("/drivers/", "POST", {"name": name, "license_number": license_number, "active": True})
                    st.success("Driver added.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)


def render_trips(data):
    st.title("Trips")
    active_filter = st.selectbox("Show trips", ["All", "Scheduled", "Active", "Completed", "Cancelled"])
    trips = data["trips"]
    if active_filter != "All":
        trips = [trip for trip in trips if trip["status"] == active_filter.casefold()]
    for trip in trips:
        with st.container(border=True):
            title, action = st.columns([4, 1])
            title.markdown(f"**{trip.get('vehicle_label') or vehicle_label(data['vehicles'], trip['vehicle'])}** · {status_label(trip['status'])}")
            title.caption(f"{trip['origin']} → {trip['destination']} · {trip.get('driver_name', '')}")
            if trip["status"] == "scheduled" and action.button("Start", key=f"start-{trip['id']}"):
                try:
                    api_request(f"/trips/{trip['id']}/start/", "POST", {})
                    st.success("Trip started.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)
            elif trip["status"] == "active" and action.button("Complete", key=f"complete-{trip['id']}"):
                st.session_state.completing_trip = trip["id"]
    if st.session_state.get("completing_trip"):
        trip_id = st.session_state.completing_trip
        trip = next((item for item in data["trips"] if item["id"] == trip_id), None)
        if trip is None:
            st.session_state.pop("completing_trip", None)
            st.warning("That trip is no longer in the current list. Refresh and try again.")
            return
        vehicle = next((item for item in data["vehicles"] if trip and item["id"] == trip["vehicle"]), None)
        with st.form("complete_trip"):
            end_odometer = st.number_input("Final odometer (km)", min_value=trip.get("start_odometer_km") or 0, value=(vehicle or {}).get("odometer_km", 0))
            if st.form_submit_button("Confirm completion", type="primary"):
                try:
                    api_request(f"/trips/{trip_id}/complete/", "POST", {"end_odometer_km": end_odometer})
                    del st.session_state.completing_trip
                    st.success("Trip completed.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)
    with st.expander("Schedule a trip"):
        available_vehicles = [item for item in data["vehicles"] if item["status"] == "available"]
        active_drivers = [item for item in data["drivers"] if item["active"]]
        with st.form("schedule_trip"):
            if not available_vehicles:
                st.warning("There are no available vehicles.")
            if not active_drivers:
                st.warning("There are no active drivers.")
            vehicle = st.selectbox("Vehicle", available_vehicles, format_func=lambda item: f"{item['label']} · {item['make']} {item['model']}", disabled=not available_vehicles)
            driver = st.selectbox("Driver", active_drivers, format_func=lambda item: item["name"], disabled=not active_drivers)
            origin = st.text_input("Origin")
            destination = st.text_input("Destination")
            if st.form_submit_button("Schedule trip", type="primary"):
                try:
                    api_request("/trips/", "POST", {"vehicle": vehicle["id"], "driver": driver["id"], "origin": origin, "destination": destination})
                    st.success("Trip scheduled.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)


def render_maintenance(data):
    st.title("Maintenance")
    st.dataframe([
        {"Vehicle": vehicle_label(data["vehicles"], record["vehicle"]), "Service": record["description"], "Date": record["service_date"], "Odometer (km)": record["odometer_km"], "Cost": record.get("cost") or "—"}
        for record in data["maintenance"]
    ], use_container_width=True, hide_index=True)
    if not data["vehicles"]:
        st.info("Add a vehicle before recording maintenance.")
        return
    with st.expander("Log service"):
        with st.form("log_service"):
            vehicle = st.selectbox("Vehicle", data["vehicles"], format_func=lambda item: item["label"])
            description = st.text_input("Service description")
            service_date = st.date_input("Service date", value=date.today())
            odometer = st.number_input("Odometer (km)", min_value=0, value=vehicle["odometer_km"] if data["vehicles"] else 0)
            cost = st.number_input("Cost", min_value=0.0, value=0.0, step=10.0)
            if st.form_submit_button("Save service record", type="primary"):
                try:
                    payload = {"vehicle": vehicle["id"], "description": description, "service_date": service_date.isoformat(), "odometer_km": odometer}
                    if cost:
                        payload["cost"] = cost
                    api_request("/maintenance/", "POST", payload)
                    st.success("Service record saved.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)


def render_locations(data):
    st.title("Live locations")
    st.dataframe([
        {"Vehicle": vehicle_label(data["vehicles"], item["vehicle"]), "Trip": item.get("trip") or "—", "Latitude": item["latitude"], "Longitude": item["longitude"], "Recorded at": item["recorded_at"]}
        for item in data["locations"]
    ], use_container_width=True, hide_index=True)
    if not data["vehicles"]:
        st.info("Add a vehicle before sending a location update.")
        return
    active_trips = [item for item in data["trips"] if item["status"] == "active"]
    with st.expander("Submit a location update"):
        with st.form("location_update"):
            vehicle = st.selectbox("Vehicle", data["vehicles"], format_func=lambda item: item["label"])
            active_trip = st.selectbox("Active trip (optional)", [None] + active_trips, format_func=lambda item: "No trip" if item is None else f"{item.get('origin')} → {item.get('destination')}")
            latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=37.7749, format="%.6f")
            longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-122.4194, format="%.6f")
            if st.form_submit_button("Send update", type="primary"):
                try:
                    payload = {"vehicle": vehicle["id"], "latitude": latitude, "longitude": longitude}
                    if active_trip:
                        payload["trip"] = active_trip["id"]
                    api_request("/locations/", "POST", payload)
                    st.success("Location update received.")
                    st.rerun()
                except Exception as exc:
                    display_error(exc)


def main():
    st.sidebar.markdown("# 🚙 FleetPulse")
    st.sidebar.caption("Fleet operations command center")
    st.sidebar.caption(f"API: `{API_BASE_URL}`")
    if not st.session_state.get("access_token"):
        display_login()
        return

    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.get('username', 'Fleet manager')}**")
        if st.button("Sign out", use_container_width=True):
            for key in ("access_token", "refresh_token", "username", "data", "completing_trip"):
                st.session_state.pop(key, None)
            st.rerun()
        st.divider()
        section = st.radio("Workspace", ["Overview", "Vehicles", "Trips", "Drivers", "Maintenance", "Locations"], label_visibility="collapsed")
        refresh = st.button("↻  Refresh data", use_container_width=True)

    if refresh or "data" not in st.session_state:
        try:
            st.session_state.data = load_data()
        except Exception as exc:
            st.error(str(exc))
            if "401" in str(exc):
                st.session_state.pop("access_token", None)
                st.info("Please sign in again to renew your access token.")
            return
    data = st.session_state.data
    try:
        {"Overview": render_overview, "Vehicles": render_vehicles, "Trips": render_trips, "Drivers": render_drivers, "Maintenance": render_maintenance, "Locations": render_locations}[section](data)
    except Exception as exc:
        st.error(str(exc))


main()
