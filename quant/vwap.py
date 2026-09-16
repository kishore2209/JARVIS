class VWAP:

    @staticmethod
    def calculate(prices, volumes):
        if len(prices) != len(volumes):
            raise ValueError(
                "Prices and volumes must have the same length."
            )

        if not prices:
            raise ValueError(
                "At least one price and volume value is required."
            )

        total_volume = sum(volumes)

        if total_volume == 0:
            raise ValueError(
                "Total volume cannot be zero."
            )

        price_volume_total = sum(
            price * volume
            for price, volume in zip(prices, volumes)
        )

        vwap = price_volume_total / total_volume

        current_price = prices[-1]

        if current_price > vwap:
            position = "ABOVE_VWAP"
        elif current_price < vwap:
            position = "BELOW_VWAP"
        else:
            position = "AT_VWAP"

        return {
            "vwap": vwap,
            "current_price": current_price,
            "position": position
        }


if __name__ == "__main__":

    prices = [
        100, 102, 101, 104, 106
    ]

    volumes = [
        10000, 12000, 15000, 18000, 20000
    ]

    print("================================")
    print("        J.A.R.V.I.S VWAP")
    print("================================")

    result = VWAP.calculate(
        prices,
        volumes
    )

    print("VWAP:", result["vwap"])
    print("Current Price:", result["current_price"])
    print("Position:", result["position"])