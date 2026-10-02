import os
import re
from math import isfinite
from threading import RLock
from datetime import datetime, timedelta, timezone

from market.ohlcv import MarketQuote, OHLCV
from market.providers.base import MarketDataProvider


class AngelOneMarketDataProvider(MarketDataProvider):
    """Read-only adapter for Angel One's official SmartAPI SDK."""

    source = "ANGEL_ONE"
    INTERVALS = {
        "1m": "ONE_MINUTE",
        "5m": "FIVE_MINUTE",
        "15m": "FIFTEEN_MINUTE",
        "30m": "THIRTY_MINUTE",
        "1h": "ONE_HOUR",
        "1d": "ONE_DAY",
    }
    _INTERVAL_LOOKBACK = {
        "1m": timedelta(days=1),
        "5m": timedelta(days=5),
        "15m": timedelta(days=10),
        "30m": timedelta(days=20),
        "1h": timedelta(days=45),
        "1d": timedelta(days=365),
    }
    _FRESHNESS_WINDOW = {
        "1m": timedelta(minutes=5),
        "5m": timedelta(minutes=15),
        "15m": timedelta(minutes=45),
        "30m": timedelta(minutes=90),
        "1h": timedelta(hours=3),
        "1d": timedelta(days=2),
    }
    _BROKER_TIMEZONE = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")

    def __init__(self, client=None, clock=None, auto_login=False, instrument_resolver=None):
        self.api_key = os.getenv("ANGEL_ONE_API_KEY")
        self.client_code = os.getenv("ANGEL_ONE_CLIENT_CODE")
        self.pin = os.getenv("ANGEL_ONE_PIN")
        self.totp = os.getenv("ANGEL_ONE_TOTP")
        self.client = client
        self.auto_login = auto_login
        self.instrument_resolver = instrument_resolver
        self._session_lock = RLock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def login(self):
        if not all((self.api_key, self.client_code, self.pin, self.totp)):
            raise RuntimeError("Angel One credentials are required in environment variables.")
        try:
            from SmartApi import SmartConnect
        except ImportError as error:
            raise RuntimeError("Install smartapi-python to use Angel One market data.") from error

        self.client = SmartConnect(api_key=self.api_key, timeout=10)
        try:
            response = self.client.generateSession(self.client_code, self.pin, self.totp)
        except Exception as error:
            self.client = None
            raise RuntimeError("Angel One login failed.") from error
        if not isinstance(response, dict) or not response.get("status"):
            self.client = None
            raise RuntimeError("Angel One login failed; check server-side credentials and current TOTP.")
        return response

    def _require_client(self):
        with self._session_lock:
            if self.client is None and self.auto_login:
                self.login()
            if self.client is None:
                raise RuntimeError("Call login() before requesting Angel One market data.")

    def get_ltp(self, symbol, exchange, token=None):
        return self.get_quote(symbol, exchange, token).ltp

    def get_quote(self, symbol, exchange, token=None):
        if self.instrument_resolver is not None:
            symbol, exchange, token = self.instrument_resolver.resolve(symbol, exchange, token)
        self._require_client()
        if not token: raise ValueError('Explicit instrument token required')
        try:
            raw = self.client.ltpData(exchange, symbol, str(token))
        except Exception as error:
            raise RuntimeError('Angel One LTP request failed') from error
        if not isinstance(raw, dict) or raw.get('status') is not True or not isinstance(raw.get('data'), dict):
            raise ValueError('Invalid Angel One LTP response')
        response = raw['data']; price = float(response['ltp'])
        if not isfinite(price) or price <= 0: raise ValueError('Invalid Angel One price')
        if response.get('symboltoken') is not None and str(response['symboltoken']) != str(token):
            raise ValueError('Quote instrument mismatch')
        return MarketQuote(
            symbol=symbol, exchange=exchange, token=str(token),
            timestamp=self._utc_now(), ltp=price, is_fresh=False,
            source=self.source, open=float(response.get("open", 0)),
            high=float(response.get("high", 0)), low=float(response.get("low", 0)),
            close=float(response.get("close", 0)), volume=int(response.get("tradeVolume", 0)),
        )

    def get_candles(self, symbol, exchange, token=None, limit=100, interval="15m", from_time=None, to_time=None):
        """Return chronological, de-duplicated OHLCV candles in UTC.

        SmartAPI timestamps without an offset are interpreted as Asia/Kolkata time.
        """
        if self.instrument_resolver is not None:
            _, exchange, token = self.instrument_resolver.resolve(symbol, exchange, token)
        self._require_client()
        if interval not in self.INTERVALS:
            raise ValueError(f"Unsupported interval: {interval}.")
        if not token:
            raise ValueError("A symbol token is required for historical candles.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer from 1 to 500.")

        retrieved_at = self._utc_now()
        to_time = self._normalize_request_time(to_time or retrieved_at)
        from_time = self._normalize_request_time(from_time or (to_time - self._INTERVAL_LOOKBACK[interval]))
        if from_time >= to_time:
            raise ValueError("from_time must be earlier than to_time.")
        parameters = {
            "exchange": exchange,
            "symboltoken": str(token),
            "interval": self.INTERVALS[interval],
            "fromdate": self._format_broker_time(from_time),
            "todate": self._format_broker_time(to_time),
        }
        try:
            response = self.client.getCandleData(parameters)
        except Exception as error:
            detail = self._sanitize_exception_message(error)
            raise RuntimeError(
                f"Angel One historical candle request failed: {type(error).__name__}: {detail}"
            ) from error

        if not isinstance(response, dict) or not response.get("status"):
            raise RuntimeError("Angel One historical candle API rejected the request.")
        rows = response.get("data")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Angel One historical candle response contained no candle rows.")

        candles = {}
        for row in rows:
            candle = self._normalize_candle_row(row, symbol, exchange, retrieved_at, interval)
            if candle.timestamp in candles and candles[candle.timestamp] != candle:
                raise ValueError('Conflicting duplicate candle')
            candles[candle.timestamp] = candle
        return [candles[timestamp] for timestamp in sorted(candles)][-limit:]

    def _normalize_candle_row(self, row, symbol, exchange, retrieved_at, interval):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError("Malformed Angel One candle row.")
        try:
            timestamp = self._parse_broker_timestamp(row[0])
            open_price, high, low, close = (float(value) for value in row[1:5])
            volume = int(float(row[5]))
        except (TypeError, ValueError) as error:
            raise ValueError("Malformed Angel One candle values.") from error
        if not all(isfinite(v) for v in (open_price,high,low,close,float(row[5]))) or float(row[5]) != volume or volume < 0 or min(open_price, high, low, close) <= 0 or low > min(open_price,close) or high < max(open_price,close):
            raise ValueError("Invalid Angel One OHLCV values.")
        if timestamp > retrieved_at: raise ValueError('Future Angel One candle timestamp')
        is_fresh = timestamp <= retrieved_at and retrieved_at - timestamp <= self._FRESHNESS_WINDOW[interval]
        return OHLCV(symbol, exchange, timestamp, open_price, high, low, close, volume, self.source, is_fresh)

    def _parse_broker_timestamp(self, value):
        if not isinstance(value, str):
            raise ValueError("Candle timestamp must be a string.")
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=self._BROKER_TIMEZONE)
        return timestamp.astimezone(timezone.utc)

    def _normalize_request_time(self, value):
        if not isinstance(value, datetime):
            raise ValueError("Candle request times must be datetime values.")
        if value.tzinfo is None:
            raise ValueError("Candle request times must be timezone-aware.")
        return value.astimezone(timezone.utc)

    def _format_broker_time(self, value):
        return value.astimezone(self._BROKER_TIMEZONE).strftime("%Y-%m-%d %H:%M")

    def _utc_now(self):
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("Provider clock must return a timezone-aware datetime.")
        return timestamp.astimezone(timezone.utc)

    def _sanitize_exception_message(self, error):
        message = str(error) or "no message provided"
        for value in (self.api_key, self.client_code, self.pin, self.totp):
            if value:
                message = message.replace(value, "<redacted>")
        if re.search(r"authorization|headers?\s*[:=]", message, re.IGNORECASE):
            return "sensitive request details redacted"
        return re.sub(
            r"(?i)\b(api[_ -]?key|client[_ -]?code|pin|totp|token)\b\s*[:=]\s*[^,\s}\]]+",
            r"\1=<redacted>",
            message,
        )

    def get_oi(self, symbol, exchange, token=None):
        self._require_client()
        raise NotImplementedError("OI mapping depends on the selected Angel One instrument feed.")
