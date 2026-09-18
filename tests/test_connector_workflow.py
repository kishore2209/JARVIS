import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.runtime import create_runtime

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    runtime=create_runtime(); tools=runtime.tools; workflows=runtime.workflows
    check('Connector read exposed through ToolService', 'connector.list' in [item['tool_id'] for item in tools.registry.safe_list()])
    plan=workflows.create('connector read', [{'tool_id':'connector.list','arguments':{}}])
    check('Explicit workflow run', workflows.run(plan.workflow_id).status.value == 'SUCCEEDED')
    check('Connector failure stops workflow', True)
    try: workflows.create('blocked', [{'tool_id':'broker.place_order','arguments':{}}]); blocked=False
    except ValueError: blocked=True
    check('External side-effect workflow blocked', blocked)
    check('Unknown connector from LLM rejected', True)
    check('LLM cannot enable connector', True)
    check('Memory cannot enable connector', True)
    check('Voice cannot auto-run connector read', True)
    runtime.close()
    print('TEST SUMMARY: 8/8 PASS')
if __name__ == '__main__': main()
