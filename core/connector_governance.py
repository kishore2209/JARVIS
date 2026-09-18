"""Default-deny external connector permission governance."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import re
from types import MappingProxyType
from typing import Mapping

class GovernanceEnvironment(str, Enum): LOCAL='LOCAL'; DEVELOPMENT='DEVELOPMENT'; TEST='TEST'; PRODUCTION='PRODUCTION'
class GovernanceValidationError(ValueError): pass

@dataclass(frozen=True)
class ConnectorPermissionProfile:
    profile_id: str
    connector_id: str
    environment: GovernanceEnvironment
    enabled: bool
    allowed_capabilities: frozenset[str]
    allowed_resources: frozenset[str]
    created_at: datetime
    updated_at: datetime
    version: int = 1
    source: str = 'ADMIN'

@dataclass(frozen=True)
class ConnectorGovernanceDecision:
    allowed: bool
    connector_id: str
    capability_id: str
    resource_id: str | None
    reason_code: str
    requires_confirmation: bool
    warnings: tuple[str, ...] = ()
    policy_version: int | None = None

class ConnectorGovernanceService:
    def __init__(self, store=None, environment='DEVELOPMENT', observability=None):
        self.store=store; self.environment=GovernanceEnvironment(environment.upper()) if environment.upper() in GovernanceEnvironment.__members__ else GovernanceEnvironment.DEVELOPMENT; self.observability=observability; self.profiles={}; self._restore()
    @staticmethod
    def normalize_resource(resource):
        if not isinstance(resource,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',resource): raise GovernanceValidationError('RESOURCE_INVALID')
        return resource
    def create_profile(self, connector_id, capabilities, resources, environment=None, enabled=True, profile_id=None):
        resources=frozenset(self.normalize_resource(item) for item in resources); caps=frozenset(str(item) for item in capabilities)
        if not caps or any('*' in item for item in resources|caps): raise GovernanceValidationError('POLICY_CONFLICT')
        now=datetime.now(timezone.utc); profile=ConnectorPermissionProfile(profile_id or f'{connector_id}-{len(self.profiles)+1}',connector_id,GovernanceEnvironment(environment.upper()) if environment else self.environment,bool(enabled),caps,resources,now,now)
        self.profiles[profile.profile_id]=profile; self._save(profile); self._event('governance_profile_created',profile); return profile
    def update_profile(self, profile_id, capabilities=None, resources=None, enabled=None):
        profile=self.profiles.get(profile_id)
        if not profile: raise GovernanceValidationError('PROFILE_NOT_FOUND')
        new_resources=profile.allowed_resources if resources is None else frozenset(self.normalize_resource(item) for item in resources)
        new_caps=profile.allowed_capabilities if capabilities is None else frozenset(str(item) for item in capabilities)
        now=datetime.now(timezone.utc); profile=replace(profile,allowed_capabilities=new_caps,allowed_resources=new_resources,enabled=profile.enabled if enabled is None else bool(enabled),updated_at=now,version=profile.version+1); self.profiles[profile_id]=profile; self._save(profile); self._event('governance_profile_updated',profile); return profile
    def decide(self, connector_id, capability_id, resource_id, credential_configured, write_enabled):
        profile=next((p for p in self.profiles.values() if p.connector_id==connector_id and p.environment is self.environment),None)
        if not profile: return ConnectorGovernanceDecision(False,connector_id,capability_id,resource_id,'PROFILE_NOT_FOUND',True)
        if not profile.enabled: return ConnectorGovernanceDecision(False,connector_id,capability_id,resource_id,'PROFILE_DISABLED',True,policy_version=profile.version)
        if not credential_configured: return ConnectorGovernanceDecision(False,connector_id,capability_id,resource_id,'CREDENTIAL_NOT_CONFIGURED',True,policy_version=profile.version)
        if not write_enabled: return ConnectorGovernanceDecision(False,connector_id,capability_id,resource_id,'WRITE_DISABLED',True,policy_version=profile.version)
        if capability_id not in profile.allowed_capabilities: return ConnectorGovernanceDecision(False,connector_id,capability_id,resource_id,'CAPABILITY_NOT_ALLOWED',True,policy_version=profile.version)
        try: normalized=self.normalize_resource(resource_id or '')
        except GovernanceValidationError: return ConnectorGovernanceDecision(False,connector_id,capability_id,resource_id,'RESOURCE_INVALID',True,policy_version=profile.version)
        if normalized not in profile.allowed_resources: return ConnectorGovernanceDecision(False,connector_id,capability_id,normalized,'RESOURCE_NOT_ALLOWED',True,policy_version=profile.version)
        return ConnectorGovernanceDecision(True,connector_id,capability_id,normalized,'GOVERNANCE_ALLOWED',True,policy_version=profile.version)
    def _save(self, profile):
        if self.store:
            payload={**profile.__dict__,'environment':profile.environment.value,'allowed_capabilities':list(profile.allowed_capabilities),'allowed_resources':list(profile.allowed_resources),'created_at':profile.created_at.isoformat(),'updated_at':profile.updated_at.isoformat()}
            with self.store.connection:self.store.connection.execute('CREATE TABLE IF NOT EXISTS connector_governance (id TEXT PRIMARY KEY, payload TEXT NOT NULL)'); self.store.connection.execute('INSERT OR REPLACE INTO connector_governance VALUES (?,?)',(profile.profile_id,json.dumps(payload)))
    def _restore(self):
        if not self.store:return
        self.store.connection.execute('CREATE TABLE IF NOT EXISTS connector_governance (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        for row in self.store.connection.execute('SELECT payload FROM connector_governance'):
            data=json.loads(row[0]); self.profiles[data['profile_id']]=ConnectorPermissionProfile(data['profile_id'],data['connector_id'],GovernanceEnvironment(data['environment']),data['enabled'],frozenset(data['allowed_capabilities']),frozenset(data['allowed_resources']),datetime.fromisoformat(data['created_at']),datetime.fromisoformat(data['updated_at']),data['version'],data['source'])
    def safe_list(self):
        return tuple({'profile_id':p.profile_id,'connector_id':p.connector_id,'environment':p.environment.value,'enabled':p.enabled,'allowed_capabilities':sorted(p.allowed_capabilities),'allowed_resources':sorted(p.allowed_resources),'version':p.version,'source':p.source} for p in self.profiles.values())
    def _event(self,name,profile):
        if self.observability:self.observability.record('GOVERNANCE',name,'COMPLETED',metadata={'profile_id':profile.profile_id,'connector_id':profile.connector_id,'version':profile.version})

__all__=['ConnectorGovernanceDecision','ConnectorGovernanceService','ConnectorPermissionProfile','GovernanceEnvironment','GovernanceValidationError']
