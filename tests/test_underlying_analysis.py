# Run from the project root: python tests/test_underlying_analysis.py
"""Deterministic offline tests for individual F&O underlying analysis."""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.context import MarketContextEngine
from market.ohlcv import OHLCV
from market.underlying_analysis import UnderlyingAnalysis, UnderlyingAnalysisEngine


def main():
    context_engine = MarketContextEngine()
    engine = UnderlyingAnalysisEngine(context_engine)
    results = []

    def make_candles(symbol="RELIANCE", count=240):
        pattern = [0, 2, 4, 1, -1, 1]
        start = datetime(2026, 9, 17, 9, 15, tzinfo=timezone.utc)
        candles = []
        for index in range(count):
            close = 100 + index * 0.4 + pattern[index % len(pattern)]
            candles.append(OHLCV(
                symbol=symbol, exchange="NSE", timestamp=start + timedelta(minutes=index),
                open=close - 0.2, high=close + 0.4, low=close - 0.5, close=close,
                volume=1000 + (index % 5) * 100 if index < count - 1 else 2500,
                source="MOCK_UNDERLYING", is_fresh=True,
            ))
        return candles

    candles = make_candles()
    market_context = context_engine.analyze(make_candles("NIFTY"))

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
        raise AssertionError("Insufficient OHLCV data was accepted.")

    def test_indicator_calculation():
        analysis = engine.analyze(candles)
        values = (analysis.ema20, analysis.ema50, analysis.ema200, analysis.rsi, analysis.macd, analysis.vwap)
        if not all(math.isfinite(value) for value in values):
            raise AssertionError("Expected finite indicator values.")

    def test_market_structure_and_trend():
        analysis = engine.analyze(candles)
        if analysis.trend != "BULLISH" or analysis.structure != "HH_HL":
            raise AssertionError("Expected BULLISH HH_HL analysis from rising test data.")

    def test_support_resistance_and_momentum():
        analysis = engine.analyze(candles)
        if not analysis.supports or not analysis.resistances or analysis.momentum != "POSITIVE":
            raise AssertionError("Expected supports, resistances, and positive momentum.")

    def test_context_alignment():
        if engine.analyze(candles, market_context).market_context_alignment != "ALIGNED":
            raise AssertionError("Expected aligned market context.")
        if engine.analyze(candles).market_context_alignment != "NOT_AVAILABLE":
            raise AssertionError("Expected missing context to be reported.")

    def test_metadata_preservation():
        analysis = engine.analyze(candles, market_context)
        if analysis.timestamp != candles[-1].timestamp or analysis.source != "MOCK_UNDERLYING" or not analysis.is_fresh:
            raise AssertionError("Source, timestamp, or freshness was not preserved.")

    def test_deterministic_output():
        first = engine.analyze(candles, market_context)
        second = engine.analyze(candles, market_context)
        if first != second or not isinstance(first, UnderlyingAnalysis):
            raise AssertionError("Underlying analysis was not deterministic.")

    print("=" * 40)
    print("J.A.R.V.I.S UNDERLYING ANALYSIS TEST")
    print("=" * 40)
    run_test("Insufficient Data", test_insufficient_data)
    run_test("Indicator Calculation", test_indicator_calculation)
    run_test("Trend And Structure", test_market_structure_and_trend)
    run_test("Support Resistance And Momentum", test_support_resistance_and_momentum)
    run_test("Context Alignment", test_context_alignment)
    run_test("Metadata Preservation", test_metadata_preservation)
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