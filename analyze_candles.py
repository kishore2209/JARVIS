"""Read-only historical candle analysis: python analyze_candles.py FILE --interval 15m."""
import argparse
import json
from pathlib import Path
from market.historical_analysis import analyze_file_text
from market.data_pipeline import MAX_FILE_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--interval", choices=["1m", "3m", "5m", "15m", "30m", "1h", "1d"])
    args = parser.parse_args()
    try:
        if args.file.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Candle file exceeds 5 MB.")
        result = analyze_file_text(args.file.read_text(encoding="utf-8-sig"), args.file.suffix.lstrip(".").lower(), args.interval)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Analysis rejected: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
