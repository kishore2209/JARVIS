class SwingPoints:
    @staticmethod
    def find(prices, window=2):
        if len(prices) < (window * 2 + 1):
            raise ValueError(f"At least {window * 2 + 1} prices are required.")

        swing_highs = []
        swing_lows = []

        for i in range(window, len(prices) - window):
            current = prices[i]
            left = prices[i - window:i]
            right = prices[i + 1:i + window + 1]

            if all(current > price for price in left + right):
                swing_highs.append({"index": i, "price": current})

            if all(current < price for price in left + right):
                swing_lows.append({"index": i, "price": current})

        return {"swing_highs": swing_highs, "swing_lows": swing_lows}
