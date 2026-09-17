from dataclasses import dataclass
from datetime import datetime

from market.context import MarketContext, MarketContextEngine
from quant.macd import MACD
from quant.support_resistance import SupportResistance
from quant.vwap import VWAP


@dataclass
class UnderlyingAnalysis:
    """Read-only deterministic technical analysis for one F&O underlying."""

    timestamp: datetime
    instrument: str
    price: float
    ema20: float
    ema50: float
    ema200: float
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    vwap: float
    vwap_position: str
    volume_condition: str
    trend: str
    structure: str
    momentum: str
    supports: list
    resistances: list
    market_context_alignment: str
    source: str
    is_fresh: bool


class UnderlyingAnalysisEngine:
    """Extends market context with per-underlying deterministic analysis only."""

    def __init__(self, context_engine=None):
        self.context_engine = context_engine or MarketContextEngine()

    def analyze(self, candles, market_context=None):
        context = self.context_engine.analyze(candles)
        prices = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        macd = MACD.calculate(prices)
        vwap = VWAP.calculate(prices, volumes)
        support_resistance = SupportResistance.detect(prices)

        return UnderlyingAnalysis(
            timestamp=context.timestamp,
            instrument=context.instrument,
            price=context.price,
            ema20=context.ema20,
            ema50=context.ema50,
            ema200=context.ema200,
            rsi=context.rsi,
            macd=macd["macd"],
            macd_signal=macd["signal"],
            macd_histogram=macd["histogram"],
            vwap=vwap["vwap"],
            vwap_position=vwap["position"],
            volume_condition=context.volume_condition,
            trend=context.trend,
            structure=context.structure,
            momentum=context.momentum,
            supports=support_resistance["supports"],
            resistances=support_resistance["resistances"],
            market_context_alignment=self._context_alignment(context, market_context),
            source=context.source,
            is_fresh=context.is_fresh,
        )

    def analyze_provider(self, provider, symbol, exchange="NSE", token=None, limit=240, market_context=None):
        candles = provider.get_candles(symbol, exchange, token, limit)
        return self.analyze(candles, market_context)

    @staticmethod
    def _context_alignment(underlying_context, market_context):
        if market_context is None:
            return "NOT_AVAILABLE"
        if not isinstance(market_context, MarketContext):
            raise ValueError("market_context must be a MarketContext result.")
        if (
            underlying_context.trend == market_context.trend
            and underlying_context.momentum == market_context.momentum
        ):
            return "ALIGNED"
        if underlying_context.trend == "UNKNOWN" or market_context.trend == "UNKNOWN":
            return "NEUTRAL"
        return "CONFLICTING"