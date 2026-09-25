import { useState } from 'react';
import { api } from '../api/client';

type Candle = {timestamp: string; open: number; high: number; low: number; close: number};
type Data = Record<string, unknown>;

export function HistoricalDataPanel({onResult}: {onResult: (data: Data) => void}) {
  const [content, setContent] = useState('');
  const [format, setFormat] = useState('json');
  const [interval, setInterval] = useState('15m');
  const [filename, setFilename] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <div className="panel"><h3>Historical candle file</h3>
    <p>Upload 200–10,000 candles in CSV or JSON. This is historical analysis only. File prices are never treated as a live feed.</p>
    <label>Candle interval<select value={interval} onChange={e => setInterval(e.target.value)}>{['1m','3m','5m','15m','30m','1h','1d'].map(x => <option key={x}>{x}</option>)}</select></label>
    <label>Candle file<input type="file" accept=".csv,.json" disabled={busy} onChange={async e => {
      setContent(''); setFilename(''); setError('');
      const file = e.target.files?.[0]; if (!file) return;
      if (file.size > 5000000) {setError('File must be no larger than 5 MB.'); return;}
      try {setContent(await file.text()); setFormat(file.name.toLowerCase().endsWith('.csv') ? 'csv' : 'json'); setFilename(file.name);}
      catch {setError('Could not read this file.');}
    }}/></label>
    <small>Columns: symbol, exchange, timestamp (with timezone), open, high, low, close, volume, source.</small>
    <p>{filename}</p><button disabled={!content || busy} onClick={async () => {
      setBusy(true); setError('');
      try {const result = await api('/api/v1/analysis/file', {method:'POST', body:JSON.stringify({content, format, interval})}); onResult(result);}
      catch {setError('Analysis rejected. Check candle count, timestamp order, interval and OHLC values.');}
      finally {setBusy(false);}
    }}>{busy ? 'Analysing history…' : 'Analyse candle file'}</button>
    {error && <p role="alert">{error}</p>}
  </div>;
}

export function HistoricalChart({data}: {data: Data}) {
  const candles = data.chart_candles as Candle[] | undefined;
  if (!candles?.length) return null;
  const provenance = data.provenance as Data;
  const min = Math.min(...candles.map(c => c.low));
  const max = Math.max(...candles.map(c => c.high));
  const y = (price: number) => 220 - 180 * (price - min) / (max - min || 1);
  const step = 720 / candles.length;
  return <div className="panel"><h3>{String(provenance.symbol)} · {String(provenance.interval)} · Historical candles</h3>
    <p>Declared source: {String(provenance.declared_source)} · Last candle: {String(provenance.data_timestamp)}</p>
    <p>HISTORICAL — NOT LIVE · Source and corporate-action adjustments are not independently verified.</p>
    <svg viewBox="0 0 800 270" role="img" aria-label="Historical OHLC candlestick chart" style={{width:'100%', minHeight:220}}>
      <text x="2" y="35" fill="currentColor" fontSize="12">{max.toFixed(2)}</text><text x="2" y="225" fill="currentColor" fontSize="12">{min.toFixed(2)}</text>
      {candles.map((c,i) => {const x = 70 + i * step; const color = c.close >= c.open ? '#1bbf9c' : '#fb7185'; return <g key={c.timestamp}><title>{`${c.timestamp} O ${c.open} H ${c.high} L ${c.low} C ${c.close}`}</title><line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={color}/><rect x={x - Math.max(1,step*.6)/2} y={Math.min(y(c.open),y(c.close))} width={Math.max(1,step*.6)} height={Math.max(1,Math.abs(y(c.open)-y(c.close)))} fill={color}/></g>;})}
      <text x="70" y="250" fill="currentColor" fontSize="11">{candles[0].timestamp.slice(0,10)}</text><text x="690" y="250" fill="currentColor" fontSize="11">{candles[candles.length-1].timestamp.slice(0,10)}</text>
    </svg><details><summary>Data fingerprint</summary><code style={{overflowWrap:'anywhere'}}>{String(provenance.content_sha256)}</code></details>
  </div>;
}
