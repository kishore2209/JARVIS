class VolumeAnalyzer:

    @staticmethod
    def analyze(volumes, period=5):
        if len(volumes) < period + 1:
            raise ValueError(
                f"At least {period + 1} volume values are required."
            )

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
            "signal": signal
        }


if __name__ == "__main__":

    volumes = [
        100000,
        105000,
        110000,
        108000,
        115000,
        150000
    ]

    print("================================")
    print("      J.A.R.V.I.S VOLUME")
    print("================================")

    result = VolumeAnalyzer.analyze(
        volumes,
        period=5
    )

    print("Period:", result["period"])
    print("Current Volume:", result["current_volume"])
    print("Average Volume:", result["average_volume"])
    print("Volume Signal:", result["signal"])