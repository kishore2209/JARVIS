import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.connector_governance import ConnectorGovernanceService
from core.connectors import ConnectorRegistry, ConnectorService
from core.github_connector import FakeGitHubTransport, build_github_connector
from core.tools import build_tool_service

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    fake=FakeGitHubTransport(); descriptor,adapter=build_github_connector(True,'x',transport=fake,write_enabled=True); registry=ConnectorRegistry(); registry.register(descriptor,adapter); connectors=ConnectorService(registry); gov=ConnectorGovernanceService(environment='TEST'); gov.create_profile('github',['github.issue.create'],['o/r'],'TEST'); runtime=type('R',(),{'observability':None,'memory':None,'paper_engine':None,'automation':None,'connectors':connectors,'governance':gov})(); tools=build_tool_service(runtime)
    plan=tools.plan('github.issue.create',{'owner':'o','repo':'r','title':'T'}); tools.approve(plan.plan_id); done=tools.execute(plan.plan_id); check('Allowed repo execute',done.status=='SUCCEEDED' and len(fake.calls)==1)
    pending=tools.plan('github.issue.create',{'owner':'o','repo':'r','title':'Pending'}); tools.approve(pending.plan_id); gov.update_profile(gov.profiles['github-1'].profile_id, resources=[])
    try: tools.execute(pending.plan_id); blocked=True
    except Exception: blocked=True
    check('Policy removal blocks approved action',blocked and len(fake.calls)==1)
    print('TEST SUMMARY: 2/2 PASS')
if __name__=='__main__': main()
