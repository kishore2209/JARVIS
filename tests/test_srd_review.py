import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
from market.persistence import SQLiteStore
from market.durable_paper import DurablePaperEngine
from market.risk import TradeProposal, RiskFirewall
from market.review import ReviewService


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.store=SQLiteStore(':memory:');self.engine=DurablePaperEngine(self.store)
        self.review=ReviewService(self.store,self.engine)
        self.now=datetime.now(timezone.utc)

    def tearDown(self): self.store.close()

    def trade(self,price):
        proposal=TradeProposal('DEMO','LONG','100','98','104','100000','1',1,10,self.now,'TEST',True)
        decision=RiskFirewall(clock=lambda:self.now).evaluate(proposal)
        order=self.engine.create_order(proposal,decision)
        fill,position=self.engine.fill_order(order.order_id,'100',self.now,'TEST')
        self.engine.close_position(position.position_id,str(price),self.now)
        return position.position_id

    def test_profit_is_not_rule_adherence(self):
        winner=self.trade(104); loser=self.trade(98)
        self.review.annotate({'position_id':winner,'strategy':'TREND','followed_rules':False,'violations':['late_entry'],'lesson':'Wait for the defined entry.'})
        self.review.annotate({'position_id':loser,'strategy':'TREND','followed_rules':True})
        result=self.review.report('monthly',datetime.now(timezone.utc)+timedelta(seconds=1))
        trades={t['position_id']:t for t in result['trades']}
        self.assertEqual(trades[winner]['outcome'],'WIN')
        self.assertEqual(trades[winner]['decision_quality'],'DECLARED_VIOLATION')
        self.assertEqual(trades[loser]['outcome'],'LOSS')
        self.assertEqual(trades[loser]['decision_quality'],'DECLARED_COMPLIANT')
        self.assertEqual(Decimal(result['metrics']['realized_pnl_before_costs']),Decimal(20))
        self.assertEqual(Decimal(result['metrics']['average_r']),Decimal('0.5'))
        self.assertEqual(Decimal(result['metrics']['maximum_closed_trade_drawdown']),Decimal(20))
        self.assertTrue(result['warnings'])
        self.assertTrue(result['lesson_candidates'][0]['requires_confirmation'])

    def test_annotation_version_and_empty_review(self):
        position=self.trade(104)
        self.review.annotate({'position_id':position,'thesis':'Original'})
        with self.assertRaises(ValueError):self.review.annotate({'position_id':position,'thesis':'Lost update'})
        self.review.annotate({'position_id':position,'thesis':'Revised'},1)
        self.assertEqual([n['thesis'] for n in self.review.history(position)],['Original','Revised'])
        empty=self.review.report('monthly',self.now-timedelta(days=60))
        self.assertEqual(empty['metrics']['sample_size'],0)
        self.assertIsNone(empty['metrics']['expectancy_per_trade'])


if __name__=='__main__':unittest.main()
