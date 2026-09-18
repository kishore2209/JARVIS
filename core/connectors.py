"""Provider-neutral, read-only external connector foundation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol


class ConnectorKind(str, Enum): INTERNAL = "INTERNAL"; HTTP_API = "HTTP_API"; MCP = "MCP"
class ConnectorRisk(str, Enum): EXTERNAL_READ_ONLY = "EXTERNAL_READ_ONLY"; EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"; PROHIBITED = "PROHIBITED"

class ConnectorValidationError(ValueError): pass

@dataclass(frozen=True)
class ConnectorCapability:
    capability_id: str
    description: str
    risk: ConnectorRisk = ConnectorRisk.EXTERNAL_READ_ONLY
    argument_schema: Mapping[str, Mapping[str, Any]] = MappingProxyType({})
    enabled: bool = True
    def __post_init__(self): object.__setattr__(self, "argument_schema", MappingProxyType({key: MappingProxyType(dict(value)) for key, value in self.argument_schema.items()}))

@dataclass(frozen=True)
class ConnectorDescriptor:
    connector_id: str
    display_name: str
    kind: ConnectorKind
    version: str
    enabled: bool
    capabilities: tuple[ConnectorCapability, ...]
    credential_required: bool = False
    configured: bool = False
    read_only: bool = True
    description: str = ""
    write_enabled: bool = False

@dataclass(frozen=True)
class ConnectorRequest:
    request_id: str
    connector_id: str
    capability_id: str
    arguments: Mapping[str, Any]
    correlation_id: str = "CONNECTOR"

@dataclass(frozen=True)
class ConnectorResult:
    request_id: str
    connector_id: str
    capability_id: str
    status: str
    data: Any = None
    warnings: tuple[str, ...] = ()
    error_category: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    correlation_id: str | None = None
    source_metadata: Mapping[str, Any] = MappingProxyType({})
    def __post_init__(self): object.__setattr__(self, "source_metadata", MappingProxyType(dict(self.source_metadata)))

class ConnectorTransport(Protocol):
    def read(self, capability_id: str, arguments: Mapping[str, Any]) -> Any: ...
    def write(self, capability_id: str, arguments: Mapping[str, Any]) -> Any: ...

class FakeMCPTransport:
    def __init__(self, resources: Mapping[str, Any] | None = None, advertised_tools: tuple[str, ...] = ()):
        self.resources = dict(resources or {}); self.advertised_tools = tuple(advertised_tools); self.calls = 0
    def initialize(self): return {"protocol": "fake-mcp", "read_only": True}
    def list_resources(self): return tuple(self.resources)
    def read_resource(self, resource: str):
        self.calls += 1
        if resource not in self.resources: raise ConnectorValidationError("resource not found")
        return self.resources[resource]
    def read(self, capability_id, arguments):
        if capability_id == "mcp.resources.list": return {"resources": list(self.list_resources())}
        if capability_id == "mcp.resource.read": return {"resource": arguments["resource"], "data": self.read_resource(arguments["resource"])}
        raise ConnectorValidationError("capability is not a read-only MCP resource capability")

class ConnectorRegistry:
    def __init__(self): self._connectors: dict[str, tuple[ConnectorDescriptor, ConnectorTransport]] = {}
    def register(self, descriptor: ConnectorDescriptor, transport: ConnectorTransport):
        if descriptor.connector_id in self._connectors: raise ConnectorValidationError("duplicate connector")
        if any(cap.risk is not ConnectorRisk.EXTERNAL_READ_ONLY for cap in descriptor.capabilities) and not (descriptor.connector_id == "github" and descriptor.write_enabled): raise ConnectorValidationError("connector has blocked side-effect capability")
        self._connectors[descriptor.connector_id] = (descriptor, transport)
    def descriptor(self, connector_id):
        if connector_id not in self._connectors: raise ConnectorValidationError("CONNECTOR_UNKNOWN")
        return self._connectors[connector_id][0]
    def transport(self, connector_id):
        if connector_id not in self._connectors: raise ConnectorValidationError("CONNECTOR_UNKNOWN")
        return self._connectors[connector_id][1]
    def capability(self, connector_id, capability_id):
        descriptor = self.descriptor(connector_id)
        for capability in descriptor.capabilities:
            if capability.capability_id == capability_id: return capability
        raise ConnectorValidationError("CAPABILITY_UNKNOWN")
    def list(self): return tuple(item[0] for item in self._connectors.values())
    def safe_list(self):
        return tuple({"connector_id": item.connector_id, "display_name": item.display_name, "kind": item.kind.value, "version": item.version, "enabled": item.enabled, "configured": bool(item.configured), "credential_required": item.credential_required, "read_only": item.read_only, "write_enabled": item.write_enabled, "description": item.description} for item in self.list())
    def safe_capabilities(self, connector_id):
        return tuple({"capability_id": cap.capability_id, "description": cap.description, "risk": cap.risk.value, "enabled": cap.enabled, "argument_schema": {key: dict(value) for key, value in cap.argument_schema.items()}} for cap in self.descriptor(connector_id).capabilities)

class ConnectorPolicyEngine:
    def validate(self, descriptor, capability, arguments, allow_side_effect=False):
        if not descriptor.enabled: raise ConnectorValidationError("CONNECTOR_DISABLED")
        if capability.risk is not ConnectorRisk.EXTERNAL_READ_ONLY and not (allow_side_effect and descriptor.connector_id == "github" and descriptor.write_enabled): raise ConnectorValidationError("SIDE_EFFECT_BLOCKED")
        if descriptor.credential_required and not descriptor.configured: raise ConnectorValidationError("CREDENTIAL_NOT_CONFIGURED")
        if not isinstance(arguments, Mapping): raise ConnectorValidationError("ARGUMENT_INVALID")
        unknown = set(arguments) - set(capability.argument_schema)
        if unknown: raise ConnectorValidationError("ARGUMENT_INVALID")
        validated = {}
        for name, schema in capability.argument_schema.items():
            if schema.get("required") and name not in arguments: raise ConnectorValidationError("ARGUMENT_INVALID")
            if name not in arguments: continue
            value = arguments[name]
            if schema.get("type", "string") == "string":
                if not isinstance(value, str) or len(value) > int(schema.get("max_length", 200)): raise ConnectorValidationError("ARGUMENT_INVALID")
                if any(term in value.lower() for term in ("authorization", "bearer", "token", "api_key", "http://", "https://")): raise ConnectorValidationError("ARGUMENT_INVALID")
            validated[name] = value
        return validated

class ConnectorService:
    def __init__(self, registry: ConnectorRegistry, observability=None, max_result_chars: int = 10000): self.registry=registry; self.policy=ConnectorPolicyEngine(); self.observability=observability; self.max_result_chars=max_result_chars
    def read(self, request: ConnectorRequest) -> ConnectorResult:
        started=datetime.now(timezone.utc)
        try:
            descriptor=self.registry.descriptor(request.connector_id); capability=self.registry.capability(request.connector_id, request.capability_id); args=self.policy.validate(descriptor, capability, request.arguments)
            if not descriptor.credential_required and descriptor.kind is ConnectorKind.MCP and not descriptor.configured: pass
            data=self.registry.transport(request.connector_id).read(request.capability_id, args)
            if len(json.dumps(data, default=str)) > self.max_result_chars: raise ConnectorValidationError("OUTPUT_TOO_LARGE")
            result=ConnectorResult(request.request_id,request.connector_id,request.capability_id,"SUCCEEDED",data,started_at=started,completed_at=datetime.now(timezone.utc),correlation_id=request.correlation_id,source_metadata={"kind":descriptor.kind.value})
            self._metric("connector_requests_total"); self._event("connector_request_completed", request, "SUCCEEDED"); return result
        except TimeoutError:
            self._metric("connector_timeouts_total"); return self._failed(request, "CONNECTOR_TIMEOUT", started)
        except ConnectorValidationError as error:
            self._metric("connector_policy_rejections_total"); return self._failed(request, str(error), started)
        except Exception as error:
            name = type(error).__name__
            category = {"GitHubTimeoutError":"CONNECTOR_TIMEOUT", "GitHubAuthError":"CONNECTOR_AUTH_FAILED", "GitHubPermissionError":"CONNECTOR_PERMISSION_DENIED", "GitHubNotFoundError":"CONNECTOR_NOT_FOUND", "GitHubRateLimitError":"CONNECTOR_RATE_LIMITED", "GitHubProviderError":"CONNECTOR_PROVIDER_ERROR"}.get(name, "CONNECTOR_ERROR")
            self._metric("connector_timeouts_total" if category == "CONNECTOR_TIMEOUT" else "connector_failures_total"); return self._failed(request, category, started)
    def write(self, request: ConnectorRequest) -> ConnectorResult:
        started=datetime.now(timezone.utc)
        try:
            descriptor=self.registry.descriptor(request.connector_id); capability=self.registry.capability(request.connector_id, request.capability_id)
            if capability.risk is not ConnectorRisk.EXTERNAL_SIDE_EFFECT or not descriptor.write_enabled: raise ConnectorValidationError("SIDE_EFFECT_BLOCKED")
            args=self.policy.validate(descriptor, capability, request.arguments, allow_side_effect=True); data=self.registry.transport(request.connector_id).write(request.capability_id, args)
            if len(json.dumps(data, default=str)) > self.max_result_chars: raise ConnectorValidationError("OUTPUT_TOO_LARGE")
            self._metric("connector_requests_total"); self._event("connector_request_completed", request, "SUCCEEDED")
            return ConnectorResult(request.request_id,request.connector_id,request.capability_id,"SUCCEEDED",data,started_at=started,completed_at=datetime.now(timezone.utc),correlation_id=request.correlation_id,source_metadata={"kind":descriptor.kind.value})
        except Exception as error:
            category=type(error).__name__ if isinstance(error, ConnectorValidationError) else "CONNECTOR_WRITE_FAILED"
            self._metric("connector_failures_total"); return self._failed(request, category, started)
    def _failed(self, request, category, started): self._event("connector_request_failed", request, category); return ConnectorResult(request.request_id,request.connector_id,request.capability_id,"FAILED",None,error_category=category,started_at=started,completed_at=datetime.now(timezone.utc),correlation_id=request.correlation_id)
    def _metric(self, name):
        if self.observability: self.observability.counters[name]=self.observability.counters.get(name,0)+1
    def _event(self, name, request, status):
        if self.observability: self.observability.record("CONNECTOR",name,status,request_id=request.correlation_id,metadata={"connector_id":request.connector_id,"capability_id":request.capability_id,"status":status})

def build_connector_service(observability=None):
    registry=ConnectorRegistry(); transport=FakeMCPTransport({"demo://status":{"status":"OK","content":"external data is untrusted"}})
    registry.register(ConnectorDescriptor("mcp.demo","Demo MCP",ConnectorKind.MCP,"1",True,(ConnectorCapability("mcp.resources.list","List resources"),ConnectorCapability("mcp.resource.read","Read resource",argument_schema={"resource":{"type":"string","required":True,"max_length":120}})),description="Offline fake read-only MCP connector"), transport)
    from core.github_connector import build_github_connector
    github_descriptor, github_adapter = build_github_connector()
    registry.register(github_descriptor, github_adapter)
    from core.jira_connector import build_jira_connector
    jira_descriptor, jira_adapter = build_jira_connector()
    registry.register(jira_descriptor, jira_adapter)
    return ConnectorService(registry, observability)

__all__=["ConnectorCapability","ConnectorDescriptor","ConnectorKind","ConnectorPolicyEngine","ConnectorRequest","ConnectorResult","ConnectorRegistry","ConnectorRisk","ConnectorService","ConnectorValidationError","FakeMCPTransport","build_connector_service"]
