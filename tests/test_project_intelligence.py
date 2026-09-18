import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRegistry, ConnectorService
from core.github_connector import FakeGitHubTransport, build_github_connector
from core.jira_connector import FakeJiraTransport, build_jira_connector
from core.project_intelligence import ProjectIntelligenceService, ProjectValidationError
from market.persistence import SQLiteStore

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    github=FakeGitHubTransport({'/repos/o/r/pulls':[{'number':42,'title':'JAR-123 Fix','body':'JAR-123 handled','updated_at':'2026-01-02T00:00:00Z'}]}); gd,ga=build_github_connector(True,'x',transport=github); jira=FakeJiraTransport({'/rest/api/3/search':{'issues':[{'key':'JAR-123','fields':{'summary':'Fix'}}]}}); jd,ja=build_jira_connector(True,'https://t.atlassian.net','e','x',jira); reg=ConnectorRegistry(); reg.register(gd,ga);reg.register(jd,ja); service=ProjectIntelligenceService(ConnectorService(reg)); workspace=service.create('Backend','JAR','o','r','w1'); check('Create workspace',workspace.workspace_id=='w1'); snapshot=service.snapshot('w1'); check('Correlation direct reference',len(snapshot.links)==1 and snapshot.links[0].jira_issue_key=='JAR-123'); check('Timestamps preserved',snapshot.links[0].source_timestamp is not None); check('Fuzzy unsupported',len(snapshot.links)==1)
    for args in [('Bad','JAR','*','r'),('Bad','JAR','o','*')]:
        try: service.create(*args); valid=True
        except ProjectValidationError: valid=False
        check('Invalid resource rejected',not valid)
    path=tempfile.mktemp(suffix='.db'); store=SQLiteStore(path); persisted=ProjectIntelligenceService(ConnectorService(reg),store); persisted.create('Backend','JAR','o','r','persist'); store.close();store=SQLiteStore(path); restored=ProjectIntelligenceService(ConnectorService(reg),store);check('Restart restore',len(restored.list())==1);store.close();os.remove(path)
    print('TEST SUMMARY: 8/8 PASS')
if __name__=='__main__': main()
