"""Safe personal memory storage, validation, migration, and bounded retrieval."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import re
from typing import Any, Iterable, Mapping
from uuid import uuid4

from market.persistence import SQLiteStore


class MemoryCategory(str, Enum):
    PROFILE = "PROFILE"
    PREFERENCE = "PREFERENCE"
    SETTING = "SETTING"
    WORK_CONTEXT = "WORK_CONTEXT"
    PROJECT_CONTEXT = "PROJECT_CONTEXT"
    LEARNING_CONTEXT = "LEARNING_CONTEXT"
    GENERAL_FACT = "GENERAL_FACT"
    TRADING = "TRADING"
    SEMANTIC = "SEMANTIC"
    OPERATIONAL = "OPERATIONAL"
    CONVERSATION = "CONVERSATION"


class MemoryScope(str, Enum):
    SESSION = "SESSION"
    DURABLE = "DURABLE"


class MemorySource(str, Enum):
    EXPLICIT_USER = "EXPLICIT_USER"
    MIGRATED_LEGACY = "MIGRATED_LEGACY"
    SYSTEM_SETTING = "SYSTEM_SETTING"
    DERIVED_CANDIDATE = "DERIVED_CANDIDATE"


class MemoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FORGOTTEN = "FORGOTTEN"


SECRET_TERMS = ("api_key", "secret", "password", "pin", "totp", "access_token", "refresh_token", "authorization", "bearer", "session_token", "broker_token", "gemini_api_key")
AUTHORITY_KEYS = ("risk_approved", "explicit_user_authorization", "live_execution", "paper_authorized", "current_market_price", "current_option_oi", "current_pcr", "current_portfolio_value", "approved")
ALLOWED_CATEGORIES = frozenset(item.value for item in MemoryCategory)


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    category: MemoryCategory
    scope: MemoryScope
    key: str
    value: str
    source: MemorySource
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    confidence: float | None = None
    tags: tuple[str, ...] = ()
    provenance: str = ""
    version: int = 1
    source_refs: tuple[str, ...] = ()
    source_turns: tuple[str, ...] = ()
    parent_ids: tuple[str, ...] = ()
    session_id: str | None = None


@dataclass(frozen=True)
class MemoryCandidate:
    category: MemoryCategory
    key: str
    value: str
    reason: str
    source: MemorySource = MemorySource.DERIVED_CANDIDATE
    requires_confirmation: bool = True


class MemoryValidationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | datetime | None) -> datetime | None:
    if value is None: return value
    if isinstance(value, datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _blocked(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in SECRET_TERMS) or any(term in lowered for term in AUTHORITY_KEYS) or "current price" in lowered or "portfolio value" in lowered or "option oi" in lowered or "current pcr" in lowered or "placeorder" in lowered


def _record_dict(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": record.memory_id, "category": record.category.value, "scope": record.scope.value,
        "key": record.key, "value": record.value, "source": record.source.value,
        "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat(),
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "status": record.status.value, "confidence": record.confidence, "tags": list(record.tags),
        "provenance": record.provenance, "version": record.version,
        "source_refs": list(record.source_refs), "source_turns": list(record.source_turns),
        "parent_ids": list(record.parent_ids), "session_id": record.session_id,
    }


def _record_from(value: Mapping[str, Any]) -> MemoryRecord:
    return MemoryRecord(
        memory_id=str(value["memory_id"]), category=MemoryCategory(value["category"]), scope=MemoryScope(value["scope"]),
        key=str(value["key"]), value=str(value["value"]), source=MemorySource(value["source"]),
        created_at=_parse_time(value["created_at"]) or _now(), updated_at=_parse_time(value["updated_at"]) or _now(),
        expires_at=_parse_time(value.get("expires_at")), status=MemoryStatus(value.get("status", "ACTIVE")),
        confidence=value.get("confidence"), tags=tuple(value.get("tags", ())), provenance=str(value.get("provenance", "")),
        version=int(value.get("version", 1)),
        source_refs=tuple(value.get("source_refs", ())), source_turns=tuple(value.get("source_turns", ())),
        parent_ids=tuple(value.get("parent_ids", ())), session_id=value.get("session_id"),
    )


class MemoryRepository:
    """Typed repository over the existing SQLiteStore, with an in-memory fallback."""
    def __init__(self, store: SQLiteStore | None = None):
        self.store = store
        self._records: dict[str, MemoryRecord] = {}
        self._history: dict[str, list[MemoryRecord]] = {}
        self._revoked: set[str] = set()
        if store is not None:
            with store.connection:
                store.connection.execute("CREATE TABLE IF NOT EXISTS memory_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                store.connection.execute("CREATE TABLE IF NOT EXISTS memory_history (id TEXT, version INTEGER, payload TEXT NOT NULL, PRIMARY KEY(id,version))")
                store.connection.execute("CREATE TABLE IF NOT EXISTS memory_revocations (source TEXT PRIMARY KEY)")

    def save(self, record: MemoryRecord) -> MemoryRecord:
        payload = _record_dict(record)
        if self.store is None:
            previous = self._records.get(record.memory_id)
            if previous: self._history.setdefault(record.memory_id, []).append(previous)
            self._records[record.memory_id] = record
        else:
            with self.store.connection:
                old = self.store.connection.execute("SELECT payload FROM memory_records WHERE id=?", (record.memory_id,)).fetchone()
                if old:
                    previous = json.loads(old[0])
                    if record.version != previous["version"] + 1: raise MemoryValidationError("Memory version conflict")
                    self.store.connection.execute("INSERT INTO memory_history VALUES (?,?,?)", (record.memory_id, previous["version"], old[0]))
                self.store.connection.execute("INSERT OR REPLACE INTO memory_records VALUES (?, ?)", (record.memory_id, json.dumps(payload)))
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        if self.store is None: return self._records.get(memory_id)
        row = self.store.connection.execute("SELECT payload FROM memory_records WHERE id=?", (memory_id,)).fetchone()
        return _record_from(json.loads(row[0])) if row else None

    def list(self) -> tuple[MemoryRecord, ...]:
        if self.store is None: return tuple(self._records.values())
        rows = self.store.connection.execute("SELECT payload FROM memory_records ORDER BY id").fetchall()
        return tuple(_record_from(json.loads(row[0])) for row in rows)

    def history(self, memory_id: str) -> tuple[MemoryRecord, ...]:
        if self.store is None: return tuple(self._history.get(memory_id, ()))
        rows = self.store.connection.execute("SELECT payload FROM memory_history WHERE id=? ORDER BY version", (memory_id,)).fetchall()
        return tuple(_record_from(json.loads(row[0])) for row in rows)

    def revoke_source(self, source: str):
        if not source or len(source) > 200: raise MemoryValidationError("Invalid source reference")
        if self.store is None: self._revoked.add(source)
        else:
            with self.store.connection:
                self.store.connection.execute("INSERT OR IGNORE INTO memory_revocations VALUES (?)", (source,))

    def permitted(self, record, seen=None):
        seen = set() if seen is None else seen
        if record.memory_id in seen: return False
        seen = seen | {record.memory_id}
        if record.status is not MemoryStatus.ACTIVE or (record.expires_at and record.expires_at <= _now()): return False
        revoked = self._revoked if self.store is None else {r[0] for r in self.store.connection.execute("SELECT source FROM memory_revocations")}
        if revoked.intersection(record.source_refs): return False
        for parent_id in record.parent_ids:
            parent = self.get(parent_id)
            if parent is None or not self.permitted(parent, seen): return False
        return True

    def purge(self, memory_id: str) -> bool:
        if self.store is None:
            self._history.pop(memory_id, None)
            return self._records.pop(memory_id, None) is not None
        with self.store.connection:
            self.store.connection.execute("DELETE FROM memory_history WHERE id=?", (memory_id,))
            return self.store.connection.execute("DELETE FROM memory_records WHERE id=?", (memory_id,)).rowcount > 0

    def delete(self, memory_id: str) -> bool:
        if self.store is None: return self._records.pop(memory_id, None) is not None
        with self.store.connection:
            return self.store.connection.execute("DELETE FROM memory_records WHERE id=?", (memory_id,)).rowcount > 0


class MemoryRetriever:
    def __init__(self, repository: MemoryRepository, max_memories_per_request: int = 5, max_memory_context_chars: int = 2000):
        if max_memories_per_request <= 0 or max_memory_context_chars <= 0: raise MemoryValidationError("retrieval limits must be positive")
        self.repository = repository; self.max_memories_per_request = max_memories_per_request; self.max_memory_context_chars = max_memory_context_chars

    def retrieve(self, text: str = "", intent: str = "", entities: Mapping[str, Any] | None = None) -> tuple[MemoryRecord, ...]:
        now = _now(); query = f"{text} {intent} {' '.join(str(value) for value in (entities or {}).values())}".lower()
        active = [record for record in self.repository.list() if self.repository.permitted(record) and (record.scope is not MemoryScope.SESSION or bool(record.session_id) and record.session_id == (entities or {}).get("session_id"))]
        def score(record: MemoryRecord) -> tuple[int, float, int]:
            exact = int(record.key.lower() in query or any(tag.lower() in query for tag in record.tags))
            category = int(record.category.value.lower() in query)
            explicit = int(record.source is MemorySource.EXPLICIT_USER)
            return (exact * 4 + category * 2 + explicit, record.updated_at.timestamp(), record.version)
        tokens = set(re.findall(r"[\w]+", query))
        def relevant(record):
            terms = set(re.findall(r"[\w]+", (record.key.replace("_", " ") + " " + " ".join(record.tags) + " " + record.value).lower()))
            return bool(tokens & terms) or score(record)[0] >= 4
        return tuple(sorted((r for r in active if relevant(r)), key=score, reverse=True)[:self.max_memories_per_request])

    def safe_context(self, records: Iterable[MemoryRecord]) -> dict[str, Any]:
        items = []; size = 0
        for record in records:
            if not self.repository.permitted(record): continue
            item = {"category": record.category.value, "scope": record.scope.value, "key": record.key, "value": record.value, "source": record.source.value, "memory_id": record.memory_id, "version": record.version, "effective_at": record.updated_at.isoformat(), "provenance": record.provenance, "source_turns": list(record.source_turns)}
            encoded = json.dumps(item, ensure_ascii=False)
            if size + len(encoded) > self.max_memory_context_chars: break
            items.append(item); size += len(encoded)
        return {"memories": items}


class JarvisMemoryService:
    def __init__(self, repository: MemoryRepository, observability=None, retriever: MemoryRetriever | None = None):
        self.repository = repository; self.observability = observability; self.retriever = retriever or MemoryRetriever(repository)

    def _validate(self, category: MemoryCategory | str, scope: MemoryScope | str, key: str, value: Any) -> tuple[MemoryCategory, MemoryScope, str, str]:
        try: category = category if isinstance(category, MemoryCategory) else MemoryCategory(category)
        except ValueError as error: raise MemoryValidationError("invalid memory category") from error
        try: scope = scope if isinstance(scope, MemoryScope) else MemoryScope(scope)
        except ValueError as error: raise MemoryValidationError("invalid memory scope") from error
        key, value = str(key).strip(), str(value).strip()
        if not key or not value or len(key) > 120 or len(value) > 2000: raise MemoryValidationError("memory key/value is invalid or oversized")
        if _blocked(key) or _blocked(value): raise MemoryValidationError("memory content is not allowed")
        return category, scope, key, value

    def create(self, category, key: str, value: Any, scope: MemoryScope | str = MemoryScope.DURABLE, source: MemorySource | str = MemorySource.EXPLICIT_USER, expires_at=None, tags: Iterable[str] = (), provenance: str = "", *, source_refs=(), source_turns=(), parent_ids=(), session_id=None) -> MemoryRecord:
        category, scope, key, value = self._validate(category, scope, key, value)
        try: source = source if isinstance(source, MemorySource) else MemorySource(source)
        except ValueError as error: raise MemoryValidationError("invalid memory source") from error
        if scope is MemoryScope.DURABLE and source not in {MemorySource.EXPLICIT_USER, MemorySource.MIGRATED_LEGACY, MemorySource.SYSTEM_SETTING}:
            raise MemoryValidationError("durable memory requires explicit confirmation")
        for group in (source_refs, source_turns, parent_ids, tags):
            if isinstance(group, str) or len(tuple(group)) > 50 or any(not isinstance(x, str) or not x or len(x) > 200 for x in group):
                raise MemoryValidationError("Invalid memory metadata")
        if len(provenance) > 1000 or _blocked(provenance): raise MemoryValidationError("Invalid provenance")
        for parent_id in parent_ids:
            parent = self.repository.get(parent_id)
            if parent is None or not self.repository.permitted(parent): raise MemoryValidationError("Parent evidence unavailable")
            source_refs = tuple(sorted(set(source_refs) | set(parent.source_refs)))
        current = next((item for item in self.repository.list() if item.key == key and item.category is category and item.scope is scope and item.session_id == session_id and item.status is MemoryStatus.ACTIVE), None)
        if current and current.memory_id in parent_ids: raise MemoryValidationError("Memory cannot derive from itself")
        now = _now()
        record = MemoryRecord(current.memory_id if current else uuid4().hex, category, scope, key, value, source, current.created_at if current else now, now, _parse_time(expires_at), MemoryStatus.ACTIVE, tags=tuple(tags), provenance=provenance or source.value, version=(current.version + 1 if current else 1))
        record = replace(record, source_refs=tuple(sorted(set(source_refs) | set(current.source_refs if current else ()))), source_turns=tuple(source_turns), parent_ids=tuple(parent_ids) or (current.parent_ids if current else ()), session_id=session_id)
        self.repository.save(record); self._metric("memory_updates_total" if current else "memory_writes_total"); self._event("memory_updated" if current else "memory_created", record)
        return record

    def get(self, memory_id: str) -> MemoryRecord | None: return self.repository.get(memory_id)
    def list(self, category=None, scope=None) -> tuple[MemoryRecord, ...]:
        records = self.repository.list()
        if category:
            category_value = category.value if isinstance(category, MemoryCategory) else str(category)
            records = tuple(item for item in records if item.category.value == category_value)
        if scope:
            scope_value = scope.value if isinstance(scope, MemoryScope) else str(scope)
            records = tuple(item for item in records if item.scope.value == scope_value)
        return records
    def search(self, query: str) -> tuple[MemoryRecord, ...]:
        lowered = query.lower(); return tuple(item for item in self.list() if lowered in item.key.lower() or lowered in item.value.lower())
    def forget(self, memory_id: str) -> bool:
        record = self.get(memory_id)
        if not record: return False
        self.repository.save(replace(record, status=MemoryStatus.FORGOTTEN, updated_at=_now(), version=record.version + 1)); self._metric("memory_forgets_total"); self._event("memory_forgotten", record); return True
    def candidate(self, category, key: str, value: Any, reason: str) -> MemoryCandidate:
        category, _, key, value = self._validate(category, MemoryScope.SESSION, key, value)
        return MemoryCandidate(category, key, value, reason)
    def retrieve(self, text: str, intent: str = "", entities=None) -> tuple[MemoryRecord, ...]:
        records = self.retriever.retrieve(text, intent, entities); self._metric("memory_retrievals_total"); self._event("memory_retrieved", None, len(records)); return records
    def safe_context(self, text: str, intent: str = "", entities=None) -> dict[str, Any]: return self.retriever.safe_context(self.retrieve(text, intent, entities))

    def migrate_legacy(self, path) -> int:
        from pathlib import Path
        path = Path(path)
        if not path.exists(): return 0
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error: raise MemoryValidationError("legacy memory is malformed") from error
        if not isinstance(data, Mapping): raise MemoryValidationError("legacy memory must be an object")
        migrated = 0
        for key, value in data.items():
            try:
                if any(item.key == str(key) and item.source is MemorySource.MIGRATED_LEGACY for item in self.repository.list()): continue
                self.create(MemoryCategory.PREFERENCE, str(key), value, source=MemorySource.MIGRATED_LEGACY, provenance=str(path)); migrated += 1
            except MemoryValidationError: self._metric("memory_rejections_total")
        if migrated: self._event("memory_migration_completed", None, migrated)
        return migrated

    def _metric(self, name: str):
        if self.observability: self.observability.counters[name] = self.observability.counters.get(name, 0) + 1
    def _event(self, event_type: str, record: MemoryRecord | None, count: int = 1):
        if self.observability: self.observability.record("MEMORY", event_type, "COMPLETED", metadata={"memory_id": record.memory_id if record else None, "category": record.category.value if record else None, "scope": record.scope.value if record else None, "source": record.source.value if record else None, "count": count})


__all__ = ["ALLOWED_CATEGORIES", "JarvisMemoryService", "MemoryCandidate", "MemoryCategory", "MemoryRecord", "MemoryRepository", "MemoryRetriever", "MemoryScope", "MemorySource", "MemoryStatus", "MemoryValidationError"]
