# Run from the project root: python tests/test_quant_all.py
"""Deterministic smoke tests for all J.A.R.V.I.S. quant engine modules."""

import math
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from quant.indicators import Indicators
from quant.macd import MACD
from quant.market_structure import MarketStructure
from quant.momentum import MomentumDetector
from quant.rsi import RSI
from quant.support_resistance import SupportResistance
from quant.swing import SwingPoints
from quant.trend import TrendDetector
from quant.volume import VolumeAnalyzer
from quant.vwap import VWAP


def main():
    prices = [100 + index * 0.5 for index in range(240)]
    volumes = [1000 + (index % 7) * 100 for index in range(239)] + [2500]
    swing_prices = [100, 105, 102, 108, 104, 111, 106, 114, 108, 117, 110]
    results = []

    def run_test(name, test):
        try:
            test()
            results.append((name, True, ""))
            print(f"[PASS] {name}")
        except Exception as error:
            results.append((name, False, str(error)))
            print(f"[FAIL] {name}")
            print(f"Reason: {error}")

    def test_ema(period):
        value = Indicators.ema(prices, period)
        values = Indicators.ema_set(prices)
        expected_key = f"ema_{period}"
        if not math.isfinite(value) or not math.isclose(value, values[expected_key]):
            raise AssertionError("EMA result is invalid or differs from ema_set().")

    def test_rsi():
        value = RSI.calculate(prices, 14)
        if not math.isclose(value, 100.0):
            raise AssertionError(f"Expected RSI 100.0, got {value}.")

    def test_swing_points():
        result = SwingPoints.find(swing_prices, window=1)
        if len(result["swing_highs"]) < 2 or len(result["swing_lows"]) < 2:
            raise AssertionError("Expected multiple swing highs and swing lows.")

    def test_market_structure():
        swings = SwingPoints.find(swing_prices, window=1)
        result = MarketStructure.detect(swings["swing_highs"], swings["swing_lows"])
        types = {item["type"] for item in result}
        if not {"HH", "HL"}.issubset(types):
            raise AssertionError(f"Expected HH and HL structure, got {types}.")

    def test_trend():
        result = TrendDetector.detect([
            {"type": "HH", "price": 108, "index": 3},
            {"type": "HL", "price": 104, "index": 4},
        ])
        if result != "BULLISH":
            raise AssertionError(f"Expected BULLISH, got {result}.")

    def test_momentum():
        result = MomentumDetector.calculate(prices, period=10)
        if result["direction"] != "POSITIVE" or result["momentum"] <= 0:
            raise AssertionError(f"Expected positive momentum, got {result}.")

    def test_volume():
        result = VolumeAnalyzer.analyze(volumes, period=5)
        if result["signal"] != "HIGH":
            raise AssertionError(f"Expected HIGH volume, got {result['signal']}.")

    def test_support_resistance():
        result = SupportResistance.detect(swing_prices, window=1)
        if len(result["supports"]) < 2 or len(result["resistances"]) < 2:
            raise AssertionError("Expected multiple supports and resistances.")

    def test_vwap():
        result = VWAP.calculate(prices, volumes)
        if not math.isfinite(result["vwap"]) or result["position"] != "ABOVE_VWAP":
            raise AssertionError(f"Expected a valid VWAP below the current price, got {result}.")

    def test_macd():
        result = MACD.calculate(prices)
        if not all(math.isfinite(result[key]) for key in ("macd", "signal", "histogram")):
            raise AssertionError(f"Expected finite MACD values, got {result}.")

    print("=" * 40)
    print("J.A.R.V.I.S QUANT ENGINE TEST")
    print("=" * 40)
    run_test("EMA 20", lambda: test_ema(20))
    run_test("EMA 50", lambda: test_ema(50))
    run_test("EMA 200", lambda: test_ema(200))
    run_test("RSI 14", test_rsi)
    run_test("Swing Points", test_swing_points)
    run_test("Market Structure", test_market_structure)
    run_test("Trend Detection", test_trend)
    run_test("Momentum", test_momentum)
    run_test("Volume Analysis", test_volume)
    run_test("Support/Resistance", test_support_resistance)
    run_test("VWAP", test_vwap)
    run_test("MACD", test_macd)

    passed = sum(passed for _, passed, _ in results)
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