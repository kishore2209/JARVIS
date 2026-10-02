import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from datetime import datetime,timedelta,timezone
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from market.ohlcv import OHLCV
from market.research import ResearchPipeline, price_zones
from core.jobs import JobService
from personal.service import PersonalService
from market.persistence import SQLiteStore

NOW=datetime(2026,9,25,4,0,tzinfo=timezone.utc)
def series(symbol,direction=1):
    return [OHLCV(symbol,'NSE',NOW-timedelta(minutes=239-i),1000+direction*i,1002+direction*i,999+direction*i,1001+direction*i,1000,'FIXTURE') for i in range(240)]

class PipelineTests(unittest.TestCase):
    def test_aligned_and_opposing_context(self):
        p=ResearchPipeline()
        r=p.analyze(series('A'),as_of=NOW,index_candles=series('INDEX'),sector_candles=series('SECTOR'),adjustment_status='RAW')
        self.assertTrue(r['technical_filter_passed'])
        self.assertFalse(r['live'])
        r=p.analyze(series('A'),as_of=NOW,index_candles=series('INDEX',-1),sector_candles=series('SECTOR'),adjustment_status='RAW')
        self.assertFalse(r['technical_filter_passed']);self.assertIn('INDEX_NOT_ALIGNED',r['blockers'])
    def test_missing_stale_future_and_self_context(self):
        p=ResearchPipeline();r=p.analyze(series('A'),as_of=NOW+timedelta(days=8))
        self.assertTrue({'INDEX_MISSING','SECTOR_MISSING','ADJUSTMENT_UNKNOWN','UNDERLYING_DATA_STALE'}<=set(r['blockers']))
        with self.assertRaises(ValueError):p.analyze(series('A'),as_of=NOW-timedelta(minutes=5))
        with self.assertRaises(ValueError):p.analyze(series('A'),as_of=NOW,index_candles=series('A'))
    def test_partial_scan(self):
        r=ResearchPipeline().scan([{'symbol':'A','candles':series('A')},{'symbol':'BAD','candles':series('BAD')[:2]}],as_of=NOW)
        self.assertEqual([x['status'] for x in r['results']],['ANALYZED','DATA_REJECTED'])
        self.assertFalse(r['universe_verified_active_fno'])
    def test_zone_confirmed_only_after_departure(self):
        cs=[OHLCV('A','NSE',NOW+timedelta(minutes=i),*prices,100,'FIXTURE') for i,prices in enumerate([(100,102,99,101),(104,106,103,105),(106,108,105,107),(100,101,98,98.5)])]
        self.assertEqual(price_zones(cs[:2]),[])
        z=price_zones(cs[:3])[0];self.assertEqual(z['state'],'FRESH');self.assertEqual(z['known_at'],cs[2].timestamp.isoformat())
        self.assertEqual(price_zones(cs)[0]['state'],'INVALIDATED')

class JobTests(unittest.TestCase):
    def test_duplicate_restart_and_disable(self):
        with tempfile.TemporaryDirectory() as d:
            path=d+'/s.db';s=SQLiteStore(path);j=JobService(s,PersonalService(s))
            j.register('brief','MORNING_BRIEF',NOW,86400)
            self.assertEqual(j.tick(NOW)[0]['status'],'SUCCEEDED');self.assertEqual(j.tick(NOW),[])
            result=j.results()[0]['result'];self.assertEqual(result['status'],'PARTIAL');self.assertEqual(result['delivery'],'LOCAL_ONLY')
            s.close();s=SQLiteStore(path);j=JobService(s,PersonalService(s));self.assertEqual(j.tick(NOW),[])
            j.set_enabled('brief',False);self.assertEqual(j.tick(NOW+timedelta(days=2)),[]);s.close()
    def test_two_workers_one_occurrence(self):
        with tempfile.TemporaryDirectory() as d:
            s=SQLiteStore(d+'/s.db');j=JobService(s,PersonalService(s));j.register('plan','DAILY_PLAN',NOW)
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:j.tick(NOW),range(2)))
            self.assertEqual(sum(len(x) for x in results),1);self.assertEqual(len(j.results()),1);s.close()
    def test_crash_lease_and_bounded_retry(self):
        with tempfile.TemporaryDirectory() as d:
            s=SQLiteStore(d+'/s.db');j=JobService(s,PersonalService(s));j.register('plan','DAILY_PLAN',NOW)
            with s.connection:s.connection.execute('UPDATE scheduled_jobs SET lease_until=?,attempts=1,last_status=?',((NOW+timedelta(minutes=5)).isoformat(),'RUNNING'))
            self.assertEqual(j.tick(NOW),[])
            def fail(_):raise OSError('transient')
            j.handlers['DAILY_PLAN']=fail
            self.assertEqual(j.tick(NOW+timedelta(minutes=6))[0]['status'],'RETRY_PENDING')
            self.assertEqual(j.tick(NOW+timedelta(minutes=8))[0]['status'],'FAILED')
            self.assertFalse(j.list()[0]['enabled']);s.close()
    def test_cancelled_success_cannot_publish(self):
        with tempfile.TemporaryDirectory() as d:
            s=SQLiteStore(d+'/s.db');j=JobService(s,PersonalService(s));j.register('plan','DAILY_PLAN',NOW)
            def cancelled(_):
                j.set_enabled('plan',False)
                return {'obsolete':True}
            j.handlers['DAILY_PLAN']=cancelled
            self.assertEqual(j.tick(NOW),[])
            self.assertEqual(j.results(),[])
            self.assertEqual(j.list()[0]['last_status'],'CANCELLED');s.close()

    def test_cancelled_failure_cannot_reenable(self):
        with tempfile.TemporaryDirectory() as d:
            s=SQLiteStore(d+'/s.db');j=JobService(s,PersonalService(s));j.register('plan','DAILY_PLAN',NOW)
            def cancelled(_):
                j.set_enabled('plan',False)
                raise OSError('old worker failed')
            j.handlers['DAILY_PLAN']=cancelled
            self.assertEqual(j.tick(NOW),[])
            self.assertFalse(j.list()[0]['enabled'])
            self.assertEqual(j.list()[0]['last_status'],'CANCELLED');s.close()

    def test_reenabled_job_rejects_old_claim(self):
        with tempfile.TemporaryDirectory() as d:
            s=SQLiteStore(d+'/s.db');j=JobService(s,PersonalService(s));j.register('plan','DAILY_PLAN',NOW)
            calls=[]
            def handler(_):
                calls.append(1)
                if len(calls)==1:
                    j.set_enabled('plan',False);j.set_enabled('plan',True)
                    return {'obsolete':True}
                return {'fresh':True}
            j.handlers['DAILY_PLAN']=handler
            self.assertEqual(len(j.tick(NOW)),1)
            self.assertEqual(j.results()[0]['result'],{'fresh':True});s.close()

    def test_alerts_quiet_hours_and_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            s=SQLiteStore(d+'/s.db');j=JobService(s,PersonalService(s));night=NOW.replace(hour=18)
            self.assertEqual(j.alert('stale','Stale feed',now=night)['delivery_status'],'DEFERRED_QUIET_HOURS')
            self.assertTrue(j.alert('stale','Stale feed',now=night+timedelta(seconds=2))['deduplicated'])
            self.assertEqual(j.alert('urgent','Stop',severity='CRITICAL',now=night,critical_bypass=True)['delivery_status'],'LOCAL_ONLY')
            self.assertEqual(len(j.alerts()),2);s.close()

if __name__=='__main__':unittest.main()
