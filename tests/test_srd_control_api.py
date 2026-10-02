import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from fastapi.testclient import TestClient

workspace=tempfile.TemporaryDirectory()
os.environ['JARVIS_DB_ENABLED']='true'
os.environ['JARVIS_DB_PATH']=workspace.name+'/state.db'
os.environ['JARVIS_API_TOKEN']='test-control-owner-'*3
from api import app,runtime


class ControlAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=TestClient(app,headers={'Authorization':'Bearer '+os.environ['JARVIS_API_TOKEN']})

    @classmethod
    def tearDownClass(cls):
        cls.client.close();runtime.close();workspace.cleanup()

    def test_cited_chat_and_tool_search(self):
        document=self.client.post('/api/v1/knowledge',json={'title':'Entry plan','source':'local:strategy','text':'Risk budget uses capital and stop distance.'})
        self.assertEqual(document.status_code,200)
        search=self.client.post('/api/v1/knowledge/search',json={'query':'stop distance'}).json()['result']
        self.assertEqual(search['matches'][0]['version'],1)
        chat=self.client.post('/api/v1/chat',json={'text':'search knowledge: stop distance'}).json()
        self.assertIn('KNOWLEDGE_SEARCH',str(chat))
        self.assertIn(search['matches'][0]['citation_id'],str(chat))
        self.assertIn('knowledge.search',str(self.client.get('/api/v1/tools').json()))
        forbidden=self.client.post('/api/v1/knowledge/search',json={'query':'risk','principal':'someone-else'})
        self.assertEqual(forbidden.status_code,422)
        self.client.post('/api/v1/knowledge/revoke',json={'source':'local:strategy'})
        self.assertTrue(self.client.post('/api/v1/knowledge/search',json={'query':'stop distance'}).json()['result']['empty'])

    def test_durable_worker_task_and_trace(self):
        payload={'kind':'DAILY_PLAN','payload':{},'idempotency_key':'daily-test','tool_budget':1}
        response=self.client.post('/api/v1/tasks',json=payload,headers={'X-Correlation-ID':'trace-control'})
        self.assertEqual(response.status_code,202)
        identifier=response.json()['task']['id']
        self.assertEqual(self.client.post('/api/v1/tasks',json=payload).json()['task']['id'],identifier)
        self.assertEqual(self.client.post('/api/v1/tasks',json={**payload,'kind':'BROKER_ORDER'}).status_code,400)
        runtime.tasks.run_next()
        completed=self.client.get('/api/v1/tasks/'+identifier).json()['task']
        self.assertEqual(completed['state'],'COMPLETED')
        self.assertEqual(completed['correlation_id'],'trace-control')
        self.assertIsNone(runtime.tasks.run_next())
        self.assertEqual(self.client.get('/api/v1/paper/review?period=weekly').json()['result']['metrics']['sample_size'],0)

    def test_owner_auth_required(self):
        with TestClient(app) as anonymous:
            self.assertEqual(anonymous.get('/api/v1/knowledge').status_code,401)
            self.assertEqual(anonymous.post('/api/v1/tasks',json={}).status_code,401)


if __name__=='__main__':unittest.main()
