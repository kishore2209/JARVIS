# Run from the project root: python tests/test_market_context.py
"""Deterministic offline tests for the read-only market context engine."""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.context import MarketContext, MarketContextEngine
from market.ohlcv import OHLCV


def main():
    engine = MarketContextEngine()
    results = []

    def make_candles(symbol="NIFTY", count=240):
        pattern = [0, 2, 4, 1, -1, 1]
        start = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)
        candles = []
        for index in range(count):
            close = 100 + index * 0.4 + pattern[index % len(pattern)]
            candles.append(OHLCV(
                symbol=symbol, exchange="NSE", timestamp=start + timedelta(minutes=index),
                open=close - 0.2, high=close + 0.4, low=close - 0.5, close=close,
                volume=1000 + (index % 5) * 100 if index < count - 1 else 2500,
                source="MOCK_CONTEXT", is_fresh=True,
            ))
        return candles

    candles = make_candles()

    def run_test(name, test):
        try:
            test()
            results.append((name, True))
            print(f"[PASS] {name}")
        except Exception as error:
            results.append((name, False))
            print(f"[FAIL] {name}")
            print(f"Reason: {error}")

    def test_insufficient_data():
        try:
            engine.analyze(make_candles(count=199))
        except ValueError:
            return
        raise AssertionError("Insufficient candles were accepted.")

    def test_indicators():
        context = engine.analyze(candles)
        if not all(math.isfinite(value) for value in (context.ema20, context.ema50, context.ema200, context.rsi)):
            raise AssertionError("Expected finite indicator values.")

    def test_trend_classification():
        if engine.analyze(candles).trend != "BULLISH":
            raise AssertionError("Expected BULLISH trend from rising swing data.")

    def test_structure_classification():
        if engine.analyze(candles).structure != "HH_HL":
            raise AssertionError("Expected HH_HL market structure.")

    def test_metadata():
        context = engine.analyze(candles)
        if context.timestamp != candles[-1].timestamp or context.source != "MOCK_CONTEXT" or not context.is_fresh:
            raise AssertionError("Market context did not preserve OHLCV metadata.")

    def test_deterministic_output():
        first = engine.analyze(candles)
        second = engine.analyze(candles)
        if first != second or not isinstance(first, MarketContext):
            raise AssertionError("Market context output was not deterministic.")

    print("=" * 40)
    print("J.A.R.V.I.S MARKET CONTEXT TEST")
    print("=" * 40)
    run_test("Insufficient Data", test_insufficient_data)
    run_test("Indicator Calculation", test_indicators)
    run_test("Trend Classification", test_trend_classification)
    run_test("Structure Classification", test_structure_classification)
    run_test("Metadata Preservation", test_metadata)
    run_test("Deterministic Output", test_deterministic_output)

    passed = sum(passed for _, passed in results)
    failed = len(results) - passed
    print("=" * 40)
    print("TEST SUMMARY")
    print("=" * 40)
    print(f"Total Tests : {len(results)}")
    print(f"Passed      : {passed}")
    print(f"Failed      : {failed}")
    print("Status      : ALL TESTS PASSED" if failed == 0 else "Status      : TESTS FAILED")
    print("=" * 40)
    return failed


if __name__ == "__main__":
    sys.exit(main())