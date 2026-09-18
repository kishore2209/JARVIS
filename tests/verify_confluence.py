# Run from the project root: python tests/verify_confluence.py
"""Offline deterministic Phase E verification; no broker calls."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.confluence import ConfluenceEngine
from market.ohlcv import OHLCV
from market.strategies.engine import MultiStrategyEngine
from market.underlying_analysis import UnderlyingAnalysisEngine
from datetime import datetime, timedelta, timezone

start = datetime(2026, 9, 17, 9, 15, tzinfo=timezone.utc)
pattern = [0, 2, 4, 1, -1, 1]
candles = [OHLCV("RELIANCE", "NSE", start + timedelta(minutes=index), 100 + index*.4 + pattern[index % 6]-.2, 100 + index*.4 + pattern[index % 6]+.4, 100 + index*.4 + pattern[index % 6]-.5, 100 + index*.4 + pattern[index % 6], 2500 if index == 239 else 1000, "MOCK_CONFLUENCE", True) for index in range(240)]
analysis = UnderlyingAnalysisEngine().analyze(candles)
evidence = MultiStrategyEngine().analyze(candles, analysis)
result = ConfluenceEngine().analyze(analysis, evidence)
print(f"Instrument: {result.instrument}")
print(f"Directional bias: {result.directional_bias}")
print(f"Bullish evidence score: {result.bullish_score}")
print(f"Bearish evidence score: {result.bearish_score}")
print(f"Net evidence score: {result.net_evidence_score}")
print(f"Evidence quality: {result.evidence_quality}")
print(f"Agreement count: {result.agreement_count}")
print(f"Conflict count: {result.conflict_count}")
print(f"Market alignment: {result.market_context_alignment}")
print(f"Data completeness: {result.data_completeness}")
print(f"Freshness: {result.is_fresh}")
print(f"Supporting evidence: {list(result.thesis_facts)[:4]}")
print(f"Conflicting evidence: {list(result.conflicting_evidence)}")
print(f"Invalidation conditions: {list(result.invalidation_conditions)}")