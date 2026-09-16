class Indicators:
    @staticmethod
    def ema(prices, period):
        if len(prices) < period:
            raise ValueError(f"At least {period} prices are required to calculate EMA.")

        multiplier = 2 / (period + 1)
        ema_value = sum(prices[:period]) / period

        for price in prices[period:]:
            ema_value = ((price - ema_value) * multiplier) + ema_value

        return ema_value

    @staticmethod
    def ema_set(prices):
        return {
            "ema_20": Indicators.ema(prices, 20),
            "ema_50": Indicators.ema(prices, 50),
            "ema_200": Indicators.ema(prices, 200),
        }
