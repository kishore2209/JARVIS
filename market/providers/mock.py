from datetime import datetime, timedelta, timezone

from market.ohlcv import MarketQuote, OHLCV
from market.providers.base import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    """Deterministic offline data suitable for quant-engine tests."""

    source = "MOCK"
    _SYMBOL = "JARVIS"
    _EXCHANGE = "NSE"
    _TOKEN = "000001"
    _START = datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc)

    def _validate(self, symbol, exchange, token):
        if symbol != self._SYMBOL or exchange != self._EXCHANGE:
            raise ValueError("Mock data is only available for JARVIS on NSE.")
        if token is not None and token != self._TOKEN:
            raise ValueError("Invalid mock token.")

    def get_candles(self, symbol, exchange, token=None, limit=100):
        self._validate(symbol, exchange, token)
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer.")

        candles = []
        for index in range(min(limit, 240)):
            close = 100.0 + index * 0.5
            candles.append(OHLCV(
                symbol=self._SYMBOL,
                exchange=self._EXCHANGE,
                timestamp=self._START + timedelta(minutes=index),
                open=close - 0.2,
                high=close + 0.4,
                low=close - 0.5,
                close=close,
                volume=1000 + (index % 7) * 100,
                source=self.source,
            ))
        return candles

    def get_quote(self, symbol, exchange, token=None):
        candles = self.get_candles(symbol, exchange, token, limit=240)
        latest = candles[-1]
        return MarketQuote(
            symbol=latest.symbol,
            exchange=latest.exchange,
            token=self._TOKEN,
            timestamp=latest.timestamp,
            ltp=latest.close,
            source=self.source,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            volume=latest.volume,
        )

    def get_ltp(self, symbol, exchange, token=None):
        return self.get_quote(symbol, exchange, token).ltp