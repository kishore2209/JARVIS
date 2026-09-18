import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.tools import ToolDescriptor, ToolRegistry, ToolRiskClass, ToolValidationError

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def descriptor(tool_id="read.test", risk=ToolRiskClass.READ_ONLY, schema=None, enabled=True, confirmation=False):
    return ToolDescriptor(tool_id, "Test", "Test tool", risk, confirmation, ("ANALYSIS_ONLY",), schema or {}, enabled=enabled)

def main():
    registry = ToolRegistry(); registry.register(descriptor(), lambda args: {"ok": True})
    check("Register read-only tool", registry.descriptor("read.test").risk_class is ToolRiskClass.READ_ONLY)
    try: registry.register(descriptor(), lambda args: None); duplicate = False
    except ToolValidationError: duplicate = True
    check("Duplicate registration rejected", duplicate)
    try: registry.descriptor("missing"); unknown = False
    except ToolValidationError: unknown = True
    check("Unknown tool rejected", unknown)
    disabled = ToolRegistry(); disabled.register(descriptor("disabled", enabled=False), lambda args: None)
    check("Disabled descriptor preserved", not disabled.descriptor("disabled").enabled)
    check("Descriptor immutable", descriptor().__dataclass_params__.frozen)
    check("Safe list output", registry.safe_list()[0]["tool_id"] == "read.test" and "adapter" not in str(registry.safe_list()))
    for risk in (ToolRiskClass.FINANCIAL, ToolRiskClass.PROHIBITED, ToolRiskClass.EXTERNAL_SIDE_EFFECT):
        try: ToolRegistry().register(descriptor("blocked" + risk.value, risk), lambda args: None); blocked = False
        except ToolValidationError: blocked = True
        check(f"{risk.value} blocked", blocked)
    schema_registry = ToolRegistry(); schema_registry.register(descriptor("schema", schema={"query":{"type":"string","required":True,"max_length":5}}), lambda args: args)
    check("Argument schema validates", schema_registry.validate_arguments("schema", {"query":"ok"}) == {"query":"ok"})
    for name, value in (("Unknown argument", {"bad":"x"}), ("Missing argument", {}), ("Wrong type", {"query": 1}), ("Oversized argument", {"query":"123456"}), ("Credential argument", {"query":"api_key=secret"})):
        try: schema_registry.validate_arguments("schema", value); valid = True
        except ToolValidationError: valid = False
        check(name, not valid)
    print("TEST SUMMARY: 15/15 PASS")
if __name__ == "__main__": main()
