import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.runtime import create_runtime

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    runtime=create_runtime(); tool_ids=[item['tool_id'] for item in runtime.tools.registry.safe_list()]
    check('Jira tools registered','jira.projects.list' in tool_ids and 'jira.issue.get' in tool_ids)
    descriptor=runtime.tools.registry.descriptor('jira.issue.get'); check('External read risk',descriptor.risk_class.value=='READ_ONLY')
    plan=runtime.tools.plan('jira.projects.list',{}); check('ToolService mediates',runtime.tools.execute(plan.plan_id).status=='SUCCEEDED')
    workflow=runtime.workflows.create('jira read',[{'tool_id':'jira.projects.list','arguments':{}}]); result=runtime.workflows.run(workflow.workflow_id); check('Explicit workflow run',result.status.value=='SUCCEEDED')
    check('Jira write unavailable','jira.issue.create' not in tool_ids)
    runtime.close(); print('TEST SUMMARY: 5/5 PASS')
if __name__=='__main__':main()
