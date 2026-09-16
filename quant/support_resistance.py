class SupportResistance:
    @staticmethod
    def detect(prices, window=2):
        if len(prices) < (window * 2 + 1):
            raise ValueError(f"At least {window * 2 + 1} prices are required.")

        supports = []
        resistances = []

        for i in range(window, len(prices) - window):
            current = prices[i]
            left = prices[i - window:i]
            right = prices[i + 1:i + window + 1]

            if all(current < price for price in left + right):
                supports.append({"index": i, "price": current})

            if all(current > price for price in left + right):
                resistances.append({"index": i, "price": current})

        return {"supports": supports, "resistances": resistances}
