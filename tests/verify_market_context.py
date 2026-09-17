# Run from the project root: python tests/verify_market_context.py
"""Manual offline verification using the existing MockMarketDataProvider only."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.context import MarketContextEngine
from market.providers.mock import MockMarketDataProvider


def main():
    context = MarketContextEngine().analyze_provider(
        MockMarketDataProvider(), "JARVIS", "NSE", "000001", limit=240
    )
    print("=" * 40)
    print("J.A.R.V.I.S MARKET CONTEXT VERIFY")
    print("=" * 40)
    print(f"Instrument: {context.instrument}")
    print(f"Price: {context.price}")
    print(f"EMA20: {context.ema20:.4f}")
    print(f"EMA50: {context.ema50:.4f}")
    print(f"EMA200: {context.ema200:.4f}")
    print(f"RSI: {context.rsi:.2f}")
    print(f"Trend: {context.trend}")
    print(f"Structure: {context.structure}")
    print(f"Momentum: {context.momentum}")
    print(f"Volume condition: {context.volume_condition}")
    print(f"Regime: {context.regime}")
    print(f"Metadata: source={context.source} | timestamp={context.timestamp.isoformat()} | fresh={context.is_fresh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())