# Run from the project root: python tests/verify_angel_one_ohlcv.py RELIANCE NSE 500325 15m
"""Manual read-only verification of Angel One normalized historical OHLCV."""

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.providers.angel_one import AngelOneMarketDataProvider
from market.underlying_analysis import UnderlyingAnalysisEngine


def main():
    if not all(os.getenv(name) for name in ("ANGEL_ONE_API_KEY", "ANGEL_ONE_CLIENT_CODE", "ANGEL_ONE_PIN", "ANGEL_ONE_TOTP")):
        print("Live verification skipped: Angel One credentials not configured.")
        return 0

    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    exchange = sys.argv[2] if len(sys.argv) > 2 else "NSE"
    token = sys.argv[3] if len(sys.argv) > 3 else "500325"
    interval = sys.argv[4] if len(sys.argv) > 4 else "15m"
    provider = AngelOneMarketDataProvider()

    try:
        provider.login()
        candles = provider.get_candles(symbol, exchange, token, 240, interval)
    except (RuntimeError, ValueError) as error:
        print(f"Live verification failed: {error}")
        return 1

    latest = candles[-1]
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")
    print(f"Candle count: {len(candles)}")
    print(f"First timestamp: {candles[0].timestamp.isoformat()}")
    print(f"Last timestamp: {latest.timestamp.isoformat()}")
    print(f"Latest close: {latest.close}")
    print(f"Source: {latest.source}")
    print(f"Freshness: {latest.is_fresh}")
    if len(candles) >= 200:
        analysis = UnderlyingAnalysisEngine().analyze(candles)
        print(f"Analysis: trend={analysis.trend} | rsi={analysis.rsi:.2f} | macd={analysis.macd:.4f} | vwap={analysis.vwap:.4f}")
    else:
        print("Analysis skipped: at least 200 candles are required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())