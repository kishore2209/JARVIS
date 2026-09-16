class MomentumDetector:

    @staticmethod
    def calculate(prices, period=10):
        if len(prices) <= period:
            raise ValueError(
                f"At least {period + 1} prices are required."
            )

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
            "direction": direction
        }


if __name__ == "__main__":

    prices = [
        100, 101, 102, 101, 103,
        105, 104, 106, 108, 109,
        111, 112, 114, 113, 115
    ]

    print("================================")
    print("    J.A.R.V.I.S MOMENTUM")
    print("================================")

    result = MomentumDetector.calculate(
        prices,
        period=10
    )

    print("Period:", result["period"])
    print("Current Price:", result["current_price"])
    print("Previous Price:", result["previous_price"])
    print("Momentum:", result["momentum"])
    print("Direction:", result["direction"])