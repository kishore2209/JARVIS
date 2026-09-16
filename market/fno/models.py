from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass
class FNOInstrument:
    """Normalized F&O instrument record supplied by an instrument-master adapter."""

    symbol: str
    exchange: str
    token: str
    instrument_type: str
    underlying_symbol: str
    expiry: date | None
    strike: float | None
    option_type: str | None
    lot_size: int
    tick_size: float
    active: bool
    source: str
    timestamp: datetime
    is_fresh: bool = True

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        else:
            self.timestamp = self.timestamp.astimezone(timezone.utc)

    @classmethod
    def from_record(cls, record):
        record = dict(record)
        expiry = record.get("expiry")
        if isinstance(expiry, str):
            record["expiry"] = date.fromisoformat(expiry)
        return cls(**record)