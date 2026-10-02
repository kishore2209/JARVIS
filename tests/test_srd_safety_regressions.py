import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from unittest.mock import patch
from core.runtime import RuntimeConfig,create_runtime
from core.tools import ToolRegistry,ToolDescriptor,ToolRiskClass,ToolService
from core.connector_governance import ConnectorGovernanceService,GovernanceValidationError
from market.persistence import SQLiteStore
from market.providers.angel_one import AngelOneMarketDataProvider


class SafetyTests(unittest.TestCase):
    def test_concurrent_execution_runs_adapter_once(self):
        calls=[];registry=ToolRegistry()
        registry.register(ToolDescriptor('test.read','Read','Test read',ToolRiskClass.READ_ONLY,False,('ANALYSIS_ONLY',),{}),lambda _:calls.append('called'))
        service=ToolService(registry);plan=service.plan('test.read')
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:service.execute(plan.plan_id),range(2)))
        self.assertEqual(calls,['called'])
        self.assertEqual({r.status for r in results},{'SUCCEEDED','REJECTED'})

    def test_uncertain_adapter_failure_is_not_retried(self):
        calls=[];registry=ToolRegistry()
        def fail(_):calls.append(1);raise TimeoutError('unknown outcome')
        registry.register(ToolDescriptor('test.write','Write','Test write',ToolRiskClass.LOCAL_REVERSIBLE,True,('ANALYSIS_ONLY',),{}),fail)
        service=ToolService(registry);plan=service.plan('test.write');service.approve(plan.plan_id)
        self.assertEqual(service.execute(plan.plan_id).status,'FAILED')
        self.assertEqual(service.execute(plan.plan_id).status,'REJECTED')
        self.assertEqual(calls,[1])

    def test_governance_deletion_persists_and_environment_is_not_inferred(self):
        with tempfile.TemporaryDirectory() as directory:
            path=directory+'/state.db';store=SQLiteStore(path)
            service=ConnectorGovernanceService(store,'PAPER')
            profile=service.create_profile('github',['github.issue.create'],['o/r'])
            with self.assertRaises(GovernanceValidationError):service.update_profile(profile.profile_id,enabled='false')
            service.delete_profile(profile.profile_id,'github');store.close()
            restored=SQLiteStore(path)
            self.assertEqual(ConnectorGovernanceService(restored,'PAPER').safe_list(),())
            restored.close()
        with self.assertRaises(ValueError):ConnectorGovernanceService(environment='TYPO')

    def test_real_provider_is_opt_in_and_no_login_on_startup(self):
        with patch.object(AngelOneMarketDataProvider,'login') as login:
            runtime=create_runtime(RuntimeConfig(market_provider='ANGEL_ONE'))
            try:
                self.assertEqual(runtime.orchestrator.provider.source,'ANGEL_ONE')
                self.assertEqual(runtime.config.safe_status()['market_data_mode'],'ANGEL_ONE_READ_ONLY')
                login.assert_not_called()
            finally:runtime.close()

    def test_candle_geometry_conflicting_duplicates_and_future_rejected(self):
        now=datetime(2026,9,26,10,tzinfo=timezone.utc)
        row=['2026-09-26T09:55:00+00:00',100,103,99,102,100]
        bad_rows=[[row,[*row[:4],101,100]], [[row[0],100,101,99,102,100]], [['2026-09-27T09:55:00+00:00',100,103,99,102,100]]]
        for rows in bad_rows:
            client=type('Client',(),{'getCandleData':lambda _self,_args:{'status':True,'data':rows}})()
            provider=AngelOneMarketDataProvider(client,lambda:now)
            with self.assertRaises(ValueError):provider.get_candles('X','NSE','1')

    def test_ltp_without_exchange_timestamp_is_not_fresh(self):
        client=type('Client',(),{'ltpData':lambda *args:{'status':True,'data':{'ltp':100,'symboltoken':'1'}}})()
        quote=AngelOneMarketDataProvider(client).get_quote('X','NSE','1')
        self.assertFalse(quote.is_fresh)


if __name__=='__main__':unittest.main()
