from datetime import datetime, timezone


class MarketData:
    def __init__(self):
        self.source = "UNKNOWN"
        self.status = "READY"

    def create_snapshot(self, symbol, price):
        return {
            "symbol": symbol,
            "price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self.source,
        }
