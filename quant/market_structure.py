class MarketStructure:
    @staticmethod
    def detect(swing_highs, swing_lows):
        structure = []
        previous_high = None
        previous_low = None

        for high in swing_highs:
            price = high["price"]
            if previous_high is not None:
                if price > previous_high:
                    structure.append({"type": "HH", "price": price, "index": high["index"]})
                elif price < previous_high:
                    structure.append({"type": "LH", "price": price, "index": high["index"]})
            previous_high = price

        for low in swing_lows:
            price = low["price"]
            if previous_low is not None:
                if price > previous_low:
                    structure.append({"type": "HL", "price": price, "index": low["index"]})
                elif price < previous_low:
                    structure.append({"type": "LL", "price": price, "index": low["index"]})
            previous_low = price

        structure.sort(key=lambda x: x["index"])
        return structure
