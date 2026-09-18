"""Validated runtime configuration and side-effect-safe application composition."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Iterable

from core.automation import AutomationController
from core.conversation import JarvisConversationService
from core.interface_service import JarvisInterfaceService
from core.llm import LLMConfig, build_external_llm_from_env
from core.memory import JarvisMemoryService, MemoryRepository
from core.tools import ToolService, build_tool_service
from core.workflows import WorkflowService
from core.connectors import build_connector_service
from core.connector_governance import ConnectorGovernanceService
from core.project_intelligence import ProjectIntelligenceService
from core.project_delivery import ProjectDeliveryService
from core.observability import Observability
from core.orchestrator import JarvisOrchestrator
from market.paper_trading import PaperAccount, PaperTradingEngine
from market.persistence import SQLiteStore
from market.providers.mock import MockMarketDataProvider

JARVIS_VERSION = "0.1.0"
_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class RuntimeConfigurationError(ValueError):
    pass


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    if raw.lower() not in {"true", "false"}:
        raise RuntimeConfigurationError(f"{name} must be true or false")
    return raw.lower() == "true"


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "data/jarvis.db"
    db_enabled: bool = False
    timezone_name: str = "Asia/Kolkata"
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    llm: LLMConfig = LLMConfig()

    def __post_init__(self) -> None:
        if not self.host or any(char.isspace() for char in self.host):
            raise RuntimeConfigurationError("JARVIS_HOST must be a non-empty host")
        if not 1 <= self.port <= 65535:
            raise RuntimeConfigurationError("JARVIS_PORT must be between 1 and 65535")
        if self.timezone_name != "Asia/Kolkata":
            raise RuntimeConfigurationError("JARVIS_TIMEZONE must be Asia/Kolkata")
        if self.log_level not in _ALLOWED_LOG_LEVELS:
            raise RuntimeConfigurationError("JARVIS_LOG_LEVEL is unsupported")
        if not self.db_path.strip() or Path(self.db_path).name in {".", ""}:
            raise RuntimeConfigurationError("JARVIS_DB_PATH is invalid")
        if not self.cors_origins or any(origin == "*" for origin in self.cors_origins):
            raise RuntimeConfigurationError("wildcard CORS is not permitted")

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        origins = tuple(item.strip() for item in os.getenv("JARVIS_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if item.strip())
        try:
            port = int(os.getenv("JARVIS_PORT", "8000"))
        except ValueError as error:
            raise RuntimeConfigurationError("JARVIS_PORT must be an integer") from error
        return cls(
            environment=os.getenv("JARVIS_ENV", "development"),
            host=os.getenv("JARVIS_HOST", "127.0.0.1"),
            port=port,
            db_path=os.getenv("JARVIS_DB_PATH", "data/jarvis.db"),
            db_enabled=_bool("JARVIS_DB_ENABLED", False),
            timezone_name=os.getenv("JARVIS_TIMEZONE", "Asia/Kolkata"),
            log_level=os.getenv("JARVIS_LOG_LEVEL", "INFO").upper(),
            cors_origins=origins,
            llm=LLMConfig.from_environment(),
        )

    def safe_status(self, llm_configured: bool = False) -> dict:
        return {
            "environment": self.environment,
            "version": JARVIS_VERSION,
            "host": self.host,
            "port": self.port,
            "database_enabled": self.db_enabled,
            "database_path": self.db_path if self.db_enabled else None,
            "timezone": self.timezone_name,
            "log_level": self.log_level,
            "llm_provider": self.llm.provider.value,
            "llm_enabled": self.llm.enabled,
            "llm_configured": bool(llm_configured),
            "cors_origins": list(self.cors_origins),
            "live_execution_supported": False,
        }


@dataclass
class RuntimeComponents:
    config: RuntimeConfig
    observability: Observability
    orchestrator: JarvisOrchestrator
    paper_engine: PaperTradingEngine
    automation: AutomationController
    interface_service: JarvisInterfaceService
    conversation: JarvisConversationService
    memory: JarvisMemoryService
    tools: ToolService
    workflows: WorkflowService
    connectors: object
    governance: ConnectorGovernanceService
    projects: ProjectIntelligenceService
    delivery: ProjectDeliveryService
    store: SQLiteStore | None = None

    def close(self) -> None:
        if self.store is not None:
            self.store.close()
            self.store = None
        self.observability.record("RUNTIME", "APPLICATION_SHUTDOWN", "COMPLETED", message="application shutdown")


def create_runtime(config: RuntimeConfig | None = None) -> RuntimeComponents:
    config = config or RuntimeConfig.from_environment()
    observability = Observability()
    provider = MockMarketDataProvider()
    orchestrator = JarvisOrchestrator(provider, observability=observability)
    paper_engine = PaperTradingEngine(PaperAccount("100000"))
    automation = AutomationController(orchestrator)
    llm = build_external_llm_from_env(observability, config.llm) if config.llm.enabled else None
    conversation = JarvisConversationService(orchestrator, observability=observability, external_llm=llm, llm_config=config.llm)
    store = SQLiteStore(config.db_path, observability) if config.db_enabled else None
    memory = JarvisMemoryService(MemoryRepository(store), observability=observability)
    conversation.memory_service = memory
    observability.record("RUNTIME", "APPLICATION_STARTED", "COMPLETED", message="application started", metadata={"environment": config.environment, "version": JARVIS_VERSION})
    connectors = build_connector_service(observability)
    governance = ConnectorGovernanceService(store, config.environment, observability)
    projects = ProjectIntelligenceService(connectors, store)
    delivery = ProjectDeliveryService(projects)
    tools = build_tool_service(type("RuntimeView", (), {"observability": observability, "memory": memory, "paper_engine": paper_engine, "automation": automation, "connectors": connectors, "governance": governance, "projects": projects, "delivery": delivery})(), observability)
    conversation.tool_service = tools
    workflows = WorkflowService(tools, store, observability)
    return RuntimeComponents(config, observability, orchestrator, paper_engine, automation, JarvisInterfaceService(orchestrator, automation), conversation, memory, tools, workflows, connectors, governance, projects, delivery, store)


__all__ = ["JARVIS_VERSION", "RuntimeConfig", "RuntimeComponents", "RuntimeConfigurationError", "create_runtime"]
