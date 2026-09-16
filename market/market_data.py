from datetime import datetime, timezone

from market.providers.mock import MockMarketDataProvider


class MarketData:
    """Small facade that defaults to deterministic mock market data."""

    def __init__(self, provider=None):
        self.provider = provider or MockMarketDataProvider()
        self.source = self.provider.source
        self.status = "READY"

    def create_snapshot(self, symbol, price):
        return {
            "symbol": symbol,
            "price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self.source,
        }

    def get_quote(self, symbol, exchange="NSE", token=None):
        return self.provider.get_quote(symbol, exchange, token)

    def get_candles(self, symbol, exchange="NSE", token=None, limit=100):
        return self.provider.get_candles(symbol, exchange, token, limit)
