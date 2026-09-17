# Run from the project root: python tests/test_fno_intelligence.py
"""Deterministic offline tests for the read-only F&O intelligence engine."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.fno.intelligence import FNOIntelligenceEngine, FuturesMarketData, OptionMarketData
from market.fno.models import FNOInstrument


def main():
    timestamp = datetime(2026, 9, 17, 10, tzinfo=timezone.utc)
    expiry = date(2026, 10, 29)
    engine = FNOIntelligenceEngine()
    results = []

    def future(price_change=10, oi_change=100, fresh=True):
        instrument = FNOInstrument("NIFTY29OCTFUT", "NFO", "FUT1", "FUTURE", "NIFTY", expiry, None, None, 75, .05, True, "MOCK_FNO", timestamp, fresh)
        return FuturesMarketData.from_instrument(instrument, 25000, 10000, 500000, oi_change, price_change)

    def option(strike, option_type, oi, fresh=True):
        instrument = FNOInstrument(f"NIFTY29OCT{strike}{option_type}", "NFO", f"{strike}{option_type}", "OPTION", "NIFTY", expiry, strike, option_type, 75, .05, True, "MOCK_FNO", timestamp, fresh)
        return OptionMarketData.from_instrument(instrument, 100, 1000, oi, 10)

    options = [option(24900, "CE", 100), option(25000, "CE", 300), option(25100, "CE", 200), option(24900, "PE", 400), option(25000, "PE", 150), option(25100, "PE", 250)]

    def run_test(name, test):
        try:
            test()
            results.append((name, True))
            print(f"[PASS] {name}")
        except Exception as error:
            results.append((name, False))
            print(f"[FAIL] {name}")
            print(f"Reason: {error}")

    def test_future_normalization():
        result = engine.analyze_future(future())
        if result.data.contract_symbol != "NIFTY29OCTFUT" or result.data.lot_size != 75:
            raise AssertionError("Future was not normalized from its instrument.")

    def test_oi_interpretations():
        expected = [(10, 1, "LONG_BUILDUP"), (-10, 1, "SHORT_BUILDUP"), (10, -1, "SHORT_COVERING"), (-10, -1, "LONG_UNWINDING")]
        if [engine.analyze_future(future(price, oi)).oi_interpretation for price, oi, _ in expected] != [item[2] for item in expected]:
            raise AssertionError("Price/OI interpretations are incorrect.")

    def test_unknown_missing_data():
        data = future(None, None)
        if engine.analyze_future(data).oi_interpretation != "UNKNOWN":
            raise AssertionError("Missing inputs must not produce an OI interpretation.")

    def test_option_aggregation():
        result = engine.analyze_option_chain("NIFTY", 25020, options)
        if (result.total_ce_oi, result.total_pe_oi, result.pcr) != (600, 800, 800 / 600):
            raise AssertionError("CE/PE OI aggregation or PCR is incorrect.")

    def test_atm_moneyness_and_max_oi():
        result = engine.analyze_option_chain("NIFTY", 25020, options)
        if result.atm_strike != 25000 or result.highest_ce_oi_strike != 25000 or result.highest_pe_oi_strike != 24900:
            raise AssertionError("ATM or max OI strikes are incorrect.")
        if result.strike_moneyness["NIFTY29OCT24900CE"] != "ITM" or result.strike_moneyness["NIFTY29OCT25100PE"] != "ITM":
            raise AssertionError("ITM/ATM/OTM classification is incorrect.")

    def test_validation_and_metadata():
        try:
            engine.analyze_future(future(fresh=False))
        except ValueError:
            pass
        else:
            raise AssertionError("Stale future data was accepted.")
        malformed = option(25000, "CE", -1)
        try:
            engine.analyze_option_chain("NIFTY", 25020, [malformed])
        except ValueError:
            pass
        else:
            raise AssertionError("Negative option OI was accepted.")
        result = engine.analyze_option_chain("NIFTY", 25020, options)
        if result.source != "MOCK_FNO" or result.timestamp != timestamp or not result.is_fresh:
            raise AssertionError("Option-chain metadata was not preserved.")

    def test_deterministic_output():
        if engine.analyze_option_chain("NIFTY", 25020, options) != engine.analyze_option_chain("NIFTY", 25020, options):
            raise AssertionError("Option-chain analysis was not deterministic.")

    print("=" * 40)
    print("J.A.R.V.I.S F&O INTELLIGENCE TEST")
    print("=" * 40)
    run_test("Futures Normalization", test_future_normalization)
    run_test("OI Interpretations", test_oi_interpretations)
    run_test("Unknown Missing Data", test_unknown_missing_data)
    run_test("Option Aggregation", test_option_aggregation)
    run_test("ATM Moneyness And Max OI", test_atm_moneyness_and_max_oi)
    run_test("Validation And Metadata", test_validation_and_metadata)
    run_test("Deterministic Output", test_deterministic_output)
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