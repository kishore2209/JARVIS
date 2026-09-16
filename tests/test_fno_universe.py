# Run from the project root: python tests/test_fno_universe.py
"""Offline deterministic tests for the J.A.R.V.I.S. F&O universe."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.fno.models import FNOInstrument
from market.fno.instrument_master import AngelOneInstrumentMasterAdapter
from market.fno.universe import FNOUniverse, mock_fno_records
from market.fno.validators import validate_instrument


def main():
    universe = FNOUniverse(mock_fno_records())
    adapter = AngelOneInstrumentMasterAdapter(datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc))
    results = []

    def run_test(name, test):
        try:
            test()
            results.append((name, True))
            print(f"[PASS] {name}")
        except Exception as error:
            results.append((name, False))
            print(f"[FAIL] {name}")
            print(f"Reason: {error}")

    def test_model_creation():
        instrument = universe.all()[0]
        if not isinstance(instrument, FNOInstrument) or instrument.timestamp.tzinfo != timezone.utc:
            raise AssertionError("F&O model was not created with a UTC timestamp.")

    def test_valid_instrument():
        if validate_instrument(universe.all()[0], require_active=True).symbol != "RELIANCE26SEP_FUT":
            raise AssertionError("Expected valid active RELIANCE future.")

    def test_invalid_instrument():
        record = mock_fno_records()[0]
        record["lot_size"] = 0
        try:
            FNOUniverse([record])
        except ValueError:
            return
        raise AssertionError("Invalid lot size was accepted.")

    def test_active_filtering():
        if len(universe.active_instruments()) != 5:
            raise AssertionError("Expected five active mock instruments.")

    def test_futures_filtering():
        if len(universe.futures()) != 3:
            raise AssertionError("Expected three active futures.")

    def test_options_filtering():
        if {item.option_type for item in universe.options()} != {"CE", "PE"}:
            raise AssertionError("Expected CE and PE options.")

    def test_symbol_filtering():
        if len(universe.by_underlying("RELIANCE")) != 1:
            raise AssertionError("Expected one RELIANCE instrument.")

    def test_expiry_filtering():
        if len(universe.by_expiry(date(2026, 9, 24))) != 5:
            raise AssertionError("Expected all active mock instruments at the fixed expiry.")

    def test_validation():
        inactive = next(item for item in universe.all() if not item.active)
        try:
            validate_instrument(inactive, require_active=True)
        except ValueError as error:
            if "inactive" in str(error):
                return
            raise
        raise AssertionError("Inactive instrument was accepted for active use.")

    def test_mock_universe_loading():
        if len(universe.all()) != 6 or {item.source for item in universe.all()} != {"MOCK_TEST"}:
            raise AssertionError("Mock universe was not loaded as deterministic test data.")

    def master_record(instrument_type, symbol, **overrides):
        record = {
            "token": "MASTER001", "symbol": symbol, "name": "NIFTY",
            "expiry": "24SEP2026", "strike": "2500000.000000",
            "lotsize": "75", "tick_size": "5.000000",
            "instrumenttype": instrument_type, "exch_seg": "NFO",
        }
        record.update(overrides)
        return record

    def test_master_future():
        instrument = adapter.normalize_record(master_record("FUTIDX", "NIFTY24SEPFUT"))
        if instrument.instrument_type != "FUTURE" or instrument.strike is not None:
            raise AssertionError("Future record was not normalized.")

    def test_master_call_option():
        instrument = adapter.normalize_record(master_record("OPTIDX", "NIFTY24SEP25000CE"))
        if instrument.instrument_type != "OPTION" or instrument.option_type != "CE":
            raise AssertionError("Call option record was not normalized.")

    def test_master_put_option():
        instrument = adapter.normalize_record(master_record("OPTIDX", "NIFTY24SEP25000PE"))
        if instrument.option_type != "PE":
            raise AssertionError("Put option record was not normalized.")

    def test_master_invalid_rejection():
        try:
            adapter.normalize_record(master_record("OPTIDX", "NIFTY24SEP25000CE", lotsize="0"))
        except ValueError:
            return
        raise AssertionError("Malformed record was accepted.")

    def test_master_unsupported_rejection():
        if adapter.normalize_record(master_record("COMDTY", "GOLD", exch_seg="MCX")) is not None:
            raise AssertionError("Unsupported record was not ignored.")

    def test_master_expiry_normalization():
        if adapter.normalize_record(master_record("FUTIDX", "NIFTY24SEPFUT")).expiry != date(2026, 9, 24):
            raise AssertionError("Expiry was not normalized.")

    def test_master_strike_normalization():
        if adapter.normalize_record(master_record("OPTIDX", "NIFTY24SEP25000CE")).strike != 25000.0:
            raise AssertionError("Strike was not normalized.")

    def test_master_lot_and_tick_normalization():
        instrument = adapter.normalize_record(master_record("OPTIDX", "NIFTY24SEP25000CE"))
        if instrument.lot_size != 75 or instrument.tick_size != 0.05:
            raise AssertionError("Lot size or tick size was not normalized.")

    def test_master_source_and_timestamp():
        instrument = adapter.normalize_record(master_record("FUTIDX", "NIFTY24SEPFUT", source="FIXTURE"))
        if instrument.source != "FIXTURE" or instrument.timestamp != adapter.timestamp:
            raise AssertionError("Source or timestamp was not preserved.")

    def test_master_universe_loading():
        records = [master_record("FUTIDX", "NIFTY24SEPFUT"), master_record("OPTIDX", "NIFTY24SEP25000CE")]
        normalized_universe = FNOUniverse(adapter.normalize_records(records))
        if len(normalized_universe.all()) != 2:
            raise AssertionError("Normalized master records did not load into FNOUniverse.")

    print("=" * 40)
    print("J.A.R.V.I.S F&O UNIVERSE TEST")
    print("=" * 40)
    run_test("Model Creation", test_model_creation)
    run_test("Valid Instrument", test_valid_instrument)
    run_test("Invalid Instrument", test_invalid_instrument)
    run_test("Active Filtering", test_active_filtering)
    run_test("Futures Filtering", test_futures_filtering)
    run_test("Options Filtering", test_options_filtering)
    run_test("Symbol Filtering", test_symbol_filtering)
    run_test("Expiry Filtering", test_expiry_filtering)
    run_test("Validation", test_validation)
    run_test("Mock Universe Loading", test_mock_universe_loading)
    run_test("Master Future", test_master_future)
    run_test("Master Call Option", test_master_call_option)
    run_test("Master Put Option", test_master_put_option)
    run_test("Master Invalid Rejection", test_master_invalid_rejection)
    run_test("Master Unsupported Rejection", test_master_unsupported_rejection)
    run_test("Master Expiry Normalization", test_master_expiry_normalization)
    run_test("Master Strike Normalization", test_master_strike_normalization)
    run_test("Master Lot/Tick Normalization", test_master_lot_and_tick_normalization)
    run_test("Master Source/Timestamp", test_master_source_and_timestamp)
    run_test("Master Universe Loading", test_master_universe_loading)

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