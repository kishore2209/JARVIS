"""SRD regression tests: adversarial boundaries, recovery, provenance and personal OS."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.runtime import RuntimeConfig, RuntimeConfigurationError, create_runtime
from core.security import install_api_security
from core.memory import JarvisMemoryService, MemoryRepository
from market.persistence import SQLiteStore
from market.durable_paper import DurablePaperEngine
from market.risk import TradeProposal, RiskFirewall
from market.ohlcv import OHLCV
from market.charts import render_chart
from personal.service import PersonalService
from quant.atr import atr

NOW = datetime.now(timezone.utc)


def proposal():
    return TradeProposal('DEMO','LONG','100','98','104','100000','1',1,10,datetime.now(timezone.utc),'TEST',True)


class SecurityTests(unittest.TestCase):
    def app(self, token=''):
        app=FastAPI()
        @app.post('/data')
        def data(payload:dict): return payload
        @app.get('/health')
        def health(): return {'status':'OK'}
        install_api_security(app,RuntimeConfig(api_token=token))
        return app

    def test_token_and_host_and_origin(self):
        token='local-test-value-'*3
        c=TestClient(self.app(token))
        self.assertEqual(c.post('/data',json={}).status_code,401)
        headers={'Authorization':'Bearer '+token}
        self.assertEqual(c.post('/data',json={'a':1},headers=headers).json(),{'a':1})
        self.assertEqual(c.post('/data',json={},headers={**headers,'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(c.post('/data',json={},headers={**headers,'Host':'evil.example'}).status_code,400)
        r=c.post('/data',json={},headers=headers)
        self.assertTrue(r.headers['X-Correlation-ID'])
        self.assertNotIn(token,repr(RuntimeConfig(api_token=token)))

    def test_remote_requires_token(self):
        with self.assertRaises(RuntimeConfigurationError): RuntimeConfig(host='0.0.0.0')
        with self.assertRaises(RuntimeConfigurationError): RuntimeConfig(environment='production')
        c=TestClient(self.app(),client=('198.51.100.1',123))
        self.assertEqual(c.post('/data',json={}).status_code,403)
        self.assertEqual(c.get('/health').status_code,200)

    def test_chunked_size_limit(self):
        c=TestClient(self.app())
        r=c.post('/data',content=iter([b'a'*1_100_000,b'b'*1_100_000]))
        self.assertEqual(r.status_code,413)

    def test_nan_and_future(self):
        with self.assertRaises(ValueError): replace(proposal(),proposed_entry='NaN')
        with self.assertRaises(ValueError): replace(proposal(),capital_available='Infinity')
        self.assertFalse(RiskFirewall().evaluate(replace(proposal(),timestamp=NOW+timedelta(days=1))).approved)


class RecoveryTests(unittest.TestCase):
    def test_paper_restart_and_counter(self):
        with tempfile.TemporaryDirectory() as d:
            config=RuntimeConfig(db_enabled=True,db_path=d+'/state.db')
            runtime=create_runtime(config);p=proposal();decision=RiskFirewall().evaluate(p)
            order=runtime.paper_engine.create_order(p,decision)
            _,position=runtime.paper_engine.fill_order(order.order_id,100,NOW,'TEST')
            runtime.close()
            runtime=create_runtime(config)
            self.assertEqual(runtime.paper_engine.account.available_cash,Decimal('99000'))
            self.assertIn(position.position_id,runtime.paper_engine.account.open_positions)
            runtime.paper_engine.close_position(position.position_id,104,NOW)
            order2=runtime.paper_engine.create_order(p,decision)
            self.assertNotEqual(order.order_id,order2.order_id)
            runtime.paper_engine.set_kill_switch(True);runtime.close()
            runtime=create_runtime(config)
            self.assertEqual(runtime.paper_engine.account.realized_pnl,40)
            self.assertEqual(runtime.paper_engine.account.available_cash,100040)
            with self.assertRaises(ValueError):runtime.paper_engine.create_order(p,decision)
            runtime.close()

    def test_rollback_on_disk_failure(self):
        engine=DurablePaperEngine();p=proposal()
        with patch.object(engine,'_save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):engine.create_order(p,RiskFirewall().evaluate(p))
        self.assertEqual(engine.account.order_history,{})
        self.assertEqual(engine._order_number,0)

    def test_stale_writer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            store=SQLiteStore(d+'/state.db');a=DurablePaperEngine(store)
            a.set_kill_switch(False);b=DurablePaperEngine(store)
            a.set_kill_switch(True)
            with self.assertRaises(ValueError): b.set_kill_switch(False)
            store.close()

    def test_changed_proposal_rejected(self):
        engine=DurablePaperEngine();p=proposal();decision=RiskFirewall().evaluate(p)
        with self.assertRaises(ValueError):engine.create_order(replace(p,proposed_entry=101),decision)
        self.assertEqual(engine.account.order_history,{})

    def test_sqlite_thread_access(self):
        with tempfile.TemporaryDirectory() as d:
            store=SQLiteStore(d+'/state.db');personal=PersonalService(store)
            def save(i):return personal.save('notes',{'id':str(i),'title':'n','body':'b','observed_at':NOW.isoformat()})
            with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(save,range(20)))
            self.assertEqual(len(personal.list('notes')),20)
            store.close()


class MemoryTests(unittest.TestCase):
    def test_history_revocation_transitive_restart(self):
        with tempfile.TemporaryDirectory() as d:
            store=SQLiteStore(d+'/state.db');s=JarvisMemoryService(MemoryRepository(store))
            a=s.create('PREFERENCE','language','Telugu',source_refs=('private-doc',),source_turns=('turn-1',))
            s.create('PREFERENCE','language','English',source_turns=('turn-2',))
            self.assertEqual(s.repository.history(a.memory_id)[0].value,'Telugu')
            b=s.create('PROJECT_CONTEXT','summary','English preference',parent_ids=(a.memory_id,))
            c=s.create('PROJECT_CONTEXT','nested','English summary',parent_ids=(b.memory_id,))
            self.assertIn(c,s.retrieve('nested'))
            s.repository.revoke_source('private-doc');store.close()
            store=SQLiteStore(d+'/state.db');s=JarvisMemoryService(MemoryRepository(store))
            self.assertEqual(s.retrieve('English language nested'),())
            self.assertEqual(s.safe_context('English')['memories'],[])
            s.repository.purge(a.memory_id)
            self.assertEqual(s.repository.history(a.memory_id),())
            store.close()

    def test_unrelated_and_session_isolation(self):
        s=JarvisMemoryService(MemoryRepository())
        a=s.create('WORK_CONTEXT','project','Apollo',scope='SESSION',session_id='A')
        self.assertEqual(s.retrieve('Apollo',entities={'session_id':'B'}),())
        self.assertEqual(s.retrieve('Apollo',entities={'session_id':'A'}),(a,))
        s.create('PREFERENCE','language','Telugu')
        self.assertEqual(s.retrieve('weather'),())

    def test_category_does_not_overwrite(self):
        s=JarvisMemoryService(MemoryRepository())
        s.create('PROFILE','name','Kishor');s.create('PROJECT_CONTEXT','name','Jarvis')
        self.assertEqual(len(s.list()),2)


class PersonalTests(unittest.TestCase):
    def base(self,identifier):return {'id':identifier,'observed_at':NOW.isoformat()}
    def test_finance_coverage_and_decimal(self):
        s=PersonalService()
        s.save('balances',{**self.base('cash'),'name':'Cash','kind':'CASH','value':'100.10'})
        s.save('balances',{**self.base('loan'),'name':'Loan','kind':'LIABILITY','value':'20.05'})
        s.save('balances',{**self.base('old'),'observed_at':(NOW-timedelta(days=2)).isoformat(),'name':'Old','kind':'INVESTMENT','value':'500'})
        s.save('expenses',{**self.base('expense'),'account_id':'cash','amount':'0.10','category':'Food'})
        r=s.finance_summary(NOW,expected_accounts=('cash','loan','old','missing'))
        self.assertEqual(Decimal(r['covered_net_worth']),Decimal('80.05'))
        self.assertEqual(r['coverage']['stale'],['old']);self.assertEqual(r['coverage']['missing'],['missing'])
        self.assertEqual(r['monthly_expenses'],'0.10');self.assertEqual(r['completeness'],'PARTIAL')

    def test_idempotency_conflicts_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            store=SQLiteStore(d+'/s.db');s=PersonalService(store)
            data={**self.base('x'),'title':'Note','body':'Original'}
            self.assertEqual(s.save('notes',data)['version'],1)
            self.assertEqual(s.save('notes',data)['version'],1)
            with self.assertRaises(ValueError):s.save('notes',{**data,'body':'changed'})
            s.save('notes',{**data,'body':'changed'},1);store.close()
            store=SQLiteStore(d+'/s.db');s=PersonalService(store)
            self.assertEqual(s.list('notes')[0]['body'],'changed')
            with self.assertRaises(ValueError):s.delete('notes','x',1)
            s.delete('notes','x',2);self.assertEqual(s.list('notes'),[]);store.close()

    def test_calendar_conflicts_recurring_tasks_and_cancellation(self):
        s=PersonalService()
        for id,offset in [('a',0),('b',30)]:
            s.save('events',{**self.base(id),'title':id,'start_at':(NOW+timedelta(minutes=offset)).isoformat(),'end_at':(NOW+timedelta(minutes=offset+60)).isoformat()})
        self.assertEqual(s.daily_plan(NOW)['conflicts'],[['a','b']])
        task={**self.base('t'),'title':'Study','due_at':(NOW-timedelta(days=4)).isoformat(),'kind':'LEARNING','recurrence_days':1}
        s.save('tasks',task);updated=s.complete_task('t',1,NOW)
        self.assertGreater(datetime.fromisoformat(updated['due_at']),NOW)
        with self.assertRaises(ValueError):s.complete_task('t',1,NOW)
        payload={k:v for k,v in updated.items() if k!='version'};payload['status']='CANCELLED'
        s.save('tasks',payload,2);self.assertEqual(s.daily_plan(NOW+timedelta(days=3))['tasks'],[])

    def test_invalid_numbers_and_timestamps(self):
        s=PersonalService()
        for value in ('NaN','Infinity','-1'):
            with self.assertRaises(ValueError):s.save('balances',{**self.base('x'),'name':'Bad','kind':'CASH','value':value})
        with self.assertRaises(ValueError):s.save('notes',{'id':'n','title':'n','body':'n','observed_at':'2026-01-01T00:00:00'})


class ChartTests(unittest.TestCase):
    def candles(self):
        return [OHLCV('DEMO','NSE',NOW+timedelta(minutes=i),100,102,99,101,1000,'FIXTURE') for i in range(21)]
    def test_determinism_and_traceability(self):
        candles=self.candles();a=render_chart(candles,'1m');b=render_chart(candles,'1m')
        self.assertEqual(a,b);self.assertFalse(a['metadata']['live'])
        candles[-1].close=100.5
        self.assertNotEqual(a['metadata']['artifact_id'],render_chart(candles,'1m')['metadata']['artifact_id'])
    def test_invalid_candles_and_escaping(self):
        candles=self.candles();candles[-1].high=100
        with self.assertRaises(ValueError):render_chart(candles,'1m')
        candles=self.candles();candles[0].symbol='<script>'
        with self.assertRaises(ValueError):render_chart(candles,'1m')
        for c in candles:c.symbol='<script>'
        self.assertNotIn('<script>',render_chart(candles,'1m')['svg'])
    def test_atr_golden(self):
        self.assertEqual(atr(self.candles()),3)
        with self.assertRaises(ValueError):atr(self.candles()[:14])

if __name__=='__main__':unittest.main()
