"""Regression tests for data validity, source isolation, and actual HTTP analysis."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import csv
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from market.data_pipeline import load_candle_text, parse_candle, validate_candles, FileMarketDataProvider, ReadOnlyAngelDataProvider
from market.historical_analysis import analyze_file_text
from core.runtime import RuntimeConfig, create_runtime


def rows():
    start = datetime(2026, 1, 2, 4, tzinfo=timezone.utc)
    return [dict(symbol="TEST", exchange="NSE", timestamp=(start + timedelta(minutes=15*i)).isoformat(), open=100+i/10, high=101+i/10, low=99+i/10, close=100.5+i/10, volume=1000+i, source="SYNTHETIC_TEST_FIXTURE") for i in range(240)]


class DataTests(unittest.TestCase):
    def test_reproducible_analysis_and_provenance(self):
        text = json.dumps({"interval":"15m", "candles":rows()})
        a = analyze_file_text(text)
        self.assertEqual(a, analyze_file_text(text))
        self.assertEqual(a["provenance"]["candle_count"], 240)
        self.assertEqual(a["provenance"]["freshness_status"], "HISTORICAL_NOT_LIVE")
        self.assertFalse(a["underlying_analysis"]["is_fresh"])
        self.assertEqual(a["data_completeness"], "PARTIAL")
        self.assertEqual(len(a["chart_candles"]), 240)

    def test_csv_and_file_runtime(self):
        data=rows(); stream=io.StringIO(); writer=csv.DictWriter(stream, fieldnames=data[0].keys()); writer.writeheader(); writer.writerows(data)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'candles.csv';path.write_text(stream.getvalue())
            runtime=create_runtime(RuntimeConfig(data_provider="FILE",candle_file=str(path),candle_interval="15m"))
            try:
                self.assertIsInstance(runtime.orchestrator.provider, FileMarketDataProvider)
                self.assertFalse(runtime.orchestrator.provider.get_candles("TEST","NSE")[-1].is_fresh)
                with self.assertRaises(ValueError):runtime.orchestrator.provider.get_candles("OTHER","NSE")
                with self.assertRaises(ValueError):runtime.orchestrator.provider.get_candles("TEST","NSE",interval="1m")
                with self.assertRaises(ValueError):runtime.orchestrator.provider.get_quote("TEST","NSE")
            finally:runtime.close()

    def test_bad_data_rejected(self):
        for edit in [{"high":90},{"low":110},{"volume":1.5},{"volume":True},{"close":"NaN"},{"close":"Infinity"},{"open":0},{"timestamp":"2026-01-02T04:00:00"},{"timestamp":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}]:
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                load_candle_text(json.dumps([{**rows()[0],**edit}]), interval="15m")
        for data in [rows()[::-1], rows()+[rows()[-1]], [rows()[0],{**rows()[1],"symbol":"OTHER"}], [rows()[0],{**rows()[1],"source":"OTHER"}]]:
            with self.assertRaises(ValueError):load_candle_text(json.dumps(data),interval="15m")
        with self.assertRaises(ValueError):load_candle_text(json.dumps({"interval":"1d","candles":rows()}), interval="15m")

    def test_wall_clock_freshness(self):
        candle=parse_candle(rows()[0]);now=candle.timestamp+timedelta(minutes=10)
        self.assertTrue(validate_candles([candle],"15m",now)[0].is_fresh)
        self.assertFalse(validate_candles([candle],"15m",now+timedelta(days=1))[0].is_fresh)
        with self.assertRaises(ValueError):validate_candles([candle],"15m",candle.timestamp-timedelta(seconds=1))

    def test_angel_read_only_selection_and_failure(self):
        class Adapter:
            client=None
            INTERVALS={"15m":"FIFTEEN_MINUTE"}
            def login(self):raise RuntimeError("credential secret must not escape")
        provider=ReadOnlyAngelDataProvider(Adapter())
        self.assertFalse(hasattr(provider,"placeOrder"))
        with self.assertRaisesRegex(ValueError,"no mock fallback") as error:provider.get_candles("TEST","NSE","123")
        self.assertNotIn("credential secret",str(error.exception))
        runtime=create_runtime(RuntimeConfig(data_provider="ANGEL_ONE"))
        self.assertIsInstance(runtime.orchestrator.provider,ReadOnlyAngelDataProvider)
        runtime.close()

    def test_http_file_analysis_and_safe_errors(self):
        from api import app
        from fastapi.testclient import TestClient
        client=TestClient(app)
        payload={"content":json.dumps(rows()),"format":"json","interval":"15m"}
        response=client.post('/api/v1/analysis/file',json=payload)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["provenance"]["symbol"],"TEST")
        for content in ['{}','not json',json.dumps([{**rows()[0],"high":1}])]:
            self.assertEqual(client.post('/api/v1/analysis/file',json={**payload,"content":content}).status_code,400)
        self.assertEqual(client.post('/api/v1/analysis/full',json={"instrument":"MISSING"}).json()["status"],"ERROR")

if __name__=='__main__':unittest.main()
