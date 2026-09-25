"""One reproducible historical analysis path for CLI and API."""
from core.interface_service import serialize
from market.context import MarketContextEngine
from market.underlying_analysis import UnderlyingAnalysisEngine
from market.strategies.engine import MultiStrategyEngine
from market.confluence import ConfluenceEngine
from market.data_pipeline import load_candle_text


def analyze_file_text(text, format_name="json", interval=None):
    candles, interval, fingerprint = load_candle_text(text, format_name, interval)
    context = MarketContextEngine().analyze(candles)
    underlying = UnderlyingAnalysisEngine().analyze(candles)
    strategies = MultiStrategyEngine().analyze(candles, underlying, historical=True)
    confluence = ConfluenceEngine().analyze(underlying, strategies)
    return {
        "status": "OK",
        "execution_mode": "HISTORICAL_ANALYSIS_ONLY",
        "data_completeness": "PARTIAL",
        "provenance": {
            "symbol": candles[-1].symbol, "exchange": candles[-1].exchange,
            "declared_source": candles[-1].source, "source_independently_verified": False,
            "interval": interval, "candle_count": len(candles),
            "first_timestamp": candles[0].timestamp.isoformat(),
            "data_timestamp": candles[-1].timestamp.isoformat(),
            "content_sha256": fingerprint, "freshness_status": "HISTORICAL_NOT_LIVE",
            "price_adjustment_status": "NOT_VERIFIED",
        },
        "underlying_analysis": serialize(underlying),
        "instrument_context": serialize(context),
        "strategy_evidence": serialize(strategies),
        "confluence_analysis": serialize(confluence),
        "chart_candles": serialize(candles[-240:]),
        "warnings": [
            "Historical file data is not a live market feed or an execution authorization.",
            "Nifty and sector confirmation, news, OI and current instrument master are NOT_AVAILABLE.",
            "Independent market context was not supplied; alignment is NOT_AVAILABLE.",
            "Corporate-action adjustments and trading-session completeness have not been verified.",
        ],
    }
