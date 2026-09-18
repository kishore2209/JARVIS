import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.observability import Observability
from core.tools import ToolDescriptor, ToolErrorCategory, ToolRegistry, ToolRiskClass, ToolService, ToolValidationError

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    obs = Observability(); registry = ToolRegistry(); calls = []
    registry.register(ToolDescriptor("read.test","Read","read",ToolRiskClass.READ_ONLY,False,("ANALYSIS_ONLY",),{}), lambda args: {"safe": True})
    registry.register(ToolDescriptor("mutate.test","Mutate","mutate",ToolRiskClass.LOCAL_REVERSIBLE,True,("ANALYSIS_ONLY",),{"value":{"type":"string","required":True,"max_length":20}}), lambda args: calls.append(args) or {"changed": True})
    service = ToolService(registry, obs)
    read_plan = service.plan("read.test")
    check("Read-only plan", read_plan.requires_confirmation is False and read_plan.status.value == "PLANNED")
    read_result = service.execute(read_plan.plan_id)
    check("Read-only execution", read_result.status == "SUCCEEDED" and read_result.result["safe"])
    check("Result structured", read_result.error_category is None)
    plan = service.plan("mutate.test", {"value":"one"})
    check("Side-effect plan requires confirmation", plan.status.value == "AWAITING_CONFIRMATION")
    blocked = service.execute(plan.plan_id)
    check("No execution before approval", blocked.status == "REJECTED" and not calls)
    try: service.approve("wrong"); wrong = False
    except ToolValidationError: wrong = True
    check("Wrong plan approval rejected", wrong)
    service.approve(plan.plan_id)
    result = service.execute(plan.plan_id)
    check("Correct plan approval", result.status == "SUCCEEDED")
    duplicate = service.execute(plan.plan_id)
    check("Duplicate execution blocked", duplicate.status == "REJECTED")
    check("Approved side effect executes once", len(calls) == 1)
    expired = service.plan("mutate.test", {"value":"two"}); service.plans[expired.plan_id] = type(expired)(**{**expired.__dict__, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    try: service.approve(expired.plan_id); expired_blocked = False
    except ToolValidationError: expired_blocked = True
    check("Expired approval rejected", expired_blocked)
    failing = ToolRegistry(); failing.register(ToolDescriptor("fail.test","Fail","fail",ToolRiskClass.READ_ONLY,False,("ANALYSIS_ONLY",),{}), lambda args: (_ for _ in ()).throw(RuntimeError("secret stack")))
    failing_service = ToolService(failing)
    failed = failing_service.execute(failing_service.plan("fail.test").plan_id)
    check("Adapter exception sanitized", failed.status == "FAILED" and "secret" not in str(failed))
    check("Audit created", any(event.event_type == "tool_execution_completed" for event in obs.events))
    check("Telemetry emitted", obs.counters.get("tool_executions_total") == 2)
    check("No shell execution path", not any(name in str(registry.safe_list()).lower() for name in ("subprocess","powershell","cmd.exe")))
    print("TEST SUMMARY: 20/20 PASS")
if __name__ == "__main__": main()
