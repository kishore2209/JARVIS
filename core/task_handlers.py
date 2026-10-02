"""Allowlisted read-only handlers. Each unit consumes budget before starting."""
from datetime import datetime, timedelta, timezone
from market.ohlcv import OHLCV
from market.research import ResearchPipeline


def candles(rows):
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('Expected at most 500 candles')
    return tuple(OHLCV(
        symbol=r['symbol'], exchange=r['exchange'], timestamp=datetime.fromisoformat(r['timestamp']),
        open=float(r['open']), high=float(r['high']), low=float(r['low']), close=float(r['close']),
        volume=float(r['volume']), source=r['source'], is_fresh=r.get('is_fresh') is True,
    ) for r in rows)


def register_task_handlers(tasks, personal, knowledge):
    def daily(payload, consume):
        consume(tools=1)
        return personal.daily_plan()

    def retrieve(payload, consume):
        consume(tools=1)
        return knowledge.retrieve(payload['query'], principal='owner')

    def scan(payload, consume):
        items = payload.get('items', [])
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError('Expected 1..100 supplied instruments')
        as_of = datetime.fromisoformat(payload['as_of'])
        if as_of.tzinfo is None:
            raise ValueError('Aware as_of required')
        index = candles(payload.get('index_candles', []))
        results = []
        for item in items:
            consume(tools=1)  # also checks cancellation and deadline between instruments
            try:
                result = ResearchPipeline().scan([{**item, 'candles': candles(item.get('candles', [])),
                    'sector_candles': candles(item.get('sector_candles', []))}], as_of=as_of,
                    timeframe=payload.get('timeframe', '1d'), index_candles=index)
                results.extend(result['results'])
            except (ValueError, KeyError, TypeError):
                results.append({'symbol': item.get('symbol', 'UNKNOWN'), 'status': 'DATA_REJECTED', 'result': None})
        return {'as_of': as_of.isoformat(), 'universe_source': 'USER_SUPPLIED',
                'universe_verified_active_fno': False, 'results': results, 'total': len(results),
                'technical_pass_count': sum(bool(r['result'] and r['result']['technical_filter_passed']) for r in results)}

    tasks.handlers.update(DAILY_PLAN=daily, KNOWLEDGE_RETRIEVAL=retrieve, RESEARCH_SCAN=scan)
