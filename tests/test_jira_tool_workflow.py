import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.runtime import create_runtime
from unittest.mock import patch
from core.jira_connector import build_jira_connector, FakeJiraTransport

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    disabled=build_jira_connector(enabled=False,base_url='',email='',token='')
    with patch('core.jira_connector.build_jira_connector',return_value=disabled):
        runtime=create_runtime()
    plan=runtime.tools.plan('jira.projects.list',{})
    check('Disabled connector failure propagated',runtime.tools.execute(plan.plan_id).status=='FAILED')
    workflow=runtime.workflows.create('disabled jira',[{'tool_id':'jira.projects.list','arguments':{}}])
    check('Disabled workflow cannot claim success',runtime.workflows.run(workflow.workflow_id).status.value=='FAILED')
    runtime.close()
    fake=FakeJiraTransport({'/rest/api/3/project':[{'key':'TEST','name':'Fixture project'}]})
    configured=build_jira_connector(enabled=True,base_url='https://fixture.atlassian.net',email='fixture',token='fixture-token',transport=fake)
    with patch('core.jira_connector.build_jira_connector',return_value=configured):
        runtime=create_runtime()
    tool_ids=[item['tool_id'] for item in runtime.tools.registry.safe_list()]
    check('Jira tools registered','jira.projects.list' in tool_ids and 'jira.issue.get' in tool_ids)
    descriptor=runtime.tools.registry.descriptor('jira.issue.get'); check('External read risk',descriptor.risk_class.value=='READ_ONLY')
    plan=runtime.tools.plan('jira.projects.list',{}); check('ToolService mediates',runtime.tools.execute(plan.plan_id).status=='SUCCEEDED')
    workflow=runtime.workflows.create('jira read',[{'tool_id':'jira.projects.list','arguments':{}}]); result=runtime.workflows.run(workflow.workflow_id); check('Explicit workflow run',result.status.value=='SUCCEEDED')
    check('Jira write unavailable','jira.issue.create' not in tool_ids)
    check('Both reads reached fixture transport',len(fake.calls)==2)
    runtime.close(); print('TEST SUMMARY: 8/8 PASS')
if __name__=='__main__':main()
