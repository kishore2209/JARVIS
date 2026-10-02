import sys,os,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient

workspace=tempfile.TemporaryDirectory()
os.environ['JARVIS_DB_ENABLED']='true'
os.environ['JARVIS_DB_PATH']=workspace.name+'/state.db'
os.environ['JARVIS_API_TOKEN']='test-owner-value-'*3
from api import app,runtime

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=TestClient(app,headers={'Authorization':'Bearer '+os.environ['JARVIS_API_TOKEN']})
    @classmethod
    def tearDownClass(cls):cls.c.close();runtime.close();workspace.cleanup()
    def test_personal_persistence_and_patch_version(self):
        now=datetime.now(timezone.utc).isoformat()
        payload={'id':'cash','name':'Cash','kind':'CASH','value':'120.50','observed_at':now}
        r=self.c.post('/api/v1/personal/balances',json=payload)
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['record']['version'],1)
        self.assertEqual(self.c.get('/api/v1/personal/finance-summary').json()['result']['covered_net_worth'],'120.50')
        self.assertEqual(self.c.post('/api/v1/personal/balances',json={**payload,'value':'130'}).status_code,400)
        self.assertEqual(self.c.post('/api/v1/personal/balances?expected_version=1',json={**payload,'value':'130'}).json()['record']['version'],2)
        self.assertEqual(self.c.get('/api/v1/personal/export').json()['records']['balances'][0]['value'],'130')
    def test_memory_history_routes(self):
        first=self.c.post('/api/v1/memory',json={'category':'PREFERENCE','key':'language','value':'Telugu','source_refs':['src']}).json()['memory']
        self.c.patch('/api/v1/memory/'+first['memory_id'],json={'value':'English'})
        history=self.c.get('/api/v1/memory/'+first['memory_id']+'/history').json()['history']
        self.assertEqual(history[0]['value'],'Telugu')
        self.assertEqual(self.c.post('/api/v1/memory/sources/revoke',json={'source':'src'}).status_code,200)
        self.assertEqual(runtime.memory.retrieve('language'),())
    def test_cors_mutations(self):
        r=self.c.options('/api/v1/memory/x',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'PATCH','Access-Control-Request-Headers':'Authorization,Content-Type'})
        self.assertEqual(r.status_code,200)
        self.assertIn('PATCH',r.headers['access-control-allow-methods'])
    def test_chart_storage_and_bad_geometry(self):
        c={'symbol':'X','exchange':'NSE','timestamp':datetime.now(timezone.utc).isoformat(),'open':100,'high':102,'low':99,'close':101,'volume':100,'source':'FILE'}
        r=self.c.post('/api/v1/charts',json={'candles':[c],'timeframe':'1d'}).json()
        self.assertTrue(r['chart']['persisted']);identifier=r['chart']['metadata']['artifact_id']
        self.assertEqual(self.c.get('/api/v1/charts/'+identifier).json()['chart']['svg'],r['chart']['svg'])
        self.assertEqual(self.c.post('/api/v1/charts',json={'candles':[{**c,'high':100}]}).status_code,400)
    def test_durable_jobs_and_reports(self):
        self.assertEqual(self.c.post('/api/v1/jobs',json={'id':'brief','kind':'MORNING_BRIEF','next_at':(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()}).status_code,200)
        self.assertEqual(self.c.post('/api/v1/jobs-tick').json()['runs'][0]['status'],'SUCCEEDED')
        self.assertEqual(self.c.get('/api/v1/reports').json()['reports'][0]['result']['status'],'PARTIAL')
        self.assertEqual(self.c.patch('/api/v1/jobs/brief',json={'enabled':False}).status_code,200)
    def test_authorization_is_boolean(self):
        p={'instrument':'X','direction':'LONG','proposed_entry':'100','proposed_stop':'98','proposed_target':'104','capital_available':'100000','risk_per_trade_percent':'1','lot_size':1,'quantity_requested':10,'timestamp':datetime.now(timezone.utc).isoformat(),'explicit_user_authorization':'false'}
        self.assertEqual(self.c.post('/api/v1/paper/execute',json=p).json()['code'],'AUTHORIZATION_REQUIRED')
        self.assertEqual(self.c.post('/api/v1/paper/kill-switch',json={'enabled':True}).status_code,200)
        self.assertEqual(self.c.post('/api/v1/paper/execute',json={**p,'explicit_user_authorization':True}).json()['status'],'ERROR')
        self.c.post('/api/v1/paper/kill-switch',json={'enabled':False})

if __name__=='__main__':unittest.main()
