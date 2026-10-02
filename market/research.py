"""Read-only, replayable multi-instrument analysis over explicitly supplied datasets."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta
import hashlib
import json
from math import isfinite

from market.charts import render_chart
from market.context import MarketContextEngine
from market.underlying_analysis import UnderlyingAnalysisEngine
from market.strategies.engine import MultiStrategyEngine
from market.confluence import ConfluenceEngine
from quant.atr import atr

ENGINE_VERSION = 'research-pipeline-1'


def validate_series(candles, as_of, maximum_age, minimum=200):
    if as_of.tzinfo is None or maximum_age <= timedelta(0): raise ValueError('Aware as-of time and positive freshness budget required')
    if not minimum <= len(candles) <= 500: raise ValueError(f'Series needs {minimum}..500 candles')
    first=candles[0]; previous=None
    for c in candles:
        if (c.symbol,c.exchange,c.source)!=(first.symbol,first.exchange,first.source):raise ValueError('Mixed series identity/source')
        if c.timestamp.tzinfo is None or c.timestamp>as_of or previous and c.timestamp<=previous:raise ValueError('Future, duplicate or unordered candle')
        if not all(isfinite(float(v)) for v in (c.open,c.high,c.low,c.close,c.volume)) or min(c.open,c.close,c.low)<=0 or c.volume<0 or c.low>min(c.open,c.close) or c.high<max(c.open,c.close):raise ValueError('Invalid candle')
        previous=c.timestamp
    fresh=as_of-candles[-1].timestamp<=maximum_age and candles[-1].is_fresh
    return tuple(replace(c,is_fresh=fresh) for c in candles)


def price_zones(candles):
    """Experimental one-bar base + two-bar departure; no future access beyond prefix.

    A base's full high/low is the zone. Departure requires two closes beyond it
    and a combined move of at least one base range. Subsequent intersections
    count as retests; a close through the distal edge invalidates it.
    """
    zones=[]
    for i in range(len(candles)-2):
        base,a,b=candles[i:i+3];width=base.high-base.low
        if width<=0:continue
        side='DEMAND' if min(a.close,b.close)>base.high and b.close-base.high>=width else 'SUPPLY' if max(a.close,b.close)<base.low and base.low-b.close>=width else None
        if not side:continue
        later=candles[i+3:]
        invalid=any(c.close<base.low if side=='DEMAND' else c.close>base.high for c in later)
        retests=sum(c.low<=base.high and c.high>=base.low for c in later)
        zones.append({'kind':side,'low':base.low,'high':base.high,'base_timestamp':base.timestamp.isoformat(),'known_at':b.timestamp.isoformat(),'retests':retests,'state':'INVALIDATED' if invalid else 'RETESTED' if retests else 'FRESH','version':'base-two-departure-1','validation_status':'EXPERIMENTAL'})
    return zones[-20:]


class ResearchPipeline:
    def analyze(self,candles,*,as_of,timeframe='1d',index_candles=(),sector_candles=(),maximum_age=timedelta(days=4),adjustment_status='UNKNOWN'):
        candles=validate_series(candles,as_of,maximum_age)
        index=MarketContextEngine().analyze(validate_series(index_candles,as_of,maximum_age)) if index_candles else None
        sector=MarketContextEngine().analyze(validate_series(sector_candles,as_of,maximum_age)) if sector_candles else None
        if index and index.instrument==candles[0].symbol:raise ValueError('Index context must be a distinct instrument')
        if sector and sector.instrument==candles[0].symbol:raise ValueError('Sector context must be a distinct instrument')
        analysis=UnderlyingAnalysisEngine().analyze(candles,index)
        strategies=MultiStrategyEngine().analyze(candles,analysis,index) if analysis.is_fresh else ()
        confluence=ConfluenceEngine().analyze(analysis,strategies,index) if strategies else None
        blockers=[]
        if not analysis.is_fresh:blockers.append('UNDERLYING_DATA_STALE')
        direction='LONG' if analysis.price>analysis.ema50>analysis.ema200 else 'SHORT' if analysis.price<analysis.ema50<analysis.ema200 else 'NEUTRAL'
        for label,context in [('INDEX',index),('SECTOR',sector)]:
            if not context:blockers.append(label+'_MISSING');continue
            if not context.is_fresh:blockers.append(label+'_STALE')
            aligned=(context.price>context.ema20>context.ema50) if direction=='LONG' else (context.price<context.ema20<context.ema50) if direction=='SHORT' else False
            if not aligned:blockers.append(label+'_NOT_ALIGNED')
        if adjustment_status=='UNKNOWN':blockers.append('ADJUSTMENT_UNKNOWN')
        if direction=='NEUTRAL':blockers.append('UNDERLYING_NOT_TRENDING')
        chart=render_chart(candles,timeframe,adjustment_status)
        return {'analysis_id':chart['metadata']['artifact_id'],'engine_version':ENGINE_VERSION,'as_of':as_of.isoformat(),'source':analysis.source,'data_timestamp':analysis.timestamp.isoformat(),'data_mode':'SUPPLIED_SNAPSHOT','live':False,'direction':direction,'technical_filter_passed':not blockers,'blockers':blockers,'analysis':asdict(analysis),'index':asdict(index) if index else None,'sector':asdict(sector) if sector else None,'strategies':strategies,'confluence':confluence,'atr14':atr(candles),'zones':price_zones(candles),'chart':chart,'warnings':['Snapshot analysis only; not an order approval.','News, contract freshness and liquidity require separate validation.','Zone detector is experimental; precision/recall validation remains open.']}

    def scan(self,items,*,as_of,timeframe='1d',index_candles=(),maximum_age=timedelta(days=4)):
        if not 1<=len(items)<=100:raise ValueError('Scanner accepts 1..100 supplied instruments per batch')
        results=[]
        for item in items:
            symbol=item.get('symbol','UNKNOWN')
            try:
                result=self.analyze(item['candles'],as_of=as_of,timeframe=timeframe,index_candles=index_candles,sector_candles=item.get('sector_candles',()),maximum_age=maximum_age,adjustment_status=item.get('adjustment_status','UNKNOWN'))
                if result['analysis']['instrument']!=symbol:raise ValueError('Requested symbol does not match candle identity')
                result.pop('chart');results.append({'symbol':symbol,'status':'ANALYZED','result':result})
            except (ValueError,KeyError,TypeError):results.append({'symbol':symbol,'status':'DATA_REJECTED','result':None})
        return {'as_of':as_of.isoformat(),'universe_source':'USER_SUPPLIED','universe_verified_active_fno':False,'results':results,'total':len(results),'technical_pass_count':sum(bool(r['result'] and r['result']['technical_filter_passed']) for r in results)}
