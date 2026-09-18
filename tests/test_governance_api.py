import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from api import app

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    with TestClient(app) as client:
        listed=client.get('/api/v1/governance/connectors'); check('Governance list',listed.status_code==200)
        created=client.post('/api/v1/governance/connectors/github/profiles',json={'allowed_capabilities':['github.issue.create'],'allowed_resources':['o/r'],'environment':'DEVELOPMENT'}); check('Governance create',created.status_code==200)
        profile=created.json()['profile']; shown=client.get('/api/v1/governance/connectors/github'); check('Governance show',shown.status_code==200 and shown.json()['profiles'])
        bad=client.post('/api/v1/governance/connectors/github/profiles',json={'allowed_capabilities':['github.issue.create'],'allowed_resources':['*'],'environment':'DEVELOPMENT'}); check('Wildcard rejected',bad.status_code==400)
        secret=client.post('/api/v1/governance/connectors/github/profiles',json={'allowed_capabilities':['github.issue.create'],'allowed_resources':['o/r'],'GITHUB_TOKEN':'secret'}); check('Token field rejected',secret.status_code==400 and 'secret' not in secret.text)
    print('TEST SUMMARY: 5/5 PASS')
if __name__=='__main__': main()
