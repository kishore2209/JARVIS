# J.A.R.V.I.S v1 Foundation

Personal AI Operating System — engineering baseline.

## Current scope
This package contains the foundation built so far:
- Core command processing
- AI intent brain
- Persistent memory
- Market-data snapshot structure
- OHLCV model
- Deterministic quantitative modules:
  EMA 20/50/200, RSI 14, swing points, market structure, trend, momentum,
  volume, support/resistance, VWAP, MACD
- Initial project folders for future agents, voice, tests and integrations

## Important
This is a read-only engineering foundation. It does NOT place live trades.
No API keys, passwords, broker credentials, or secrets are included.

## Setup
```powershell
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python jarvis_core.py
```

## Roadmap
1. Foundation verification
2. Real market-data adapter (Angel One SmartAPI)
3. Historical OHLCV normalization and freshness controls
4. Quant engine expansion
5. Full active NSE F&O analysis engine
6. Strategy/confluence engine
7. Portfolio and risk firewall
8. Paper execution
9. AI orchestration and tools
10. UI/voice/mobile integrations
11. Controlled production deployment

Architecture principle:
LLM = reasoning/orchestration/explanation.
Python Quant Engine = deterministic numerical calculations.
Risk Firewall = safety/validation.
Broker Adapter = execution boundary.
