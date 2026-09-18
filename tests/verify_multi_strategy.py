# Run from the project root: python tests/verify_multi_strategy.py
"""Offline deterministic Phase D verification; no broker calls."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.ohlcv import OHLCV
from market.strategies.engine import MultiStrategyEngine

start = datetime(2026, 9, 17, 9, 15, tzinfo=timezone.utc)
pattern = [0, 2, 4, 1, -1, 1]
candles = []
for index in range(240):
    close = 100 + index * .4 + pattern[index % len(pattern)]
    candles.append(OHLCV("RELIANCE", "NSE", start + timedelta(minutes=index), close - .2, close + .4, close - .5, close, 2500 if index == 239 else 1000, "MOCK_STRATEGY", True))

print("Instrument: RELIANCE")
print("Market context alignment: NOT_AVAILABLE")
for item in MultiStrategyEngine().analyze(candles):
    print(f"{item.strategy_name}: {item.direction} / {item.evidence_strength} / {list(item.evidence)[:2]}")