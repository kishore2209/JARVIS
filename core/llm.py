"""Offline-safe external language-model foundation for JARVIS.

This module intentionally has no conversation, orchestration, risk, or broker
integration. Provider output remains untrusted data until validated here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
import time
from time import perf_counter
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

from core.llm_prompts import (
    EXPLANATION_PROMPT_VERSION,
    EXPLANATION_SYSTEM_PROMPT_V1,
    INTENT_PROMPT_VERSION,
    INTENT_SYSTEM_PROMPT_V1,
)

MAX_SAFE_RETRIES = 2
MAX_SAFE_OUTPUT_TOKENS = 4_096
MAX_SAFE_TEXT_CHARS = 10_000
MAX_SAFE_CONTEXT_CHARS = 10_000
MAX_SAFE_RESULT_CHARS = 30_000
ALLOWED_INTENTS = frozenset({
    "HELP", "SYSTEM_STATUS", "FULL_ANALYSIS", "MARKET_CONTEXT", "UNDERLYING_ANALYSIS",
    "FNO_ANALYSIS", "PORTFOLIO_ANALYSIS", "BACKTEST", "AUTOMATION_STATUS",
    "RISK_VALIDATE", "PAPER_EXECUTE", "UNSUPPORTED_LIVE_ACTION",
})
UNSAFE_FIELDS = frozenset({
    "authorized", "authorization", "explicit_user_authorization", "risk_approved",
    "risk_decision", "approved", "execute", "execution_authorized", "place_order", "live_execute",
    "broker_token", "access_token", "api_key", "token", "instrument_token",
})
TRADE_FIELDS = frozenset({"entry", "stop", "target", "quantity", "risk_percent", "proposed_entry", "proposed_stop", "proposed_target", "candidate_entry", "candidate_stop", "candidate_target"})
INTENT_OUTPUT_FIELDS = frozenset({"intent", "entities", "missing_fields", "follow_up_required", "warnings", "reason"})


class LLMProvider(str, Enum):
    NONE = "NONE"
    GEMINI = "GEMINI"


class LLMOperation(str, Enum):
    INTENT = "INTENT"
    EXPLANATION = "EXPLANATION"


class LLMErrorCategory(str, Enum):
    NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    DISABLED = "LLM_DISABLED"
    TIMEOUT = "LLM_TIMEOUT"
    RATE_LIMITED = "LLM_RATE_LIMITED"
    PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    SAFETY_REJECTED = "LLM_SAFETY_REJECTED"
    CONFIGURATION_ERROR = "LLM_CONFIGURATION_ERROR"


class LLMConfigurationError(ValueError):
    pass


class LLMValidationError(ValueError):
    pass


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return _freeze(dict(value or {}))


def _text_size(value: Any) -> int:
    return len(value) if isinstance(value, str) else len(json.dumps(value, sort_keys=True, default=str))


@dataclass(frozen=True)
class LLMConfig:
    provider: LLMProvider = LLMProvider.GEMINI
    enabled: bool = False
    model_name: str = "gemini-2.5-flash"
    timeout_seconds: float = 10.0
    max_output_tokens: int = 512
    max_retries: int = 1
    intent_llm_enabled: bool = False
    explanation_llm_enabled: bool = False
    intent_temperature: float = 0.0
    explanation_temperature: float = 0.2
    max_user_text_chars: int = 4_000
    max_result_chars: int = 30_000
    max_context_chars: int = 10_000

    def __post_init__(self) -> None:
        if not isinstance(self.provider, LLMProvider):
            try: object.__setattr__(self, "provider", LLMProvider(self.provider))
            except ValueError as error: raise LLMConfigurationError("unsupported provider") from error
        if not self.model_name or self.timeout_seconds <= 0 or self.max_output_tokens <= 0 or self.max_output_tokens > MAX_SAFE_OUTPUT_TOKENS:
            raise LLMConfigurationError("model, timeout, and output token limits must be positive")
        if self.max_retries < 0 or self.max_retries > MAX_SAFE_RETRIES:
            raise LLMConfigurationError("max_retries is outside the safe bound")
        if not 0 <= self.intent_temperature <= 1 or not 0 <= self.explanation_temperature <= 1:
            raise LLMConfigurationError("temperature must be between 0 and 1")
        if any(limit <= 0 for limit in (self.max_user_text_chars, self.max_result_chars, self.max_context_chars)):
            raise LLMConfigurationError("text limits must be positive")
        if self.max_user_text_chars > MAX_SAFE_TEXT_CHARS or self.max_context_chars > MAX_SAFE_CONTEXT_CHARS or self.max_result_chars > MAX_SAFE_RESULT_CHARS:
            raise LLMConfigurationError("text limits exceed the safe bound")

    @classmethod
    def from_environment(cls) -> "LLMConfig":
        provider = os.getenv("LLM_PROVIDER", "GEMINI")
        try:
            return cls(provider=LLMProvider(provider), model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), enabled=os.getenv("JARVIS_LLM_ENABLED", os.getenv("LLM_ENABLED", "false")).lower() == "true")
        except ValueError as error:
            raise LLMConfigurationError("unsupported provider") from error


def configuration_status(config: LLMConfig | None = None) -> dict[str, Any]:
    config = config or LLMConfig()
    return {"provider": config.provider.value, "enabled": config.enabled, "configured": bool(os.getenv("GEMINI_API_KEY")) if config.provider is LLMProvider.GEMINI else False}


@dataclass(frozen=True)
class LLMIntentRequest:
    request_id: str
    text: str
    allowed_intents: frozenset[str] = ALLOWED_INTENTS
    language_hint: str = "auto"
    safe_context: Mapping[str, Any] = field(default_factory=dict)
    prompt_version: str = INTENT_PROMPT_VERSION

    def __post_init__(self) -> None:
        if not self.text.strip(): raise LLMValidationError("text is required")
        if _text_size(self.text) > MAX_SAFE_TEXT_CHARS: raise LLMValidationError("user text exceeds safe limit")
        if _text_size(self.safe_context) > MAX_SAFE_CONTEXT_CHARS: raise LLMValidationError("context exceeds safe limit")
        if not set(self.allowed_intents).issubset(ALLOWED_INTENTS): raise LLMValidationError("allowed intents contain unsupported values")
        object.__setattr__(self, "safe_context", _mapping(self.safe_context))
        object.__setattr__(self, "allowed_intents", frozenset(self.allowed_intents))


@dataclass(frozen=True)
class LLMExplanationRequest:
    request_id: str
    structured_result: Mapping[str, Any]
    language_hint: str = "auto"
    style_hint: str = "concise"
    prompt_version: str = EXPLANATION_PROMPT_VERSION

    def __post_init__(self) -> None:
        copied = json.loads(json.dumps(dict(self.structured_result), default=str))
        if _text_size(copied) > MAX_SAFE_RESULT_CHARS: raise LLMValidationError("result exceeds safe limit")
        object.__setattr__(self, "structured_result", _mapping(copied))


@dataclass(frozen=True)
class LLMIntentResult:
    provider: str = LLMProvider.NONE.value
    model: str = ""
    prompt_version: str = INTENT_PROMPT_VERSION
    valid: bool = False
    intent: str = ""
    entities: Mapping[str, Any] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    follow_up_required: bool = False
    requires_user_review: bool = False
    warnings: tuple[str, ...] = ()
    error_category: str | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entities", _mapping(self.entities))
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class LLMExplanationResult:
    provider: str = LLMProvider.NONE.value
    model: str = ""
    prompt_version: str = EXPLANATION_PROMPT_VERSION
    valid: bool = False
    message: str = ""
    warnings: tuple[str, ...] = ()
    error_category: str | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))


class ExternalLanguageModelAdapter(Protocol):
    def is_configured(self) -> bool: ...
    def parse_intent(self, request: LLMIntentRequest) -> LLMIntentResult: ...
    def compose_explanation(self, request: LLMExplanationRequest) -> LLMExplanationResult: ...


def _failure(category: LLMErrorCategory, provider: str = LLMProvider.NONE.value, model: str = "", operation: str = "intent") -> LLMIntentResult | LLMExplanationResult:
    result_type = LLMIntentResult if operation == "intent" else LLMExplanationResult
    return result_type(provider=provider, model=model, valid=False, error_category=category.value)


def validate_intent_output(raw: Any, request: LLMIntentRequest, provider: str = LLMProvider.NONE.value, model: str = "") -> LLMIntentResult:
    if not isinstance(raw, Mapping): return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    if set(raw) & UNSAFE_FIELDS: return _failure(LLMErrorCategory.SAFETY_REJECTED, provider, model)
    if set(raw) - INTENT_OUTPUT_FIELDS: return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    intent = raw.get("intent")
    if not isinstance(intent, str) or intent not in request.allowed_intents: return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    entities = raw.get("entities", {})
    if not isinstance(entities, Mapping): return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    if any(not isinstance(key, str) for key in entities): return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    if any(key in entities for key in UNSAFE_FIELDS): return _failure(LLMErrorCategory.SAFETY_REJECTED, provider, model)
    allowed_entities = {"symbol", "exchange", "interval", "candidate_entry", "candidate_stop", "candidate_target"}
    if set(entities) - allowed_entities: return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    safe_entities = dict(entities)
    trade_fields = TRADE_FIELDS & set(safe_entities)
    if "missing_fields" in raw and (not isinstance(raw["missing_fields"], (list, tuple)) or not all(isinstance(item, str) for item in raw["missing_fields"])): return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    if "follow_up_required" in raw and not isinstance(raw["follow_up_required"], bool): return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    if "warnings" in raw and (not isinstance(raw["warnings"], (list, tuple)) or not all(isinstance(item, str) for item in raw["warnings"])): return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model)
    warnings = tuple(raw.get("warnings", ()))
    if trade_fields: warnings += ("Candidate trading fields require explicit user review.",)
    missing = tuple(raw.get("missing_fields", ()))
    follow_up = bool(raw.get("follow_up_required", False)) or bool(missing)
    return LLMIntentResult(provider, model, request.prompt_version, True, intent, safe_entities, missing, follow_up, bool(trade_fields), warnings)


def validate_explanation_output(raw: Any, provider: str, model: str) -> LLMExplanationResult:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("message"), str) or not raw["message"].strip():
        return _failure(LLMErrorCategory.INVALID_RESPONSE, provider, model, "explanation")
    return LLMExplanationResult(provider, model, EXPLANATION_PROMPT_VERSION, True, raw["message"].strip(), tuple(str(item) for item in raw.get("warnings", ()) if isinstance(item, str)))


class FakeLanguageModelAdapter:
    def __init__(self, intent_result: Any = None, explanation_result: Any = None, error: LLMErrorCategory | None = None):
        self.intent_result = intent_result
        self.explanation_result = explanation_result
        self.error = error
        self.intent_calls = 0
        self.explanation_calls = 0

    def is_configured(self) -> bool: return self.error not in {LLMErrorCategory.NOT_CONFIGURED, LLMErrorCategory.DISABLED}
    def parse_intent(self, request: LLMIntentRequest) -> LLMIntentResult:
        self.intent_calls += 1
        if self.error: return _failure(self.error, "FAKE", "fake", "intent")
        raw = self.intent_result if self.intent_result is not None else {"intent": "HELP", "entities": {}}
        return validate_intent_output(raw, request, "FAKE", "fake")
    def compose_explanation(self, request: LLMExplanationRequest) -> LLMExplanationResult:
        self.explanation_calls += 1
        if self.error: return _failure(self.error, "FAKE", "fake", "explanation")
        raw = self.explanation_result if self.explanation_result is not None else {"message": "Data unavailable."}
        return validate_explanation_output(raw, "FAKE", "fake")


class GeminiLanguageModelAdapter:
    def __init__(self, config: LLMConfig | None = None, api_key: str | None = None, client_factory: Callable[..., Any] | None = None, sleeper: Callable[[float], None] | None = None, observability: Any | None = None):
        self.config = config or LLMConfig()
        self._api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        self._client_factory = client_factory
        self._sleeper = sleeper or (lambda seconds: None)
        self._client = None
        self.observability = observability

    def __repr__(self):
        return f"GeminiLanguageModelAdapter(provider='GEMINI', model={self.config.model_name!r}, configured={self.is_configured()}, enabled={self.config.enabled})"

    def is_configured(self) -> bool: return self.config.provider is LLMProvider.GEMINI and bool(self._api_key)
    def parse_intent(self, request: LLMIntentRequest) -> LLMIntentResult:
        if not self.is_configured(): return _failure(LLMErrorCategory.NOT_CONFIGURED, "GEMINI", self.config.model_name)
        if not self.config.enabled: return _failure(LLMErrorCategory.DISABLED, "GEMINI", self.config.model_name)
        raw, error, latency, retries = self._generate(INTENT_SYSTEM_PROMPT_V1, {"text": request.text, "allowed_intents": sorted(request.allowed_intents), "language_hint": request.language_hint, "safe_context": dict(request.safe_context), "prompt_version": request.prompt_version})
        if error: return _failure(error, "GEMINI", self.config.model_name)
        if raw is None: return _failure(LLMErrorCategory.INVALID_RESPONSE, "GEMINI", self.config.model_name)
        result = validate_intent_output(raw, request, "GEMINI", self.config.model_name)
        return result if result.valid else LLMIntentResult(provider="GEMINI", model=self.config.model_name, prompt_version=request.prompt_version, error_category=result.error_category, latency_ms=latency)
    def compose_explanation(self, request: LLMExplanationRequest) -> LLMExplanationResult:
        if not self.is_configured(): return _failure(LLMErrorCategory.NOT_CONFIGURED, "GEMINI", self.config.model_name, "explanation")
        if not self.config.enabled: return _failure(LLMErrorCategory.DISABLED, "GEMINI", self.config.model_name, "explanation")
        raw, error, latency, retries = self._generate(EXPLANATION_SYSTEM_PROMPT_V1, dict(request.structured_result))
        if error: return _failure(error, "GEMINI", self.config.model_name, "explanation")
        result = validate_explanation_output(raw, "GEMINI", self.config.model_name)
        return LLMExplanationResult(provider="GEMINI", model=self.config.model_name, prompt_version=request.prompt_version, valid=result.valid, message=result.message, warnings=result.warnings, error_category=result.error_category, latency_ms=latency)

    def _client_or_error(self):
        if self._client is not None: return self._client
        try:
            factory = self._client_factory or self._default_client_factory
            self._client = factory(self._api_key)
            return self._client
        except Exception:
            return None

    @staticmethod
    def _default_client_factory(api_key):
        from google import genai
        return genai.Client(api_key=api_key)

    def _generate(self, system_prompt: str, payload: Mapping[str, Any]):
        started = perf_counter(); attempts = 0; last_error = None
        for attempt in range(self.config.max_retries + 1):
            attempts = attempt
            client = self._client_or_error()
            if client is None: return None, LLMErrorCategory.PROVIDER_ERROR, int((perf_counter() - started) * 1000), attempts
            try:
                contents = system_prompt + "\nINPUT_JSON:\n" + json.dumps(payload, sort_keys=True, default=str)
                response = self._call_client(client, contents)
                text = response if isinstance(response, str) else getattr(response, "text", response)
                if isinstance(text, Mapping): raw = dict(text)
                elif isinstance(text, str) and len(text) <= self.config.max_result_chars:
                    raw = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
                else: return None, LLMErrorCategory.INVALID_RESPONSE, int((perf_counter() - started) * 1000), attempts
                return raw, None, int((perf_counter() - started) * 1000), attempts
            except Exception as error:
                if isinstance(error, json.JSONDecodeError):
                    return None, LLMErrorCategory.INVALID_RESPONSE, int((perf_counter() - started) * 1000), attempts
                last_error = self._map_provider_error(error)
                if last_error not in {LLMErrorCategory.PROVIDER_ERROR, LLMErrorCategory.TIMEOUT, LLMErrorCategory.RATE_LIMITED} or attempt >= self.config.max_retries:
                    return None, last_error, int((perf_counter() - started) * 1000), attempts
                self._sleeper(min(0.25 * (attempt + 1), 0.5))
        return None, last_error or LLMErrorCategory.PROVIDER_ERROR, int((perf_counter() - started) * 1000), attempts

    def _call_client(self, client, contents):
        models = getattr(client, "models", None)
        if models is not None and hasattr(models, "generate_content"):
            try: return models.generate_content(model=self.config.model_name, contents=contents, config={"temperature": self.config.intent_temperature, "max_output_tokens": self.config.max_output_tokens})
            except TypeError: return models.generate_content(model=self.config.model_name, contents=contents)
        if hasattr(client, "generate_content"): return client.generate_content(contents)
        raise RuntimeError("Gemini client does not support content generation")

    @staticmethod
    def _map_provider_error(error):
        name = type(error).__name__.lower(); message = str(error).lower()
        if "timeout" in name or "timeout" in message: return LLMErrorCategory.TIMEOUT
        if "rate" in name or "429" in message or "resourceexhausted" in name: return LLMErrorCategory.RATE_LIMITED
        return LLMErrorCategory.PROVIDER_ERROR


def build_external_llm_from_env(observability: Any | None = None, config: LLMConfig | None = None):
    config = config or LLMConfig.from_environment()
    if not config.enabled or config.provider is not LLMProvider.GEMINI: return None
    return GeminiLanguageModelAdapter(config=config, observability=observability)


def safe_llm_metadata(provider: str, model: str, operation: LLMOperation, status: str, prompt_version: str, input_length: int, output_length: int = 0, latency_ms: int | None = None, retry_count: int = 0) -> dict[str, Any]:
    return {"provider": provider, "model": model, "operation": operation.value, "status": status, "prompt_version": prompt_version, "input_length": input_length, "output_length": output_length, "latency_ms": latency_ms, "retry_count": retry_count}


__all__ = ["ALLOWED_INTENTS", "EXPLANATION_SYSTEM_PROMPT_V1", "EXPLANATION_PROMPT_VERSION", "ExternalLanguageModelAdapter", "FakeLanguageModelAdapter", "GeminiLanguageModelAdapter", "INTENT_SYSTEM_PROMPT_V1", "INTENT_PROMPT_VERSION", "LLMConfig", "LLMConfigurationError", "LLMErrorCategory", "LLMExplanationRequest", "LLMExplanationResult", "LLMIntentRequest", "LLMIntentResult", "LLMOperation", "LLMProvider", "LLMValidationError", "build_external_llm_from_env", "configuration_status", "safe_llm_metadata", "validate_explanation_output", "validate_intent_output"]
