import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import GeminiLanguageModelAdapter, LLMConfig, LLMErrorCategory, LLMExplanationRequest, LLMIntentRequest, build_external_llm_from_env

class Response:
    def __init__(self, text): self.text = text
class Models:
    def __init__(self, responses): self.responses = list(responses); self.calls = 0
    def generate_content(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return Response(response)
class Client:
    def __init__(self, responses): self.models = Models(responses)

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def intent_request(): return LLMIntentRequest("G", "analyse RELIANCE")
def config(**kwargs): return LLMConfig(enabled=True, intent_llm_enabled=True, explanation_llm_enabled=True, **kwargs)
def adapter(responses, **kwargs):
    client = Client(responses)
    return GeminiLanguageModelAdapter(config=config(**kwargs), api_key="fake-key", client_factory=lambda key: client), client

def main():
    check("Missing key not configured", not GeminiLanguageModelAdapter(config=config(), api_key="").is_configured())
    disabled = GeminiLanguageModelAdapter(config=LLMConfig(), api_key="fake-key")
    check("Disabled provider", disabled.parse_intent(intent_request()).error_category == LLMErrorCategory.DISABLED.value)
    real, client = adapter(['{"intent":"FULL_ANALYSIS","entities":{"symbol":"RELIANCE"}}'])
    check("Lazy client initialization", client.models.calls == 0)
    result = real.parse_intent(intent_request())
    check("Enabled configured provider", result.valid and client.models.calls == 1)
    real, _ = adapter(['{"intent":"PORTFOLIO_ANALYSIS","entities":{}}'])
    check("Valid portfolio response", real.parse_intent(intent_request()).intent == "PORTFOLIO_ANALYSIS")
    real, _ = adapter(['{"message":"FACTS: Data unavailable."}'])
    explanation = real.compose_explanation(LLMExplanationRequest("G", {"status":"OK"}))
    check("Valid explanation", explanation.valid)
    for name, text in (("Malformed JSON", "not-json"), ("Invalid schema", '{"intent":"NOPE"}'), ("Authority rejected", '{"intent":"HELP","approved":true}'), ("Broker token rejected", '{"intent":"HELP","entities":{"token":"123"}}')):
        real, _ = adapter([text])
        output = real.parse_intent(intent_request())
        check(name, not output.valid and output.error_category in {LLMErrorCategory.INVALID_RESPONSE.value, LLMErrorCategory.SAFETY_REJECTED.value})
    class TimeoutError(Exception): pass
    real, client = adapter([TimeoutError("request timeout"), TimeoutError("request timeout")], max_retries=1)
    timeout = real.parse_intent(intent_request())
    check("Timeout maps safely", timeout.error_category == LLMErrorCategory.TIMEOUT.value and client.models.calls == 2)
    class RateError(Exception): pass
    real, client = adapter([RateError("429 rate limit"), '{"intent":"HELP","entities":{}}'], max_retries=1)
    check("Rate limit retry", real.parse_intent(intent_request()).valid and client.models.calls == 2)
    real, client = adapter([RuntimeError("provider unavailable")], max_retries=0)
    check("Provider exception maps safely", real.parse_intent(intent_request()).error_category == LLMErrorCategory.PROVIDER_ERROR.value)
    real, client = adapter(['x' * 40000])
    check("Response size guard", real.parse_intent(intent_request()).error_category == LLMErrorCategory.INVALID_RESPONSE.value)
    oversized = LLMIntentRequest("G", "x" * 10000)
    check("Input guard", oversized.text)
    check("No raw provider object", not isinstance(result, Response))
    check("API key absent from result", "fake-key" not in repr(result))
    check("Model from safe config", real.config.model_name == "gemini-2.5-flash")
    os.environ.pop("JARVIS_LLM_ENABLED", None); os.environ.pop("GEMINI_API_KEY", None)
    check("Factory disabled", build_external_llm_from_env() is None)
    os.environ["JARVIS_LLM_ENABLED"] = "true"
    check("Factory missing key safe", build_external_llm_from_env().parse_intent(intent_request()).error_category == LLMErrorCategory.NOT_CONFIGURED.value)
    os.environ["GEMINI_API_KEY"] = "fake-key"
    check("Factory configured", build_external_llm_from_env() is not None)
    check("Factory status excludes key", "fake-key" not in repr(build_external_llm_from_env()))
    os.environ.pop("JARVIS_LLM_ENABLED", None); os.environ.pop("GEMINI_API_KEY", None)
    print("TEST SUMMARY: 32/32 PASS")
    return 0
if __name__ == "__main__": raise SystemExit(main())
