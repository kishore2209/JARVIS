"""Deterministic, evidence-based delivery analysis over ProjectSnapshots."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

@dataclass(frozen=True)
class ProjectDeliveryConfig:
    jira_stale_days: int=14
    pr_stale_days: int=7
    max_attention_items: int=50
    max_history_snapshots: int=20
    max_brief_chars: int=12000
    def __post_init__(self):
        if self.jira_stale_days<=0 or self.pr_stale_days<=0 or self.max_attention_items<=0 or self.max_history_snapshots<=0 or self.max_brief_chars<=0: raise ValueError('delivery limits must be positive')

@dataclass(frozen=True)
class ProjectDeliverySignal:
    signal_type: str
    title: str
    reason: str
    evidence: tuple[Any,...]=()
    severity: str='INFO'

@dataclass(frozen=True)
class ProjectDeliveryAnalysis:
    analysis_id: str
    workspace_id: str
    snapshot_id: str
    retrieved_at: datetime
    signals: tuple[ProjectDeliverySignal,...]
    metrics: dict[str, Any]
    activity: tuple[dict[str,Any],...]
    warnings: tuple[str,...]
    completeness: bool
    def __post_init__(self): object.__setattr__(self,'signals',tuple(self.signals)); object.__setattr__(self,'activity',tuple(self.activity)); object.__setattr__(self,'warnings',tuple(self.warnings))

class ProjectDeliveryService:
    def __init__(self, project_service, config=None): self.projects=project_service; self.config=config or ProjectDeliveryConfig(); self.history={}
    def analyze(self, workspace_id, current_snapshot=None, previous_snapshot=None, now=None):
        current=current_snapshot or self.projects.snapshots.get(workspace_id)
        if current is None: raise ValueError('project snapshot required')
        now=now or datetime.now(timezone.utc); signals=[]; warnings=list(current.warnings); previous_issue={item.get('key'):item for item in (previous_snapshot.jira_issues if previous_snapshot else ()) if isinstance(item,dict)}; current_issue={item.get('key'):item for item in current.jira_issues if isinstance(item,dict)}; previous_pr={str(item.get('number')):item for item in (previous_snapshot.github_prs if previous_snapshot else ()) if isinstance(item,dict)}; current_pr={str(item.get('number')):item for item in current.github_prs if isinstance(item,dict)}
        if previous_snapshot and current.partial_result: warnings.append('PARTIAL_COMPARISON')
        for key in current_issue.keys()-previous_issue.keys(): signals.append(ProjectDeliverySignal('NEW_ACTIVITY',f'New Jira issue {key}', 'Issue newly observed.',(key,)))
        for key in current_pr.keys()-previous_pr.keys(): signals.append(ProjectDeliverySignal('NEW_ACTIVITY',f'New pull request #{key}', 'Pull request newly observed.',(key,)))
        for key in current_issue.keys() & previous_issue.keys():
            old=previous_issue[key].get('fields',{}).get('status',{}).get('name'); new=current_issue[key].get('fields',{}).get('status',{}).get('name')
            if old and new and old!=new: signals.append(ProjectDeliverySignal('STATUS_CHANGED',f'{key} status changed',f'{old} -> {new}',(key,)))
        linked={link.jira_issue_key for link in current.links}
        for key in sorted(set(current.unlinked_jira)): signals.append(ProjectDeliverySignal('UNLINKED_JIRA_ISSUE',f'{key} has no matching GitHub reference','No matching GitHub reference was found in the retrieved snapshot.',(key,)))
        for pr in current.unlinked_prs: signals.append(ProjectDeliverySignal('UNLINKED_PULL_REQUEST',f'PR #{pr} has no Jira reference','No valid Jira issue-key reference was found.',(pr,)))
        for issue in current.jira_issues:
            fields=issue.get('fields',{}) if isinstance(issue,dict) else {}; updated=fields.get('updated') or issue.get('updated_at') if isinstance(issue,dict) else None; status=fields.get('status',{}).get('name') if isinstance(fields.get('status'),dict) else fields.get('status')
            if updated and status and status.lower() not in {'done','closed','resolved'}:
                try:
                    age=(now-datetime.fromisoformat(updated.replace('Z','+00:00'))).days
                    if age>=self.config.jira_stale_days: signals.append(ProjectDeliverySignal('STALE_JIRA_ISSUE',f'{issue.get("key")} may need review',f'No recorded update within configured threshold ({self.config.jira_stale_days} days).',(issue.get('key'),),'REVIEW'))
                except ValueError: warnings.append('INVALID_JIRA_TIMESTAMP')
        for pr in current.github_prs:
            if str(pr.get('state','')).lower()=='open' and pr.get('updated_at'):
                try:
                    age=(now-datetime.fromisoformat(str(pr['updated_at']).replace('Z','+00:00'))).days
                    if age>=self.config.pr_stale_days: signals.append(ProjectDeliverySignal('STALE_PULL_REQUEST',f'PR #{pr.get("number")} may need review',f'No recorded update within configured threshold ({self.config.pr_stale_days} days).',(pr.get('number'),),'REVIEW'))
                except ValueError: warnings.append('INVALID_PR_TIMESTAMP')
        metrics={'jira_issue_count':len(current.jira_issues),'linked_issue_count':len(linked),'unlinked_issue_count':len(current.unlinked_jira),'open_pr_count':sum(str(p.get('state','')).lower()=='open' for p in current.github_prs),'unlinked_pr_count':len(current.unlinked_prs),'stale_issue_count':sum(s.signal_type=='STALE_JIRA_ISSUE' for s in signals),'stale_pr_count':sum(s.signal_type=='STALE_PULL_REQUEST' for s in signals),'state_mismatch_count':0,'complete':not current.partial_result}
        return ProjectDeliveryAnalysis(uuid4().hex,workspace_id,current.snapshot_id,current.retrieved_at,tuple(signals[:self.config.max_attention_items]),metrics,(),tuple(warnings),not current.partial_result)
    def brief(self, analysis):
        sections=['SNAPSHOT SUMMARY',f'Workspace: {analysis.workspace_id}',f'Retrieved: {analysis.retrieved_at.isoformat()}','WHAT CHANGED']+[f'- {s.title}: {s.reason}' for s in analysis.signals]+['METRICS',json_line(analysis.metrics),'WARNINGS']+[f'- {w}' for w in analysis.warnings]
        return '\n'.join(sections)[:self.config.max_brief_chars]

def json_line(value):
    import json
    return json.dumps(value,sort_keys=True)

__all__=['ProjectDeliveryAnalysis','ProjectDeliveryConfig','ProjectDeliveryService','ProjectDeliverySignal']
