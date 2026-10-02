"""Deterministic single-owner local finance, planner, notes, and draft services."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import threading
from zoneinfo import ZoneInfo
from personal.models import MODELS, Task


class PersonalService:
    def __init__(self, store=None):
        self.store = store
        self._data = {}
        self._lock = threading.RLock()
        if store:
            with store.connection:
                store.connection.execute('CREATE TABLE IF NOT EXISTS personal_records (kind TEXT, id TEXT, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(kind,id))')

    def list(self, kind, limit=100, offset=0):
        if kind not in MODELS: raise ValueError('Unknown record kind')
        if not 1 <= limit <= 500 or offset < 0: raise ValueError('Invalid pagination')
        if self.store:
            rows = self.store.connection.execute('SELECT version,payload FROM personal_records WHERE kind=? ORDER BY id LIMIT ? OFFSET ?', (kind, limit, offset)).fetchall()
            return [{'version': r['version'], **json.loads(r['payload'])} for r in rows]
        records = [v for (k, _), v in sorted(self._data.items()) if k == kind]
        return [dict(r) for r in records[offset:offset+limit]]

    def all(self, kind):
        # Used only by deterministic calculations; paginated APIs remain bounded.
        out = []
        while True:
            batch = self.list(kind, 500, len(out)); out.extend(batch)
            if len(batch) < 500: return out

    def save(self, kind, payload, expected_version=None):
        if kind not in MODELS: raise ValueError('Unknown record kind')
        model = MODELS[kind].model_validate(payload)
        data = model.model_dump(mode='json')
        encoded = json.dumps(data, sort_keys=True)
        with self._lock:
            if self.store:
                with self.store.connection:
                    # Reserve the write transaction before checking the current version.
                    self.store.connection.execute('BEGIN IMMEDIATE')
                    old = self.store.connection.execute('SELECT version,payload FROM personal_records WHERE kind=? AND id=?', (kind, model.id)).fetchone()
                    if old and json.loads(old['payload']) == data: return {'version': old['version'], **data}
                    if old and expected_version != old['version']: raise ValueError('VERSION_CONFLICT')
                    if not old and expected_version not in (None, 0): raise ValueError('VERSION_CONFLICT')
                    version = old['version'] + 1 if old else 1
                    self.store.connection.execute('INSERT OR REPLACE INTO personal_records VALUES (?,?,?,?)', (kind, model.id, version, encoded))
            else:
                old = self._data.get((kind, model.id))
                if old and {k:v for k,v in old.items() if k != 'version'} == data: return dict(old)
                if old and expected_version != old['version']: raise ValueError('VERSION_CONFLICT')
                if not old and expected_version not in (None, 0): raise ValueError('VERSION_CONFLICT')
                version = old['version'] + 1 if old else 1
                self._data[kind, model.id] = {'version': version, **data}
            return {'version': version, **data}

    def delete(self, kind, identifier, expected_version):
        if kind not in MODELS: raise ValueError('Unknown record kind')
        with self._lock:
            if self.store:
                with self.store.connection:
                    if not self.store.connection.execute('DELETE FROM personal_records WHERE kind=? AND id=? AND version=?', (kind, identifier, expected_version)).rowcount:
                        raise ValueError('NOT_FOUND_OR_VERSION_CONFLICT')
            else:
                row = self._data.get((kind, identifier))
                if not row or row['version'] != expected_version: raise ValueError('NOT_FOUND_OR_VERSION_CONFLICT')
                del self._data[kind, identifier]
        return {'deleted': True}

    def finance_summary(self, as_of=None, expected_accounts=(), max_age_days=1):
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None: raise ValueError('Timezone required')
        balances = self.all('balances')
        available = []; stale = []; disconnected = []; future = []
        for b in balances:
            age = now - datetime.fromisoformat(b['observed_at'])
            if not b['connected']: disconnected.append(b['id'])
            elif age < timedelta(0): future.append(b['id'])
            elif age > timedelta(days=max_age_days): stale.append(b['id'])
            else: available.append(b)
        assets = sum((Decimal(b['value']) for b in available if b['kind'] != 'LIABILITY'), Decimal(0))
        debts = sum((Decimal(b['value']) for b in available if b['kind'] == 'LIABILITY'), Decimal(0))
        missing = sorted(set(expected_accounts) - {b['id'] for b in balances})
        local = now.astimezone(ZoneInfo('Asia/Kolkata'))
        month = local.strftime('%Y-%m')
        expenses = [e for e in self.all('expenses') if datetime.fromisoformat(e['observed_at']).astimezone(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m') == month and datetime.fromisoformat(e['observed_at']) <= now]
        budgets = []
        for b in self.all('budgets'):
            if b['month'] != month: continue
            spent = sum((Decimal(e['amount']) for e in expenses if e['category'] == b['category']), Decimal(0))
            budgets.append({'id': b['id'], 'category': b['category'], 'limit': b['limit'], 'spent': str(spent), 'remaining': str(Decimal(b['limit'])-spent)})
        return {'as_of': now.isoformat(), 'currency': 'INR', 'assets': str(assets), 'liabilities': str(debts), 'covered_net_worth': str(assets-debts),
                'coverage': {'included_accounts': [b['id'] for b in available], 'missing': missing, 'stale': stale, 'disconnected': disconnected, 'future_dated': future},
                'completeness': 'PARTIAL' if not expected_accounts or missing or stale or disconnected or future else 'COMPLETE_FOR_DECLARED_ACCOUNTS',
                'balances': available, 'monthly_expenses': str(sum((Decimal(e['amount']) for e in expenses), Decimal(0))), 'budgets': budgets,
                'unpaid_bills': [b for b in self.all('bills') if not b['paid']],
                'goals': [{**g, 'progress_percent': str(Decimal(g['saved'])/Decimal(g['target'])*100)} for g in self.all('goals')],
                'warnings': ['User-entered values only. Expenses do not silently adjust balance snapshots. Missing accounts are excluded.', 'Goal progress never authorizes increasing trading risk.']}

    def daily_plan(self, as_of=None):
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None: raise ValueError('Timezone required')
        day = now.astimezone(ZoneInfo('Asia/Kolkata')).date()
        tasks = []
        for raw in self.all('tasks'):
            task = Task.model_validate({k:v for k,v in raw.items() if k != 'version'})
            if task.status != 'OPEN': continue
            if task.due_at.astimezone(ZoneInfo('Asia/Kolkata')).date() <= day:
                tasks.append(raw)
        events = [e for e in self.all('events') if datetime.fromisoformat(e['start_at']).astimezone(ZoneInfo('Asia/Kolkata')).date() <= day <= datetime.fromisoformat(e['end_at']).astimezone(ZoneInfo('Asia/Kolkata')).date()]
        conflicts = []
        for i, a in enumerate(events):
            for b in events[i+1:]:
                if datetime.fromisoformat(a['start_at']) < datetime.fromisoformat(b['end_at']) and datetime.fromisoformat(b['start_at']) < datetime.fromisoformat(a['end_at']): conflicts.append([a['id'], b['id']])
        return {'date': str(day), 'timezone': 'Asia/Kolkata', 'tasks': sorted(tasks, key=lambda t:t['due_at']), 'events': sorted(events, key=lambda e:e['start_at']), 'conflicts': conflicts, 'external_calendar_connected': False}

    def complete_task(self, identifier, expected_version, completed_at=None):
        now = completed_at or datetime.now(timezone.utc)
        row = next((t for t in self.all('tasks') if t['id'] == identifier), None)
        if not row or row['version'] != expected_version or row['status'] != 'OPEN': raise ValueError('TASK_STATE_CONFLICT')
        data = {k:v for k,v in row.items() if k != 'version'}
        if row['recurrence_days']:
            due = datetime.fromisoformat(row['due_at']); interval = timedelta(days=row['recurrence_days'])
            occurrences = max(1, (now - due) // interval + 1)
            data['due_at'] = (due + occurrences * interval).isoformat()
        else: data['status'] = 'DONE'
        data['observed_at'] = now.isoformat()
        return self.save('tasks', data, expected_version)
