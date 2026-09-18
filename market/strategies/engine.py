from market.underlying_analysis import UnderlyingAnalysisEngine
from market.strategies.analyzers import (BreakoutStrategy, DemandSupplyStrategy, FibonacciStrategy, PatternStrategy, SupportResistanceStrategy, TrendFollowingStrategy, VolumeConfirmationStrategy)
from market.strategies.evidence import StrategyEvidence


class MultiStrategyEngine:
    """Runs isolated evidence analyzers; failures become explicit evidence records."""

    def __init__(self, strategies=None, analysis_engine=None):
        self.analysis_engine = analysis_engine or UnderlyingAnalysisEngine()
        self.strategies = strategies or [TrendFollowingStrategy(), SupportResistanceStrategy(), BreakoutStrategy(), VolumeConfirmationStrategy(), DemandSupplyStrategy(), FibonacciStrategy(), PatternStrategy()]

    def analyze(self, candles, underlying_analysis=None, market_context=None, fno_intelligence=None):
        self._validate_candles(candles)
        analysis = underlying_analysis or self.analysis_engine.analyze(candles, market_context)
        results = []
        for strategy in self.strategies:
            try:
                results.append(strategy.evaluate(candles, analysis, market_context, fno_intelligence))
            except Exception as error:
                results.append(StrategyEvidence(strategy.name, analysis.instrument, analysis.timestamp, "NEUTRAL", "INSUFFICIENT", (f"strategy error: {type(error).__name__}",), (), (), analysis.source, analysis.is_fresh, "PARTIAL", "NOT_AVAILABLE"))
        return tuple(results)

    @staticmethod
    def _validate_candles(candles):
        if len(candles) < 200:
            raise ValueError("At least 200 normalized candles are required.")
        timestamps = [candle.timestamp for candle in candles]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            raise ValueError("Candles must be chronological and have unique timestamps.")
        if not all(candle.is_fresh for candle in candles):
            raise ValueError("Stale candles cannot be analyzed as current context.")