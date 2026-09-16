class RSI:
    @staticmethod
    def calculate(prices, period=14):
        if len(prices) <= period:
            raise ValueError(
                f"At least {period + 1} prices are required to calculate RSI."
            )

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]

            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        average_gain = sum(gains[:period]) / period
        average_loss = sum(losses[:period]) / period

        if average_loss == 0:
            return 100.0

        relative_strength = average_gain / average_loss
        rsi = 100 - (100 / (1 + relative_strength))

        for i in range(period, len(gains)):
            average_gain = (
                (average_gain * (period - 1)) + gains[i]
            ) / period

            average_loss = (
                (average_loss * (period - 1)) + losses[i]
            ) / period

            if average_loss == 0:
                rsi = 100.0
            else:
                relative_strength = average_gain / average_loss
                rsi = 100 - (100 / (1 + relative_strength))

        return rsi


if __name__ == "__main__":
    prices = list(range(100, 131))

    print("================================")
    print("       J.A.R.V.I.S RSI")
    print("================================")

    result = RSI.calculate(prices, 14)

    print("RSI 14:", result)