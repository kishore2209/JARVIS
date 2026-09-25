"""Validated read-only candle pipeline. No order execution or mock fallback."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from market.ohlcv import OHLCV
from market.providers.base import MarketDataProvider

INTERVALS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}
MAX_CANDLES = 10000
MAX_FILE_BYTES = 5_000_000


def aware_timestamp(value):
    try:
        value = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError) as error:
        raise ValueError("Timestamp must be an ISO datetime with an explicit timezone.") from error


def number(value, name, integer=False):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite numeric data.") from error
    if not math.isfinite(result) or (integer and not result.is_integer()):
        raise ValueError(f"{name} must be finite" + (" integer data." if integer else " numeric data."))
    return int(result) if integer else result


def parse_candle(row):
    if not isinstance(row, dict):
        raise ValueError("Each candle must be an object.")
    required = ("symbol", "exchange", "timestamp", "open", "high", "low", "close", "volume", "source")
    if any(key not in row for key in required):
        raise ValueError("Candle requires symbol, exchange, timestamp, OHLC, volume and source.")
    for name in ("symbol", "exchange", "source"):
        if not isinstance(row[name], str) or not row[name].strip() or len(row[name]) > 128:
            raise ValueError(f"Invalid candle {name}.")
    values = {name: number(row[name], name) for name in ("open", "high", "low", "close")}
    volume = number(row["volume"], "volume", integer=True)
    if min(values.values()) <= 0 or volume < 0 or not (values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]):
        raise ValueError("Invalid OHLC geometry, price or volume.")
    return OHLCV(row["symbol"], row["exchange"], aware_timestamp(row["timestamp"]), **values, volume=volume, source=row["source"], is_fresh=False)


def validate_candles(candles, interval, now=None, historical=False):
    if interval not in INTERVALS:
        raise ValueError("Unsupported candle interval.")
    if not candles or len(candles) > MAX_CANDLES:
        raise ValueError(f"Provide between 1 and {MAX_CANDLES} candles.")
    now = aware_timestamp(now or datetime.now(timezone.utc))
    identity = (candles[0].symbol, candles[0].exchange, candles[0].source)
    previous = None
    result = []
    for original in candles:
        candle = parse_candle(vars(original))
        if (candle.symbol, candle.exchange, candle.source) != identity:
            raise ValueError("Mixed instruments, exchanges or sources are not allowed.")
        if previous is not None and candle.timestamp <= previous:
            raise ValueError("Candles must be chronological with unique timestamps.")
        if candle.timestamp > now:
            raise ValueError("Future-dated candles are not allowed.")
        previous = candle.timestamp
        fresh = not historical and timedelta(0) <= now - candle.timestamp <= timedelta(seconds=INTERVALS[interval] * 3)
        result.append(replace(candle, is_fresh=fresh))
    return result


def load_candle_text(text, format_name="json", interval=None):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Candle file exceeds 5 MB.")
    if format_name == "json":
        try:
            payload = json.loads(text)
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid candle JSON.") from error
        if isinstance(payload, dict):
            file_interval = payload.get("interval")
            if interval and file_interval and interval != file_interval:
                raise ValueError("Requested interval differs from file interval.")
            interval = file_interval or interval
            rows = payload.get("candles")
        else:
            rows = payload
    elif format_name == "csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError("Only JSON and CSV candle files are supported.")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CANDLES:
        raise ValueError("Candle file must contain a bounded nonempty list.")
    if interval not in INTERVALS:
        raise ValueError("An explicit supported candle interval is required.")
    candles = validate_candles([parse_candle(row) for row in rows], interval, historical=True)
    return candles, interval, hashlib.sha256(text.encode("utf-8")).hexdigest()


class FileMarketDataProvider(MarketDataProvider):
    """Server-configured local history; file paths never come from HTTP requests."""
    source = "LOCAL_FILE"
    supports_interval = True

    def __init__(self, path, interval=None):
        path = Path(path)
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Candle file is unavailable or exceeds 5 MB.")
        self.candles, self.interval, self.content_sha256 = load_candle_text(path.read_text(encoding="utf-8-sig"), path.suffix.lstrip(".").lower(), interval)

    def get_candles(self, symbol, exchange, token=None, limit=240, interval=None):
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer.")
        if (symbol, exchange) != (self.candles[0].symbol, self.candles[0].exchange):
            raise ValueError("Instrument is not available in the configured candle file.")
        if interval and interval != self.interval:
            raise ValueError("Requested interval differs from file interval.")
        return [replace(c) for c in self.candles[-limit:]]

    def get_quote(self, *args, **kwargs):
        raise ValueError("Historical files do not provide live quotes.")

    def get_ltp(self, *args, **kwargs):
        raise ValueError("Historical files do not provide live prices.")


class ReadOnlyAngelDataProvider(MarketDataProvider):
    """Lazy login on explicit reads; no startup network calls and no order facade."""
    source = "ANGEL_ONE"
    supports_interval = True

    def __init__(self, adapter=None):
        from market.providers.angel_one import AngelOneMarketDataProvider
        from threading import RLock
        self._adapter = adapter or AngelOneMarketDataProvider()
        self._lock = RLock()

    def get_candles(self, symbol, exchange, token=None, limit=240, interval="15m"):
        if not isinstance(symbol, str) or not symbol.strip() or not token:
            raise ValueError("Symbol, exchange and current broker instrument token are required.")
        if interval not in self._adapter.INTERVALS:
            raise ValueError("Interval is not supported by this Angel One adapter.")
        with self._lock:
            try:
                if self._adapter.client is None:
                    self._adapter.login()
                candles = self._adapter.get_candles(symbol, exchange, token, limit, interval=interval)
            except Exception as error:
                raise ValueError("Angel One read failed. Check server credentials, session, token and network; no mock fallback was used.") from error
        now = datetime.now(timezone.utc)
        candles = validate_candles(candles, interval, now=now)
        # SmartAPI candles use bar-open timestamps. Exclude the still-forming bar.
        candles = [c for c in candles if c.timestamp + timedelta(seconds=INTERVALS[interval]) <= now]
        if not candles:
            raise ValueError("No completed candles are available.")
        return candles

    def get_quote(self, *args, **kwargs):
        raise ValueError("Runtime read-only adapter currently supports completed candles only.")

    def get_ltp(self, *args, **kwargs):
        raise ValueError("Runtime read-only adapter currently supports completed candles only.")
