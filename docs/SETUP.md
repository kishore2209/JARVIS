# J.A.R.V.I.S Runtime Setup

## Prerequisites

- Python 3.14.x (the runtime used for validation)
- Node.js/npm compatible with the checked-in frontend lockfile
- No broker or Gemini credentials are required for deterministic local mode

## Backend

```powershell
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m jarvis_server
```

The canonical ASGI command is also:

```powershell
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Health and readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/readiness?workflow=DETERMINISTIC_CHAT'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/readiness?workflow=LIVE'
Invoke-RestMethod http://127.0.0.1:8000/api/v1/diagnostics
```

## Frontend

```powershell
Set-Location frontend
npm ci
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000` by default. Set `VITE_API_BASE_URL` only when the backend is hosted elsewhere. Production output is created with `npm run build` in `frontend/dist`; the frontend is served separately in this phase.

## Configuration

Copy `.env.example` to `.env`. `JARVIS_LLM_ENABLED=false` keeps Gemini disabled. To enable the optional server-side Gemini adapter, set `JARVIS_LLM_ENABLED=true` and provide `GEMINI_API_KEY`; the key is never sent to the frontend or returned by diagnostics. Angel One variables are server-side only and are not required for the mock/offline runtime.

Set `JARVIS_DB_ENABLED=true` to create the configured SQLite database at `JARVIS_DB_PATH`. Runtime databases are ignored by Git. Startup restores no jobs automatically into execution; automation remains explicit-tick only.

Personal memory uses the same SQLite store when database persistence is enabled. Memory writes are explicit, bounded, and filtered for credentials and financial authority. With persistence disabled, the memory service remains available in-process but is not durable.

Workflows use the same SQLite store when persistence is enabled. Workflow metadata and step state restore after restart, but protected tool plans and approvals expire across restart; no workflow auto-resumes or executes during startup. A new explicit approval and resume action is required.

Phase W connectors are static, server-side allowlists and read-only by design. The included MCP connector uses an offline fake transport for validation; no network call, arbitrary URL, credential input, subprocess launch, or remote MCP tool execution is available. Future connectors must register fixed capabilities and remain behind ToolService and WorkflowService policy.

The optional GitHub connector is read-only. Set `JARVIS_GITHUB_ENABLED=true` and provide `GITHUB_TOKEN` only on the server when using a least-privilege, read-only fine-grained token. `GITHUB_API_BASE_URL` is fixed to `https://api.github.com`; no issue/PR/file/branch writes, merges, commits, Actions dispatches, or frontend credential input are supported. Automated GitHub tests use fake transport; real access is manual and opt-in only.

GitHub collaboration writes remain disabled by default. Phase Y allows only issue creation, issue comments, and pull-request conversation comments when `JARVIS_GITHUB_WRITE_ENABLED=true`; each action requires a plan, preview, exact approval, and separate explicit execution. Merge, push, commit, branch, repository administration, and workflow dispatch remain blocked.

The optional Jira connector is read-only in Phase AA. Configure `JARVIS_JIRA_ENABLED=true`, `JIRA_BASE_URL=https://tenant.atlassian.net`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` only on the server. Supported capabilities are project list/read, issue read, and bounded structured issue search. Raw JQL and all Jira writes are unavailable; automated tests use fake transport and perform no network calls.

Project Intelligence uses explicit workspace mappings between a Jira project and GitHub repository. Correlation requires deterministic Jira issue-key references in branch, commit, PR title, or PR body evidence. It does not use fuzzy semantic matching, does not mutate Jira/GitHub state, and refreshes only through an explicit project snapshot action.

## Validation

```powershell
python tests/verify_runtime.py
python tests/test_runtime_config.py
python tests/test_runtime_app.py
python tests/test_llm_foundation.py
python tests/test_llm_routing.py
python tests/test_gemini_adapter.py
```

Run the full backend and frontend suites from the repository instructions before deployment. No validation command makes broker calls or requires Gemini network access.

## Operational limits

- LIVE trading remains unsupported.
- There is no automatic scheduler or background trading loop.
- Voice support depends on browser capabilities and remains push-to-talk.
- Gemini is optional and requires external connectivity only when explicitly enabled.
- TLS, reverse proxy, process supervision, and production secret injection remain deployment-environment responsibilities.
