# Run from the project root: python tests/verify_angel_one_fno_intelligence.py
"""Safe read-only capability check for future Angel One F&O intelligence data."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.providers.angel_one import AngelOneMarketDataProvider


def main():
    provider = AngelOneMarketDataProvider()
    print("Live F&O/OI verification skipped: current AngelOneMarketDataProvider has no supported read-only OI or option-chain retrieval method.")
    print(f"Provider source: {provider.source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())