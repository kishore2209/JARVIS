"""Exact broker-symbol resolution with bounded, fail-closed master caching."""
from datetime import datetime, timedelta, timezone
from threading import RLock

from market.providers.angel_one_instrument_master import AngelOneInstrumentMasterClient


class AngelOneInstrumentResolver:
    def __init__(self, client=None, clock=None, ttl=timedelta(hours=6)):
        if ttl <= timedelta(0):
            raise ValueError('Instrument cache TTL must be positive')
        self.client = client or AngelOneInstrumentMasterClient()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ttl = ttl
        self._records = []
        self._loaded_at = None
        self._lock = RLock()

    def resolve(self, symbol, exchange, token=None):
        symbol, exchange = str(symbol).strip().upper(), str(exchange).strip().upper()
        if not symbol or not exchange:
            raise ValueError('Symbol and exchange are required')
        with self._lock:
            now = self.clock()
            if now.tzinfo is None:
                raise ValueError('Instrument clock must be timezone-aware')
            if self._loaded_at is None or not timedelta(0) <= now - self._loaded_at < self.ttl:
                records = self.client.fetch_records()
                if not records:
                    raise ValueError('Empty instrument master')
                self._records, self._loaded_at = records, now
            matches = []
            for row in self._records:
                if str(row.get('exch_seg', '')).upper() != exchange:
                    continue
                broker_symbol = str(row.get('symbol', '')).upper()
                # Only an equity-series suffix is an allowed alias. Never guess a derivative.
                if broker_symbol != symbol and not (exchange == 'NSE' and broker_symbol == symbol + '-EQ'):
                    continue
                if row.get('active') is False:
                    continue
                expiry = row.get('expiry')
                if expiry:
                    try:
                        expiry_date = datetime.strptime(str(expiry).upper(), '%d%b%Y').date()
                    except ValueError:
                        expiry_date = datetime.strptime(str(expiry), '%Y-%m-%d').date()
                    if expiry_date < now.astimezone(timezone(timedelta(hours=5, minutes=30))).date():
                        continue
                resolved_token = str(row.get('token', '')).strip()
                if not resolved_token or not resolved_token.isdigit():
                    raise ValueError('Invalid instrument token in master')
                matches.append((broker_symbol, exchange, resolved_token))
            matches = set(matches)
            if len(matches) != 1:
                raise ValueError('Instrument not found or ambiguous; use the exact broker symbol and exchange')
            result = matches.pop()
            if token is not None and str(token).strip() and str(token).strip() != result[2]:
                raise ValueError('Instrument token does not match broker master')
            return result
