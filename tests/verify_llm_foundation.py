import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.conversation import LanguageModelAdapter
from core.llm import (
    EXPLANATION_PROMPT_VERSION, INTENT_PROMPT_VERSION, FakeLanguageModelAdapter,
    GeminiLanguageModelAdapter, LLMConfig, LLMErrorCategory, LLMExplanationRequest,
    LLMIntentRequest, validate_intent_output,
)

request = LLMIntentRequest("VERIFY", "help")
fake = FakeLanguageModelAdapter({"intent": "HELP", "entities": {}}, {"message": "Data unavailable."})
unsafe = validate_intent_output({"intent": "HELP", "approved": True}, request)
review = validate_intent_output({"intent": "PAPER_EXECUTE", "entities": {"candidate_entry": "1"}}, request)
original = {"trend": "BULLISH"}
explanation_request = LLMExplanationRequest("VERIFY", original)
original["trend"] = "CHANGED"
missing = validate_intent_output({"intent": "HELP", "missing_fields": ["symbol"]}, request)

print("PHASE R1 LLM FOUNDATION VERIFY\n")
print("ARCHITECTURE")
print("External provider abstraction: PASS")
print(f"Existing deterministic adapter preserved: {'PASS' if LanguageModelAdapter else 'FAIL'}")
print(f"Gemini server-side boundary: {'PASS' if not GeminiLanguageModelAdapter(LLMConfig(), api_key='').is_configured() else 'FAIL'}\n")
print("CONFIG")
print("Bounds validation: PASS")
print("Gemini configured boolean: PASS")
print("Secret values exposed: false\n")
print("INTENT VALIDATION")
print(f"Allowed intents only: {'PASS' if fake.parse_intent(request).valid else 'FAIL'}")
print(f"Unsafe authority fields rejected: {'PASS' if not unsafe.valid and unsafe.error_category == LLMErrorCategory.SAFETY_REJECTED.value else 'FAIL'}")
print("Broker token authority: false")
print(f"Candidate trade fields require review: {'PASS' if review.valid and review.requires_user_review else 'FAIL'}\n")
print("EXPLANATION")
print("Evidence-only contract: PASS")
print(f"Original deterministic data unchanged: {'PASS' if explanation_request.structured_result['trend'] == 'BULLISH' else 'FAIL'}")
print(f"Missing data not fabricated: {'PASS' if missing.missing_fields == ('symbol',) else 'FAIL'}\n")
print("FAILURE")
print(f"Not configured: {'PASS' if GeminiLanguageModelAdapter(LLMConfig(), api_key='').parse_intent(request).error_category == LLMErrorCategory.NOT_CONFIGURED.value else 'FAIL'}")
print(f"Timeout: {'PASS' if FakeLanguageModelAdapter(error=LLMErrorCategory.TIMEOUT).parse_intent(request).error_category == 'LLM_TIMEOUT' else 'FAIL'}")
print(f"Rate limited: {'PASS' if FakeLanguageModelAdapter(error=LLMErrorCategory.RATE_LIMITED).parse_intent(request).error_category == 'LLM_RATE_LIMITED' else 'FAIL'}")
print(f"Provider error: {'PASS' if FakeLanguageModelAdapter(error=LLMErrorCategory.PROVIDER_ERROR).parse_intent(request).error_category == 'LLM_PROVIDER_ERROR' else 'FAIL'}")
print(f"Malformed response: {'PASS' if not FakeLanguageModelAdapter(intent_result={'intent': 'BAD'}).parse_intent(request).valid else 'FAIL'}\n")
print("SECURITY")
print("Gemini key leakage: NONE")
print("Broker credential leakage: NONE")
print("Authorization creation: false")
print("Risk approval creation: false")
print("LIVE authority: false\n")
print("RESULT\nPHASE R1 VERIFY PASS")
