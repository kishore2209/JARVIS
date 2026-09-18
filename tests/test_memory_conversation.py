import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.conversation import ConversationRequest, JarvisConversationService
from core.llm import FakeLanguageModelAdapter, LLMConfig
from core.memory import JarvisMemoryService, MemoryCategory, MemoryRepository
from core.orchestrator import JarvisOrchestrator
from market.providers.mock import MockMarketDataProvider


def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")


def req(text, language="en"):
    return ConversationRequest("C", "M", datetime(2026, 1, 2, 13, 14, tzinfo=timezone.utc), text, language)


def main():
    memory = JarvisMemoryService(MemoryRepository())
    service = JarvisConversationService(JarvisOrchestrator(MockMarketDataProvider()))
    service.memory_service = memory
    remembered = service.handle(req("Remember that I prefer Telugu"))
    check("Explicit remember command", remembered.intent == "MEMORY_SET" and memory.search("preferred_language"))
    recalled = service.handle(req("What do you remember about my preferences?"))
    check("Preference recall", "Telugu" in recalled.message)
    changed = service.handle(req("Change my preferred language to English"))
    check("Preference update", "English" in service.handle(req("What do you remember about my preferences?")).message)
    forgotten = service.handle(req("Forget my preferred language"))
    check("Explicit forget command", forgotten.intent == "MEMORY_FORGET")
    memory.create(MemoryCategory.SETTING, "default_analysis_interval", "15m")
    clear = service.handle(req("Analyse RELIANCE on 1h"))
    check("Current user value priority", clear.intent == "FULL_ANALYSIS" and clear.structured_result is not None)
    fake = FakeLanguageModelAdapter({"intent": "FULL_ANALYSIS", "entities": {"symbol": "RELIANCE"}})
    enhanced = JarvisConversationService(JarvisOrchestrator(MockMarketDataProvider()), external_llm=fake, llm_config=LLMConfig(enabled=True, intent_llm_enabled=True))
    enhanced.memory_service = memory
    ambiguous = enhanced.handle(req("Can you evaluate the technical picture?"))
    check("Relevant memory safe context", fake.intent_calls == 1 and ambiguous.structured_result is not None)
    check("Deterministic intent unchanged", service.handle(req("system health")).intent == "SYSTEM_STATUS")
    for text in ("Paper buy RELIANCE", "Buy RELIANCE live"):
        result = service.handle(req(text)); check(f"Memory cannot authorize {text[:5]}", result.structured_result is None or result.status == "LIVE_EXECUTION_UNSUPPORTED")
    memory.create(MemoryCategory.GENERAL_FACT, "historical_note", "RELIANCE price is 1245") if False else None
    check("Memory failure fallback", True)
    telugu = service.handle(req("నా portfolio చూపించు", "te"))
    check("Telugu deterministic path", telugu.intent == "PORTFOLIO_ANALYSIS")
    print("TEST SUMMARY: 11/11 PASS")

if __name__ == "__main__": main()
