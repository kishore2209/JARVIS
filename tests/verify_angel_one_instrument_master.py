# Run from the project root: python tests/verify_angel_one_instrument_master.py
"""Manual read-only verification of Angel One's public instrument-master endpoint."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.fno.instrument_master_service import AngelOneFNOUniverseService
from market.fno.universe import FNOUniverse
from market.providers.angel_one_instrument_master import InstrumentMasterDownloadError


def main():
    service = AngelOneFNOUniverseService()

    print("=" * 40)
    print("J.A.R.V.I.S ANGEL ONE MASTER VERIFY")
    print("=" * 40)

    try:
        raw_records = service.client.fetch_records()
        print("HTTP/download success: PASS")
        print(f"Raw records downloaded: {len(raw_records)}")
    except InstrumentMasterDownloadError as error:
        print("HTTP/download success: FAIL")
        print(f"Reason: {error}")
        return 1

    try:
        instruments = service.adapter.normalize_records(raw_records)
    except ValueError as error:
        print("Normalization: FAIL")
        print(f"Reason: {error}")
        return 1

    universe = FNOUniverse(instruments)
    print("Normalization: PASS")
    print(f"Normalized F&O instruments: {len(universe.all())}")

    sample_instruments = universe.all()[:5]
    print("Sample normalized instruments:")
    if not sample_instruments:
        print("None")
    for instrument in sample_instruments:
        print(
            f"- {instrument.symbol} | {instrument.instrument_type} | "
            f"{instrument.exchange} | token={instrument.token} | "
            f"expiry={instrument.expiry} | source={instrument.source} | "
            f"timestamp={instrument.timestamp.isoformat()} | fresh={instrument.is_fresh}"
        )

    if raw_records:
        record = raw_records[0]
        timestamp = record["timestamp"].isoformat()
        print(f"Retrieval metadata: source={record['source']} | timestamp={timestamp} | fresh={record['is_fresh']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())