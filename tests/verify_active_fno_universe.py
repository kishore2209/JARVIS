# Run from the project root: python tests/verify_active_fno_universe.py
"""Manual read-only verification of the active F&O universe from Angel One data."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.fno.active_universe import ActiveFNOUniverseBuilder
from market.fno.instrument_master_service import AngelOneFNOUniverseService
from market.providers.angel_one_instrument_master import InstrumentMasterDownloadError


def main():
    service = AngelOneFNOUniverseService()
    builder = ActiveFNOUniverseBuilder()

    try:
        normalized_universe = service.load_universe()
        active_universe = builder.build(normalized_universe.all())
    except (InstrumentMasterDownloadError, ValueError) as error:
        print(f"Active F&O universe verification failed: {error}")
        return 1

    underlyings = builder.underlying_symbols(active_universe)
    futures = active_universe.futures()
    calls = builder.call_options(active_universe)
    puts = builder.put_options(active_universe)
    samples = underlyings[:10]

    print("=" * 40)
    print("J.A.R.V.I.S ACTIVE F&O UNIVERSE VERIFY")
    print("=" * 40)
    print(f"Total normalized instruments: {len(normalized_universe.all())}")
    print(f"Active instruments: {len(active_universe.all())}")
    print(f"Unique F&O underlying symbols: {len(underlyings)}")
    print(f"Futures count: {len(futures)}")
    print(f"Call option count: {len(calls)}")
    print(f"Put option count: {len(puts)}")
    print(f"Sample underlyings: {', '.join(samples)}")

    if active_universe.all():
        instrument = active_universe.all()[0]
        print(
            f"Metadata: source={instrument.source} | "
            f"timestamp={instrument.timestamp.isoformat()} | fresh={instrument.is_fresh}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())