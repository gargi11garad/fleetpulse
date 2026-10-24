## Deploy directly to Streamlit Community Cloud

The Streamlit app runs the FleetPulse UI and Django data models in one Streamlit process. No external API host or `API_BASE_URL` secret is required. The app creates/migrates its SQLite demo database and seeds sample fleet records when it starts.

1. Push this repository to GitHub.
2. In [Streamlit Community Cloud](https://share.streamlit.io/), choose **Create app**.
3. Select `gargi11garad/fleetpulse`, branch `main`, and main file `streamlit_app.py`.
4. Choose a public app URL and click **Deploy**.
5. Sign in with `fleet-manager` / `FleetPulseDemo!ChangeMe`.

This is a shared portfolio demo with sample data. Do not enter real fleet or personal information. Streamlit Community Cloud does not guarantee persistence of local file storage, so changes to the SQLite demo data may be cleared when the app restarts. See [Streamlit's data connection guidance](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data) for details.

## Local Streamlit UI

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The same sign-in works locally after the app's first startup migration and demo seed.

## Local REST API

For backend/API development, use the Django server separately:

```powershell
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The API is at `http://127.0.0.1:8000/api/v1/`, docs at `/api/docs/`, and the Django dashboard at `/`. The SQLite fallback is used by default; configure `DATABASE_URL` for PostgreSQL.

Never commit `.env`, `db.sqlite3`, or real credentials. The public demo login is intentionally for sample data only.
