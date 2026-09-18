"""Bounded, sequential, restart-safe workflow orchestration over ToolService."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from core.tools import ToolApproval, ToolErrorCategory, ToolPlanStatus, ToolRiskClass, ToolService, ToolValidationError


class WorkflowStatus(str, Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class WorkflowStepStatus(str, Enum):
    PENDING = "PENDING"
    PLANNED = "PLANNED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    order: int
    tool_id: str
    arguments: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()
    risk_class: ToolRiskClass = ToolRiskClass.READ_ONLY
    requires_confirmation: bool = False
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    tool_plan_id: str | None = None
    result_reference: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class WorkflowPlan:
    workflow_id: str
    title: str
    source: str
    status: WorkflowStatus
    steps: tuple[WorkflowStep, ...]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    correlation_id: str
    version: int = 1
    max_steps: int = 5
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self):
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class WorkflowExecutionResult:
    workflow_id: str
    status: WorkflowStatus
    steps: tuple[WorkflowStep, ...]
    results: Mapping[str, Any]
    warnings: tuple[str, ...] = ()

    def __post_init__(self): object.__setattr__(self, "results", MappingProxyType(dict(self.results)))


class WorkflowValidationError(ValueError):
    pass


class WorkflowService:
    def __init__(self, tool_service: ToolService, store=None, observability=None, max_steps: int = 5, ttl_seconds: int = 900):
        if max_steps <= 0: raise WorkflowValidationError("max workflow steps must be positive")
        self.tools = tool_service; self.store = store; self.observability = observability; self.max_steps = max_steps; self.ttl = timedelta(seconds=ttl_seconds); self.workflows: dict[str, WorkflowPlan] = {}; self.results: dict[str, dict[str, Any]] = {}
        if store is not None:
            with store.connection: store.connection.execute("CREATE TABLE IF NOT EXISTS workflow_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            self._restore()

    def create(self, title: str, steps: list[Mapping[str, Any]], source: str = "USER", correlation_id: str = "WORKFLOW") -> WorkflowPlan:
        if not steps or len(steps) > self.max_steps: raise WorkflowValidationError("workflow step count is outside the safe bound")
        seen = set(); validated = []; now = datetime.now(timezone.utc)
        for index, item in enumerate(steps):
            step_id = str(item.get("step_id", f"step-{index + 1}"))
            if step_id in seen: raise WorkflowValidationError("duplicate workflow step id")
            seen.add(step_id)
            tool_id = str(item.get("tool_id", "")); descriptor = self.tools.registry.descriptor(tool_id)
            arguments = self.tools.registry.validate_arguments(tool_id, item.get("arguments", {}))
            depends = tuple(item.get("depends_on", ()))
            if any(dependency not in seen for dependency in depends): raise WorkflowValidationError("workflow dependency must reference an earlier step")
            validated.append(WorkflowStep(step_id, index, tool_id, arguments, depends, descriptor.risk_class, descriptor.requires_confirmation, WorkflowStepStatus.PENDING, created_at=now, updated_at=now))
        plan = WorkflowPlan(uuid4().hex, title[:120], source, WorkflowStatus.READY, tuple(validated), now, now, now + self.ttl, correlation_id, max_steps=self.max_steps)
        self.workflows[plan.workflow_id] = plan; self._metric("workflow_plans_total"); self._event("workflow_created", plan); self._save(plan); return plan

    def list(self) -> tuple[WorkflowPlan, ...]: return tuple(self.workflows.values())
    def show(self, workflow_id: str) -> WorkflowPlan: return self._get(workflow_id)

    def run(self, workflow_id: str) -> WorkflowExecutionResult:
        plan = self._get(workflow_id); self._ensure_runnable(plan)
        if plan.status in {WorkflowStatus.SUCCEEDED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED}: return self._result(plan)
        self._update(plan, status=WorkflowStatus.RUNNING); self._event("workflow_started", plan)
        steps = list(plan.steps); results = dict(self.results.get(plan.workflow_id, {}))
        for index, step in enumerate(steps):
            if step.status is WorkflowStepStatus.SUCCEEDED: continue
            if any(steps_by_id(steps, dep).status is not WorkflowStepStatus.SUCCEEDED for dep in step.depends_on): self._update(plan, status=WorkflowStatus.FAILED); return self._result(self._get(workflow_id))
            try:
                if step.tool_plan_id is None:
                    tool_plan = self.tools.plan(step.tool_id, step.arguments, plan.source, plan.correlation_id)
                    step = replace(step, tool_plan_id=tool_plan.plan_id, status=WorkflowStepStatus.AWAITING_CONFIRMATION if tool_plan.requires_confirmation else WorkflowStepStatus.PLANNED, updated_at=datetime.now(timezone.utc))
                    steps[index] = step; self._replace_steps(plan, steps)
                if step.status is WorkflowStepStatus.AWAITING_CONFIRMATION or (self.tools.registry.descriptor(step.tool_id).requires_confirmation and step.status is not WorkflowStepStatus.APPROVED):
                    self._update(plan, status=WorkflowStatus.WAITING_FOR_APPROVAL); self._event("workflow_waiting_for_approval", self._get(workflow_id)); return self._result(self._get(workflow_id))
                execution = self.tools.execute(step.tool_plan_id)
                if execution.status != "SUCCEEDED":
                    steps[index] = replace(step, status=WorkflowStepStatus.FAILED, updated_at=datetime.now(timezone.utc)); self._replace_steps(plan, steps); self._update(plan, status=WorkflowStatus.FAILED); self._event("workflow_step_failed", self._get(workflow_id)); return self._result(self._get(workflow_id))
                steps[index] = replace(step, status=WorkflowStepStatus.SUCCEEDED, result_reference=step.tool_plan_id, updated_at=datetime.now(timezone.utc)); results[step.step_id] = execution.result; self.results[plan.workflow_id] = results; self._replace_steps(plan, steps); self._event("workflow_step_completed", self._get(workflow_id))
            except (ToolValidationError, ValueError):
                steps[index] = replace(step, status=WorkflowStepStatus.FAILED, updated_at=datetime.now(timezone.utc)); self._replace_steps(plan, steps); self._update(plan, status=WorkflowStatus.FAILED); self._event("workflow_step_failed", self._get(workflow_id)); return self._result(self._get(workflow_id))
        self._update(plan, status=WorkflowStatus.SUCCEEDED); self._event("workflow_completed", self._get(workflow_id)); return self._result(self._get(workflow_id))

    def approve_step(self, workflow_id: str, step_id: str) -> ToolApproval:
        plan = self._get(workflow_id); self._ensure_runnable(plan); step = self._step(plan, step_id)
        if step.status is not WorkflowStepStatus.AWAITING_CONFIRMATION or not step.tool_plan_id: raise WorkflowValidationError("step is not awaiting approval")
        approval = self.tools.approve(step.tool_plan_id); steps = [replace(item, status=WorkflowStepStatus.APPROVED, updated_at=datetime.now(timezone.utc)) if item.step_id == step_id else item for item in plan.steps]; self._replace_steps(plan, steps); return approval

    def resume(self, workflow_id: str) -> WorkflowExecutionResult:
        plan = self._get(workflow_id); self._ensure_runnable(plan)
        if plan.status is not WorkflowStatus.WAITING_FOR_APPROVAL: raise WorkflowValidationError("workflow is not waiting for approval")
        step = next((item for item in plan.steps if item.status is WorkflowStepStatus.APPROVED), None)
        if step is None: raise WorkflowValidationError("exact step approval is required")
        return self.run(workflow_id)

    def cancel(self, workflow_id: str) -> WorkflowPlan:
        plan = self._get(workflow_id)
        if plan.status in {WorkflowStatus.SUCCEEDED, WorkflowStatus.CANCELLED}: raise WorkflowValidationError("workflow cannot be cancelled")
        steps = tuple(replace(step, status=WorkflowStepStatus.CANCELLED, updated_at=datetime.now(timezone.utc)) if step.status not in {WorkflowStepStatus.SUCCEEDED, WorkflowStepStatus.FAILED} else step for step in plan.steps)
        plan = replace(plan, steps=steps, status=WorkflowStatus.CANCELLED, updated_at=datetime.now(timezone.utc), version=plan.version + 1); self.workflows[plan.workflow_id] = plan; self._save(plan); self._event("workflow_cancelled", plan); return plan

    def _ensure_runnable(self, plan):
        if datetime.now(timezone.utc) >= plan.expires_at: raise WorkflowValidationError("workflow expired")
        if plan.status is WorkflowStatus.CANCELLED: raise WorkflowValidationError("workflow cancelled")
    def _get(self, workflow_id):
        if workflow_id not in self.workflows: raise WorkflowValidationError("workflow not found")
        return self.workflows[workflow_id]
    def _step(self, plan, step_id):
        for step in plan.steps:
            if step.step_id == step_id: return step
        raise WorkflowValidationError("step not found")
    def _update(self, plan, **changes):
        updated = replace(self._get(plan.workflow_id), **changes, updated_at=datetime.now(timezone.utc), version=plan.version + 1); self.workflows[plan.workflow_id] = updated; self._save(updated)
    def _replace_steps(self, plan, steps): self._update(plan, steps=tuple(steps))
    def _result(self, plan): return WorkflowExecutionResult(plan.workflow_id, plan.status, plan.steps, self.results.get(plan.workflow_id, {}))
    def _save(self, plan):
        if self.store:
            payload = {"workflow_id":plan.workflow_id,"title":plan.title,"source":plan.source,"status":plan.status.value,"steps":[{"step_id":step.step_id,"order":step.order,"tool_id":step.tool_id,"arguments":dict(step.arguments),"depends_on":step.depends_on,"risk_class":step.risk_class.value,"requires_confirmation":step.requires_confirmation,"status":step.status.value,"tool_plan_id":step.tool_plan_id,"result_reference":step.result_reference,"created_at":step.created_at.isoformat() if step.created_at else None,"updated_at":step.updated_at.isoformat() if step.updated_at else None} for step in plan.steps],"created_at":plan.created_at.isoformat(),"updated_at":plan.updated_at.isoformat(),"expires_at":plan.expires_at.isoformat(),"correlation_id":plan.correlation_id,"version":plan.version,"max_steps":plan.max_steps,"metadata":dict(plan.metadata)}
            with self.store.connection: self.store.connection.execute("INSERT OR REPLACE INTO workflow_records VALUES (?,?)", (plan.workflow_id, json.dumps(payload)))
    def _restore(self):
        # Safe restart policy: restore metadata only; no tool plan or approval is auto-resumed.
        for row in self.store.connection.execute("SELECT payload FROM workflow_records ORDER BY id"):
            data = json.loads(row[0]); steps = tuple(WorkflowStep(item["step_id"], item["order"], item["tool_id"], item["arguments"], tuple(item.get("depends_on", ())), ToolRiskClass(item["risk_class"]), item["requires_confirmation"], WorkflowStepStatus(item["status"]), None, item.get("result_reference"), datetime.fromisoformat(item["created_at"]) if item.get("created_at") else None, datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None) for item in data["steps"])
            self.workflows[data["workflow_id"]] = WorkflowPlan(data["workflow_id"], data["title"], data["source"], WorkflowStatus(data["status"]), steps, datetime.fromisoformat(data["created_at"]), datetime.fromisoformat(data["updated_at"]), datetime.fromisoformat(data["expires_at"]), data["correlation_id"], data["version"], data["max_steps"], data.get("metadata", {}))
    def _metric(self, name):
        if self.observability: self.observability.counters[name] = self.observability.counters.get(name, 0) + 1
    def _event(self, name, plan):
        if self.observability: self.observability.record("WORKFLOW", name, "COMPLETED", request_id=plan.correlation_id, metadata={"workflow_id":plan.workflow_id,"status":plan.status.value,"step_count":len(plan.steps)})


def steps_by_id(steps, step_id):
    for step in steps:
        if step.step_id == step_id: return step
    raise WorkflowValidationError("dependency step not found")


__all__ = ["WorkflowExecutionResult", "WorkflowPlan", "WorkflowService", "WorkflowStatus", "WorkflowStep", "WorkflowStepStatus", "WorkflowValidationError"]
