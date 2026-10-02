"""Wilder ATR v1: seed is mean of first N true ranges after previous close."""
from math import isfinite


def atr(candles, period=14):
    if type(period) is not int or period < 1 or len(candles) < period + 1:
        raise ValueError('ATR needs period+1 candles and a positive integer period')
    ranges = []
    for previous, current in zip(candles, candles[1:]):
        values = (previous.close, current.high, current.low)
        if not all(isfinite(float(x)) for x in values) or current.high < current.low:
            raise ValueError('Invalid ATR prices')
        ranges.append(max(current.high-current.low, abs(current.high-previous.close), abs(current.low-previous.close)))
    value = sum(ranges[:period])/period
    for tr in ranges[period:]: value = (value*(period-1)+tr)/period
    return value
