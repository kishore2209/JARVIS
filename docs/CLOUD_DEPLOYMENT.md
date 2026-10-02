# Render deployment

The cloud configuration is prepared; no service has been provisioned or public URL verified.

## Proposed service

Use `render.yaml`: one Docker Starter web service in Singapore and a 1 GiB persistent disk mounted at `/var/data`. Review the current Render billing estimate before creating these paid resources. Automatic deployments are disabled. The selected branch is `codex/full-srd-milestones`.

The image builds the React dashboard and runs the Python API and read-only worker under one supervisor. Both share persistent SQLite storage. Either process exiting causes both to stop so the platform can restart the service. This is a single-instance deployment; do not scale replicas or attach an independent worker to this database.

Render supplies the HTTPS hostname. The launcher restricts allowed hosts and browser origins to it, requires an owner token, initializes the database, and rejects missing dashboard assets. A custom domain requires `JARVIS_PUBLIC_URL=https://your-domain` and platform domain configuration.

## Deployment and acceptance

1. Publish the reviewed branch, select this repository in Render Blueprints, and review the plan and disk estimate.
2. Deploy the blueprint. Verify that the nonroot container user can write the mounted disk; stop deployment if initialization fails.
3. Retrieve the generated `JARVIS_API_TOKEN` privately from the Render environment dashboard. Enter it in the app's Connection panel. Do not put it in source code, chat, URLs, or frontend environment variables.
4. Verify HTTPS dashboard and `/health`; anonymous API calls must return 401. Verify authenticated status, knowledge storage, and a DAILY_PLAN task.
5. Restart the service and verify saved records and kill-switch state persist. Check API and worker logs, task completion, graceful shutdown, and disk space.
6. Exercise encrypted backup and restore per OPERATIONS.md before storing important data. Keep recovery keys separate and backups off the service disk. A deployment rollback does not roll back database state.

Gemini is disabled and market data is MOCK initially. Optional provider secrets belong only in server-side environment configuration. Their activation and external validation remain separate work. No live trading is enabled. Paid disk deployments can interrupt service; no high-availability guarantee is made.

## Local validation

On 2026-09-26: 67 backend scripts, 37 frontend tests, TypeScript and production UI build passed. `python scripts/smoke_cloud.py` exercised the real API/worker supervisor, anonymous denial, authenticated access, durable task execution, knowledge persistence across restart, and clean shutdown with temporary storage. Docker image build, Render disk permissions, public TLS, and hosted restart behavior still require deployment validation.

References: https://render.com/docs/blueprint-spec and https://render.com/docs/disks .
