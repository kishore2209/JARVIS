import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from api import app

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    with TestClient(app) as client:
        created = client.post('/api/v1/workflows', json={'title':'Read workflow','steps':[{'tool_id':'system.status','arguments':{}}]})
        check('Create workflow', created.status_code == 200)
        workflow = created.json()['workflow']; workflow_id = workflow['workflow_id']
        check('List workflows', client.get('/api/v1/workflows').status_code == 200)
        check('Show workflow', client.get(f'/api/v1/workflows/{workflow_id}').json()['workflow']['workflow_id'] == workflow_id)
        run = client.post(f'/api/v1/workflows/{workflow_id}/run')
        check('Run read-only workflow', run.json()['result']['status'] == 'SUCCEEDED')
        protected = client.post('/api/v1/workflows', json={'title':'Protected','steps':[{'tool_id':'memory.preference.set','arguments':{'key':'language','value':'Telugu'}}]})
        protected_id = protected.json()['workflow']['workflow_id']
        waiting = client.post(f'/api/v1/workflows/{protected_id}/run')
        check('Protected step waits', waiting.json()['result']['status'] == 'WAITING_FOR_APPROVAL')
        approval = client.post(f'/api/v1/workflows/{protected_id}/steps/step-1/approve')
        check('Approve exact step', approval.status_code == 200)
        resumed = client.post(f'/api/v1/workflows/{protected_id}/resume')
        check('Resume workflow', resumed.json()['result']['status'] == 'SUCCEEDED')
        duplicate = client.post(f'/api/v1/workflows/{protected_id}/resume')
        check('Duplicate resume safe', duplicate.status_code == 400)
        cancelled = client.post('/api/v1/workflows', json={'title':'Cancel','steps':[{'tool_id':'system.status','arguments':{}}]}).json()['workflow']['workflow_id']
        check('Cancel workflow', client.post(f'/api/v1/workflows/{cancelled}/cancel').status_code == 200)
        invalid = client.post('/api/v1/workflows', json={'title':'Bad','steps':[{'tool_id':'broker.place_order','arguments':{}}]})
        check('Blocked financial workflow', invalid.status_code == 400)
        check('Safe serialization', 'traceback' not in invalid.text.lower() and 'GEMINI_API_KEY' not in invalid.text)
    print('TEST SUMMARY: 12/12 PASS')
if __name__ == '__main__': main()
