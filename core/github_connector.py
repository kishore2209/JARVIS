"""Read-only GitHub connector with fixed-host and server-side credential boundaries."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import re

from core.connectors import ConnectorCapability, ConnectorDescriptor, ConnectorKind, ConnectorRisk, ConnectorRegistry, ConnectorService, ConnectorValidationError

GITHUB_HOST = "api.github.com"
GITHUB_BASE_URL = "https://api.github.com"

class GitHubTimeoutError(TimeoutError): pass
class GitHubAuthError(RuntimeError): pass
class GitHubPermissionError(RuntimeError): pass
class GitHubNotFoundError(RuntimeError): pass
class GitHubRateLimitError(RuntimeError): pass
class GitHubProviderError(RuntimeError): pass

class GitHubTransport:
    def __init__(self, token: str | None = None, base_url: str = GITHUB_BASE_URL, timeout_seconds: float = 5.0, max_retries: int = 1):
        self.token = token; self.base_url = base_url.rstrip("/"); self.timeout_seconds = timeout_seconds; self.max_retries = max_retries; self.calls = 0
        if self.base_url != GITHUB_BASE_URL: raise ConnectorValidationError("GITHUB_API_BASE_URL must be https://api.github.com")
    def get(self, path: str, params: dict[str, str] | None = None):
        if not path.startswith("/") or ".." in path or any(char in path for char in "\r\n"):
            raise ConnectorValidationError("invalid GitHub path")
        url = self.base_url + path + (("?" + urlencode(params)) if params else "")
        if not url.startswith(GITHUB_BASE_URL + "/"): raise ConnectorValidationError("GitHub host is not allowlisted")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        self.calls += 1
        for attempt in range(self.max_retries + 1):
            try:
                request = Request(url, headers=headers, method="GET")
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    if response.status == 401: raise GitHubAuthError()
                    if response.status == 403: raise GitHubPermissionError()
                    if response.status == 404: raise GitHubNotFoundError()
                    if response.status >= 500: raise GitHubProviderError()
                    return json.loads(response.read().decode("utf-8"))
            except TimeoutError as error:
                if attempt >= self.max_retries: raise GitHubTimeoutError() from error
            except (GitHubAuthError, GitHubPermissionError, GitHubNotFoundError) as error: raise error
            except Exception as error:
                if attempt >= self.max_retries: raise GitHubProviderError() from error
        raise GitHubProviderError()

class FakeGitHubTransport:
    def __init__(self, responses: dict[str, object] | None = None, error: Exception | None = None): self.responses = responses or {}; self.error = error; self.calls = []
    def get(self, path, params=None):
        self.calls.append((path, params or {}))
        if self.error: raise self.error
        if path not in self.responses: raise GitHubNotFoundError()
        value = self.responses[path]
        if isinstance(value, Exception): raise value
        return value
    def post(self, path, body=None):
        self.calls.append(("POST", path, body or {}))
        if path in self.responses:
            value=self.responses[path]
            if isinstance(value, Exception): raise value
            return value
        return {"id": 1, "html_url": "https://github.com/example", "created_at": "2026-01-01T00:00:00Z", "title": body.get("title") if isinstance(body, dict) else None}

class GitHubConnectorAdapter:
    def __init__(self, transport, max_items: int = 100, max_pages: int = 2): self.transport = transport; self.max_items = max_items; self.max_pages = max_pages
    def read(self, capability_id, arguments):
        owner = arguments.get("owner"); repo = arguments.get("repo")
        for identifier in (owner, repo):
            if identifier is not None and (not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", identifier)):
                raise ConnectorValidationError("invalid GitHub owner or repository")
        if capability_id == "github.repositories.list": path = "/user/repos"; params = {"page": str(min(int(arguments.get("page", 1)), self.max_pages)), "per_page": str(min(int(arguments.get("per_page", 30)), 100))}
        elif capability_id == "github.repository.get": path = f"/repos/{owner}/{repo}"; params = {}
        elif capability_id == "github.branches.list": path = f"/repos/{owner}/{repo}/branches"; params = {"per_page": str(min(int(arguments.get("per_page", 30)), 100))}
        elif capability_id == "github.commits.list": path = f"/repos/{owner}/{repo}/commits"; params = {"page": str(min(int(arguments.get("page", 1)), self.max_pages)), "per_page": str(min(int(arguments.get("per_page", 30)), 100))}
        elif capability_id == "github.commit.get": path = f"/repos/{owner}/{repo}/commits/{arguments['sha']}"; params = {}
        elif capability_id == "github.issues.list": path = f"/repos/{owner}/{repo}/issues"; params = {"state": arguments.get("state", "open"), "page": str(min(int(arguments.get("page", 1)), self.max_pages)), "per_page": str(min(int(arguments.get("per_page", 30)), 100))}
        elif capability_id == "github.issue.get": path = f"/repos/{owner}/{repo}/issues/{arguments['issue_number']}"; params = {}
        elif capability_id == "github.pull_requests.list": path = f"/repos/{owner}/{repo}/pulls"; params = {"state": arguments.get("state", "open"), "page": str(min(int(arguments.get("page", 1)), self.max_pages)), "per_page": str(min(int(arguments.get("per_page", 30)), 100))}
        elif capability_id == "github.pull_request.get": path = f"/repos/{owner}/{repo}/pulls/{arguments['pull_number']}"; params = {}
        else: raise ConnectorValidationError("CAPABILITY_UNKNOWN")
        data = self.transport.get(path, params)
        if isinstance(data, list): return data[:self.max_items]
        if not isinstance(data, dict): raise ConnectorValidationError("malformed GitHub response")
        return data
    def write(self, capability_id, arguments):
        owner, repo = arguments["owner"], arguments["repo"]
        if capability_id == "github.issue.create": path=f"/repos/{owner}/{repo}/issues"; body={"title":arguments["title"], **({"body":arguments["body"]} if "body" in arguments else {})}
        elif capability_id == "github.issue.comment": path=f"/repos/{owner}/{repo}/issues/{arguments['issue_number']}/comments"; body={"body":arguments["body"]}
        elif capability_id == "github.pull_request.comment": path=f"/repos/{owner}/{repo}/issues/{arguments['pull_number']}/comments"; body={"body":arguments["body"]}
        else: raise ConnectorValidationError("CAPABILITY_UNKNOWN")
        return self.transport.post(path, body)

def _name_schema(required=True, max_length=100): return {"type":"string","required":required,"max_length":max_length}
def _repo_schema(): return {"owner":_name_schema(),"repo":_name_schema()}
def github_capabilities(write_enabled=False):
    repo=_repo_schema(); page={"type":"string","required":False,"max_length":3}; state={"type":"string","required":False,"max_length":10}
    caps=(ConnectorCapability("github.repositories.list","List authenticated repositories",argument_schema={"page":page,"per_page":page}), ConnectorCapability("github.repository.get","Read repository",argument_schema=repo), ConnectorCapability("github.branches.list","List branches",argument_schema={**repo,"per_page":page}), ConnectorCapability("github.commits.list","List commits",argument_schema={**repo,"page":page,"per_page":page}), ConnectorCapability("github.commit.get","Read commit",argument_schema={**repo,"sha":_name_schema(max_length=80)}), ConnectorCapability("github.issues.list","List issues",argument_schema={**repo,"state":state,"page":page,"per_page":page}), ConnectorCapability("github.issue.get","Read issue",argument_schema={**repo,"issue_number":{ "type":"string","required":True,"max_length":10}}), ConnectorCapability("github.pull_requests.list","List pull requests",argument_schema={**repo,"state":state,"page":page,"per_page":page}), ConnectorCapability("github.pull_request.get","Read pull request",argument_schema={**repo,"pull_number":{"type":"string","required":True,"max_length":10}}))
    if write_enabled:
        write_text={"owner":_name_schema(),"repo":_name_schema()}
        caps += (ConnectorCapability("github.issue.create","Create issue",ConnectorRisk.EXTERNAL_SIDE_EFFECT,{**write_text,"title":_name_schema(max_length=200),"body":_name_schema(required=False,max_length=5000)}), ConnectorCapability("github.issue.comment","Comment issue",ConnectorRisk.EXTERNAL_SIDE_EFFECT,{**write_text,"issue_number":_name_schema(max_length=10),"body":_name_schema(max_length=5000)}), ConnectorCapability("github.pull_request.comment","Comment pull request",ConnectorRisk.EXTERNAL_SIDE_EFFECT,{**write_text,"pull_number":_name_schema(max_length=10),"body":_name_schema(max_length=5000)}))
    return caps

def build_github_connector(enabled: bool | None = None, token: str | None = None, base_url: str | None = None, transport=None, write_enabled: bool | None = None):
    enabled = os.getenv("JARVIS_GITHUB_ENABLED", "false").lower() == "true" if enabled is None else enabled
    write_enabled = os.getenv("JARVIS_GITHUB_WRITE_ENABLED", "false").lower() == "true" if write_enabled is None else write_enabled
    token = os.getenv("GITHUB_TOKEN") if token is None else token
    base_url = os.getenv("GITHUB_API_BASE_URL", GITHUB_BASE_URL) if base_url is None else base_url
    adapter = GitHubConnectorAdapter(transport or GitHubTransport(token, base_url))
    descriptor = ConnectorDescriptor("github", "GitHub", ConnectorKind.HTTP_API, "1", enabled, github_capabilities(write_enabled), credential_required=True, configured=bool(token), read_only=not write_enabled, description="Allowlisted GitHub collaboration actions", write_enabled=write_enabled)
    return descriptor, adapter

__all__=["FakeGitHubTransport","GitHubAuthError","GitHubConnectorAdapter","GitHubNotFoundError","GitHubPermissionError","GitHubProviderError","GitHubRateLimitError","GitHubTimeoutError","GitHubTransport","build_github_connector","github_capabilities"]
