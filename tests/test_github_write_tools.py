import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRegistry
from core.github_connector import FakeGitHubTransport, build_github_connector
from core.tools import ToolService, build_tool_service

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    descriptor, adapter=build_github_connector(enabled=True, token='secret', transport=FakeGitHubTransport(), write_enabled=True); connectors=__import__('core.connectors',fromlist=['ConnectorService']).ConnectorService(ConnectorRegistry()); connectors.registry.register(descriptor, adapter)
    runtime=type('Runtime',(),{'observability':None,'memory':None,'paper_engine':None,'automation':None,'connectors':connectors})()
    tools=build_tool_service(runtime); plan=tools.plan('github.issue.create',{'owner':'o','repo':'r','title':'Title','body':'Body'})
    check('Write tool registered', plan.requires_confirmation and plan.risk_class.value == 'EXTERNAL_SIDE_EFFECT')
    before=len(adapter.transport.calls); blocked=tools.execute(plan.plan_id); check('Execute before approval blocked', blocked.status=='REJECTED' and len(adapter.transport.calls)==before)
    tools.approve(plan.plan_id); check('Approval sends no request', len(adapter.transport.calls)==before)
    done=tools.execute(plan.plan_id); check('Explicit execute sends one POST', done.status=='SUCCEEDED' and len(adapter.transport.calls)==before+1)
    duplicate=tools.execute(plan.plan_id); check('Completed plan duplicate blocked', duplicate.status=='REJECTED' and len(adapter.transport.calls)==before+1)
    check('No merge tool', 'github.pull_request.merge' not in [x['tool_id'] for x in tools.registry.safe_list()])
    print('TEST SUMMARY: 7/7 PASS')
if __name__ == '__main__': main()
