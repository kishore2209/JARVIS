from dataclasses import dataclass
from datetime import datetime

from quant.indicators import Indicators
from quant.market_structure import MarketStructure
from quant.momentum import MomentumDetector
from quant.rsi import RSI
from quant.swing import SwingPoints
from quant.trend import TrendDetector
from quant.volume import VolumeAnalyzer


@dataclass
class MarketContext:
    """Read-only broader-market context for an index, sector, or F&O underlying."""

    timestamp: datetime
    instrument: str
    price: float
    ema20: float
    ema50: float
    ema200: float
    rsi: float
    trend: str
    structure: str
    momentum: str
    volume_condition: str
    regime: str
    source: str
    is_fresh: bool


class MarketContextEngine:
    """Composes existing quant calculations over normalized OHLCV data."""

    MINIMUM_CANDLES = 200

    def analyze(self, candles):
        if len(candles) < self.MINIMUM_CANDLES:
            raise ValueError(f"At least {self.MINIMUM_CANDLES} candles are required for market context.")

        prices = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        latest = candles[-1]
        ema_values = Indicators.ema_set(prices)
        rsi = RSI.calculate(prices, 14)
        swings = SwingPoints.find(prices)
        structure_points = MarketStructure.detect(swings["swing_highs"], swings["swing_lows"])
        trend = TrendDetector.detect(structure_points)
        momentum = MomentumDetector.calculate(prices)["direction"]
        volume_condition = VolumeAnalyzer.analyze(volumes)["signal"]

        return MarketContext(
            timestamp=latest.timestamp,
            instrument=latest.symbol,
            price=latest.close,
            ema20=ema_values["ema_20"],
            ema50=ema_values["ema_50"],
            ema200=ema_values["ema_200"],
            rsi=rsi,
            trend=trend,
            structure=self._structure_label(structure_points),
            momentum=momentum,
            volume_condition=volume_condition,
            regime=self._regime(trend, momentum),
            source=latest.source,
            is_fresh=latest.is_fresh,
        )

    def analyze_provider(self, provider, symbol, exchange="NSE", token=None, limit=240):
        candles = provider.get_candles(symbol, exchange, token, limit)
        return self.analyze(candles)

    @staticmethod
    def _structure_label(structure_points):
        types = {point["type"] for point in structure_points}
        if {"HH", "HL"}.issubset(types):
            return "HH_HL"
        if {"LH", "LL"}.issubset(types):
            return "LH_LL"
        return "UNKNOWN"

    @staticmethod
    def _regime(trend, momentum):
        if trend == "BULLISH" and momentum == "POSITIVE":
            return "BULLISH_CONTEXT"
        if trend == "BEARISH" and momentum == "NEGATIVE":
            return "BEARISH_CONTEXT"
        return "NEUTRAL_CONTEXT"