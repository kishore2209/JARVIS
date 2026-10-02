"""Evidence-linked paper-trade reviews; outcomes do not imply decision quality."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field

IST = ZoneInfo('Asia/Kolkata')


class ReviewNote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    position_id: str = Field(min_length=1, max_length=100)
    strategy: str = Field(default='UNCLASSIFIED', min_length=1, max_length=100)
    regime: str = Field(default='UNKNOWN', min_length=1, max_length=100)
    thesis: str = Field(default='', max_length=4000)
    invalidation: str = Field(default='', max_length=2000)
    current_evidence: str = Field(default='', max_length=4000)
    invalidation_met: bool | None = Field(default=None, strict=True)
    followed_rules: bool | None = Field(default=None, strict=True)
    violations: list[str] = Field(default_factory=list, max_length=20)
    lesson: str = Field(default='', max_length=2000)


class ReviewService:
    def __init__(self, store, paper_engine):
        self.store, self.paper_engine = store, paper_engine
        with store.connection:
            store.connection.execute('CREATE TABLE IF NOT EXISTS review_notes (position_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(position_id,version))')

    def annotate(self, payload, expected_version=0):
        note = ReviewNote.model_validate(payload).model_dump()
        if any(not isinstance(v, str) or not 1 <= len(v) <= 200 for v in note['violations']):
            raise ValueError('Violation labels must contain 1..200 characters')
        if note['followed_rules'] is True and note['violations']:
            raise ValueError('A compliant decision cannot have declared rule violations')
        account = self.paper_engine.account
        position = account.open_positions.get(note['position_id']) or account.closed_positions.get(note['position_id'])
        if not position:
            raise ValueError('Review must refer to an existing paper position')
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Expected version required')
        with self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            current = self.store.connection.execute('SELECT max(version) FROM review_notes WHERE position_id=?', (note['position_id'],)).fetchone()[0] or 0
            if expected_version != current:
                raise ValueError('Review version conflict')
            note.update(version=current+1, recorded_at=datetime.now(timezone.utc).isoformat(), source='OWNER_ANNOTATION',
                        retrospective=True, lesson_status='CANDIDATE_REQUIRES_CONFIRMATION')
            self.store.connection.execute('INSERT INTO review_notes VALUES (?,?,?)', (note['position_id'], current+1, json.dumps(note)))
        return note

    def history(self, position_id):
        return [json.loads(r[0]) for r in self.store.connection.execute('SELECT payload FROM review_notes WHERE position_id=? ORDER BY version', (position_id,))]

    @staticmethod
    def metrics(trades):
        pnl = [Decimal(t['realized_pnl_before_costs']) for t in trades]
        gains = sum((p for p in pnl if p > 0), Decimal(0))
        losses = -sum((p for p in pnl if p < 0), Decimal(0))
        equity = peak = drawdown = Decimal(0)
        for p in pnl:
            equity += p; peak = max(peak, equity); drawdown = max(drawdown, peak-equity)
        r_values = [Decimal(t['r_multiple']) for t in trades if t['r_multiple'] is not None]
        known = [t for t in trades if t['decision_quality'] != 'UNKNOWN']
        return {'sample_size': len(trades), 'realized_pnl_before_costs': str(sum(pnl, Decimal(0))),
                'expectancy_per_trade': str(sum(pnl, Decimal(0))/len(pnl)) if pnl else None,
                'win_rate': str(Decimal(sum(p > 0 for p in pnl))/len(pnl)) if pnl else None,
                'profit_factor': str(gains/losses) if losses else None,
                'maximum_closed_trade_drawdown': str(drawdown),
                'average_r': str(sum(r_values, Decimal(0))/len(r_values)) if r_values else None,
                'r_sample_size': len(r_values), 'rule_adherence_sample_size': len(known),
                'self_reported_rule_adherence': str(Decimal(sum(t['decision_quality']=='DECLARED_COMPLIANT' for t in known))/len(known)) if known else None}

    def report(self, period='daily', as_of=None):
        as_of = as_of or datetime.now(timezone.utc)
        if as_of.tzinfo is None or period not in {'daily','weekly','monthly'}:
            raise ValueError('Aware as_of and daily/weekly/monthly period required')
        local = as_of.astimezone(IST); start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == 'weekly': start -= timedelta(days=start.weekday())
        if period == 'monthly': start = start.replace(day=1)
        trades = []
        for entry in sorted(self.paper_engine.account.journal, key=lambda e: (e.closed_at, e.position_id)):
            if not start <= entry.closed_at <= as_of: continue
            notes = [n for n in self.history(entry.position_id) if datetime.fromisoformat(n['recorded_at']) <= as_of]
            note = notes[-1] if notes else {}
            risk = abs(entry.entry_price-entry.stop)*entry.quantity
            quality = 'DECLARED_VIOLATION' if note.get('violations') or note.get('followed_rules') is False else 'DECLARED_COMPLIANT' if note.get('followed_rules') is True else 'UNKNOWN'
            trades.append({'position_id': entry.position_id, 'instrument': entry.instrument, 'closed_at': entry.closed_at.isoformat(),
                           'realized_pnl_before_costs': str(entry.realized_pnl), 'r_multiple': str(entry.realized_pnl/risk) if risk else None,
                           'outcome': 'WIN' if entry.realized_pnl > 0 else 'LOSS' if entry.realized_pnl < 0 else 'BREAKEVEN',
                           'decision_quality': quality, 'strategy': note.get('strategy', 'UNCLASSIFIED'), 'regime': note.get('regime','UNKNOWN'),
                           'thesis_status': 'DECLARED_INVALIDATED' if note.get('invalidation_met') is True else 'DECLARED_NOT_INVALIDATED' if note.get('invalidation_met') is False else 'UNKNOWN',
                           'annotation': note or None})
        groups = {}
        for field in ('strategy', 'regime'):
            groups[field] = {key: self.metrics([t for t in trades if t[field] == key]) for key in sorted({t[field] for t in trades})}
        violations = Counter(v for t in trades for v in (t['annotation'] or {}).get('violations', []))
        return {'period': period, 'from': start.isoformat(), 'as_of': as_of.isoformat(), 'mode': 'PAPER',
                'metrics': self.metrics(trades), 'groups': groups, 'trades': trades, 'repeated_violations': dict(violations),
                'lesson_candidates': [{'position_id': t['position_id'], 'lesson': t['annotation']['lesson'], 'requires_confirmation': True}
                                      for t in trades if t['annotation'] and t['annotation']['lesson']],
                'missing_evidence': ['Missed setups not recorded', 'Execution slippage and fees not recorded', 'Intratrade drawdown unavailable'],
                'warnings': ['Small sample: do not infer a durable strategy edge.'] if len(trades) < 30 else [],
                'decision_quality_basis': 'Retrospective owner declarations; profit alone does not establish decision quality.'}
