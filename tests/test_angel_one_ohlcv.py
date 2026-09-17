# Run from the project root: python tests/test_angel_one_ohlcv.py
"""Offline deterministic tests for Angel One historical OHLCV normalization."""

import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.context import MarketContextEngine
from market.providers.angel_one import AngelOneMarketDataProvider
from market.underlying_analysis import UnderlyingAnalysisEngine


class FakeSmartApi:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.parameters = None

    def getCandleData(self, parameters):
        self.parameters = parameters
        if self.error:
            raise self.error
        return self.response


def main():
    now = datetime(2026, 9, 17, 10, 5, tzinfo=timezone.utc)
    rows = [
        ["2026-09-17T15:30:00", "101", "103", "100", "102", "1000"],
        ["2026-09-17T15:28:00", "100", "102", "99", "101", "900"],
        ["2026-09-17T15:30:00", "101", "103", "100", "102", "1000"],
    ]
    results = []

    def provider(response=None, error=None):
        return AngelOneMarketDataProvider(FakeSmartApi(response, error), clock=lambda: now)

    def candles_for_analysis():
        analysis_rows = []
        for index in range(240):
            minute = index % 60
            hour = 9 + index // 60
            close = 100 + index * 0.4 + [0, 2, 4, 1, -1, 1][index % 6]
            analysis_rows.append([f"2026-09-17T{hour:02d}:{minute:02d}:00", close - .2, close + .4, close - .5, close, 1000 + index % 5 * 100])
        return provider({"status": True, "data": analysis_rows}).get_candles("RELIANCE", "NSE", "500325", 240, "1d", datetime(2025, 9, 17, tzinfo=timezone.utc), now)

    def run_test(name, test):
        try:
            test()
            results.append((name, True))
            print(f"[PASS] {name}")
        except Exception as error:
            results.append((name, False))
            print(f"[FAIL] {name}")
            print(f"Reason: {error}")

    def test_normalization_and_ordering():
        candles = provider({"status": True, "data": rows}).get_candles("RELIANCE", "NSE", "500325", 10, "5m")
        if len(candles) != 2 or candles[0].timestamp >= candles[1].timestamp or candles[-1].close != 102.0:
            raise AssertionError("Candles were not normalized, sorted, and de-duplicated.")

    def test_timestamp_and_metadata():
        candle = provider({"status": True, "data": rows}).get_candles("RELIANCE", "NSE", "500325", 10, "5m")[-1]
        if candle.timestamp.tzinfo != timezone.utc or candle.source != "ANGEL_ONE" or not candle.is_fresh:
            raise AssertionError("Expected UTC source metadata and freshness based on retrieval time.")

    def test_interval_mapping():
        client = FakeSmartApi({"status": True, "data": rows})
        AngelOneMarketDataProvider(client, clock=lambda: now).get_candles("RELIANCE", "NSE", "500325", 10, "15m")
        if client.parameters["interval"] != "FIFTEEN_MINUTE":
            raise AssertionError("Interval mapping is incorrect.")
        if client.parameters["fromdate"] != "2026-09-07 15:35" or client.parameters["todate"] != "2026-09-17 15:35":
            raise AssertionError("Broker request dates must use YYYY-MM-DD HH:MM in Asia/Kolkata time.")

    def test_response_errors():
        for response in ({"status": True, "data": []}, {"status": False, "message": "rate limit"}):
            try:
                provider(response).get_candles("RELIANCE", "NSE", "500325")
            except (ValueError, RuntimeError):
                continue
            raise AssertionError("Invalid API response was accepted.")

    def test_malformed_row_and_api_exception():
        try:
            provider({"status": True, "data": [["bad-time", 1]]}).get_candles("RELIANCE", "NSE", "500325")
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed candle row was accepted.")
        failing_provider = provider(error=ConnectionError("api-key=secret-key token=secret-token unavailable"))
        failing_provider.api_key = "secret-key"
        failing_provider.client_code = "secret-client"
        failing_provider.pin = "secret-pin"
        failing_provider.totp = "secret-totp"
        try:
            failing_provider.get_candles("RELIANCE", "NSE", "500325")
        except RuntimeError as error:
            message = str(error)
            if "ConnectionError" not in message or "secret-key" in message or "secret-token" in message:
                raise AssertionError("SDK error diagnostic was not safely sanitized.")
            return
        raise AssertionError("SDK exception was not reported.")

    def test_engine_compatibility():
        candles = candles_for_analysis()
        context = MarketContextEngine().analyze(candles)
        analysis = UnderlyingAnalysisEngine().analyze(candles, context)
        if context.instrument != "RELIANCE" or analysis.instrument != "RELIANCE":
            raise AssertionError("Normalized candles were not accepted by analysis engines.")

    print("=" * 40)
    print("J.A.R.V.I.S ANGEL ONE OHLCV TEST")
    print("=" * 40)
    run_test("Normalization And Ordering", test_normalization_and_ordering)
    run_test("Timestamp And Metadata", test_timestamp_and_metadata)
    run_test("Interval Mapping", test_interval_mapping)
    run_test("Response Errors", test_response_errors)
    run_test("Malformed Row And API Exception", test_malformed_row_and_api_exception)
    run_test("Analysis Engine Compatibility", test_engine_compatibility)

    passed = sum(passed for _, passed in results)
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