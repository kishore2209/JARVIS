# J.A.R.V.I.S v1.0.0

Personal AI operating system foundation focused on deterministic market analysis, guarded automation, and safe project tooling.

## Implemented features

### Backend platform
- FastAPI service with health, readiness, metrics, diagnostics, chat, analysis, portfolio, paper-trading, backtest, memory, tool, workflow, connector, governance, and project endpoints
- Deterministic runtime composition with optional SQLite persistence for memory, workflows, and project workspaces
- CLI entry points for local runtime access

### Market analysis and trading safety
- OHLCV data model plus deterministic analysis for market context, underlying analysis, confluence, trend, momentum, volume, support/resistance, VWAP, MACD, RSI, swing points, and multi-strategy evidence
- Historical replay backtesting
- Risk validation plus paper-trading execution with explicit user authorization
- Automation controller with explicit tick execution
- Portfolio and paper-account state handling

### Frontend
- React + Vite dashboard for diagnostics, chat, analysis, portfolio, memory, tools, workflows, projects, connectors, governance, automation, and paper trading
- Voice input/output panel with browser speech-recognition and speech-synthesis adapters
- Frontend tests for core views and safety flows

### Integrations and project tooling
- Optional server-side Gemini adapter
- Fixed-host GitHub and Jira connectors with bounded, read-only access by default
- Project intelligence snapshots that correlate Jira issue keys with GitHub pull requests
- Delivery analysis and brief generation over project snapshots
- Allowlisted internal tools and restart-safe workflows with exact-plan approval gates

## Safety boundaries
- LIVE trading is unsupported and remains disabled
- No broker credentials, API keys, or secrets belong in the repository
- Frontend credential input is unsupported; integrations are server-side only
- Automation does not auto-run on startup and paper execution still requires explicit authorization
- External connector access is allowlisted and bounded

## Setup

### Backend
```powershell
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m jarvis_server
```

### Frontend
```powershell
Set-Location frontend
npm ci
npm run dev
```

The frontend targets `http://127.0.0.1:8000` by default.

## Validation
- Backend test scripts live in `tests/`
- Frontend validation uses TypeScript, Vitest, and Vite build checks from `frontend/`

## Roadmap and current scope
- The sections above describe the code currently implemented in this repository.
- Planned future phases are tracked separately in `docs/ROADMAP.md`.
- Roadmap items are goals, not shipped functionality.

## Documentation
- `docs/SETUP.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/releases/v1.0.0.md`
