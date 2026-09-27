# Render deployment

Single Python web service serves the API and built React UI at one HTTPS origin.
Build: `pip install -r requirements-cloud.txt && npm --prefix frontend ci && npm --prefix frontend run build`
Start: `uvicorn cloud_app:app --host 0.0.0.0 --port $PORT`
Use Python 3.12 and Node 22. Keep one worker for the in-memory runtime.

All routes except `/health` require HTTP Basic authentication over Render HTTPS.
Username: `jarvis`. Password: `JARVIS_WEB_PASSWORD` in Render Environment; a random
password is generated during initial provisioning. Retrieve it from your own
Render dashboard or replace it there with a strong password (at least 24 characters).
Never put credentials in Git, a URL, or the frontend bundle.

Initial service is free-tier, with Gemini and external connectors disabled and no
persistent database. Analysis uses the existing mock provider. State can reset on
restart/redeploy and free-tier sleeping is unsuitable for always-on monitoring.
Live trading is unsupported. Do not enable real account integrations until durable
storage, production authentication and provider verification are complete.

Checks: `/health` returns 200 without credentials; root and API return 401 without
credentials; owner can open UI; cross-origin writes return 403. Frontend uses same
origin in production and localhost backend in development.
