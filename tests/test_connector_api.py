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
        listed=client.get('/api/v1/connectors')
        check('List connectors', listed.status_code == 200 and any(x['connector_id']=='mcp.demo' for x in listed.json()['connectors']))
        check('Show connector', client.get('/api/v1/connectors/mcp.demo').status_code == 200)
        caps=client.get('/api/v1/connectors/mcp.demo/capabilities')
        check('Capabilities', caps.status_code == 200 and any(x['capability_id']=='mcp.resource.read' for x in caps.json()['capabilities']))
        read=client.post('/api/v1/connectors/mcp.demo/read', json={'capability_id':'mcp.resource.read','arguments':{'resource':'demo://status'}})
        check('Read fake connector', read.status_code == 200 and read.json()['result']['status']=='SUCCEEDED')
        unknown=client.post('/api/v1/connectors/missing/read', json={'capability_id':'x','arguments':{}})
        check('Unknown connector safe', unknown.status_code == 200 and unknown.json()['status']=='ERROR')
        bad=client.post('/api/v1/connectors/mcp.demo/read', json={'capability_id':'mcp.resource.read','arguments':{'resource':'https://evil'}})
        check('Arbitrary URL rejected', bad.json()['status']=='ERROR')
        check('No secret serialization', 'GEMINI_API_KEY' not in listed.text and 'Authorization' not in listed.text)
    print('TEST SUMMARY: 7/7 PASS')
if __name__ == '__main__': main()
