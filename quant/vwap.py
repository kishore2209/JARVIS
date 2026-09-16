class VWAP:
    @staticmethod
    def calculate(prices, volumes):
        if len(prices) != len(volumes):
            raise ValueError("Prices and volumes must have the same length.")
        if not prices:
            raise ValueError("At least one price and volume value is required.")

        total_volume = sum(volumes)
        if total_volume == 0:
            raise ValueError("Total volume cannot be zero.")

        price_volume_total = sum(
            price * volume for price, volume in zip(prices, volumes)
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
            "position": position,
        }
