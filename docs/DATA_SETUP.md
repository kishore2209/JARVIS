# Read-only data setup

Default: **synthetic MOCK data**, not current market prices. No broker account
connection was made during implementation. Provider failures never fall back to mock.

## Historical files

Open **Analysis > Historical candle file**, choose an interval, and upload CSV or
JSON with 200–10,000 candles, at most 5 MB. Required columns:

```csv
symbol,exchange,timestamp,open,high,low,close,volume,source
TEST,NSE,2026-01-02T09:15:00+05:30,100,102,99,101,1000,EXAMPLE_ONLY
```

This row is a schema example, not market data. Use an authorized broker export.
Prices must be finite and positive, volume a nonnegative integer, low <= open/close
<= high. Timestamps must include timezone, be unique, chronological and not future.
All rows must share one instrument, exchange and source. Source labels are declarations,
not independently verified authenticity. Corporate actions and session gaps are not certified.

JSON accepts an array of candle objects or `{"interval":"15m","candles":[...]}`.
Envelope interval must match the chosen interval. Import intervals: 1m, 3m, 5m, 15m,
30m, 1h, 1d. Output includes SHA-256, data timestamp, indicators, warnings, and a
chart of the last 240 bars. Independent Nifty/sector/OI/news context remains missing.

CLI:

```bash
python analyze_candles.py /path/to/candles.csv --interval 15m
```

API: `POST /api/v1/analysis/file` with `content` (file text), `format` (`csv`/`json`),
and `interval`. Server file paths are not accepted from HTTP requests.

For existing provider analysis endpoints, configure a fixed server file:

```bash
export JARVIS_DATA_PROVIDER=FILE
export JARVIS_CANDLE_FILE=/absolute/path/to/candles.json
export JARVIS_CANDLE_INTERVAL=15m
python -m jarvis_server
```

Variables must be present in the process environment. Copying `.env` alone does
not load it. The file is loaded at runtime creation, so restart after replacing it.

## Angel One

Set `JARVIS_DATA_PROVIDER=ANGEL_ONE` and the existing server-only variables
`ANGEL_ONE_API_KEY`, `ANGEL_ONE_CLIENT_CODE`, `ANGEL_ONE_PIN`, and current
`ANGEL_ONE_TOTP`. Never paste credentials into chat, upload them as data, or commit
them. Authentication occurs only on an explicit read. Use a current instrument token
from the broker instrument master in the Analysis screen.

Supported broker intervals: 1m, 5m, 15m, 30m, 1h, 1d. The 3m import option does not
claim broker support. The requested interval is forwarded; still-forming bars are
excluded. Errors are sanitized and no mock fallback occurs. `/api/v1/data/status`
reports configuration, not verified connectivity. Successful configuration is not
a successful account-backed test.

Session refresh, rate limits, calendar-aware freshness, corporate actions, current
instrument identity checks and account-backed smoke tests remain production work.
SDK request shape reference checked during implementation:
https://github.com/angel-one/smartapi-python/blob/main/test/api_test.py

## Paper stop control

`POST /api/v1/paper/kill-switch` with `{"halted":true}` blocks new orders and fills.
`GET` returns the state. Resume requires `{"halted":false,"explicit_user_authorization":true}`.
State is stored atomically in `paper-safety.json` beside the configured database path;
corrupt state blocks execution. The dashboard has Stop and Check controls.
This does not liquidate positions. Full paper-account runtime persistence and
multi-process consistency remain incomplete.

Run locally with one server process. The existing API has no remote-user
authentication; do not expose it publicly. Broker order execution remains unsupported.
