"""Deterministic SVG candle/volume/EMA snapshots with immutable content IDs."""
from datetime import datetime
import hashlib
from html import escape
import json
from math import isfinite

RENDER_VERSION = 'candles-svg-1'


def render_chart(candles, timeframe, adjustment_status='UNKNOWN'):
    if not candles or len(candles) > 500: raise ValueError('Chart requires 1..500 candles')
    if timeframe not in {'1m','3m','5m','15m','30m','1h','1d','1w'}: raise ValueError('Invalid timeframe')
    if adjustment_status not in {'RAW','ADJUSTED','UNKNOWN'}: raise ValueError('Invalid adjustment status')
    first = candles[0]
    last_time = None
    for c in candles:
        if (c.symbol,c.exchange,c.source)!=(first.symbol,first.exchange,first.source): raise ValueError('Mixed chart series')
        if c.timestamp.tzinfo is None or last_time and c.timestamp <= last_time: raise ValueError('Candles must have unique ordered aware timestamps')
        if not all(isfinite(float(x)) for x in (c.open,c.high,c.low,c.close,c.volume)) or min(c.open,c.close,c.low) <= 0 or c.volume < 0 or c.low > min(c.open,c.close) or c.high < max(c.open,c.close): raise ValueError('Invalid candle geometry')
        last_time = c.timestamp
    snapshot = [[c.timestamp.isoformat(),c.open,c.high,c.low,c.close,c.volume] for c in candles]
    metadata = {'symbol':first.symbol,'exchange':first.exchange,'source':first.source,'timeframe':timeframe,'data_timestamp':last_time.isoformat(),'adjustment_status':adjustment_status,'render_version':RENDER_VERSION,'data_status':'HISTORICAL_SNAPSHOT','live':False}
    digest = hashlib.sha256(json.dumps([metadata,snapshot],sort_keys=True,allow_nan=False).encode()).hexdigest()
    metadata['artifact_id'] = digest
    metadata['source_snapshot_hash'] = hashlib.sha256(json.dumps(snapshot,allow_nan=False).encode()).hexdigest()
    width,height,left,right,top,bottom=1000,600,70,960,80,440
    low,high=min(c.low for c in candles),max(c.high for c in candles)
    spread=max(high-low,high*.01); low-=spread*.05; high+=spread*.05
    y=lambda price: bottom-(price-low)/(high-low)*(bottom-top)
    step=(right-left)/len(candles); body=max(.5,min(12,step*.65))
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Historical candlestick chart">', '<rect width="1000" height="600" fill="#101826"/>',f'<metadata>{escape(json.dumps(metadata,sort_keys=True))}</metadata>',f'<text x="25" y="28" fill="white" font-family="sans-serif" font-size="18">{escape(first.symbol[:50])} · {timeframe} · HISTORICAL SNAPSHOT</text>', f'<text x="25" y="53" fill="#b7c8da" font-family="sans-serif" font-size="12">{escape(first.source[:50])} · {last_time.isoformat()} · adjustment: {adjustment_status}</text>']
    maxvol=max(max(c.volume for c in candles),1)
    for i in range(5):
        price=low+(high-low)*i/4; py=y(price)
        parts.extend([f'<path d="M {left} {py:.2f} H {right}" stroke="#263446"/>',f'<text x="3" y="{py:.2f}" fill="#b7c8da" font-size="11">{price:.2f}</text>'])
    for i,c in enumerate(candles):
        x=left+(i+.5)*step; color='#44d4ad' if c.close>=c.open else '#ff7c82'
        parts.extend([f'<path d="M {x:.2f} {y(c.high):.2f} V {y(c.low):.2f}" stroke="{color}"/>',f'<rect x="{x-body/2:.2f}" y="{min(y(c.open),y(c.close)):.2f}" width="{body:.2f}" height="{max(1,abs(y(c.open)-y(c.close))):.2f}" fill="{color}"/>',f'<rect x="{x-body/2:.2f}" y="{550-c.volume/maxvol*80:.2f}" width="{body:.2f}" height="{c.volume/maxvol*80:.2f}" fill="{color}"/>'])
    for period,color in [(20,'#f4c95d'),(50,'#88aaff'),(200,'#dba0ff')]:
        if len(candles)<period: continue
        value=sum(c.close for c in candles[:period])/period; points=[]
        for i in range(period-1,len(candles)):
            if i>=period:value+=(candles[i].close-value)*2/(period+1)
            points.append(f'{left+(i+.5)*step:.2f},{y(value):.2f}')
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="1.5"/>')
    parts.append('<text x="70" y="582" fill="#b7c8da" font-size="12">Volume · EMA20 gold · EMA50 blue · EMA200 purple · Snapshot is not a live quote</text></svg>')
    return {'metadata':metadata,'svg':''.join(parts)}
