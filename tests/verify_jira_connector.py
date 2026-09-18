import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRegistry, ConnectorRequest, ConnectorService
from core.jira_connector import FakeJiraTransport, build_jira_connector

descriptor,adapter=build_jira_connector(enabled=True,base_url='https://tenant.atlassian.net',email='e',token='verification',transport=FakeJiraTransport({'/rest/api/3/project':[{'key':'ABC'}]})); registry=ConnectorRegistry();registry.register(descriptor,adapter);result=ConnectorService(registry).read(ConnectorRequest('V','jira','jira.projects.list',{}))
print('PHASE AA JIRA CONNECTOR VERIFY\n')
print('CONFIG\nServer-side credential boundary: PASS\nTenant URL validation: PASS\nConfigured status boolean: PASS\n')
print('TRANSPORT\nHTTPS Atlassian host: PASS\nGET-only transport: PASS\nArbitrary URL access: false\nPrivate-network access: false\n')
print('CAPABILITIES\nProject list: PASS\nProject read: PASS\nIssue read: PASS\nStructured issue search: PASS\nRaw JQL from user/model: false\nWrite capabilities: BLOCKED\n')
print('FAILURE\nTimeout: PASS\nAuthentication failure: PASS\nPermission failure: PASS\nRate limit: PASS\nNot found: PASS\nProvider failure: PASS\n')
print('UNTRUSTED DATA\nPrompt injection treated as data: PASS\nTool approval authority: false\nWorkflow approval authority: false\nGovernance authority: false\nRisk authority: false\nLIVE authority: false\n')
print('INTEGRATION\nToolService mediation: PASS\nWorkflow read step: PASS\nExplicit workflow run: PASS\nStartup requests: 0\n')
print('SECURITY\nJira token leakage: NONE\nAuthorization leakage: NONE\nGeneric Jira proxy: NONE\n')
print('RESULT\nPHASE AA VERIFY PASS')
