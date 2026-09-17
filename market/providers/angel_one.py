import os
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

    def __init__(self, client=None, clock=None):
        self.api_key = os.getenv("ANGEL_ONE_API_KEY")
        self.client_code = os.getenv("ANGEL_ONE_CLIENT_CODE")
        self.pin = os.getenv("ANGEL_ONE_PIN")
        self.totp = os.getenv("ANGEL_ONE_TOTP")
        self.client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def login(self):
        if not all((self.api_key, self.client_code, self.pin, self.totp)):
            raise RuntimeError("Angel One credentials are required in environment variables.")
        try:
            from SmartApi import SmartConnect
        except ImportError as error:
            raise RuntimeError("Install smartapi-python to use Angel One market data.") from error

        self.client = SmartConnect(api_key=self.api_key)
        return self.client.generateSession(self.client_code, self.pin, self.totp)

    def _require_client(self):
        if self.client is None:
            raise RuntimeError("Call login() before requesting Angel One market data.")

    def get_ltp(self, symbol, exchange, token=None):
        self._require_client()
        response = self.client.ltpData(exchange, symbol, token)
        return float(response["data"]["ltp"])

    def get_quote(self, symbol, exchange, token=None):
        self._require_client()
        response = self.client.quoteData(exchange, symbol, token)["data"]
        return MarketQuote(
            symbol=symbol, exchange=exchange, token=str(token),
            timestamp=datetime.now(timezone.utc), ltp=float(response["ltp"]),
            source=self.source, open=float(response.get("open", 0)),
            high=float(response.get("high", 0)), low=float(response.get("low", 0)),
            close=float(response.get("close", 0)), volume=int(response.get("tradeVolume", 0)),
        )

    def get_candles(self, symbol, exchange, token=None, limit=100, interval="15m", from_time=None, to_time=None):
        """Return chronological, de-duplicated OHLCV candles in UTC.

        SmartAPI timestamps without an offset are interpreted as Asia/Kolkata time.
        """
        self._require_client()
        if interval not in self.INTERVALS:
            raise ValueError(f"Unsupported interval: {interval}.")
        if not token:
            raise ValueError("A symbol token is required for historical candles.")
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer.")

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
            raise RuntimeError("Angel One historical candle request failed.") from error

        if not isinstance(response, dict) or not response.get("status"):
            message = response.get("message", "unknown API error") if isinstance(response, dict) else "invalid API response"
            raise RuntimeError(f"Angel One historical candle API error: {message}")
        rows = response.get("data")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Angel One historical candle response contained no candle rows.")

        candles = {}
        for row in rows:
            candle = self._normalize_candle_row(row, symbol, exchange, retrieved_at, interval)
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
        if volume < 0 or min(open_price, high, low, close) < 0 or low > high:
            raise ValueError("Invalid Angel One OHLCV values.")
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
        return value.astimezone(self._BROKER_TIMEZONE).strftime("%d-%m-%Y %H:%M")

    def _utc_now(self):
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("Provider clock must return a timezone-aware datetime.")
        return timestamp.astimezone(timezone.utc)

    def get_oi(self, symbol, exchange, token=None):
        self._require_client()
        raise NotImplementedError("OI mapping depends on the selected Angel One instrument feed.")