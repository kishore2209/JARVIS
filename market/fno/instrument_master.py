from abc import ABC, abstractmethod
from datetime import datetime, timezone

from market.fno.models import FNOInstrument
from market.fno.validators import validate_instrument


class InstrumentMasterProvider(ABC):
    """Normalizes broker instrument-master records for the F&O universe."""

    @abstractmethod
    def normalize_record(self, record):
        raise NotImplementedError

    def normalize_records(self, records):
        instruments = []
        for record in records:
            instrument = self.normalize_record(record)
            if instrument is not None:
                instruments.append(instrument)
        return instruments


class AngelOneInstrumentMasterAdapter(InstrumentMasterProvider):
    """Offline parser for Angel One instrument-master records; it performs no downloads."""

    source = "ANGEL_ONE_INSTRUMENT_MASTER"
    _TYPE_MAP = {
        "FUTSTK": "FUTURE",
        "FUTIDX": "FUTURE",
        "OPTSTK": "OPTION",
        "OPTIDX": "OPTION",
        "EQ": "EQUITY",
    }

    def __init__(self, timestamp=None):
        timestamp = timestamp or datetime.now(timezone.utc)
        self.timestamp = timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)

    def normalize_record(self, record):
        if not isinstance(record, dict):
            raise ValueError("Instrument-master record must be a dictionary.")

        raw_type = str(record.get("instrumenttype", "")).upper()
        exchange = str(record.get("exch_seg", "")).upper()
        instrument_type = self._TYPE_MAP.get(raw_type)
        if exchange not in {"NFO", "NSE"} or instrument_type is None:
            return None

        try:
            expiry = self._normalize_expiry(record.get("expiry"))
            strike = self._normalize_strike(record.get("strike"), instrument_type)
            tick_size = self._normalize_tick_size(record.get("tick_size"))
            instrument = FNOInstrument(
                symbol=str(record["symbol"]).strip(),
                exchange=exchange,
                token=str(record["token"]).strip(),
                instrument_type=instrument_type,
                underlying_symbol=str(record["name"]).strip(),
                expiry=expiry,
                strike=strike,
                option_type=self._option_type(record.get("symbol"), instrument_type),
                lot_size=int(float(record["lotsize"])),
                tick_size=tick_size,
                active=bool(record.get("active", True)),
                source=str(record.get("source", self.source)),
                timestamp=record.get("timestamp", self.timestamp),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Malformed Angel One instrument-master record: {error}") from error

        return validate_instrument(instrument)

    @staticmethod
    def _normalize_expiry(value):
        if not value:
            return None
        if hasattr(value, "year") and hasattr(value, "month"):
            return value
        for format_string in ("%d%b%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value).upper(), format_string).date()
            except ValueError:
                pass
        raise ValueError("expiry must use DDMMMYYYY or YYYY-MM-DD format.")

    @staticmethod
    def _normalize_strike(value, instrument_type):
        if instrument_type != "OPTION":
            return None
        if value is None:
            raise ValueError("option strike is required.")
        return float(value) / 100 if float(value) >= 100000 else float(value)

    @staticmethod
    def _normalize_tick_size(value):
        if value is None:
            raise ValueError("tick_size is required.")
        tick_size = float(value)
        return tick_size / 100 if tick_size >= 1 else tick_size

    @staticmethod
    def _option_type(symbol, instrument_type):
        if instrument_type != "OPTION":
            return None
        symbol = str(symbol).upper()
        if symbol.endswith("CE"):
            return "CE"
        if symbol.endswith("PE"):
            return "PE"
        raise ValueError("option symbol must end in CE or PE.")