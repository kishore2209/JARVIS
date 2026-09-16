from market.fno.universe import FNOUniverse
from market.fno.validators import validate_instrument


class ActiveFNOUniverseBuilder:
    """Builds a current analysis universe from normalized, active F&O instruments."""

    DERIVATIVE_TYPES = {"FUTURE", "OPTION"}

    def build(self, instruments):
        active_instruments = []
        for instrument in instruments:
            try:
                validate_instrument(instrument, require_active=True)
            except ValueError:
                continue
            if instrument.instrument_type in self.DERIVATIVE_TYPES:
                active_instruments.append(instrument)
        return FNOUniverse(active_instruments)

    @staticmethod
    def underlying_symbols(universe):
        return sorted({instrument.underlying_symbol for instrument in universe.all()})

    @staticmethod
    def call_options(universe):
        return [instrument for instrument in universe.options() if instrument.option_type == "CE"]

    @staticmethod
    def put_options(universe):
        return [instrument for instrument in universe.options() if instrument.option_type == "PE"]