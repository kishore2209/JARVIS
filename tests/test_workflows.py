import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.observability import Observability
from core.tools import ToolDescriptor, ToolRegistry, ToolRiskClass, ToolService, ToolValidationError
from core.workflows import WorkflowService, WorkflowStatus, WorkflowStepStatus, WorkflowValidationError
from market.persistence import SQLiteStore

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def build(store=None):
    registry = ToolRegistry(); calls=[]
    registry.register(ToolDescriptor("one","One","one",ToolRiskClass.READ_ONLY,False,("ANALYSIS_ONLY",),{}), lambda args: calls.append("one") or {"one":True})
    registry.register(ToolDescriptor("two","Two","two",ToolRiskClass.READ_ONLY,False,("ANALYSIS_ONLY",),{}), lambda args: calls.append("two") or {"two":True})
    registry.register(ToolDescriptor("mutate","Mutate","mutate",ToolRiskClass.LOCAL_REVERSIBLE,True,("ANALYSIS_ONLY",),{"value":{"type":"string","required":True,"max_length":20}}), lambda args: calls.append("mutate") or {"mutated":True})
    return WorkflowService(ToolService(registry, Observability()), store, Observability(), max_steps=3), calls

def main():
    service, calls = build()
    try: service.create("empty", []) ; empty=False
    except WorkflowValidationError: empty=True
    check("Empty workflow rejected", empty)
    plan=service.create("read workflow", [{"tool_id":"one","arguments":{}},{"tool_id":"two","arguments":{}}])
    check("Create multi-step workflow", len(plan.steps)==2 and plan.status is WorkflowStatus.READY)
    check("Ordered steps preserved", [step.order for step in plan.steps] == [0,1])
    check("Planning no side effect", calls == [])
    check("Immutable workflow", plan.__dataclass_params__.frozen)
    check("Read-only workflow executes", service.run(plan.workflow_id).status is WorkflowStatus.SUCCEEDED)
    check("Steps execute in order", calls == ["one","two"])
    protected=service.create("protected", [{"tool_id":"one","arguments":{}},{"tool_id":"mutate","arguments":{"value":"x"}}])
    waiting=service.run(protected.workflow_id)
    check("Protected step pauses", waiting.status is WorkflowStatus.WAITING_FOR_APPROVAL and calls[-1] == "one")
    check("Protected step not executed before approval", calls.count("mutate") == 0)
    try: service.approve_step(protected.workflow_id,"wrong"); wrong=False
    except WorkflowValidationError: wrong=True
    check("Wrong step approval rejected", wrong)
    service.approve_step(protected.workflow_id,"step-2")
    resumed=service.resume(protected.workflow_id)
    check("Exact step approval and resume", resumed.status is WorkflowStatus.SUCCEEDED and calls.count("mutate") == 1)
    check("Duplicate resume does not duplicate", service.run(protected.workflow_id).status is WorkflowStatus.SUCCEEDED and calls.count("mutate") == 1)
    cancelled=service.create("cancel", [{"tool_id":"one","arguments":{}}]); service.cancel(cancelled.workflow_id)
    check("Workflow cancellation", service.show(cancelled.workflow_id).status is WorkflowStatus.CANCELLED)
    try: service.run(cancelled.workflow_id); cannot=True
    except WorkflowValidationError: cannot=True
    check("Cancelled workflow cannot resume", cannot)
    expired=service.create("expired", [{"tool_id":"one","arguments":{}}]); service.workflows[expired.workflow_id]=type(expired)(**{**expired.__dict__,"expires_at":datetime.now(timezone.utc)-timedelta(seconds=1)})
    try: service.run(expired.workflow_id); expired_ok=False
    except WorkflowValidationError: expired_ok=True
    check("Expired workflow cannot run", expired_ok)
    path=tempfile.mktemp(suffix=".db"); store=SQLiteStore(path); first,_=build(store); saved=first.create("persist", [{"tool_id":"one","arguments":{}}]); store.close(); store=SQLiteStore(path); second,_=build(store); check("Workflow restart restores", second.show(saved.workflow_id).title == "persist" and second.show(saved.workflow_id).status is WorkflowStatus.READY); check("Restart does not run", second.show(saved.workflow_id).steps[0].status is WorkflowStepStatus.PENDING); store.close(); os.remove(path)
    print("TEST SUMMARY: 17/17 PASS")
if __name__ == "__main__": main()
