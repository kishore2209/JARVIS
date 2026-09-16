from abc import ABC, abstractmethod


class MarketDataProvider(ABC):
    """Interface implemented by market-data sources."""

    source = "UNKNOWN"

    @abstractmethod
    def get_ltp(self, symbol, exchange, token=None):
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, symbol, exchange, token=None):
        raise NotImplementedError

    @abstractmethod
    def get_candles(self, symbol, exchange, token=None, limit=100):
        raise NotImplementedError

    def get_oi(self, symbol, exchange, token=None):
        raise NotImplementedError("Open interest is not available from this provider.")