class MomentumDetector:
    @staticmethod
    def calculate(prices, period=10):
        if len(prices) <= period:
            raise ValueError(f"At least {period + 1} prices are required.")

        current_price = prices[-1]
        previous_price = prices[-1 - period]
        momentum = current_price - previous_price

        if momentum > 0:
            direction = "POSITIVE"
        elif momentum < 0:
            direction = "NEGATIVE"
        else:
            direction = "NEUTRAL"

        return {
            "period": period,
            "current_price": current_price,
            "previous_price": previous_price,
            "momentum": momentum,
            "direction": direction,
        }
