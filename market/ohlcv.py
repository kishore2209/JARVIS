from dataclasses import dataclass
from datetime import datetime


@dataclass
class OHLCV:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


if __name__ == "__main__":
    candle = OHLCV(
        symbol="RELIANCE",
        timestamp=datetime.now(),
        open=1400.00,
        high=1420.00,
        low=1390.00,
        close=1415.00,
        volume=1250000
    )

    print("================================")
    print("       J.A.R.V.I.S OHLCV")
    print("================================")

    print("Symbol:", candle.symbol)
    print("Open:", candle.open)
    print("High:", candle.high)
    print("Low:", candle.low)
    print("Close:", candle.close)
    print("Volume:", candle.volume)
    print("Timestamp:", candle.timestamp)