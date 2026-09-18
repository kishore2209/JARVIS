"""Read-only Jira Cloud connector with fixed tenant and structured search."""
from __future__ import annotations
import json, os, re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from core.connectors import ConnectorCapability, ConnectorDescriptor, ConnectorKind, ConnectorRegistry, ConnectorRisk, ConnectorService, ConnectorValidationError

class JiraTimeoutError(TimeoutError): pass
class JiraAuthError(RuntimeError): pass
class JiraPermissionError(RuntimeError): pass
class JiraNotFoundError(RuntimeError): pass
class JiraRateLimitError(RuntimeError): pass
class JiraProviderError(RuntimeError): pass
JIRA_CAPABILITIES = ("jira.projects.list","jira.project.get","jira.issue.get","jira.issues.search")

def validate_base_url(value: str) -> str:
    parsed=urlparse(value or '')
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/') or not parsed.hostname or not parsed.hostname.endswith('.atlassian.net') or not re.fullmatch(r'[A-Za-z0-9.-]+',parsed.hostname): raise ConnectorValidationError('JIRA_BASE_URL must be an HTTPS Atlassian Cloud host')
    return f'https://{parsed.hostname}'

def _key(value: str, pattern: str = r'[A-Za-z][A-Za-z0-9_]{0,49}'):
    if not isinstance(value,str) or not re.fullmatch(pattern,value): raise ConnectorValidationError('invalid Jira identifier')
    return value

class JiraTransport:
    def __init__(self, base_url: str, email: str|None=None, token: str|None=None, timeout_seconds: float=5.0, max_retries: int=1):
        self.base_url=validate_base_url(base_url); self.email=email; self.token=token; self.timeout_seconds=timeout_seconds; self.max_retries=max_retries; self.calls=0
    def get(self,path,params=None):
        if not path.startswith('/') or '..' in path or any(char in path for char in '\r\n'): raise ConnectorValidationError('invalid Jira path')
        url=self.base_url+path+(('?'+urlencode(params)) if params else ''); headers={'Accept':'application/json'}
        if self.email and self.token: headers['Authorization']='Basic configured-server-credential'
        self.calls+=1
        for attempt in range(self.max_retries+1):
            try:
                with urlopen(Request(url,headers=headers,method='GET'),timeout=self.timeout_seconds) as response:
                    if response.status==401: raise JiraAuthError()
                    if response.status==403: raise JiraPermissionError()
                    if response.status==404: raise JiraNotFoundError()
                    if response.status==429: raise JiraRateLimitError()
                    if response.status>=500: raise JiraProviderError()
                    return json.loads(response.read().decode())
            except TimeoutError as error:
                if attempt>=self.max_retries: raise JiraTimeoutError() from error
            except (JiraAuthError,JiraPermissionError,JiraNotFoundError,JiraRateLimitError): raise
            except Exception as error:
                if attempt>=self.max_retries: raise JiraProviderError() from error
        raise JiraProviderError()

class FakeJiraTransport:
    def __init__(self,responses=None,error=None): self.responses=responses or {}; self.error=error; self.calls=[]
    def get(self,path,params=None):
        self.calls.append((path,params or {}))
        if self.error: raise self.error
        if path not in self.responses: raise JiraNotFoundError()
        value=self.responses[path]
        if isinstance(value,Exception): raise value
        return value

class JiraConnectorAdapter:
    def __init__(self,transport,max_items=100): self.transport=transport; self.max_items=max_items
    def read(self,capability_id,args):
        if capability_id=='jira.projects.list': path='/rest/api/3/project'; params={}
        elif capability_id=='jira.project.get': path=f"/rest/api/3/project/{_key(args['project_key'])}"; params={}
        elif capability_id=='jira.issue.get': path=f"/rest/api/3/issue/{_key(args['issue_key'],r'[A-Za-z][A-Za-z0-9_]{0,20}-[0-9]{1,10}')}"; params={}
        elif capability_id=='jira.issues.search':
            project=args.get('project_key'); status=args.get('status'); text=args.get('text'); clauses=[]
            if project: clauses.append(f'project = "{_key(project)}"')
            if status: clauses.append(f'status = "{status}"')
            if text: clauses.append(f'text ~ "{text}"')
            path='/rest/api/3/search'; params={'jql':' AND '.join(clauses) or 'order by updated DESC','startAt':str(min(int(args.get('start_at',0)),1000)),'maxResults':str(min(int(args.get('max_results',20)),100))}
        else: raise ConnectorValidationError('CAPABILITY_UNKNOWN')
        data=self.transport.get(path,params)
        if not isinstance(data,(dict,list)): raise ConnectorValidationError('malformed Jira response')
        return data[:self.max_items] if isinstance(data,list) else data

def jira_capabilities():
    project={'type':'string','required':True,'max_length':50}; optional={'type':'string','required':False,'max_length':100}
    return (ConnectorCapability('jira.projects.list','List Jira projects'),ConnectorCapability('jira.project.get','Read Jira project',argument_schema={'project_key':project}),ConnectorCapability('jira.issue.get','Read Jira issue',argument_schema={'issue_key':{'type':'string','required':True,'max_length':40}}),ConnectorCapability('jira.issues.search','Search Jira issues with structured filters',argument_schema={'project_key':optional,'status':optional,'text':optional,'start_at':{'type':'string','required':False,'max_length':6},'max_results':{'type':'string','required':False,'max_length':3}}))

def build_jira_connector(enabled=None,base_url=None,email=None,token=None,transport=None):
    enabled=os.getenv('JARVIS_JIRA_ENABLED','false').lower()=='true' if enabled is None else enabled; base_url=os.getenv('JIRA_BASE_URL','') if base_url is None else base_url; email=os.getenv('JIRA_EMAIL') if email is None else email; token=os.getenv('JIRA_API_TOKEN') if token is None else token
    configured=bool(base_url and email and token); adapter=JiraConnectorAdapter(transport or (JiraTransport(base_url,email,token) if base_url else FakeJiraTransport())); descriptor=ConnectorDescriptor('jira','Jira',ConnectorKind.HTTP_API,'1',enabled,jira_capabilities(),credential_required=True,configured=configured,read_only=True,description='Read-only Jira Cloud connector')
    return descriptor,adapter

__all__=['FakeJiraTransport','JiraAuthError','JiraConnectorAdapter','JiraNotFoundError','JiraPermissionError','JiraProviderError','JiraRateLimitError','JiraTimeoutError','JiraTransport','build_jira_connector','jira_capabilities','validate_base_url']
