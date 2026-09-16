class MACD:
    @staticmethod
    def ema_series(prices, period):
        if len(prices) < period:
            raise ValueError(f"At least {period} prices are required.")

        multiplier = 2 / (period + 1)
        ema_values = []
        ema_value = sum(prices[:period]) / period
        ema_values.append(ema_value)

        for price in prices[period:]:
            ema_value = ((price - ema_value) * multiplier) + ema_value
            ema_values.append(ema_value)

        return ema_values

    @staticmethod
    def calculate(prices, fast_period=12, slow_period=26, signal_period=9):
        minimum_prices = slow_period + signal_period - 1
        if len(prices) < minimum_prices:
            raise ValueError(f"At least {minimum_prices} prices are required.")

        fast_ema = MACD.ema_series(prices, fast_period)
        slow_ema = MACD.ema_series(prices, slow_period)

        fast_start = slow_period - fast_period
        fast_aligned = fast_ema[fast_start:]

        macd_line = [
            fast - slow
            for fast, slow in zip(fast_aligned, slow_ema)
        ]

        signal_line = MACD.ema_series(macd_line, signal_period)

        macd = macd_line[-1]
        signal = signal_line[-1]
        histogram = macd - signal

        return {
            "macd": macd,
            "signal": signal,
            "histogram": histogram,
        }
