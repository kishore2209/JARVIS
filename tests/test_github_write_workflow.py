import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorService, ConnectorRegistry
from core.github_connector import FakeGitHubTransport, build_github_connector
from core.tools import build_tool_service
from core.workflows import WorkflowService, WorkflowStatus

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    fake=FakeGitHubTransport(); descriptor, adapter=build_github_connector(enabled=True, token='x', transport=fake, write_enabled=True); registry=ConnectorRegistry(); registry.register(descriptor, adapter); connector=ConnectorService(registry); runtime=type('R',(),{'observability':None,'memory':None,'paper_engine':None,'automation':None,'connectors':connector})(); tools=build_tool_service(runtime); workflows=WorkflowService(tools)
    plan=workflows.create('write', [{'tool_id':'github.issue.create','arguments':{'owner':'o','repo':'r','title':'Title'}}]); waiting=workflows.run(plan.workflow_id)
    check('Write step pauses', waiting.status is WorkflowStatus.WAITING_FOR_APPROVAL and not fake.calls)
    workflows.approve_step(plan.workflow_id,'step-1'); check('Approval alone no POST', not fake.calls)
    done=workflows.resume(plan.workflow_id); check('Explicit resume posts once', done.status is WorkflowStatus.SUCCEEDED and len(fake.calls)==1)
    check('Duplicate resume no repost', workflows.run(plan.workflow_id).status is WorkflowStatus.SUCCEEDED and len(fake.calls)==1)
    check('Merge unavailable', 'github.pull_request.merge' not in [item['tool_id'] for item in tools.registry.safe_list()])
    print('TEST SUMMARY: 5/5 PASS')
if __name__ == '__main__': main()
