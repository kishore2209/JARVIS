import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import GeminiLanguageModelAdapter, LLMConfig, LLMIntentRequest

if not os.getenv("GEMINI_API_KEY") or os.getenv("JARVIS_RUN_GEMINI_SMOKE", "false").lower() != "true":
    print("GEMINI MANUAL SMOKE: SKIPPED - NOT CONFIGURED")
    raise SystemExit(0)

adapter = GeminiLanguageModelAdapter(LLMConfig(enabled=True, intent_llm_enabled=True))
result = adapter.parse_intent(LLMIntentRequest("MANUAL-SMOKE", "How can JARVIS help me?"))
print(f"GEMINI MANUAL SMOKE: {result.intent if result.valid else result.error_category}")
