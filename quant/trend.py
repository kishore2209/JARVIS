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
