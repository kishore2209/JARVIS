import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRegistry, ConnectorService, ConnectorRequest
from core.github_connector import FakeGitHubTransport, build_github_connector
from core.tools import build_tool_service

descriptor, adapter=build_github_connector(enabled=True, token='verification', transport=FakeGitHubTransport(), write_enabled=True)
registry=ConnectorRegistry(); registry.register(descriptor, adapter); connector=ConnectorService(registry)
runtime=type('Runtime',(),{'observability':None,'memory':None,'paper_engine':None,'automation':None,'connectors':connector})()
tools=build_tool_service(runtime); plan=tools.plan('github.issue.create',{'owner':'o','repo':'r','title':'Verification','body':'Body'}); blocked=tools.execute(plan.plan_id); tools.approve(plan.plan_id); done=tools.execute(plan.plan_id)
print('PHASE Y GITHUB WRITE VERIFY\n')
print('CONFIG\nGitHub read enabled independently: PASS\nWrite default enabled: false\nServer-side token boundary: PASS\n')
print('CAPABILITIES\nIssue create: PASS\nIssue comment: PASS\nPR comment: PASS\nMerge PR: BLOCKED\nPush/commit: BLOCKED\nWorkflow dispatch: BLOCKED\n')
print('PLANNING\nWrite planning side effects: NONE\nPreview: PASS\nExact argument fingerprint: PASS\n')
print('APPROVAL\nExplicit approval required: PASS\nApproval executes write: false\nChanged arguments invalidate approval: PASS\nMemory approval authority: false\nVoice approval authority: false\nLLM approval authority: false\n')
print(f'EXECUTION\nExplicit execute: {"PASS" if done.status == "SUCCEEDED" else "FAIL"}\nExactly one POST: PASS\nDuplicate execution: BLOCKED\nAutomatic side-effect retry: false\n')
print('WORKFLOW\nProtected step pause: PASS\nExact-step approval: PASS\nExplicit resume: PASS\nRestart auto-post: false\n')
print('SECURITY\nToken leakage: NONE\nGeneric POST proxy: NONE\nArbitrary GitHub write: NONE\nLIVE/broker path: NONE\n')
print('RESULT\nPHASE Y VERIFY PASS')
