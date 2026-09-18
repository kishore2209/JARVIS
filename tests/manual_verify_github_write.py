import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

required = ("GITHUB_TOKEN", "JARVIS_GITHUB_WRITE_ENABLED", "JARVIS_RUN_GITHUB_WRITE_SMOKE", "JARVIS_GITHUB_SMOKE_OWNER", "JARVIS_GITHUB_SMOKE_REPO", "JARVIS_GITHUB_SMOKE_CONFIRM")
if not all(os.getenv(name) for name in required) or os.getenv("JARVIS_GITHUB_WRITE_ENABLED") != "true" or os.getenv("JARVIS_RUN_GITHUB_WRITE_SMOKE") != "true" or os.getenv("JARVIS_GITHUB_SMOKE_CONFIRM") != "YES":
    print("GITHUB WRITE MANUAL SMOKE: SKIPPED")
    raise SystemExit(0)

from core.connectors import ConnectorRequest, ConnectorRegistry, ConnectorService
from core.github_connector import build_github_connector
owner, repo = os.environ["JARVIS_GITHUB_SMOKE_OWNER"], os.environ["JARVIS_GITHUB_SMOKE_REPO"]
descriptor, adapter = build_github_connector(enabled=True, write_enabled=True)
registry = ConnectorRegistry(); registry.register(descriptor, adapter)
result = ConnectorService(registry).write(ConnectorRequest("MANUAL", "github", "github.issue.create", {"owner": owner, "repo": repo, "title": "JARVIS MANUAL SMOKE TEST", "body": "Explicitly opted-in manual Phase Y smoke test."}))
print(f"GITHUB WRITE MANUAL SMOKE: status={result.status} result_summary=created")
