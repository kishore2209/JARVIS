class TrendDetector:
    @staticmethod
    def detect(structure):
        if not structure:
            return "UNKNOWN"

        hh_count = sum(1 for item in structure if item["type"] == "HH")
        hl_count = sum(1 for item in structure if item["type"] == "HL")
        lh_count = sum(1 for item in structure if item["type"] == "LH")
        ll_count = sum(1 for item in structure if item["type"] == "LL")

        bullish = hh_count + hl_count
        bearish = lh_count + ll_count

        if bullish > bearish:
            return "BULLISH"

        if bearish > bullish:
            return "BEARISH"

        return "SIDEWAYS"


if __name__ == "__main__":
    structure = [
        {"type": "HH", "price": 108, "index": 6},
        {"type": "HL", "price": 103, "index": 8},
        {"type": "HH", "price": 110, "index": 10},
        {"type": "HL", "price": 105, "index": 12}
    ]

    trend = TrendDetector.detect(structure)

    print("================================")
    print("       J.A.R.V.I.S TREND")
    print("================================")
    print("Detected Trend:", trend)