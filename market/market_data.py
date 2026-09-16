from datetime import datetime, timezone


class MarketData:
    def __init__(self):
        self.source = "UNKNOWN"
        self.status = "READY"

    def create_snapshot(self, symbol, price):
        snapshot = {
            "symbol": symbol,
            "price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self.source,
        }

        return snapshot


if __name__ == "__main__":
    market = MarketData()

    snapshot = market.create_snapshot(
        symbol="RELIANCE",
        price=1400.00
    )

    print("================================")
    print("     J.A.R.V.I.S MARKET DATA")
    print("================================")
    print("Status:", market.status)
    print("Snapshot:", snapshot)