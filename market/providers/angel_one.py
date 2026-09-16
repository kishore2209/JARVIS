import os
from datetime import datetime, timezone

from market.ohlcv import MarketQuote, OHLCV
from market.providers.base import MarketDataProvider


class AngelOneMarketDataProvider(MarketDataProvider):
    """Read-only adapter for Angel One's official SmartAPI SDK."""

    source = "ANGEL_ONE"

    def __init__(self):
        self.api_key = os.getenv("ANGEL_ONE_API_KEY")
        self.client_code = os.getenv("ANGEL_ONE_CLIENT_CODE")
        self.pin = os.getenv("ANGEL_ONE_PIN")
        self.totp = os.getenv("ANGEL_ONE_TOTP")
        self.client = None

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

    def get_candles(self, symbol, exchange, token=None, limit=100):
        self._require_client()
        raise NotImplementedError("Map SmartAPI candle parameters to this method when a timeframe contract is chosen.")

    def get_oi(self, symbol, exchange, token=None):
        self._require_client()
        raise NotImplementedError("OI mapping depends on the selected Angel One instrument feed.")