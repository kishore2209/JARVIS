"""Allowlisted, human-in-the-loop tool framework for safe internal actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping
from uuid import uuid4

from core.memory import JarvisMemoryService, MemoryCategory, MemoryScope, MemoryValidationError


class ToolRiskClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOCAL_REVERSIBLE = "LOCAL_REVERSIBLE"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"
    FINANCIAL = "FINANCIAL"
    PROHIBITED = "PROHIBITED"


class ToolPlanStatus(str, Enum):
    PLANNED = "PLANNED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ToolErrorCategory(str, Enum):
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_DISABLED = "TOOL_DISABLED"
    TOOL_INVALID_ARGUMENT = "TOOL_INVALID_ARGUMENT"
    TOOL_CONFIRMATION_REQUIRED = "TOOL_CONFIRMATION_REQUIRED"
    TOOL_APPROVAL_INVALID = "TOOL_APPROVAL_INVALID"
    TOOL_EXPIRED = "TOOL_EXPIRED"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_POLICY_REJECTED = "TOOL_POLICY_REJECTED"


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    display_name: str
    description: str
    risk_class: ToolRiskClass
    requires_confirmation: bool
    allowed_execution_modes: tuple[str, ...]
    argument_schema: Mapping[str, Mapping[str, Any]]
    version: str = "1"
    enabled: bool = True

    def __post_init__(self):
        object.__setattr__(self, "argument_schema", MappingProxyType({key: MappingProxyType(dict(value)) for key, value in self.argument_schema.items()}))


@dataclass(frozen=True)
class ToolInvocationPlan:
    plan_id: str
    tool_id: str
    validated_arguments: Mapping[str, Any]
    risk_class: ToolRiskClass
    requires_confirmation: bool
    status: ToolPlanStatus
    created_at: datetime
    expires_at: datetime
    preview: str
    source: str
    correlation_id: str
    argument_fingerprint: str

    def __post_init__(self):
        object.__setattr__(self, "validated_arguments", MappingProxyType(dict(self.validated_arguments)))


@dataclass(frozen=True)
class ToolApproval:
    plan_id: str
    tool_id: str
    argument_fingerprint: str
    approved_at: datetime
    source: str = "EXPLICIT_USER"


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    requires_confirmation: bool
    reason_code: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolExecutionResult:
    plan_id: str
    tool_id: str
    status: str
    result: Any = None
    warnings: tuple[str, ...] = ()
    error_category: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    correlation_id: str | None = None


def _safe_text(value: Any, max_length: int = 500) -> str:
    text = str(value)
    if len(text) > max_length: raise ToolValidationError("argument exceeds maximum length")
    lowered = text.lower()
    if any(term in lowered for term in ("api_key", "secret", "password", "pin", "totp", "access_token", "authorization", "bearer", "broker_token")):
        raise ToolValidationError("credential-like argument is prohibited")
    return text


def _fingerprint(arguments: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(arguments), sort_keys=True, default=str).encode()).hexdigest()


class ToolRegistry:
    def __init__(self): self._tools: dict[str, tuple[ToolDescriptor, Callable[[Mapping[str, Any]], Any]]] = {}

    def register(self, descriptor: ToolDescriptor, adapter: Callable[[Mapping[str, Any]], Any]) -> None:
        if descriptor.tool_id in self._tools: raise ToolValidationError("duplicate tool identifier")
        if descriptor.risk_class in {ToolRiskClass.FINANCIAL, ToolRiskClass.PROHIBITED} or (descriptor.risk_class is ToolRiskClass.EXTERNAL_SIDE_EFFECT and not descriptor.tool_id.startswith("github.")):
            raise ToolValidationError("tool risk class is blocked in Phase U")
        if not callable(adapter): raise ToolValidationError("tool adapter must be callable")
        self._tools[descriptor.tool_id] = (descriptor, adapter)

    def descriptor(self, tool_id: str) -> ToolDescriptor:
        if tool_id not in self._tools: raise ToolValidationError(ToolErrorCategory.TOOL_NOT_FOUND.value)
        return self._tools[tool_id][0]

    def adapter(self, tool_id: str) -> Callable[[Mapping[str, Any]], Any]:
        if tool_id not in self._tools: raise ToolValidationError(ToolErrorCategory.TOOL_NOT_FOUND.value)
        return self._tools[tool_id][1]

    def list(self) -> tuple[ToolDescriptor, ...]: return tuple(item[0] for item in self._tools.values())

    def safe_list(self) -> tuple[dict[str, Any], ...]:
        return tuple({"tool_id": item.tool_id, "display_name": item.display_name, "description": item.description, "risk_class": item.risk_class.value, "requires_confirmation": item.requires_confirmation, "allowed_execution_modes": item.allowed_execution_modes, "argument_schema": {key: dict(value) for key, value in item.argument_schema.items()}, "version": item.version, "enabled": item.enabled} for item in self.list())

    def validate_arguments(self, tool_id: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        descriptor = self.descriptor(tool_id)
        if not isinstance(arguments, Mapping): raise ToolValidationError(ToolErrorCategory.TOOL_INVALID_ARGUMENT.value)
        unknown = set(arguments) - set(descriptor.argument_schema)
        if unknown: raise ToolValidationError(f"{ToolErrorCategory.TOOL_INVALID_ARGUMENT.value}: unknown argument")
        validated = {}
        for name, schema in descriptor.argument_schema.items():
            required = bool(schema.get("required", False))
            if name not in arguments:
                if required: raise ToolValidationError(f"{ToolErrorCategory.TOOL_INVALID_ARGUMENT.value}: missing argument")
                continue
            value = arguments[name]
            expected = schema.get("type", "string")
            if expected == "string":
                if not isinstance(value, str): raise ToolValidationError(ToolErrorCategory.TOOL_INVALID_ARGUMENT.value)
                validated[name] = _safe_text(value, int(schema.get("max_length", 500)))
            elif expected == "boolean":
                if not isinstance(value, bool): raise ToolValidationError(ToolErrorCategory.TOOL_INVALID_ARGUMENT.value)
                validated[name] = value
            else: raise ToolValidationError(ToolErrorCategory.TOOL_INVALID_ARGUMENT.value)
        return validated


class ToolPolicyEngine:
    def decide(self, descriptor: ToolDescriptor, source: str, arguments: Mapping[str, Any], runtime_mode: str, approval: ToolApproval | None = None, plan: ToolInvocationPlan | None = None) -> ToolPolicyDecision:
        if not descriptor.enabled: return ToolPolicyDecision(False, False, "TOOL_DISABLED")
        if runtime_mode not in descriptor.allowed_execution_modes: return ToolPolicyDecision(False, False, "EXECUTION_MODE_UNSUPPORTED")
        if descriptor.risk_class in {ToolRiskClass.FINANCIAL, ToolRiskClass.PROHIBITED}: return ToolPolicyDecision(False, False, "RISK_CLASS_BLOCKED")
        if descriptor.requires_confirmation:
            if plan is None or approval is None: return ToolPolicyDecision(False, True, "CONFIRMATION_REQUIRED")
            if approval.plan_id != plan.plan_id or approval.tool_id != plan.tool_id or approval.argument_fingerprint != plan.argument_fingerprint: return ToolPolicyDecision(False, True, "APPROVAL_INVALID")
        return ToolPolicyDecision(True, descriptor.requires_confirmation, "TOOL_ALLOWED")


class ToolService:
    def __init__(self, registry: ToolRegistry, observability=None, plan_ttl_seconds: int = 300, governance=None):
        self.registry = registry; self.policy = ToolPolicyEngine(); self.observability = observability; self.governance=governance; self.plan_ttl = timedelta(seconds=plan_ttl_seconds); self.plans: dict[str, ToolInvocationPlan] = {}; self.approvals: dict[str, ToolApproval] = {}; self.results: dict[str, ToolExecutionResult] = {}

    def plan(self, tool_id: str, arguments: Mapping[str, Any] | None = None, source: str = "USER", correlation_id: str = "TOOL") -> ToolInvocationPlan:
        descriptor = self.registry.descriptor(tool_id); validated = self.registry.validate_arguments(tool_id, arguments or {})
        self._check_governance(descriptor, validated)
        now = datetime.now(timezone.utc); requires = descriptor.requires_confirmation
        plan = ToolInvocationPlan(uuid4().hex, tool_id, validated, descriptor.risk_class, requires, ToolPlanStatus.AWAITING_CONFIRMATION if requires else ToolPlanStatus.PLANNED, now, now + self.plan_ttl, json.dumps(validated, sort_keys=True), source, correlation_id, _fingerprint(validated))
        self.plans[plan.plan_id] = plan; self._metric("tool_plans_total"); self._event("tool_plan_created", plan)
        if requires: self._event("tool_confirmation_required", plan)
        return plan

    def approve(self, plan_id: str, source: str = "EXPLICIT_USER") -> ToolApproval:
        plan = self._get_plan(plan_id); self._check_expired(plan)
        if not plan.requires_confirmation: raise ToolValidationError(ToolErrorCategory.TOOL_POLICY_REJECTED.value)
        approval = ToolApproval(plan.plan_id, plan.tool_id, plan.argument_fingerprint, datetime.now(timezone.utc), source); self.approvals[plan_id] = approval; self.plans[plan_id] = ToolInvocationPlan(**{**plan.__dict__, "status": ToolPlanStatus.APPROVED}); self._metric("tool_confirmations_total"); self._event("tool_approved", plan); return approval

    def execute(self, plan_id: str, approval: ToolApproval | None = None) -> ToolExecutionResult:
        plan = self._get_plan(plan_id); self._check_expired(plan)
        if plan_id in self.results: self._metric("tool_duplicate_execution_blocked_total"); return ToolExecutionResult(plan_id, plan.tool_id, ToolPlanStatus.REJECTED.value, warnings=("Plan already completed.",), error_category="TOOL_POLICY_REJECTED", correlation_id=plan.correlation_id)
        descriptor=self.registry.descriptor(plan.tool_id); self._check_governance(descriptor, plan.validated_arguments)
        approval = approval or self.approvals.get(plan_id); decision = self.policy.decide(descriptor, plan.source, plan.validated_arguments, "ANALYSIS_ONLY", approval, plan)
        if not decision.allowed: self._metric("tool_rejections_total"); return ToolExecutionResult(plan_id, plan.tool_id, ToolPlanStatus.REJECTED.value, warnings=(decision.reason_code,), error_category=decision.reason_code, correlation_id=plan.correlation_id)
        started = datetime.now(timezone.utc); self._metric("tool_executions_total"); self._event("tool_execution_started", plan)
        try:
            value = self.registry.adapter(plan.tool_id)(plan.validated_arguments)
            result = ToolExecutionResult(plan_id, plan.tool_id, ToolPlanStatus.SUCCEEDED.value, value, started_at=started, completed_at=datetime.now(timezone.utc), correlation_id=plan.correlation_id)
            self.results[plan_id] = result; self._event("tool_execution_completed", plan); return result
        except Exception:
            self._metric("tool_failures_total"); self._event("tool_execution_failed", plan); return ToolExecutionResult(plan_id, plan.tool_id, ToolPlanStatus.FAILED.value, error_category=ToolErrorCategory.TOOL_EXECUTION_FAILED.value, correlation_id=plan.correlation_id)

    def show(self, plan_id: str) -> ToolInvocationPlan: return self._get_plan(plan_id)
    def _get_plan(self, plan_id):
        if plan_id not in self.plans: raise ToolValidationError(ToolErrorCategory.TOOL_NOT_FOUND.value)
        return self.plans[plan_id]
    def _check_expired(self, plan):
        if datetime.now(timezone.utc) >= plan.expires_at: raise ToolValidationError(ToolErrorCategory.TOOL_EXPIRED.value)
    def _metric(self, name):
        if self.observability: self.observability.counters[name] = self.observability.counters.get(name, 0) + 1
    def _event(self, name, plan):
        if self.observability: self.observability.record("TOOLS", name, "COMPLETED", request_id=plan.correlation_id, metadata={"tool_id": plan.tool_id, "risk_class": plan.risk_class.value, "status": plan.status.value})
    def _check_governance(self, descriptor, arguments):
        if self.governance and descriptor.risk_class is ToolRiskClass.EXTERNAL_SIDE_EFFECT:
            resource = f"{arguments.get('owner','')}/{arguments.get('repo','')}"
            decision=self.governance.decide('github', descriptor.tool_id, resource, True, True)
            if not decision.allowed: raise ToolValidationError(decision.reason_code)


def build_tool_service(runtime, observability=None) -> ToolService:
    registry = ToolRegistry()
    mode = ("ANALYSIS_ONLY",)
    registry.register(ToolDescriptor("system.status", "System status", "Current core status.", ToolRiskClass.READ_ONLY, False, mode, {}), lambda _args: {"status": "OK", "live_execution_supported": False})
    registry.register(ToolDescriptor("system.readiness", "System readiness", "Current deterministic readiness.", ToolRiskClass.READ_ONLY, False, mode, {"workflow": {"type": "string", "required": False, "max_length": 40}}), lambda args: runtime.observability.readiness(args.get("workflow", "ANALYSIS_ONLY")))
    registry.register(ToolDescriptor("memory.list", "Memory list", "List selected personal context.", ToolRiskClass.READ_ONLY, False, mode, {}), lambda _args: [record for record in runtime.memory.list()])
    registry.register(ToolDescriptor("memory.search", "Memory search", "Search selected personal context.", ToolRiskClass.READ_ONLY, False, mode, {"query": {"type": "string", "required": True, "max_length": 120}}), lambda args: list(runtime.memory.search(args["query"])))
    registry.register(ToolDescriptor("portfolio.summary", "Portfolio summary", "Read current paper portfolio summary.", ToolRiskClass.READ_ONLY, False, mode, {}), lambda _args: runtime.paper_engine.account)
    registry.register(ToolDescriptor("automation.status", "Automation status", "Read automation jobs and history metadata.", ToolRiskClass.READ_ONLY, False, mode, {}), lambda _args: {"jobs": list(runtime.automation.jobs), "history_count": len(runtime.automation.history)})
    registry.register(ToolDescriptor("memory.preference.set", "Set memory preference", "Set one explicit local preference.", ToolRiskClass.LOCAL_REVERSIBLE, True, mode, {"key": {"type": "string", "required": True, "max_length": 120}, "value": {"type": "string", "required": True, "max_length": 500}}), lambda args: runtime.memory.create(MemoryCategory.PREFERENCE, args["key"], args["value"], scope=MemoryScope.DURABLE))
    if getattr(runtime, "connectors", None):
        registry.register(ToolDescriptor("connector.list", "Connector list", "List configured read-only connectors.", ToolRiskClass.READ_ONLY, False, mode, {}), lambda _args: runtime.connectors.registry.safe_list())
        registry.register(ToolDescriptor("connector.capabilities", "Connector capabilities", "List capabilities for one connector.", ToolRiskClass.READ_ONLY, False, mode, {"connector_id": {"type": "string", "required": True, "max_length": 80}}), lambda args: runtime.connectors.registry.safe_capabilities(args["connector_id"]))
        registry.register(ToolDescriptor("connector.read", "Connector read", "Read a preconfigured connector resource.", ToolRiskClass.READ_ONLY, False, mode, {"connector_id": {"type": "string", "required": True, "max_length": 80}, "capability_id": {"type": "string", "required": True, "max_length": 120}, "resource": {"type": "string", "required": False, "max_length": 120}}), lambda args: runtime.connectors.read(__import__("core.connectors", fromlist=["ConnectorRequest"]).ConnectorRequest("TOOL", args["connector_id"], args["capability_id"], {"resource": args["resource"]})).data)
        if any(item["connector_id"] == "jira" for item in runtime.connectors.registry.safe_list()):
            for capability_id, schema in (("jira.projects.list", {}), ("jira.project.get", {"project_key":{"type":"string","required":True,"max_length":50}}), ("jira.issue.get", {"issue_key":{"type":"string","required":True,"max_length":40}}), ("jira.issues.search", {"project_key":{"type":"string","required":False,"max_length":50},"status":{"type":"string","required":False,"max_length":100},"text":{"type":"string","required":False,"max_length":100},"start_at":{"type":"string","required":False,"max_length":6},"max_results":{"type":"string","required":False,"max_length":3}})):
                registry.register(ToolDescriptor(capability_id, capability_id, "Read-only Jira capability.", ToolRiskClass.READ_ONLY, False, mode, schema), lambda args, capability_id=capability_id: runtime.connectors.read(__import__("core.connectors",fromlist=["ConnectorRequest"]).ConnectorRequest("TOOL","jira",capability_id,args)).data)
            if getattr(runtime, "projects", None): registry.register(ToolDescriptor("project.snapshot", "Project snapshot", "Bounded Jira/GitHub project intelligence.", ToolRiskClass.READ_ONLY, False, mode, {"workspace_id":{"type":"string","required":True,"max_length":100}}), lambda args: runtime.projects.snapshot(args["workspace_id"]))
            if getattr(runtime, "delivery", None):
                registry.register(ToolDescriptor("project.delivery", "Project delivery", "Describe deterministic project changes and attention signals.", ToolRiskClass.READ_ONLY, False, mode, {"workspace_id":{"type":"string","required":True,"max_length":100}}), lambda args: runtime.delivery.analyze(args["workspace_id"]))
                registry.register(ToolDescriptor("project.brief", "Project brief", "Render a deterministic project delivery brief.", ToolRiskClass.READ_ONLY, False, mode, {"workspace_id":{"type":"string","required":True,"max_length":100}}), lambda args: runtime.delivery.brief(runtime.delivery.analyze(args["workspace_id"])) )
        github = runtime.connectors.registry.descriptor("github")
        if github.write_enabled:
            for capability_id, schema in (("github.issue.create", {"owner":{"type":"string","required":True,"max_length":100},"repo":{"type":"string","required":True,"max_length":100},"title":{"type":"string","required":True,"max_length":200},"body":{"type":"string","required":False,"max_length":5000}}), ("github.issue.comment", {"owner":{"type":"string","required":True,"max_length":100},"repo":{"type":"string","required":True,"max_length":100},"issue_number":{"type":"string","required":True,"max_length":10},"body":{"type":"string","required":True,"max_length":5000}}), ("github.pull_request.comment", {"owner":{"type":"string","required":True,"max_length":100},"repo":{"type":"string","required":True,"max_length":100},"pull_number":{"type":"string","required":True,"max_length":10},"body":{"type":"string","required":True,"max_length":5000}})):
                registry.register(ToolDescriptor(capability_id, capability_id, "Allowlisted GitHub collaboration action.", ToolRiskClass.EXTERNAL_SIDE_EFFECT, True, mode, schema), lambda args, capability_id=capability_id: runtime.connectors.write(__import__("core.connectors", fromlist=["ConnectorRequest"]).ConnectorRequest("TOOL", "github", capability_id, args)).data)
    return ToolService(registry, observability, governance=getattr(runtime, 'governance', None))


__all__ = ["ToolApproval", "ToolDescriptor", "ToolErrorCategory", "ToolExecutionResult", "ToolInvocationPlan", "ToolPlanStatus", "ToolPolicyDecision", "ToolPolicyEngine", "ToolRegistry", "ToolRiskClass", "ToolService", "ToolValidationError", "build_tool_service"]
