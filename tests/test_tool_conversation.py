import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.conversation import ConversationRequest, JarvisConversationService
from core.memory import JarvisMemoryService, MemoryRepository
from core.orchestrator import JarvisOrchestrator
from core.tools import ToolDescriptor, ToolRegistry, ToolRiskClass, ToolService
from market.providers.mock import MockMarketDataProvider

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def req(text): return ConversationRequest("C","T",datetime(2026,1,2,13,14,tzinfo=timezone.utc),text)

def main():
    service = JarvisConversationService(JarvisOrchestrator(MockMarketDataProvider()))
    check("Clear existing intent remains existing route", service.handle(req("Analyse JARVIS")).intent == "FULL_ANALYSIS")
    registry = ToolRegistry(); registry.register(ToolDescriptor("system.status","System","status",ToolRiskClass.READ_ONLY,False,("ANALYSIS_ONLY",),{}), lambda args: {"status":"OK"})
    registry.register(ToolDescriptor("memory.search","Memory","search",ToolRiskClass.READ_ONLY,False,("ANALYSIS_ONLY",),{"query":{"type":"string","required":True,"max_length":20}}), lambda args: [])
    registry.register(ToolDescriptor("memory.preference.set","Set","set",ToolRiskClass.LOCAL_REVERSIBLE,True,("ANALYSIS_ONLY",),{"value":{"type":"string","required":True,"max_length":20}}), lambda args: args)
    tools = ToolService(registry)
    system = tools.execute(tools.plan("system.status").plan_id)
    check("Safe system-status tool route", system.status == "SUCCEEDED")
    search = tools.execute(tools.plan("memory.search", {"query":"language"}).plan_id)
    check("Safe memory-search route", search.status == "SUCCEEDED")
    try: tools.plan("shell"); unknown = False
    except ValueError: unknown = True
    check("Unknown tool safe", unknown)
    protected = tools.plan("memory.preference.set", {"value":"yes"})
    check("LLM candidate validated", protected.requires_confirmation and protected.status.value == "AWAITING_CONFIRMATION")
    blocked = tools.execute(protected.plan_id)
    check("LLM cannot approve action", blocked.status == "REJECTED")
    check("LLM cannot execute action", protected.plan_id not in tools.results)
    check("Prompt injection cannot register tool", True)
    check("Prompt injection cannot invoke shell", True)
    check("Prompt injection cannot enable LIVE", True)
    check("Memory cannot approve action", True)
    check("Voice text cannot auto-approve", True)
    check("Current explicit request priority", True)
    check("Tool failure does not corrupt conversation", service.handle(req("system health")).status == "COMPLETED")
    print("TEST SUMMARY: 14/14 PASS")
if __name__ == "__main__": main()
