"""Atomic, versioned local PAPER checkpoints. No external broker integration."""
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from functools import wraps
import copy
import json
import threading

from market.paper_trading import (PaperTradingEngine, PaperAccount, PaperPosition,
                                 VirtualOrder, VirtualFill, TradeJournalEntry)
from market.risk import RiskDecision

_TYPES = {c.__name__: c for c in (PaperAccount, PaperPosition, VirtualOrder, VirtualFill, TradeJournalEntry, RiskDecision)}


def pack(value):
    if is_dataclass(value):
        if type(value).__name__ not in _TYPES: raise ValueError('Unsupported paper evidence type')
        return {'$type': type(value).__name__, 'fields': {f.name: pack(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, Decimal): return {'$decimal': str(value)}
    if isinstance(value, datetime): return {'$datetime': value.isoformat()}
    if isinstance(value, tuple): return {'$tuple': [pack(x) for x in value]}
    if isinstance(value, list): return [pack(x) for x in value]
    if isinstance(value, dict): return {str(k): pack(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, bool, int, float)): return value
    raise ValueError('Unsupported paper checkpoint value')


def unpack(value):
    if isinstance(value, list): return [unpack(x) for x in value]
    if not isinstance(value, dict): return value
    if '$decimal' in value:
        number = Decimal(value['$decimal'])
        if not number.is_finite(): raise ValueError('Non-finite checkpoint amount')
        return number
    if '$datetime' in value:
        dt = datetime.fromisoformat(value['$datetime'])
        if dt.tzinfo is None: raise ValueError('Naive checkpoint timestamp')
        return dt
    if '$tuple' in value: return tuple(unpack(x) for x in value['$tuple'])
    if '$type' in value:
        if value['$type'] not in _TYPES: raise ValueError('Unknown checkpoint type')
        return _TYPES[value['$type']](**{k: unpack(v) for k, v in value['fields'].items()})
    return {k: unpack(v) for k, v in value.items()}


def checkpoint(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        with self._lock:
            if self._depth: return method(self, *args, **kwargs)
            before = copy.deepcopy(self._state())
            self._depth += 1
            try:
                result = method(self, *args, **kwargs)
                self._save()
                return result
            except Exception:
                self._load_state(before)
                raise
            finally:
                self._depth -= 1
    return run


class DurablePaperEngine(PaperTradingEngine):
    def __init__(self, store=None, starting_cash='100000'):
        super().__init__(PaperAccount(starting_cash))
        self.store = store
        self._lock = threading.RLock()
        self._depth = 0
        self._revision = 0
        self.kill_switch = False
        if store:
            with store.connection:
                store.connection.execute('CREATE TABLE IF NOT EXISTS paper_checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            row = store.connection.execute('SELECT revision,payload FROM paper_checkpoint WHERE id=1').fetchone()
            if row:
                self._revision = row['revision']
                state = unpack(json.loads(row['payload']))
                if not isinstance(state.get('account'), PaperAccount): raise ValueError('Invalid paper checkpoint')
                self._load_state(state)
            elif any(store.read_all(table) for table in ('orders', 'fills', 'positions', 'journal')):
                raise ValueError('Legacy paper records require explicit reconciliation/migration before runtime use')

    def _state(self):
        return {'account': self.account, 'orders': self._order_number, 'fills': self._fill_number,
                'positions': self._position_number, 'kill_switch': self.kill_switch}

    def _load_state(self, state):
        self.account = state['account']
        self._order_number, self._fill_number, self._position_number = state['orders'], state['fills'], state['positions']
        self.kill_switch = state['kill_switch']

    def _save(self):
        if not self.store: return
        payload = json.dumps(pack(self._state()), allow_nan=False)
        with self.store.connection:
            if self._revision == 0:
                self.store.connection.execute('INSERT INTO paper_checkpoint VALUES (1,1,?)', (payload,))
            elif self.store.connection.execute('UPDATE paper_checkpoint SET revision=revision+1,payload=? WHERE id=1 AND revision=?', (payload, self._revision)).rowcount != 1:
                raise ValueError('Paper state changed in another process; reload before continuing')
        self._revision += 1

    @checkpoint
    def set_kill_switch(self, enabled):
        if type(enabled) is not bool: raise ValueError('Kill switch must be boolean')
        self.kill_switch = enabled
        return {'enabled': enabled, 'scope': 'PAPER_NEW_ORDERS_AND_FILLS'}

    @checkpoint
    def create_order(self, proposal, decision):
        if self.kill_switch: raise ValueError('KILL_SWITCH_ACTIVE')
        return super().create_order(proposal, decision)

    @checkpoint
    def fill_order(self, *args, **kwargs):
        if self.kill_switch: raise ValueError('KILL_SWITCH_ACTIVE')
        return super().fill_order(*args, **kwargs)

    @checkpoint
    def mark_to_market(self, *args, **kwargs): return super().mark_to_market(*args, **kwargs)

    @checkpoint
    def close_position(self, *args, **kwargs): return super().close_position(*args, **kwargs)

    @checkpoint
    def evaluate_completed_candle(self, *args, **kwargs): return super().evaluate_completed_candle(*args, **kwargs)
