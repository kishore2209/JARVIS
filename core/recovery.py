"""Encrypted SQLite snapshots and non-overwriting, fail-closed restoration."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from time import perf_counter

from cryptography.fernet import Fernet, InvalidToken
from market.persistence import SCHEMA_VERSION
from market.durable_paper import pack
from market.paper_trading import PaperAccount

MAX_DATABASE_BYTES = 64 * 1024 * 1024


def _write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def backup(store, destination, key):
    started = perf_counter()
    cipher = Fernet(key)
    pages = store.connection.execute('PRAGMA page_count').fetchone()[0]
    page_size = store.connection.execute('PRAGMA page_size').fetchone()[0]
    if pages * page_size > MAX_DATABASE_BYTES:
        raise ValueError('Local snapshot exceeds 64 MiB; use a production backup service')
    snapshot = sqlite3.connect(':memory:')
    try:
        store.connection.backup(snapshot)
        snapshot.execute('PRAGMA journal_mode=MEMORY')
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source database integrity check failed')
        data = snapshot.serialize()
        # The online backup includes committed WAL content. SQLite documents
        # these format bytes for deserializing a WAL snapshot in memory:
        # https://www.sqlite.org/c3ref/deserialize.html
        data = data[:18] + b'\x01\x01' + data[20:]
    finally:
        snapshot.close()
    if len(data) > MAX_DATABASE_BYTES:
        raise ValueError('Snapshot size exceeded')
    manifest = {'format': 'jarvis-backup-1', 'schema_version': SCHEMA_VERSION,
                'created_at': datetime.now(timezone.utc).isoformat(), 'database_bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest()}
    _write_new(destination, cipher.encrypt(json.dumps(manifest).encode() + b'\n' + data))
    return {**manifest, 'duration_seconds': round(perf_counter() - started, 4)}


def restore(source, destination, key):
    started = perf_counter()
    source = Path(source)
    if source.stat().st_size > MAX_DATABASE_BYTES * 2:
        raise ValueError('Encrypted backup too large')
    try:
        manifest_bytes, data = Fernet(key).decrypt(source.read_bytes()).split(b'\n', 1)
        manifest = json.loads(manifest_bytes)
    except (InvalidToken, ValueError, json.JSONDecodeError) as error:
        raise ValueError('Backup authentication or format validation failed') from error
    if (manifest.get('format') != 'jarvis-backup-1' or manifest.get('schema_version') != SCHEMA_VERSION
            or len(data) > MAX_DATABASE_BYTES or manifest.get('database_bytes') != len(data)
            or manifest.get('sha256') != hashlib.sha256(data).hexdigest()):
        raise ValueError('Backup manifest mismatch')
    # Validate without creating a plaintext file, then lock financial state and
    # disable scheduled work before the new database becomes visible.
    snapshot = sqlite3.connect(':memory:')
    try:
        snapshot.deserialize(data)
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Restored database integrity check failed')
        if snapshot.execute('SELECT version FROM schema_version').fetchall() != [(SCHEMA_VERSION,)]:
            raise ValueError('Restored schema mismatch')
        tables = {r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with snapshot:
            snapshot.execute('CREATE TABLE IF NOT EXISTS paper_checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            row = snapshot.execute('SELECT revision,payload FROM paper_checkpoint WHERE id=1').fetchone()
            if row:
                state = json.loads(row[1]); state['kill_switch'] = True
                snapshot.execute('UPDATE paper_checkpoint SET revision=revision+1,payload=? WHERE id=1', (json.dumps(state),))
            else:
                if any(snapshot.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in ('orders','fills','positions','journal')):
                    raise ValueError('Legacy financial records require manual reconciliation')
                state = pack({'account': PaperAccount('100000'), 'orders': 0, 'fills': 0, 'positions': 0, 'kill_switch': True})
                snapshot.execute('INSERT INTO paper_checkpoint VALUES (1,1,?)', (json.dumps(state),))
            if 'scheduled_jobs' in tables:
                snapshot.execute('UPDATE scheduled_jobs SET enabled=0,claim=NULL,lease_until=NULL')
            if 'request_tasks' in tables:
                for identifier, version, payload in snapshot.execute("SELECT id,version,payload FROM request_tasks WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED')").fetchall():
                    task = json.loads(payload); task.update(state='FAILED', error='RESTORED_REQUIRES_RESUBMISSION', version=version+1, result=None)
                    task['history'].append({'state': 'FAILED', 'at': datetime.now(timezone.utc).isoformat(), 'actor': 'recovery', 'reason': task['error'], 'version': version+1})
                    snapshot.execute('UPDATE request_tasks SET state=?,version=?,payload=? WHERE id=?', ('FAILED', version+1, json.dumps(task), identifier))
            snapshot.execute('CREATE TABLE IF NOT EXISTS recovery_events (at TEXT NOT NULL, manifest TEXT NOT NULL)')
            snapshot.execute('INSERT INTO recovery_events VALUES (?,?)', (datetime.now(timezone.utc).isoformat(), json.dumps(manifest)))
        _write_new(destination, snapshot.serialize())
    finally:
        snapshot.close()
    return {'status': 'RESTORED_WITH_ACTIONS_BLOCKED', 'source_snapshot_at': manifest['created_at'],
            'restore_seconds': round(perf_counter() - started, 4), 'paper_kill_switch': True,
            'scheduled_jobs_enabled': False, 'broker_reconciled': False}
