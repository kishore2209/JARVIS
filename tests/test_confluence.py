# Run from the project root: python tests/test_confluence.py
"""Deterministic offline tests for Phase E evidence aggregation."""
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.confluence import ConfluenceEngine
from market.context import MarketContext
from market.strategies.evidence import StrategyEvidence
from market.underlying_analysis import UnderlyingAnalysis


def main():
    timestamp = datetime(2026, 9, 17, 10, tzinfo=timezone.utc)
    engine = ConfluenceEngine()
    results = []
    def underlying(fresh=True):
        return UnderlyingAnalysis(timestamp, "RELIANCE", 100, 105, 100, 95, 60, 1, .5, .5, 98, "ABOVE_VWAP", "HIGH", "BULLISH", "HH_HL", "POSITIVE", [], [], "NOT_AVAILABLE", "MOCK", fresh)
    def item(name, direction, strength, complete="COMPLETE", fresh=True, invalidation="level invalidated"):
        return StrategyEvidence(name, "RELIANCE", timestamp, direction, strength, (f"{name} fact",), ("conflict noted",) if name == "RESISTANCE" else (), (invalidation,), "MOCK", fresh, complete)
    def run(name, test):
        try: test(); results.append(True); print(f"[PASS] {name}")
        except Exception as error: results.append(False); print(f"[FAIL] {name}"); print(f"Reason: {error}")
    def test_bull_bear_scores():
        result = engine.analyze(underlying(), [item("TREND", "BULLISH", "HIGH"), item("VOLUME", "BULLISH", "MEDIUM"), item("FIB", "BULLISH", "LOW")])
        if (result.bullish_score, result.bearish_score, result.net_evidence_score, result.directional_bias, result.evidence_quality) != (6, 0, 6, "BULLISH", "HIGH"): raise AssertionError("bullish score rules incorrect")
        bear = engine.analyze(underlying(), [item("TREND", "BEARISH", "HIGH"), item("VOLUME", "BEARISH", "MEDIUM")])
        if bear.directional_bias != "BEARISH" or bear.bearish_score != 5: raise AssertionError("bearish score rules incorrect")
    def test_mixed_neutral_insufficient():
        mixed = engine.analyze(underlying(), [item("TREND", "BULLISH", "HIGH"), item("RESISTANCE", "BEARISH", "MEDIUM")])
        if mixed.directional_bias != "MIXED" or mixed.conflict_count < 2: raise AssertionError("mixed conflict missing")
        neutral = engine.analyze(underlying(), [item("RANGE", "NEUTRAL", "LOW")])
        if neutral.directional_bias != "NEUTRAL": raise AssertionError("neutral evidence missing")
        insufficient = engine.analyze(underlying(), [item("PATTERN", "NEUTRAL", "INSUFFICIENT", "PARTIAL")])
        if insufficient.directional_bias != "INSUFFICIENT" or insufficient.evidence_quality != "INSUFFICIENT": raise AssertionError("insufficient evidence missing")
    def test_facts_invalidation_context_fno():
        context = MarketContext(timestamp, "NIFTY", 100, 1, 1, 1, 50, "BULLISH", "HH_HL", "POSITIVE", "HIGH", "BULLISH_CONTEXT", "MOCK", True)
        result = engine.analyze(underlying(), [item("TREND", "BULLISH", "HIGH"), item("VOLUME", "BULLISH", "MEDIUM")], context, type("Future", (), {"oi_interpretation": "LONG_BUILDUP"})())
        if result.market_context_alignment != "ALIGNED" or len(result.invalidation_conditions) != 1 or "Futures OI interpretation is LONG_BUILDUP" not in result.thesis_facts: raise AssertionError("facts, invalidations, or context missing")
    def test_partial_stale_metadata_determinism():
        evidence = [item("TREND", "BULLISH", "HIGH", "PARTIAL")]
        result = engine.analyze(underlying(), evidence)
        if result.data_completeness != "PARTIAL" or "Futures and options intelligence unavailable" not in result.thesis_facts: raise AssertionError("partial optional data handling missing")
        stale = engine.analyze(underlying(False), evidence)
        if stale.is_fresh or stale.data_completeness != "INSUFFICIENT": raise AssertionError("stale core data handling missing")
        if result != engine.analyze(underlying(), evidence): raise AssertionError("output is not deterministic")
    print("="*40); print("J.A.R.V.I.S CONFLUENCE TEST"); print("="*40)
    run("Scores And Directional Bias", test_bull_bear_scores); run("Mixed Neutral Insufficient", test_mixed_neutral_insufficient); run("Facts Invalidations Context FNO", test_facts_invalidation_context_fno); run("Partial Stale Metadata Determinism", test_partial_stale_metadata_determinism)
    passed=sum(results); print("="*40); print("TEST SUMMARY"); print("="*40); print(f"Total Tests : {len(results)}"); print(f"Passed      : {passed}"); print(f"Failed      : {len(results)-passed}"); print("Status      : ALL TESTS PASSED" if passed == len(results) else "Status      : TESTS FAILED"); print("="*40); return len(results)-passed
if __name__ == "__main__": sys.exit(main())