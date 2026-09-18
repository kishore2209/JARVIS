from market.strategies.evidence import StrategyEvidence
from quant.swing import SwingPoints


def _result(name, analysis, direction="NEUTRAL", strength="LOW", evidence=(), conflicts=(), invalidations=(), completeness="COMPLETE", alignment="NOT_AVAILABLE"):
    return StrategyEvidence(name, analysis.instrument, analysis.timestamp, direction, strength, tuple(evidence), tuple(conflicts), tuple(invalidations), analysis.source, analysis.is_fresh, completeness, alignment)


class TrendFollowingStrategy:
    name = "TREND_FOLLOWING"

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        bullish = analysis.ema20 > analysis.ema50 > analysis.ema200 and analysis.trend == "BULLISH" and analysis.momentum == "POSITIVE"
        bearish = analysis.ema20 < analysis.ema50 < analysis.ema200 and analysis.trend == "BEARISH" and analysis.momentum == "NEGATIVE"
        alignment = analysis.market_context_alignment
        if bullish:
            return _result(self.name, analysis, "BULLISH", "HIGH", ("EMA20 > EMA50 > EMA200", "bullish structure", "positive momentum"), ("market context conflicts",) if alignment == "CONFLICTING" else (), ("EMA ordering no longer bullish",), alignment=alignment)
        if bearish:
            return _result(self.name, analysis, "BEARISH", "HIGH", ("EMA20 < EMA50 < EMA200", "bearish structure", "negative momentum"), ("market context conflicts",) if alignment == "CONFLICTING" else (), ("EMA ordering no longer bearish",), alignment=alignment)
        return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("trend conditions are not fully aligned",), completeness="PARTIAL", alignment=alignment)


class SupportResistanceStrategy:
    name = "SUPPORT_RESISTANCE"

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        supports = [point["price"] for point in analysis.supports]
        resistances = [point["price"] for point in analysis.resistances]
        if not supports and not resistances:
            return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("no completed swing levels",), completeness="PARTIAL")
        nearest_support = max((level for level in supports if level <= analysis.price), default=None)
        nearest_resistance = min((level for level in resistances if level >= analysis.price), default=None)
        proximity = analysis.price * 0.01
        if nearest_support is not None and analysis.price - nearest_support <= proximity:
            return _result(self.name, analysis, "BULLISH", "MEDIUM", (f"price near observed support {nearest_support}",), (), (f"completed close below {nearest_support}",))
        if nearest_resistance is not None and nearest_resistance - analysis.price <= proximity:
            return _result(self.name, analysis, "BEARISH", "MEDIUM", (f"price near observed resistance {nearest_resistance}",), (), (f"completed close above {nearest_resistance}",))
        return _result(self.name, analysis, evidence=("price is between observed swing levels",))


class BreakoutStrategy:
    name = "BREAKOUT_BREAKDOWN"

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        if len(candles) < 6:
            return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("fewer than six completed candles",), completeness="PARTIAL")
        closes = [candle.close for candle in candles]
        prior_high = max(closes[-6:-1])
        prior_low = min(closes[-6:-1])
        confirmed = analysis.volume_condition == "HIGH"
        if closes[-1] > prior_high:
            return _result(self.name, analysis, "BULLISH", "HIGH" if confirmed else "LOW", (f"completed close above prior range high {prior_high}", "high volume confirmation" if confirmed else "volume confirmation missing"), () if confirmed else ("weak breakout evidence",), (f"completed close below {prior_high}",))
        if closes[-1] < prior_low:
            return _result(self.name, analysis, "BEARISH", "HIGH" if confirmed else "LOW", (f"completed close below prior range low {prior_low}", "high volume confirmation" if confirmed else "volume confirmation missing"), () if confirmed else ("weak breakdown evidence",), (f"completed close above {prior_low}",))
        return _result(self.name, analysis, evidence=("latest completed candle remains inside prior range",))


class VolumeConfirmationStrategy:
    name = "VOLUME_CONFIRMATION"

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        if analysis.volume_condition != "HIGH":
            return _result(self.name, analysis, strength="LOW", evidence=(f"volume condition is {analysis.volume_condition}",), completeness="PARTIAL")
        if analysis.momentum == "POSITIVE":
            return _result(self.name, analysis, "BULLISH", "MEDIUM", ("high volume confirms positive momentum",))
        if analysis.momentum == "NEGATIVE":
            return _result(self.name, analysis, "BEARISH", "MEDIUM", ("high volume confirms negative momentum",))
        return _result(self.name, analysis, evidence=("high volume without directional momentum",))


class DemandSupplyStrategy:
    name = "DEMAND_SUPPLY"

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        demand = [point["price"] for point in analysis.supports[-3:]]
        supply = [point["price"] for point in analysis.resistances[-3:]]
        if not demand and not supply:
            return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("no swing zones available",), completeness="PARTIAL")
        near_demand = any(abs(analysis.price - level) <= analysis.price * .01 for level in demand)
        near_supply = any(abs(analysis.price - level) <= analysis.price * .01 for level in supply)
        direction = "BULLISH" if near_demand else "BEARISH" if near_supply else "NEUTRAL"
        return _result(self.name, analysis, direction, "MEDIUM" if direction != "NEUTRAL" else "LOW", (f"candidate demand zones: {demand}", f"candidate supply zones: {supply}", "zones are swing-derived observations"), (), ("price exits the nearby candidate zone",))


class FibonacciStrategy:
    name = "FIBONACCI_RETRACEMENT"

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        swings = SwingPoints.find([candle.close for candle in candles])
        anchors = swings["swing_lows"][-1:] + swings["swing_highs"][-1:]
        if len(anchors) < 2:
            return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("two swing anchors are required",), completeness="PARTIAL")
        low, high = sorted((point["price"] for point in anchors))
        if low == high:
            return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("swing range is zero",), completeness="PARTIAL")
        levels = {ratio: high - (high - low) * ratio for ratio in (.236, .382, .5, .618, .786)}
        nearest_ratio = min(levels, key=lambda ratio: abs(levels[ratio] - analysis.price))
        return _result(self.name, analysis, evidence=(f"swing anchors low={low}, high={high}", f"retracement levels={levels}", f"nearest retracement={nearest_ratio}"), invalidations=("swing anchors are replaced by later completed swings",))


class PatternStrategy:
    name = "CHART_PATTERNS"
    tolerance = .01

    def evaluate(self, candles, analysis, market_context=None, fno_intelligence=None):
        swings = SwingPoints.find([candle.close for candle in candles], window=1)
        for label, points, direction in (("DOUBLE_TOP", swings["swing_highs"], "BEARISH"), ("DOUBLE_BOTTOM", swings["swing_lows"], "BULLISH")):
            if len(points) >= 2:
                first, second = points[-2:]
                if abs(first["price"] - second["price"]) / first["price"] <= self.tolerance:
                    return _result(self.name, analysis, direction, "MEDIUM", (f"{label} points={first, second}", f"tolerance={self.tolerance}"), (), ("completed candle breaks the pattern extreme",))
        return _result(self.name, analysis, strength="INSUFFICIENT", evidence=("no deterministic double top or double bottom",), completeness="PARTIAL")