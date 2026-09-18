from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import re

from core.orchestrator import JarvisRequest
from core.llm import LLMConfig, LLMErrorCategory, LLMExplanationRequest, LLMIntentRequest
from core.memory import MemoryCategory, MemoryScope, MemorySource, MemoryValidationError

@dataclass(frozen=True)
class ConversationRequest:
    conversation_id:str;request_id:str;timestamp:datetime;text:str;language:str="en";context:dict|None=None;source:str="USER";explicit_user_authorization:bool=False
@dataclass(frozen=True)
class ConversationResponse:
    request_id:str;intent:str;status:str;message:str;structured_result:object|None;warnings:tuple;follow_up_required:bool;execution_mode:str;sources:tuple;is_fresh:bool|None;missing_fields:tuple=();ai_usage:object|None=None
@dataclass(frozen=True)
class AIUsageMetadata:
    used:bool=False;provider:str|None=None;operation:str|None=None;fallback:bool=False;prompt_version:str|None=None;error_category:str|None=None
class ConversationAIMode(str,Enum):
    AUTO="AUTO";DETERMINISTIC_ONLY="DETERMINISTIC_ONLY";LLM_ENHANCED="LLM_ENHANCED"
class LanguageModelAdapter:
    def interpret(self,request):raise NotImplementedError
class DeterministicIntentAdapter(LanguageModelAdapter):
    def interpret(self,request):
        text=request.text.lower().strip(); symbol=self._symbol(request.text)
        if any(word in text for word in ("buy","sell","live","order","కొను","అమ్మ")):return "UNSUPPORTED_LIVE_ACTION",symbol
        if any(word in text for word in ("paper","risk","trade risk")):return "PAPER_EXECUTE" if "paper" in text else "RISK_VALIDATE",symbol
        if any(word in text for word in ("portfolio","పోర్ట్‌ఫోలియో","portfolio చూప")):return "PORTFOLIO_ANALYSIS",symbol
        if any(word in text for word in ("automation","ఆటోమేషన్")):return "AUTOMATION_STATUS",symbol
        if any(word in text for word in ("backtest","బ్యాక్‌టెస్ట్")):return "BACKTEST",symbol
        if any(word in text for word in ("health","status","స్థితి","ఏంటి")):return "SYSTEM_STATUS",symbol
        if "f&o" in text or "fno" in text:return "FNO_ANALYSIS",symbol
        if "market context" in text:return "MARKET_CONTEXT",symbol
        if "underlying" in text:return "UNDERLYING_ANALYSIS",symbol
        if any(word in text for word in ("full analysis","analyse","analyze","analysis","చెయ్యి","విశ్లేషణ")):return "FULL_ANALYSIS",symbol
        return "HELP",symbol
    @staticmethod
    def _symbol(text):
        match=re.search(r"\b([A-Z][A-Z0-9]{1,14})\b",text)
        return match.group(1) if match and match.group(1) not in {"FULL","ANALYSIS","SHOW","PAPER","LIVE"} else None
class JarvisConversationService:
    def __init__(self,orchestrator,adapter=None,observability=None,external_llm=None,llm_config=None,ai_mode=ConversationAIMode.AUTO):
        self.orchestrator=orchestrator;self.adapter=adapter or DeterministicIntentAdapter();self.observability=observability;self.external_llm=external_llm;self.llm_config=llm_config or LLMConfig();self.ai_mode=ConversationAIMode(ai_mode);self.memory_service=None
        self.tool_service=None
    def handle(self,request):
        if not isinstance(request,ConversationRequest) or not request.text.strip():return ConversationResponse(getattr(request,"request_id",""),"HELP","INVALID_REQUEST","A non-empty conversation request is required.",None,(),True,"ANALYSIS_ONLY",(),None)
        memory_response = self._memory_command(request)
        if memory_response is not None: return memory_response
        github_plan = self._github_write_candidate(request)
        if github_plan is not None: return github_plan
        intent,symbol=self.adapter.interpret(request)
        if intent=="UNSUPPORTED_LIVE_ACTION":return ConversationResponse(request.request_id,intent,"LIVE_EXECUTION_UNSUPPORTED","Live execution is unsupported. Paper execution requires an explicit proposal and authorization.",None,(),False,"ANALYSIS_ONLY",(),None)
        usage=AIUsageMetadata()
        if self._needs_llm(request,intent) and self.external_llm and self.ai_mode != ConversationAIMode.DETERMINISTIC_ONLY and self.llm_config.enabled and self.llm_config.intent_llm_enabled and self.external_llm.is_configured():
            safe_context={"deterministic_intent":intent,"symbol":symbol}
            if self.memory_service:
                try: safe_context["memory"] = self.memory_service.safe_context(request.text, intent, {"symbol": symbol})
                except Exception: safe_context["memory"] = {"memories": []}
            llm_request=LLMIntentRequest(request.request_id,request.text,language_hint=request.language,safe_context=safe_context)
            self._metric("llm_requests_total");self._metric("llm_intent_requests_total")
            llm_result=self.external_llm.parse_intent(llm_request)
            if llm_result.valid:
                intent=llm_result.intent;symbol=symbol or llm_result.entities.get("symbol");usage=AIUsageMetadata(True,llm_result.provider,"INTENT",False,llm_result.prompt_version)
            else:
                self._metric("llm_failures_total");self._metric("llm_fallbacks_total")
                usage=AIUsageMetadata(True,llm_result.provider,"INTENT",True,llm_result.prompt_version,llm_result.error_category)
        if intent=="SYSTEM_STATUS":return ConversationResponse(request.request_id,intent,"COMPLETED","J.A.R.V.I.S is online.",None,(),False,"ANALYSIS_ONLY",(),None)
        if intent in {"HELP","BACKTEST","PORTFOLIO_ANALYSIS","AUTOMATION_STATUS","RISK_VALIDATE","PAPER_EXECUTE","FNO_ANALYSIS"}:
            return ConversationResponse(request.request_id,intent,"FOLLOW_UP_REQUIRED","This workflow requires explicit structured input.",None,("No market data or proposal was inferred from conversation.",),True,"ANALYSIS_ONLY",(),None,("structured_input",),usage)
        if symbol is None:return ConversationResponse(request.request_id,intent,"FOLLOW_UP_REQUIRED","Please provide an instrument symbol.",None,("Instrument is required.",),True,"ANALYSIS_ONLY",(),None,("instrument",),usage)
        result=self.orchestrator.handle(JarvisRequest(request.request_id,intent,request.timestamp,symbol,"NSE",None,"15m","CONVERSATION","ANALYSIS_ONLY",source=request.source))
        message=self._compose(result)
        if self.ai_mode == ConversationAIMode.LLM_ENHANCED and self.external_llm and self.llm_config.enabled and self.llm_config.explanation_llm_enabled and self.external_llm.is_configured():
            self._metric("llm_requests_total");self._metric("llm_explanation_requests_total")
            explanation=self.external_llm.compose_explanation(LLMExplanationRequest(request.request_id,asdict(result),language_hint=request.language))
            if explanation.valid: message=explanation.message;usage=AIUsageMetadata(True,explanation.provider,"EXPLANATION",False,explanation.prompt_version)
            else: self._metric("llm_failures_total");self._metric("llm_fallbacks_total")
        if self.observability:self.observability.record("CONVERSATION","INTENT",result.status,request_id=request.request_id,instrument=symbol,message=intent)
        return ConversationResponse(request.request_id,intent,result.status,message,result,tuple(result.warnings),False,result.execution_mode,result.data_sources,result.is_fresh,ai_usage=usage)
    def _needs_llm(self,request,intent):
        if intent != "HELP": return False
        return request.text.lower().strip() not in {"help","hi","hello","what can you do"}
    def _memory_command(self, request):
        if not self.memory_service: return None
        text = request.text.strip()
        lowered = text.lower()
        if "what do you remember" in lowered or "remember my preferences" in lowered:
            records = self.memory_service.list(scope=MemoryScope.DURABLE)
            message = "; ".join(f"{item.key}={item.value}" for item in records if item.status.value == "ACTIVE") or "I do not have any durable preferences yet."
            return ConversationResponse(request.request_id,"MEMORY_RECALL","COMPLETED",message,None,(),False,"ANALYSIS_ONLY",(),None)
        if lowered.startswith("remember that ") or lowered.startswith("remember my ") or lowered.startswith("change my "):
            body = text.split(" ", 2)[-1] if lowered.startswith("remember") else text[10:]
            match = re.match(r"(?:my )?(.+?)\s+(?:is|to|=)\s+(.+)$", body, re.IGNORECASE)
            if not match:
                preferred = re.match(r"(?:I )?prefer\s+(.+)$", body, re.IGNORECASE)
                if preferred: match = ("preferred_language", preferred.group(1))
            if not match: return ConversationResponse(request.request_id,"MEMORY_SET","FOLLOW_UP_REQUIRED","Please provide a memory as key and value.",None,("Memory value is required.",),True,"ANALYSIS_ONLY",(),None,("memory_value",))
            raw_key, value = match.groups() if hasattr(match, "groups") else match; key = self._memory_key(raw_key)
            try: record = self.memory_service.create(MemoryCategory.PREFERENCE, key, value, scope=MemoryScope.DURABLE, source=MemorySource.EXPLICIT_USER)
            except MemoryValidationError as error: return ConversationResponse(request.request_id,"MEMORY_SET","INVALID_REQUEST",str(error),None,("Memory was not stored.",),False,"ANALYSIS_ONLY",(),None)
            return ConversationResponse(request.request_id,"MEMORY_SET","COMPLETED",f"I will remember your {record.key} preference.",None,(),False,"ANALYSIS_ONLY",(),None)
        if lowered.startswith("forget ") or lowered.startswith("forget my "):
            key = self._memory_key(text.split(" ", 1)[1])
            records = self.memory_service.search(key)
            forgotten = any(self.memory_service.forget(item.memory_id) for item in records)
            return ConversationResponse(request.request_id,"MEMORY_FORGET","COMPLETED",("I forgot that memory." if forgotten else "I could not find that memory."),None,(),False,"ANALYSIS_ONLY",(),None)
        return None
    def _github_write_candidate(self, request):
        if not self.tool_service: return None
        text = request.text.strip()
        match = re.match(r"create an issue in ([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+) titled (.+)$", text, re.IGNORECASE)
        if not match: return None
        owner, repo, title = match.groups()
        try: plan = self.tool_service.plan("github.issue.create", {"owner": owner, "repo": repo, "title": title}, "CONVERSATION", request.request_id)
        except Exception: return ConversationResponse(request.request_id, "GITHUB_WRITE", "FOLLOW_UP_REQUIRED", "GitHub write actions are disabled or unavailable.", None, ("Explicit approval is required.",), True, "ANALYSIS_ONLY", (), None)
        return ConversationResponse(request.request_id, "GITHUB_WRITE_PLAN", "CONFIRMATION_REQUIRED", f"Planned GitHub issue creation for {owner}/{repo}: {title}. Explicit approval and execution are required.", plan, ("No GitHub write has been performed.",), True, "ANALYSIS_ONLY", (), None)
    @staticmethod
    def _memory_key(raw):
        key = re.sub(r"\s+", "_", raw.lower().strip())
        return {"prefer_telugu":"preferred_language", "preferred_language":"preferred_language", "default_analysis_interval":"default_analysis_interval", "analysis_interval":"default_analysis_interval"}.get(key, key)
    def _metric(self,name):
        if self.observability:self.observability.counters[name]=self.observability.counters.get(name,0)+1
    @staticmethod
    def _compose(result):
        if result.underlying_analysis:return f"Facts: underlying trend is {result.underlying_analysis.trend}; freshness is {result.is_fresh}."
        return "No deterministic analysis result is available."