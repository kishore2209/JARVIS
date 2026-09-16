class VolumeAnalyzer:
    @staticmethod
    def analyze(volumes, period=5):
        if len(volumes) < period + 1:
            raise ValueError(f"At least {period + 1} volume values are required.")

        current_volume = volumes[-1]
        previous_volumes = volumes[-1 - period:-1]
        average_volume = sum(previous_volumes) / period

        if current_volume > average_volume:
            signal = "HIGH"
        elif current_volume < average_volume:
            signal = "LOW"
        else:
            signal = "NORMAL"

        return {
            "period": period,
            "current_volume": current_volume,
            "average_volume": average_volume,
            "signal": signal,
        }
