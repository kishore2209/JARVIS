# Run from the project root: python tests/test_market_data.py
"""Offline deterministic tests for the market-data adapter foundation."""

import sys
from datetime import timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.ohlcv import MarketQuote, OHLCV
from market.providers.mock import MockMarketDataProvider
from quant.indicators import Indicators
from quant.volume import VolumeAnalyzer
from quant.vwap import VWAP


def main():
    provider = MockMarketDataProvider()
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

    def test_mock_provider():
        if provider.source != "MOCK":
            raise AssertionError("Mock provider source must be MOCK.")

    def test_ltp():
        if provider.get_ltp("JARVIS", "NSE", "000001") != 219.5:
            raise AssertionError("Mock LTP does not match the deterministic latest close.")

    def test_quote():
        quote = provider.get_quote("JARVIS", "NSE")
        if not isinstance(quote, MarketQuote) or quote.close != quote.ltp:
            raise AssertionError("Quote was not normalized correctly.")

    def test_ohlcv():
        candles = provider.get_candles("JARVIS", "NSE", limit=240)
        if len(candles) != 240 or not all(isinstance(candle, OHLCV) for candle in candles):
            raise AssertionError("Expected 240 normalized OHLCV candles.")

    def test_timestamp():
        quote = provider.get_quote("JARVIS", "NSE")
        if quote.timestamp.tzinfo != timezone.utc:
            raise AssertionError("Timestamp must be UTC-aware.")

    def test_source():
        candle = provider.get_candles("JARVIS", "NSE", limit=1)[0]
        if candle.source != "MOCK" or not candle.is_fresh:
            raise AssertionError("Mock source or freshness is incorrect.")

    def test_normalization():
        candle = provider.get_candles("JARVIS", "NSE", limit=1)[0]
        if (candle.symbol, candle.exchange, candle.open, candle.high, candle.low) != ("JARVIS", "NSE", 99.8, 100.4, 99.5):
            raise AssertionError("OHLCV fields are not normalized as expected.")

    def test_validation():
        try:
            provider.get_quote("INVALID", "NSE")
        except ValueError:
            return
        raise AssertionError("Invalid symbol did not raise ValueError.")

    def test_quant_integration():
        candles = provider.get_candles("JARVIS", "NSE", limit=240)
        closes = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        if Indicators.ema(closes, 200) <= 0:
            raise AssertionError("Quant engine could not calculate EMA from normalized closes.")
        if VolumeAnalyzer.analyze(volumes)["signal"] not in {"HIGH", "LOW", "NORMAL"}:
            raise AssertionError("Quant engine could not analyze normalized volumes.")
        if VWAP.calculate(closes, volumes)["vwap"] <= 0:
            raise AssertionError("Quant engine could not calculate VWAP from normalized data.")

    print("=" * 40)
    print("J.A.R.V.I.S MARKET DATA TEST")
    print("=" * 40)
    run_test("Mock Provider", test_mock_provider)
    run_test("LTP", test_ltp)
    run_test("Quote", test_quote)
    run_test("OHLCV", test_ohlcv)
    run_test("Timestamp", test_timestamp)
    run_test("Source", test_source)
    run_test("Normalization", test_normalization)
    run_test("Validation", test_validation)
    run_test("Quant Integration", test_quant_integration)

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