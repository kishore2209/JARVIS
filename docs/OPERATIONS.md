# Local operation and recovery

This is a single-owner development/paper deployment. It does not establish production, regulatory, broker-execution or mobile-delivery readiness.

## Run the dashboard from one server

Use Python 3.12 and Node 22 or newer compatible with the frontend lockfile. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
export JARVIS_DB_ENABLED=true
export JARVIS_SERVE_UI=true
python -m jarvis_server
```

Open http://127.0.0.1:8000. In PowerShell, activate with `.venv\Scripts\Activate.ps1` and set variables with `$env:JARVIS_DB_ENABLED="true"` and `$env:JARVIS_SERVE_UI="true"`. The launcher reads process environment variables; `.env.example` is a reference and is not auto-loaded.

For development, leave `JARVIS_SERVE_UI=false`, start the backend and run `npm run dev` in `frontend`. Vite proxies `/api` and `/health` to the backend. The built dashboard uses the same origin by default. `VITE_API_BASE_URL` is an optional build-time override.

For remote access, configure a TLS reverse proxy, explicit `JARVIS_ALLOWED_HOSTS` and `JARVIS_CORS_ORIGINS`, and a server-side `JARVIS_API_TOKEN` of at least 32 characters. Enter only that owner access token in the Connection panel. It is held in page memory, not local/session storage; refresh requires reconnecting. A non-loopback backend binding without a token is rejected. No public deployment is configured in this milestone. Do not expose the unauthenticated local backend through a proxy.

## Durable read-only tasks

Set the same database path in both server and worker environments:

```bash
export JARVIS_DB_ENABLED=true
export JARVIS_DB_PATH=data/jarvis.db
python -m jarvis_worker
```

`--once` performs one scheduled-job tick and at most one queued task, then exits. The worker supports `DAILY_PLAN`, `KNOWLEDGE_RETRIEVAL`, and `RESEARCH_SCAN` request tasks. It does not place orders or send messages. Queued tasks are submitted from the Tasks panel or `POST /api/v1/tasks`. Idempotency keys bind the exact input and budget. Each handler consumes budget before a unit of work. Cancellation is checked between instruments; a running deterministic calculation is not forcibly interrupted. Late results are rejected. An interrupted task expires into FAILED rather than being silently replayed. Recovery requires a new explicit submission.

The daily and morning scheduled reports still lack live market/news/flow inputs and explicitly report that missing coverage. Local alerts have no WhatsApp/email/push delivery.

## Source-grounded knowledge

The Knowledge panel accepts text and a source reference. It does not crawl a supplied URL. Retrieval uses a local BM25 lexical baseline, current document permissions, versions, source revocation, expiry and ancestry checks. Results include exact character offsets, content hashes and citation IDs. Use `search knowledge: your query` in Chat for quoted source excerpts, or the allowlisted `knowledge.search` tool. No retrieved source text can authorize an action. Capacity is bounded to 1,000 documents of at most 100,000 characters; embeddings, PDF ingestion and retrieval-quality benchmarking remain future work.

## Read-only Angel One data

Install `requirements-broker.txt`, set `JARVIS_MARKET_PROVIDER=ANGEL_ONE` and the server-side credentials listed in `.env.example`. Authentication happens on the first data request, not startup. The TOTP value must be current; session refresh/reconnect is not automated. Call the analysis API with the verified exchange/token/symbol and requested interval. The Analysis form requires an explicit provider token and clears it when the symbol or exchange changes. Verify the symbol/exchange/token against your provider instrument master; automatic instrument resolution is not implemented.

There is no fallback from a failed real request to mock data. The LTP endpoint lacks a verified exchange timestamp in this adapter and is marked not fresh. Historical candles validate geometry, future times and conflicting duplicates. Account access and entitlements have not been tested here. LIVE order execution remains unsupported.

## Configured MCP resources

`JARVIS_MCP_HTTP_ENABLED=true` enables a fixed administrator-supplied HTTPS endpoint in `JARVIS_MCP_ENDPOINT`. Set `JARVIS_MCP_RESOURCES` to a JSON alias map such as `{"daily":"report://daily"}`. Optional `JARVIS_MCP_TOKEN` is server-side only. The connector ID is `mcp.remote`; capabilities are `mcp.resources.list` and `mcp.resource.read` with `{"resource":"daily"}`.

The transport negotiates protocol 2025-06-18 or 2025-03-26, handles JSON and bounded SSE responses, validates response IDs, and closes sessions. Server discovery cannot expand the configured resource allowlist. Redirects, server requests, tool calls, sampling, elicitation, stdio and binary resources are unsupported. It uses a 10-second network timeout and a checked 25-second request budget. No OAuth onboarding or live service interoperability was tested. The offline `mcp.demo` remains separate.

Protocol references: [transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports), [lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle).

## Encrypted backups and restore drill

Generate a Fernet key and keep it in a secret manager or another protected location, separate from snapshots and the repository. Supply it through `JARVIS_BACKUP_KEY`; no key is accepted in command arguments or printed by the backup command. The [Fernet documentation](https://cryptography.io/en/latest/fernet/) describes key generation and rotation.

```bash
python -m jarvis_backup backup data/jarvis.db backups/snapshot.enc
python -m jarvis_backup restore backups/snapshot.enc data/restored.db
```

Both destinations must be new files. The backup uses SQLite's online backup mechanism and encrypts a checksummed, schema-versioned snapshot. The local implementation is bounded to a 64 MiB database. Restore verifies authenticated ciphertext, hash, schema and database integrity before creating a new database. Restored paper trading has its kill switch enabled; scheduled jobs are disabled and unfinished tasks fail with `RESTORED_REQUIRES_RESUBMISSION`. Existing files are never overwritten.

Local operating targets, not measured service guarantees: take a backup at least daily (RPO target 24 hours), and aim to restore read-only operation within 30 minutes (RTO target). Actual data loss equals time since the chosen successful snapshot. Retention, off-device copies, key rotation and scheduled backups are operator responsibilities. Test a restore into a separate path before relying on a backup. Compare records, balances and task history, retain the emitted timestamps/duration, and keep the original database until reconciliation is complete. The automated fixture drill is not evidence of production RTO.

The active SQLite database is not encrypted by this feature; use operating-system disk encryption. Broker reconciliation is unavailable because live execution is not implemented. Do not unlock financial actions based only on a successful restore.

## Incident actions

| Incident | Immediate action | Recovery evidence |
|---|---|---|
| Stale or failed data feed | Stop relying on current-market outputs; leave real-provider failures visible | Correct instrument identity, timestamp, adjustment state and source after reconnection |
| Broker outage or uncertain account state | Keep execution disabled; inspect the broker directly | Broker-state reconciliation before any future live execution feature is enabled |
| Gemini outage | Use deterministic analysis and explicit knowledge retrieval | Provider configuration and a bounded successful test; no fabricated fallback facts |
| Database failure | Stop server/worker writes; preserve the failed database; restore into a new path | Integrity check, schema, paper checkpoint, records and history comparison |
| Notification failure | Inspect local reports/alerts manually | Delivery is not implemented; do not label local alert creation as delivery |

## Trading reviews

Daily/weekly/monthly periods use Asia/Kolkata boundaries. Reviews operate on closed paper trades and report sample size, P&L before costs, R, expectancy, closed-trade drawdown, strategy/regime groups and owner-declared rule adherence. `POST /api/v1/paper/review-notes` records versioned retrospective notes tied to an existing position. Profitable trades can violate rules; losing trades can follow them. Lessons remain candidates and are not automatically promoted to memory. Fees, slippage, missed setups and intratrade drawdown remain missing evidence.
