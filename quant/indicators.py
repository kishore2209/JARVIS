class Indicators:
    @staticmethod
    def ema(prices, period):
        if len(prices) < period:
            raise ValueError(
                f"At least {period} prices are required to calculate EMA."
            )

        multiplier = 2 / (period + 1)

        # First EMA value = SMA
        ema_value = sum(prices[:period]) / period

        for price in prices[period:]:
            ema_value = (
                (price - ema_value) * multiplier
            ) + ema_value

        return ema_value


if __name__ == "__main__":
    prices = [
        100, 102, 101, 105, 107,
        106, 108, 110, 109, 112
    ]

    print("================================")
    print("       J.A.R.V.I.S QUANT")
    print("================================")

    print("EMA 5:", Indicators.ema(prices, 5))