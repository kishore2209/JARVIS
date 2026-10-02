"""Durable, bounded read-only request execution using SRD Appendix G states.

No task handler may perform external writes or submit orders. An interrupted
task fails closed after its lease/deadline; it is never silently replayed.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from core.interface_service import serialize

TRANSITIONS = {
    'RECEIVED': {'UNDERSTANDING', 'FAILED'},
    'UNDERSTANDING': {'CONTEXT', 'FAILED'},
    'CONTEXT': {'PLANNING', 'FAILED'},
    'PLANNING': {'EXECUTING', 'FAILED', 'CANCELLED'},
    'EXECUTING': {'VALIDATING', 'FAILED', 'CANCELLED'},
    'VALIDATING': {'SYNTHESIS', 'APPROVAL', 'FAILED'},
    'SYNTHESIS': {'APPROVAL', 'COMPLETED', 'FAILED'},
    'APPROVAL': {'ACTING', 'FAILED', 'CANCELLED'},
    'ACTING': {'RECONCILING', 'FAILED'},
    'RECONCILING': {'COMPLETED', 'FAILED'},
    'COMPLETED': set(), 'FAILED': set(), 'CANCELLED': set(),
}
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED'}


class TaskStopped(ValueError):
    pass


class TaskService:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.handlers = {}
        with store.connection:
            store.connection.execute('CREATE TABLE IF NOT EXISTS request_tasks (id TEXT PRIMARY KEY, version INTEGER NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL)')

    def _now(self):
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError('Task clock must be timezone-aware')
        return value.astimezone(timezone.utc)

    def submit(self, kind, payload, *, idempotency_key, correlation_id, seconds=120, tool_budget=100, token_budget=0):
        if kind not in self.handlers:
            raise ValueError('Unsupported read-only task kind')
        for value in (idempotency_key, correlation_id):
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise ValueError('Bounded idempotency key and correlation ID required')
        if type(seconds) is not int or not 1 <= seconds <= 300:
            raise ValueError('Deadline must be 1..300 seconds')
        if type(tool_budget) is not int or not 1 <= tool_budget <= 100:
            raise ValueError('Tool budget must be 1..100')
        if type(token_budget) is not int or not 0 <= token_budget <= 100000:
            raise ValueError('Invalid token budget')
        encoded = json.dumps({'kind': kind, 'input': payload, 'seconds': seconds, 'tools': tool_budget, 'tokens': token_budget}, sort_keys=True, allow_nan=False)
        if len(encoded.encode()) > 1_500_000:
            raise ValueError('Task input too large')
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        identifier = hashlib.sha256(idempotency_key.encode()).hexdigest()
        now = self._now().isoformat()
        task = {'id': identifier, 'kind': kind, 'state': 'RECEIVED', 'version': 1, 'input': payload,
                'fingerprint': fingerprint, 'correlation_id': correlation_id, 'created_at': now,
                'deadline_seconds': seconds, 'deadline_at': None, 'tool_budget': tool_budget,
                'token_budget': token_budget, 'tools_used': 0, 'tokens_used': 0,
                'cancel_requested': False, 'claim': None, 'result': None, 'error': None,
                'history': [{'state': 'RECEIVED', 'at': now, 'actor': 'gateway', 'reason': 'submitted', 'version': 1}]}
        with self.store.connection:
            self.store.connection.execute('INSERT OR IGNORE INTO request_tasks VALUES (?,?,?,?)', (identifier, 1, 'RECEIVED', json.dumps(task)))
        existing = self.get(identifier)
        if existing['fingerprint'] != fingerprint:
            raise ValueError('Idempotency key reused with a different request')
        return existing

    def get(self, identifier):
        row = self.store.connection.execute('SELECT payload FROM request_tasks WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Unknown task')
        return json.loads(row[0])

    def list(self, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Limit must be 1..100')
        return [self.public(json.loads(r[0])) for r in self.store.connection.execute('SELECT payload FROM request_tasks ORDER BY rowid DESC LIMIT ?', (limit,))]

    @staticmethod
    def public(task):
        return {k: v for k, v in task.items() if k not in {'input', 'claim', 'fingerprint'}}

    def _save(self, task, version):
        task['version'] = version + 1
        cursor = self.store.connection.execute('UPDATE request_tasks SET version=?,state=?,payload=? WHERE id=? AND version=?',
            (task['version'], task['state'], json.dumps(task, allow_nan=False), task['id'], version))
        if cursor.rowcount != 1:
            raise TaskStopped('Task version changed')

    def transition(self, identifier, state, *, claim, reason, result=None):
        with self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            task = self.get(identifier)
            if task['claim'] != claim or not claim:
                raise TaskStopped('Task claim mismatch')
            if state not in TRANSITIONS[task['state']]:
                raise TaskStopped('Invalid task transition')
            version = task['version']
            if state not in {'FAILED', 'CANCELLED'}:
                self._check(task)
            task['state'] = state
            task['history'].append({'state': state, 'at': self._now().isoformat(), 'actor': 'worker', 'reason': reason, 'version': version + 1})
            if state == 'COMPLETED':
                task['result'] = serialize(result)
            if state == 'FAILED':
                task['error'] = reason
            self._save(task, version)
        return task

    def cancel(self, identifier):
        with self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            task = self.get(identifier)
            if task['state'] in TERMINAL:
                return self.public(task)
            if task['state'] in {'VALIDATING', 'SYNTHESIS', 'ACTING', 'RECONCILING'}:
                raise ValueError('Task has passed its cancellation checkpoint')
            task['cancel_requested'] = True
            self._save(task, task['version'])
        return self.public(task)

    def _check(self, task):
        if task['deadline_at'] and self._now() >= datetime.fromisoformat(task['deadline_at']):
            raise TaskStopped('DEADLINE_EXCEEDED')
        if task['cancel_requested'] and task['state'] in {'PLANNING', 'EXECUTING', 'APPROVAL'}:
            raise TaskStopped('CANCELLED')
        if task['state'] in TERMINAL:
            raise TaskStopped('TASK_TERMINAL')

    def consume(self, identifier, claim, *, tools=0, tokens=0):
        if any(type(n) is not int or n < 0 for n in (tools, tokens)):
            raise ValueError('Usage must be nonnegative integers')
        with self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            task = self.get(identifier)
            if task['claim'] != claim or not claim:
                raise TaskStopped('Task claim mismatch')
            self._check(task)
            if task['tools_used'] + tools > task['tool_budget'] or task['tokens_used'] + tokens > task['token_budget']:
                raise TaskStopped('BUDGET_EXCEEDED')
            task['tools_used'] += tools
            task['tokens_used'] += tokens
            self._save(task, task['version'])

    def recover(self):
        """Expire interrupted work, including work owned by another dead worker."""
        for row in self.store.connection.execute("SELECT id FROM request_tasks WHERE state NOT IN ('RECEIVED','COMPLETED','FAILED','CANCELLED')").fetchall():
            task = self.get(row[0])
            if task['deadline_at'] and self._now() >= datetime.fromisoformat(task['deadline_at']):
                try:
                    self.transition(task['id'], 'FAILED', claim=task['claim'], reason='WORKER_INTERRUPTED_OR_DEADLINE_EXCEEDED')
                except TaskStopped:
                    pass

    def run_next(self):
        self.recover()
        with self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            row = self.store.connection.execute("SELECT id FROM request_tasks WHERE state='RECEIVED' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return None
            task = self.get(row[0]); version = task['version']
            task['claim'] = uuid4().hex
            task['deadline_at'] = (self._now() + timedelta(seconds=task['deadline_seconds'])).isoformat()
            task['state'] = 'UNDERSTANDING'
            task['history'].append({'state': 'UNDERSTANDING', 'at': self._now().isoformat(), 'actor': 'worker', 'reason': 'claimed', 'version': version + 1})
            self._save(task, version)
        identifier, claim = task['id'], task['claim']
        try:
            self.transition(identifier, 'CONTEXT', claim=claim, reason='read-only handler resolved')
            self.transition(identifier, 'PLANNING', claim=claim, reason='bounded input and budgets registered')
            self.transition(identifier, 'EXECUTING', claim=claim, reason='begin read-only handler')
            result = self.handlers[task['kind']](task['input'], lambda **usage: self.consume(identifier, claim, **usage))
            self.transition(identifier, 'VALIDATING', claim=claim, reason='handler returned')
            encoded = json.dumps(serialize(result), allow_nan=False)
            if len(encoded.encode()) > 2_000_000:
                raise ValueError('Task output too large')
            self.transition(identifier, 'SYNTHESIS', claim=claim, reason='structured result validated')
            self.transition(identifier, 'COMPLETED', claim=claim, reason='read-only result ready', result=result)
        except Exception as error:
            current = self.get(identifier)
            if current['state'] not in TERMINAL:
                cancelled = current['cancel_requested'] and 'CANCELLED' in TRANSITIONS[current['state']]
                reason = str(error) if isinstance(error, TaskStopped) else 'HANDLER_FAILED'
                self.transition(identifier, 'CANCELLED' if cancelled else 'FAILED', claim=claim, reason=reason)
        return self.public(self.get(identifier))
