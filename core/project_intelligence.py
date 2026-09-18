"""Bounded, deterministic Jira/GitHub project correlation."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import json, re
from types import MappingProxyType
from uuid import uuid4
from core.connectors import ConnectorRequest, ConnectorService

ISSUE_KEY = re.compile(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{1,20}-[0-9]{1,10})(?![A-Za-z0-9])')
class ProjectValidationError(ValueError): pass
@dataclass(frozen=True)
class ProjectWorkspace:
    workspace_id: str; name: str; jira_project_key: str; github_owner: str; github_repo: str; enabled: bool=True; created_at: datetime|None=None; updated_at: datetime|None=None; version: int=1
@dataclass(frozen=True)
class ProjectEvidenceLink:
    jira_issue_key: str; github_reference_type: str; github_reference_id: str; repository: str; evidence_text_excerpt: str; reason: str; source_timestamp: str|None; retrieved_at: datetime
@dataclass(frozen=True)
class ProjectSnapshot:
    snapshot_id: str; workspace_id: str; retrieved_at: datetime; jira_available: bool; github_available: bool; partial_result: bool; jira_issues: tuple; github_prs: tuple; github_commits: tuple; links: tuple; unlinked_jira: tuple; unlinked_prs: tuple; warnings: tuple=()
    def __post_init__(self):
        for name in ('jira_issues','github_prs','github_commits','links','unlinked_jira','unlinked_prs','warnings'):
            object.__setattr__(self,name,tuple(getattr(self,name)))

class ProjectIntelligenceService:
    def __init__(self, connectors: ConnectorService, store=None, max_items=25): self.connectors=connectors; self.store=store; self.max_items=max_items; self.workspaces={}; self.snapshots={}; self._restore()
    @staticmethod
    def _key(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,20}',value): raise ProjectValidationError('invalid Jira project key')
        return value.upper()
    @staticmethod
    def _repo(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',value): raise ProjectValidationError('invalid GitHub resource')
        return value
    def create(self,name,jira_project_key,github_owner,github_repo,workspace_id=None):
        workspace_id=workspace_id or uuid4().hex
        if workspace_id in self.workspaces: raise ProjectValidationError('duplicate workspace')
        now=datetime.now(timezone.utc); workspace=ProjectWorkspace(workspace_id,name[:120],self._key(jira_project_key),self._repo(github_owner),self._repo(github_repo),True,now,now)
        self.workspaces[workspace_id]=workspace; self._save(workspace); return workspace
    def update(self,workspace_id,**changes):
        workspace=self.show(workspace_id); updated=ProjectWorkspace(workspace.workspace_id,changes.get('name',workspace.name),self._key(changes.get('jira_project_key',workspace.jira_project_key)),self._repo(changes.get('github_owner',workspace.github_owner)),self._repo(changes.get('github_repo',workspace.github_repo)),changes.get('enabled',workspace.enabled),workspace.created_at,datetime.now(timezone.utc),workspace.version+1); self.workspaces[workspace_id]=updated; self._save(updated); return updated
    def delete(self,workspace_id):
        if workspace_id not in self.workspaces: raise ProjectValidationError('workspace not found')
        del self.workspaces[workspace_id]; return True
    def list(self): return tuple(self.workspaces.values())
    def show(self,workspace_id):
        if workspace_id not in self.workspaces: raise ProjectValidationError('workspace not found')
        return self.workspaces[workspace_id]
    def snapshot(self,workspace_id):
        workspace=self.show(workspace_id); retrieved=datetime.now(timezone.utc); warnings=[]
        jira_result=self.connectors.read(ConnectorRequest('PROJECT-JIRA','jira','jira.issues.search',{'project_key':workspace.jira_project_key,'max_results':str(self.max_items)})); github_result=self.connectors.read(ConnectorRequest('PROJECT-GITHUB','github','github.pull_requests.list',{'owner':workspace.github_owner,'repo':workspace.github_repo,'state':'open','per_page':str(self.max_items)}))
        jira_ok=jira_result.status=='SUCCEEDED'; github_ok=github_result.status=='SUCCEEDED'
        jira_data=(jira_result.data or {}).get('issues',[]) if isinstance(jira_result.data,dict) else (jira_result.data or [])
        prs=github_result.data if isinstance(github_result.data,list) else []
        if not jira_ok: warnings.append('JIRA_UNAVAILABLE')
        if not github_ok: warnings.append('GITHUB_UNAVAILABLE')
        links=[]; jira_keys={str(item.get('key','')).upper() for item in jira_data if isinstance(item,dict)}; linked=set()
        for pr in prs[:self.max_items]:
            text=' '.join(str(pr.get(field,'')) for field in ('title','body','head','ref','base')); keys=set(ISSUE_KEY.findall(text))
            for key in keys:
                if key in jira_keys:
                    linked.add(key); links.append(ProjectEvidenceLink(key,'PR_TITLE_BODY','PR#'+str(pr.get('number','')),f'{workspace.github_owner}/{workspace.github_repo}',text[:240],'DIRECT_REFERENCE',pr.get('updated_at'),retrieved))
        snapshot=ProjectSnapshot(uuid4().hex,workspace_id,retrieved,jira_ok,github_ok,not(jira_ok and github_ok),tuple(jira_data[:self.max_items]),tuple(prs[:self.max_items]),(),tuple(links),tuple(sorted(jira_keys-linked)),tuple(str(pr.get('number')) for pr in prs if isinstance(pr,dict) and str(pr.get('number')) not in {x.github_reference_id.removeprefix('PR#') for x in links}),tuple(warnings)); self.snapshots[workspace_id]=snapshot; return snapshot
    def _save(self,w):
        if self.store:
            self.store.connection.execute('CREATE TABLE IF NOT EXISTS project_workspaces (id TEXT PRIMARY KEY,payload TEXT NOT NULL)'); self.store.connection.execute('INSERT OR REPLACE INTO project_workspaces VALUES (?,?)',(w.workspace_id,json.dumps({**w.__dict__,'created_at':w.created_at.isoformat(),'updated_at':w.updated_at.isoformat()}))); self.store.connection.commit()
    def _restore(self):
        if not self.store:return
        self.store.connection.execute('CREATE TABLE IF NOT EXISTS project_workspaces (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        for row in self.store.connection.execute('SELECT payload FROM project_workspaces'):
            d=json.loads(row[0]); self.workspaces[d['workspace_id']]=ProjectWorkspace(d['workspace_id'],d['name'],d['jira_project_key'],d['github_owner'],d['github_repo'],d['enabled'],datetime.fromisoformat(d['created_at']),datetime.fromisoformat(d['updated_at']),d['version'])
__all__=['ProjectEvidenceLink','ProjectIntelligenceService','ProjectSnapshot','ProjectValidationError','ProjectWorkspace']
