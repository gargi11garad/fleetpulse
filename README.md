# FleetPulse

FleetPulse is a portfolio backend for fleet and mobility operations. It models vehicles, drivers, trips, GPS updates, and maintenance history, then exposes those workflows through a documented REST API.

## Features

- Django REST Framework API with JWT authentication and staff-only writes
- PostgreSQL in Docker; SQLite fallback for local development
- Vehicle and driver CRUD, filtering, search, ordering, and pagination
- Transactional trip start/completion with vehicle availability and odometer updates
- GPS location ingestion and latest-location lookup
- Maintenance records, service-due flag, and fleet dashboard summary
- OpenAPI schema and Swagger UI
- Responsive operations dashboard served at `/` with vehicle, driver, trip, and maintenance views
- Basic anonymous and authenticated API rate limits

## Run locally

Requires Python 3.11+ and PostgreSQL. For a simple SQLite setup, remove `DATABASE_URL` from `.env`.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

To run with Docker, copy `.env.example` to `.env`, then run `docker compose up --build`. For Docker, keep the provided `DATABASE_URL` (the `db` host is the Compose service). The API is at `http://localhost:8000`, interactive documentation at `/api/docs/`, and admin at `/admin/`.

## Web interface

Open `http://127.0.0.1:8000/` and sign in with a Django user. For the seeded demo, use `fleet-manager` / `FleetPulseDemo!ChangeMe`. The dashboard summarizes the fleet, while the navigation provides vehicle, trip, driver, and maintenance tables. Staff users can create records and run trip start/completion actions from the interface. The browser stores the short-lived access and refresh tokens in local storage for this local demo.

## Authentication

Obtain a token with `POST /api/v1/auth/token/` using a Django username and password:

```json
{"username":"admin","password":"your-password"}
```

Pass `Authorization: Bearer <access>` on API requests. Authenticated users can read. Staff users can create and change fleet records. Create a staff user with `createsuperuser` or through Django admin.

`python manage.py seed_demo` creates a sample fleet manager, vehicles, driver, and scheduled trip. The demo login is `fleet-manager` / `FleetPulseDemo!ChangeMe`; change or remove it before exposing the app outside a local demo.

## Deploy

This repository includes a Streamlit operations console and a Render Blueprint for the Django API. Streamlit Community Cloud runs the Streamlit interface; the Django API and PostgreSQL database need a separate public host. The included `render.yaml` defines that API service and database. Free hosting is suitable for a portfolio demo and may sleep or have storage limits.

1. Create a GitHub repository and push this project. `.env`, the local SQLite database, and local dependency folders are excluded by `.gitignore`.
2. In Render, create a Blueprint from the repository and set `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, and optionally `BOOTSTRAP_ADMIN_EMAIL` when prompted. Render builds the API, applies migrations, creates the initial staff account, and starts Gunicorn. Copy the resulting API URL, ending in `/api/v1`.
3. Connect GitHub to Streamlit Community Cloud and deploy `streamlit_app.py` from the repository's default branch. Add a Streamlit secret named `API_BASE_URL`, for example `https://your-fleetpulse-api.onrender.com/api/v1`.
4. Sign in to the Streamlit app with the bootstrap account created in Render.

For local Streamlit development, install `requirements.txt`, start Django in one terminal with `python manage.py runserver`, then start the interface in another with `streamlit run streamlit_app.py`.

Never commit `.env`, `db.sqlite3`, Streamlit secrets, or a real account password. The local `seed_demo` credentials are for development only; the Render deployment does not run that demo seeder.

## Main endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/token/` | Obtain access and refresh tokens |
| GET/POST | `/api/v1/vehicles/` | List or create vehicles |
| GET | `/api/v1/vehicles/{id}/latest_location/` | Fetch latest vehicle coordinates |
| GET/POST | `/api/v1/drivers/` | List or create drivers |
| GET/POST | `/api/v1/trips/` | List or schedule trips |
| POST | `/api/v1/trips/{id}/start/` | Start a scheduled trip |
| POST | `/api/v1/trips/{id}/complete/` | Complete an active trip; body includes `end_odometer_km` |
| GET/POST | `/api/v1/locations/` | Read or ingest GPS updates |
| GET/POST | `/api/v1/maintenance/` | Read or record vehicle service |
| GET | `/api/v1/dashboard/` | Fleet status summary |
| GET | `/api/schema/` and `/api/docs/` | OpenAPI schema and Swagger UI |

List endpoints accept `page`, `page_size` (maximum configured by DRF), filters such as `?status=active`, `?vehicle=<uuid>`, and search via `?search=...` where enabled.

## Example workflow

1. Create a vehicle and driver as a staff user.
2. Create a trip referencing their UUIDs, with `origin` and `destination`.
3. Call the trip's `/start/` action. FleetPulse locks and checks the vehicle, marks the trip active, and records the starting odometer.
4. Post location updates to `/api/v1/locations/` with vehicle/trip IDs and coordinates.
5. Complete the trip with an `end_odometer_km`. The vehicle returns to available or is flagged for maintenance when its service interval is reached.
6. Read `/api/v1/dashboard/` or the vehicle latest-location endpoint.

## Design notes

- UUIDs make externally exposed entity identifiers harder to enumerate.
- Trip transitions use database transactions and row locks to prevent two concurrent starts from claiming the same vehicle.
- A composite location index supports the common latest-location-by-vehicle query.
- Location coordinates are bounded by serializer field validators; updates cannot be attached to another vehicle's trip.
- For production deployment, set a strong `DJANGO_SECRET_KEY`, disable debug, configure TLS/proxy settings, backups, monitoring, and a managed secret store. Consider adding tenant scoping before serving multiple fleet customers.
