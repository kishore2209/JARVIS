type Value = string | number | boolean | null | undefined;
type Data = Record<string, unknown>;

const labels: Record<string, string> = {
  status: 'Status', instrument: 'Instrument', timestamp: 'Timestamp', execution_mode: 'Execution mode', is_fresh: 'Freshness', trend: 'Trend',
  directional_bias: 'Confluence bias', evidence_quality: 'Evidence quality', bullish_score: 'Bullish score',
  bearish_score: 'Bearish score', net_evidence_score: 'Net score', market_context_alignment: 'Alignment',
  data_completeness: 'Completeness', total_equity: 'Equity', available_cash: 'Cash',
  capital_in_use: 'Capital in use', realized_pnl: 'Realized P&L', unrealized_pnl: 'Unrealized P&L',
  long_exposure: 'Long exposure', short_exposure: 'Short exposure', gross_exposure: 'Gross exposure',
  net_exposure: 'Net exposure', open_position_count: 'Open positions', total_trades: 'Total trades',
  winning_trades: 'Wins', losing_trades: 'Losses', net_pnl: 'Net P&L', total_return_percent: 'Return',
  maximum_drawdown: 'Max drawdown', profit_factor: 'Profit factor', expectancy: 'Expectancy',
  requests_total: 'requests_total', requests_failed: 'requests_failed', automation_runs_total: 'automation_runs_total',
  automation_failures: 'automation_failures', paper_orders_total: 'paper_orders_total', backtests_total: 'backtests_total',
  provider_configured: 'provider_configured', persistence_state: 'persistence_state', live_execution_supported: 'live_execution_supported',
  max_jobs: 'max_jobs',
};

function flattenValues(source: Data | undefined): Array<[string, Value]> {
  if (!source) return [];
  return Object.entries(source).flatMap(([key, value]) => {
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      return flattenValues(value as Data).map(([nestedKey, nestedValue]) => [`${key}.${nestedKey}`, nestedValue] as [string, Value]);
    }
    return [[key, value as Value] as [string, Value]];
  });
}

export function LoadingState(){return <p role="status">LOADING...</p>}
export function EmptyState(){return <p className="empty">NOT_AVAILABLE</p>}
export function ResultPanel({data}:{data:Data}){
  const result=(data.result||data.structured_result||data) as Data;
  if (!Object.keys(result).length) return <EmptyState/>;
  const analysis=(result.underlying_analysis||result.market_context||result) as Data;
  const confluence=result.confluence_analysis as Data|undefined;
  const portfolio=result.portfolio_analysis as Data|undefined;
  const backtest=result.backtest_result as Data|undefined;
  const source=portfolio||backtest||analysis;
  const flattenedSource = flattenValues(source);
  const fields=flattenedSource.filter(([key]) => Object.prototype.hasOwnProperty.call(labels, key.replace(/^.*\./, '')) || Object.prototype.hasOwnProperty.call(labels, key)).map(([key, value]) => {
    const keyParts = key.split('.');
    const rawKey = key.includes('.') ? keyParts[keyParts.length - 1] : key;
    return <div className="metric" key={key}><small>{labels[rawKey] ?? rawKey}</small><strong>{String(value)}</strong></div>;
  });
  const strategies=(result.strategy_evidence||[]) as Data[];
  return <div className="result"><div className="metrics">{fields}</div>{Boolean(result.message)&&<p className="empty">{String(result.message)}</p>}{confluence&&<section><h3>Confluence</h3><div className="metrics">{Object.keys(labels).filter(key=>confluence[key]!==undefined).map(key=><div className="metric" key={key}><small>{labels[key]}</small><strong>{String(confluence[key] as Value)}</strong></div>)}</div></section>}{strategies.length>0&&<section><h3>Strategy Evidence</h3><table><thead><tr><th>Strategy</th><th>Direction</th><th>Strength</th></tr></thead><tbody>{strategies.map((item,index)=><tr key={index}><td>{String(item.strategy_name)}</td><td>{String(item.direction)}</td><td>{String(item.evidence_strength)}</td></tr>)}</tbody></table></section>}{Boolean(result.warnings)&&String(result.warnings).includes('FNO_DATA')&&<p className="empty">F&O DATA NOT AVAILABLE</p>}</div>
}