"""Offline contract tests; no broker account or network needed."""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market.providers.instrument_resolver import AngelOneInstrumentResolver
from market.providers.angel_one import AngelOneMarketDataProvider


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        self.rows = [dict(symbol='RELIANCE-EQ', exch_seg='NSE', token='2885', expiry=''),
                     dict(symbol='RELIANCE', exch_seg='BSE', token='500325', expiry='')]
        self.calls = 0
        self.failure = False
        self.resolver = AngelOneInstrumentResolver(self, lambda: self.now)

    def fetch_records(self):
        self.calls += 1
        if self.failure:
            raise RuntimeError('master unavailable')
        return self.rows

    def test_exact_exchange_and_equity_alias(self):
        self.assertEqual(self.resolver.resolve('reliance', 'nse'), ('RELIANCE-EQ', 'NSE', '2885'))
        self.assertEqual(self.resolver.resolve('RELIANCE', 'BSE')[2], '500325')
        self.assertEqual(self.calls, 1)

    def test_wrong_token_rejected(self):
        with self.assertRaises(ValueError):
            self.resolver.resolve('RELIANCE', 'NSE', '500325')

    def test_unknown_and_ambiguous_rejected(self):
        with self.assertRaises(ValueError):
            self.resolver.resolve('UNKNOWN', 'NSE')
        self.rows.append(dict(symbol='RELIANCE-EQ', exch_seg='NSE', token='999'))
        with self.assertRaises(ValueError):
            self.resolver.resolve('RELIANCE', 'NSE')

    def test_expired_derivative_and_underlying_not_guessed(self):
        self.rows.append(dict(symbol='ABC24SEP26FUT', exch_seg='NFO', token='44', expiry='24SEP2026'))
        for symbol in ('ABC', 'ABC24SEP26FUT'):
            with self.assertRaises(ValueError):
                self.resolver.resolve(symbol, 'NFO')

    def test_expired_cache_fails_closed_then_recovers(self):
        self.resolver.resolve('RELIANCE', 'NSE')
        self.now += timedelta(hours=7)
        self.failure = True
        with self.assertRaises(RuntimeError):
            self.resolver.resolve('RELIANCE', 'NSE')
        self.failure = False
        self.rows = [dict(symbol='RELIANCE-EQ', exch_seg='NSE', token='999')]
        self.assertEqual(self.resolver.resolve('RELIANCE', 'NSE')[2], '999')

    def test_provider_uses_resolved_quote_identity(self):
        class Broker:
            def ltpData(inner, exchange, symbol, token):
                self.assertEqual((symbol, exchange, token), ('RELIANCE-EQ', 'NSE', '2885'))
                return dict(status=True, data=dict(ltp=100, symboltoken=token))
        provider = AngelOneMarketDataProvider(Broker(), instrument_resolver=self.resolver)
        self.assertEqual(provider.get_quote('RELIANCE', 'NSE').token, '2885')

    def test_provider_rejects_mismatch_before_broker_call(self):
        provider = AngelOneMarketDataProvider(object(), instrument_resolver=self.resolver)
        with self.assertRaises(ValueError):
            provider.get_candles('RELIANCE', 'NSE', '500325')

    def test_provider_candles_keep_requested_analysis_symbol(self):
        class Broker:
            def getCandleData(inner, params):
                self.assertEqual(params['symboltoken'], '2885')
                return dict(status=True, data=[['2026-09-25T15:00:00+05:30', 100, 102, 99, 101, 100]])
        provider = AngelOneMarketDataProvider(Broker(), clock=lambda:self.now, instrument_resolver=self.resolver)
        self.assertEqual(provider.get_candles('RELIANCE', 'NSE')[0].symbol, 'RELIANCE')

if __name__ == '__main__':
    unittest.main()
