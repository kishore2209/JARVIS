from datetime import date, datetime, timezone

from market.fno.models import FNOInstrument
from market.fno.validators import validate_instrument


class FNOUniverse:
    """In-memory F&O universe independent of any broker or exchange adapter."""

    def __init__(self, records=None):
        self._instruments = []
        if records:
            self.load(records)

    def load(self, records):
        loaded = []
        for record in records:
            instrument = record if isinstance(record, FNOInstrument) else FNOInstrument.from_record(record)
            loaded.append(validate_instrument(instrument))
        self._instruments.extend(loaded)
        return loaded

    def all(self):
        return list(self._instruments)

    def active_instruments(self):
        return [instrument for instrument in self._instruments if instrument.active]

    def by_underlying(self, underlying_symbol, active_only=True):
        instruments = self.active_instruments() if active_only else self.all()
        return [instrument for instrument in instruments if instrument.underlying_symbol == underlying_symbol]

    def by_expiry(self, expiry, active_only=True):
        instruments = self.active_instruments() if active_only else self.all()
        return [instrument for instrument in instruments if instrument.expiry == expiry]

    def futures(self, active_only=True):
        instruments = self.active_instruments() if active_only else self.all()
        return [instrument for instrument in instruments if instrument.instrument_type == "FUTURE"]

    def options(self, active_only=True):
        instruments = self.active_instruments() if active_only else self.all()
        return [instrument for instrument in instruments if instrument.instrument_type == "OPTION"]


def mock_fno_records():
    """Fixed TEST data only; it does not represent the current NSE F&O universe."""
    timestamp = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)
    expiry = date(2026, 9, 24)
    return [
        {"symbol": "RELIANCE26SEP_FUT", "exchange": "NFO", "token": "MOCK001", "instrument_type": "FUTURE", "underlying_symbol": "RELIANCE", "expiry": expiry, "strike": None, "option_type": None, "lot_size": 250, "tick_size": 0.05, "active": True, "source": "MOCK_TEST", "timestamp": timestamp},
        {"symbol": "HDFCBANK26SEP_FUT", "exchange": "NFO", "token": "MOCK002", "instrument_type": "FUTURE", "underlying_symbol": "HDFCBANK", "expiry": expiry, "strike": None, "option_type": None, "lot_size": 550, "tick_size": 0.05, "active": True, "source": "MOCK_TEST", "timestamp": timestamp},
        {"symbol": "INFY26SEP_FUT", "exchange": "NFO", "token": "MOCK003", "instrument_type": "FUTURE", "underlying_symbol": "INFY", "expiry": expiry, "strike": None, "option_type": None, "lot_size": 400, "tick_size": 0.05, "active": True, "source": "MOCK_TEST", "timestamp": timestamp},
        {"symbol": "TCS26SEP_FUT", "exchange": "NFO", "token": "MOCK004", "instrument_type": "FUTURE", "underlying_symbol": "TCS", "expiry": expiry, "strike": None, "option_type": None, "lot_size": 175, "tick_size": 0.05, "active": False, "source": "MOCK_TEST", "timestamp": timestamp},
        {"symbol": "NIFTY26SEP_25000CE", "exchange": "NFO", "token": "MOCK005", "instrument_type": "OPTION", "underlying_symbol": "NIFTY", "expiry": expiry, "strike": 25000.0, "option_type": "CE", "lot_size": 75, "tick_size": 0.05, "active": True, "source": "MOCK_TEST", "timestamp": timestamp},
        {"symbol": "BANKNIFTY26SEP_55000PE", "exchange": "NFO", "token": "MOCK006", "instrument_type": "OPTION", "underlying_symbol": "BANKNIFTY", "expiry": expiry, "strike": 55000.0, "option_type": "PE", "lot_size": 30, "tick_size": 0.05, "active": True, "source": "MOCK_TEST", "timestamp": timestamp},
    ]