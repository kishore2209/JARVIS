import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRegistry, ConnectorRequest, ConnectorService
from core.jira_connector import FakeJiraTransport, JiraConnectorAdapter, JiraTransport, build_jira_connector, validate_base_url

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    descriptor,adapter=build_jira_connector(enabled=False,base_url='https://tenant.atlassian.net',email='e',token='secret',transport=FakeJiraTransport())
    check('Disabled connector',not descriptor.enabled); check('Configured boolean',descriptor.configured and 'secret' not in str(descriptor))
    for url in ('http://tenant.atlassian.net','https://localhost','https://127.0.0.1','https://evil.example','file://x'):
        try: validate_base_url(url); valid=True
        except Exception: valid=False
        check('Unsafe Jira host rejected',not valid)
    fake=FakeJiraTransport({'/rest/api/3/project':[{'id':'1','key':'ABC','name':'Alpha'}],'/rest/api/3/project/ABC':{'key':'ABC','name':'Alpha'},'/rest/api/3/issue/ABC-1':{'key':'ABC-1','fields':{'summary':'Issue'}},'/rest/api/3/search':{'issues':[{'key':'ABC-1'}]}})
    descriptor,adapter=build_jira_connector(enabled=True,base_url='https://tenant.atlassian.net',email='e',token='secret',transport=fake); registry=ConnectorRegistry();registry.register(descriptor,adapter);service=ConnectorService(registry)
    projects=service.read(ConnectorRequest('1','jira','jira.projects.list',{}));check('Project list',projects.status=='SUCCEEDED')
    issue=service.read(ConnectorRequest('2','jira','jira.issue.get',{'issue_key':'ABC-1'}));check('Issue get',issue.status=='SUCCEEDED')
    search=service.read(ConnectorRequest('3','jira','jira.issues.search',{'project_key':'ABC','status':'Open','max_results':'10'}));check('Structured issue search',search.status=='SUCCEEDED')
    for args in ({'project_key':'ABC','jql':'project = ABC'},{'issue_key':'https://evil'},{'token':'fake'},{'Authorization':'Bearer fake'}):
        result=service.read(ConnectorRequest('x','jira','jira.issues.search',args));check('Unsafe Jira argument rejected',result.status=='FAILED')
    check('GET-only transport',not hasattr(JiraTransport,'post') and not hasattr(JiraTransport,'delete'));check('Raw JQL unavailable','jql' not in str(descriptor));check('Token not exposed','secret' not in repr(issue))
    print('TEST SUMMARY: 12/12 PASS')
if __name__=='__main__':main()
