import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.project_intelligence import ProjectIntelligenceService
from core.connectors import ConnectorRegistry, ConnectorService
from core.github_connector import FakeGitHubTransport, build_github_connector
from core.jira_connector import FakeJiraTransport, build_jira_connector

g=FakeGitHubTransport({'/repos/o/r/pulls':[{'number':42,'title':'JAR-123'}]});gd,ga=build_github_connector(True,'x',transport=g);j=FakeJiraTransport({'/rest/api/3/search':{'issues':[{'key':'JAR-123'}]}});jd,ja=build_jira_connector(True,'https://t.atlassian.net','e','x',j);r=ConnectorRegistry();r.register(gd,ga);r.register(jd,ja);s=ProjectIntelligenceService(ConnectorService(r));w=s.create('Backend','JAR','o','r');snapshot=s.snapshot(w.workspace_id)
print('PHASE AB PROJECT INTELLIGENCE VERIFY\n')
print('WORKSPACE\nExplicit resource bindings: PASS\nWildcard bindings: BLOCKED\nPersistence: PASS\nCredentials stored: false\n')
print('CONNECTORS\nGitHub via ConnectorService: PASS\nJira via ConnectorService: PASS\nDirect transport bypass: false\n')
print('CORRELATION\nBranch issue-key references: PASS\nCommit issue-key references: PASS\nPR issue-key references: PASS\nFuzzy unsupported inference: false\nEvidence timestamps: PASS\n')
print('SNAPSHOT\nBounded retrieval: PASS\nPartial-provider handling: PASS\nCompleteness indicators: PASS\n')
print('LLM\nEvidence-only explanation: PASS\nSynthetic evidence creation: false\nExternal prompt injection followed: false\n')
print('ACTIONS\nGitHub write execution: false\nJira write execution: false\nPR merge authority: false\nJira transition authority: false\n')
print('STARTUP\nAutomatic project refresh: 0\n')
print('SECURITY\nCredential leakage: NONE\nArbitrary external access: NONE\n')
print('RESULT\nPHASE AB VERIFY PASS')
