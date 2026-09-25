import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import unittest
import tempfile
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from market.risk import RiskFirewall,RiskConfig,TradeProposal
from market.paper_trading import PaperAccount,PaperTradingEngine

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.proposal=TradeProposal('TEST','LONG','100','98','104','100000','1',25,125,self.now,'TEST',True)
        self.firewall=RiskFirewall(clock=lambda:self.now)

    def test_future_rejected(self):
        self.assertFalse(self.firewall.evaluate(replace(self.proposal,timestamp=self.now+timedelta(seconds=1))).approved)

    def test_nonfinite_and_invalid_sizing(self):
        for value in ['NaN','Infinity','-Infinity','bad']:
            with self.assertRaises(ValueError):replace(self.proposal,proposed_entry=value)
        for edit in [{'quantity_requested':1.5},{'quantity_requested':True},{'lot_size':True},{'capital_available':0},{'risk_per_trade_percent':-1},{'risk_per_trade_percent':101}]:
            with self.subTest(edit=edit):self.assertFalse(self.firewall.evaluate(replace(self.proposal,**edit)).approved)
        self.assertFalse(RiskFirewall(RiskConfig(reject_incomplete_evidence=True),clock=lambda:self.now).evaluate(self.proposal).approved)

    def test_approval_bound_to_exact_proposal(self):
        decision=self.firewall.evaluate(self.proposal)
        engine=PaperTradingEngine(PaperAccount('100000'))
        for edit in [{'proposed_stop':'99'},{'proposed_target':'110'},{'quantity_requested':150},{'capital_available':'200000'},{'timestamp':self.now-timedelta(seconds=1)}]:
            with self.subTest(edit=edit),self.assertRaises(ValueError):engine.create_order(replace(self.proposal,**edit),decision)
        self.assertEqual(len(engine.account.order_history),0)
        engine.create_order(self.proposal,decision)

    def test_durable_stop_and_corruption_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'safety.json'
            engine=PaperTradingEngine(PaperAccount('100000'),safety_path=path)
            decision=self.firewall.evaluate(self.proposal)
            order=engine.create_order(self.proposal,decision)
            engine.set_halted(True)
            with self.assertRaises(ValueError):engine.create_order(self.proposal,decision)
            with self.assertRaises(ValueError):engine.fill_order(order.order_id,'100',self.now,'TEST')
            restarted=PaperTradingEngine(PaperAccount('100000'),safety_path=path)
            self.assertTrue(restarted.halted)
            restarted.set_halted(False);self.assertFalse(engine.halted)
            path.write_text('invalid');self.assertTrue(engine.halted)

    def test_http_authorization_and_numbers(self):
        from api import app
        from fastapi.testclient import TestClient
        from dataclasses import asdict
        payload=asdict(self.proposal)
        payload={k:str(v) if k.startswith('proposed_') or k in ('capital_available','risk_per_trade_percent') else v for k,v in payload.items()}
        payload['timestamp']=self.now.isoformat()
        c=TestClient(app)
        self.assertEqual(c.post('/api/v1/paper/execute',json={**payload,'explicit_user_authorization':'false'}).json()['code'],'AUTHORIZATION_REQUIRED')
        for edit in [{'lot_size':1.5},{'lot_size':True},{'proposed_entry':'NaN'}]:
            self.assertEqual(c.post('/api/v1/risk/validate',json={**payload,**edit}).status_code,400)

if __name__=='__main__':unittest.main()
