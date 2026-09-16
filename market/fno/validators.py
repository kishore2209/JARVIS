from datetime import date


VALID_INSTRUMENT_TYPES = {"FUTURE", "OPTION", "EQUITY", "F&O_UNDERLYING"}
VALID_OPTION_TYPES = {"CE", "PE"}


def validate_instrument(instrument, require_active=False):
    """Raise ValueError when a normalized F&O instrument is not usable."""
    if not instrument.symbol or not instrument.symbol.strip():
        raise ValueError("symbol is required.")
    if not instrument.exchange or not instrument.token:
        raise ValueError("exchange and token are required.")
    if instrument.instrument_type not in VALID_INSTRUMENT_TYPES:
        raise ValueError("invalid instrument_type.")
    if not instrument.underlying_symbol:
        raise ValueError("underlying_symbol is required.")
    if instrument.lot_size <= 0:
        raise ValueError("lot_size must be positive.")
    if instrument.tick_size <= 0:
        raise ValueError("tick_size must be positive.")

    is_derivative = instrument.instrument_type in {"FUTURE", "OPTION"}
    if is_derivative and (not isinstance(instrument.expiry, date) or instrument.expiry <= instrument.timestamp.date()):
        raise ValueError("derivative expiry must be a future date.")
    if instrument.instrument_type == "OPTION":
        if instrument.strike is None or instrument.strike <= 0:
            raise ValueError("option strike must be positive.")
        if instrument.option_type not in VALID_OPTION_TYPES:
            raise ValueError("option_type must be CE or PE.")
    if require_active and not instrument.active:
        raise ValueError("instrument is inactive.")

    return instrument