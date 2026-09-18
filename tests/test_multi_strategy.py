# Run from the project root: python tests/test_multi_strategy.py
"""Deterministic offline tests for Phase D strategy evidence."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.ohlcv import OHLCV
from market.strategies.engine import MultiStrategyEngine


def main():
    engine = MultiStrategyEngine()
    results = []
    def candles(mode="bull", count=240):
        start = datetime(2026, 9, 17, 9, 15, tzinfo=timezone.utc)
        values = []
        for index in range(count):
            base = 100 + index * .4 if mode != "bear" else 200 - index * .4
            wave = 0 if mode == "plain" else [0, 2, 4, 1, -1, 1][index % 6]
            values.append(base + wave)
        if mode == "breakout": values[-1] = max(values[-6:-1]) + 5
        if mode == "breakdown": values[-1] = min(values[-6:-1]) - 5
        if mode == "double_top": values[-8:] = [150, 155, 160, 155, 150, 155, 160.5, 154]
        if mode == "double_bottom": values[-8:] = [160, 155, 150, 155, 160, 155, 150.5, 156]
        return [OHLCV("RELIANCE", "NSE", start + timedelta(minutes=i), value-.2, value+.4, value-.5, value, 2500 if i == count-1 else 1000, "MOCK_STRATEGY", True) for i, value in enumerate(values)]
    def by_name(evidence, name): return next(item for item in evidence if item.strategy_name == name)
    def run(name, test):
        try: test(); results.append(True); print(f"[PASS] {name}")
        except Exception as error: results.append(False); print(f"[FAIL] {name}"); print(f"Reason: {error}")
    def test_trends():
        if by_name(engine.analyze(candles("bull")), "TREND_FOLLOWING").direction != "BULLISH": raise AssertionError("bullish trend missing")
        if by_name(engine.analyze(candles("bear")), "TREND_FOLLOWING").direction != "BEARISH": raise AssertionError("bearish trend missing")
    def test_breakouts_volume():
        if by_name(engine.analyze(candles("breakout")), "BREAKOUT_BREAKDOWN").direction != "BULLISH": raise AssertionError("breakout missing")
        if by_name(engine.analyze(candles("breakdown")), "BREAKOUT_BREAKDOWN").direction != "BEARISH": raise AssertionError("breakdown missing")
        if by_name(engine.analyze(candles("bull")), "VOLUME_CONFIRMATION").direction != "BULLISH": raise AssertionError("volume confirmation missing")
    def test_zones_fib_patterns():
        evidence = engine.analyze(candles("bull"))
        if by_name(evidence, "DEMAND_SUPPLY").data_completeness != "COMPLETE" or "retracement levels" not in by_name(evidence, "FIBONACCI_RETRACEMENT").evidence[1]: raise AssertionError("zones or fib missing")
        if "DOUBLE_TOP" not in str(by_name(engine.analyze(candles("double_top")), "CHART_PATTERNS").evidence): raise AssertionError("double top missing")
        if "DOUBLE_BOTTOM" not in str(by_name(engine.analyze(candles("double_bottom")), "CHART_PATTERNS").evidence): raise AssertionError("double bottom missing")
    def test_quality_metadata_determinism():
        data = candles("bull")
        first, second = engine.analyze(data), engine.analyze(data)
        if first != second or first[0].source != "MOCK_STRATEGY" or not first[0].is_fresh: raise AssertionError("metadata/determinism missing")
        try: engine.analyze(data[:199])
        except ValueError: return
        raise AssertionError("insufficient data accepted")
    def test_no_pattern_and_context_conflict():
        normal = by_name(engine.analyze(candles("plain")), "CHART_PATTERNS")
        if normal.data_completeness != "PARTIAL": raise AssertionError("no-pattern case missing")
        from market.context import MarketContextEngine
        from market.underlying_analysis import UnderlyingAnalysisEngine
        market_context = MarketContextEngine().analyze(candles("bear"))
        analysis = UnderlyingAnalysisEngine().analyze(candles("bull"), market_context)
        trend = by_name(engine.analyze(candles("bull"), analysis, market_context), "TREND_FOLLOWING")
        if trend.context_alignment != "CONFLICTING": raise AssertionError("context conflict missing")
    print("="*40); print("J.A.R.V.I.S MULTI-STRATEGY TEST"); print("="*40)
    run("Bullish And Bearish Trend", test_trends); run("Breakout Breakdown Volume", test_breakouts_volume); run("Zones Fibonacci Patterns", test_zones_fib_patterns); run("Quality Metadata Determinism", test_quality_metadata_determinism); run("No Pattern And Context Conflict", test_no_pattern_and_context_conflict)
    passed=sum(results); print("="*40); print("TEST SUMMARY"); print("="*40); print(f"Total Tests : {len(results)}"); print(f"Passed      : {passed}"); print(f"Failed      : {len(results)-passed}"); print("Status      : ALL TESTS PASSED" if passed == len(results) else "Status      : TESTS FAILED"); print("="*40); return len(results)-passed
if __name__ == "__main__": sys.exit(main())