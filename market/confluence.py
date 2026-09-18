from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConfluenceAnalysis:
    """Immutable evidence summary; directional bias is not a trade recommendation."""

    instrument: str
    timestamp: datetime
    bullish_evidence: tuple
    bearish_evidence: tuple
    neutral_evidence: tuple
    conflicting_evidence: tuple
    bullish_score: int
    bearish_score: int
    net_evidence_score: int
    agreement_count: int
    conflict_count: int
    insufficient_count: int
    evidence_quality: str
    directional_bias: str
    market_context_alignment: str
    data_completeness: str
    source_summary: tuple
    is_fresh: bool
    thesis_facts: tuple
    invalidation_conditions: tuple


class ConfluenceEngine:
    """Deterministically combines precomputed evidence without recalculating indicators."""

    STRENGTH_SCORES = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INSUFFICIENT": 0}

    def analyze(self, underlying_analysis, strategy_evidence, market_context=None, fno_intelligence=None):
        evidence = tuple(strategy_evidence)
        if not evidence:
            raise ValueError("At least one StrategyEvidence result is required.")
        if any(item.instrument != underlying_analysis.instrument for item in evidence):
            raise ValueError("Strategy evidence instrument does not match underlying analysis.")

        bullish = tuple(item for item in evidence if item.direction == "BULLISH")
        bearish = tuple(item for item in evidence if item.direction == "BEARISH")
        neutral = tuple(item for item in evidence if item.direction == "NEUTRAL")
        bullish_score = sum(self._score(item) for item in bullish)
        bearish_score = sum(self._score(item) for item in bearish)
        bias = self._directional_bias(bullish_score, bearish_score, evidence)
        conflicts = self._conflicts(bullish, bearish, evidence, bias)
        alignment = self._alignment(underlying_analysis, market_context)
        facts = self._unique(
            [fact for item in evidence for fact in item.evidence]
            + self._underlying_facts(underlying_analysis)
            + self._fno_facts(fno_intelligence)
        )
        invalidations = self._unique(condition for item in evidence for condition in item.invalidation_conditions)
        insufficient = sum(item.evidence_strength == "INSUFFICIENT" for item in evidence)
        freshness = underlying_analysis.is_fresh and all(item.is_fresh for item in evidence)
        if market_context is not None:
            freshness = freshness and market_context.is_fresh
        completeness = self._completeness(evidence, underlying_analysis.is_fresh, freshness)
        quality = self._quality(bullish_score, bearish_score, len(bullish), len(bearish), len(conflicts), completeness)
        sources = self._unique([underlying_analysis.source] + [item.source for item in evidence])
        return ConfluenceAnalysis(
            underlying_analysis.instrument, underlying_analysis.timestamp, bullish, bearish, neutral,
            conflicts, bullish_score, bearish_score, bullish_score - bearish_score,
            self._agreement_count(bullish, bearish, bias), len(conflicts), insufficient, quality, bias,
            alignment, completeness, sources, freshness, facts, invalidations,
        )

    def _score(self, item):
        return self.STRENGTH_SCORES.get(item.evidence_strength, 0)

    @staticmethod
    def _directional_bias(bullish_score, bearish_score, evidence):
        if bullish_score == bearish_score == 0:
            return "INSUFFICIENT" if all(item.evidence_strength == "INSUFFICIENT" for item in evidence) else "NEUTRAL"
        if bullish_score and bearish_score:
            return "MIXED"
        return "BULLISH" if bullish_score else "BEARISH"

    @staticmethod
    def _conflicts(bullish, bearish, evidence, bias):
        explicit = [fact for item in evidence for fact in item.conflicting_evidence]
        opposing = bearish if bias == "BULLISH" else bullish if bias == "BEARISH" else bullish + bearish if bias == "MIXED" else ()
        return tuple(explicit + [f"{item.strategy_name}: {item.direction}" for item in opposing])

    @staticmethod
    def _alignment(underlying_analysis, market_context):
        if market_context is None:
            return "NOT_AVAILABLE"
        if underlying_analysis.trend == market_context.trend and underlying_analysis.momentum == market_context.momentum:
            return "ALIGNED"
        if "UNKNOWN" in (underlying_analysis.trend, market_context.trend):
            return "NEUTRAL"
        return "CONFLICTING"

    @staticmethod
    def _underlying_facts(analysis):
        facts = [f"Market structure is {analysis.structure}", f"Momentum is {analysis.momentum}"]
        if analysis.ema20 > analysis.ema50 > analysis.ema200:
            facts.append("EMA20 > EMA50 > EMA200")
        if analysis.volume_condition == "HIGH":
            facts.append("Volume condition is HIGH")
        return facts

    @staticmethod
    def _fno_facts(fno_intelligence):
        if fno_intelligence is None:
            return ["Futures and options intelligence unavailable"]
        if hasattr(fno_intelligence, "oi_interpretation"):
            return [f"Futures OI interpretation is {fno_intelligence.oi_interpretation}"]
        if hasattr(fno_intelligence, "pcr"):
            return [f"Options PCR is {fno_intelligence.pcr}"]
        return ["Futures and options intelligence is incomplete"]

    @staticmethod
    def _completeness(evidence, core_fresh, freshness):
        if not core_fresh or not freshness:
            return "INSUFFICIENT"
        if any(item.data_completeness != "COMPLETE" for item in evidence):
            return "PARTIAL"
        return "COMPLETE"

    @staticmethod
    def _quality(bullish_score, bearish_score, bullish_count, bearish_count, conflicts, completeness):
        if completeness == "INSUFFICIENT" or (bullish_score == bearish_score == 0):
            return "INSUFFICIENT"
        if (bullish_count >= 3 and bearish_score == 0 and bullish_score >= 6) or (bearish_count >= 3 and bullish_score == 0 and bearish_score >= 6):
            return "HIGH"
        if max(bullish_score, bearish_score) >= 3 and conflicts <= 1:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _agreement_count(bullish, bearish, bias):
        return len(bullish) if bias == "BULLISH" else len(bearish) if bias == "BEARISH" else 0

    @staticmethod
    def _unique(items):
        return tuple(dict.fromkeys(items))