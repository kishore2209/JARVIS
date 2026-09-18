import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const labels = {
    instrument: 'Instrument', timestamp: 'Timestamp', is_fresh: 'Freshness', trend: 'Trend',
    directional_bias: 'Confluence bias', evidence_quality: 'Evidence quality', bullish_score: 'Bullish score',
    bearish_score: 'Bearish score', net_evidence_score: 'Net score', market_context_alignment: 'Alignment',
    data_completeness: 'Completeness', total_equity: 'Equity', available_cash: 'Cash',
    capital_in_use: 'Capital in use', realized_pnl: 'Realized P&L', unrealized_pnl: 'Unrealized P&L',
    long_exposure: 'Long exposure', short_exposure: 'Short exposure', gross_exposure: 'Gross exposure',
    net_exposure: 'Net exposure', open_position_count: 'Open positions', total_trades: 'Total trades',
    winning_trades: 'Wins', losing_trades: 'Losses', net_pnl: 'Net P&L', total_return_percent: 'Return',
    maximum_drawdown: 'Max drawdown', profit_factor: 'Profit factor', expectancy: 'Expectancy',
};
export function LoadingState() { return _jsx("p", { role: "status", children: "LOADING..." }); }
export function EmptyState() { return _jsx("p", { className: "empty", children: "NOT_AVAILABLE" }); }
export function ResultPanel({ data }) {
    const result = (data.result || data.structured_result || data);
    if (!Object.keys(result).length)
        return _jsx(EmptyState, {});
    const analysis = (result.underlying_analysis || result.market_context || result);
    const confluence = result.confluence_analysis;
    const portfolio = result.portfolio_analysis;
    const backtest = result.backtest_result;
    const source = portfolio || backtest || analysis;
    const fields = Object.keys(labels).filter(key => source[key] !== undefined).map(key => _jsxs("div", { className: "metric", children: [_jsx("small", { children: labels[key] }), _jsx("strong", { children: String(source[key]) })] }, key));
    const strategies = (result.strategy_evidence || []);
    return _jsxs("div", { className: "result", children: [_jsx("div", { className: "metrics", children: fields }), Boolean(result.message) && _jsx("p", { className: "empty", children: String(result.message) }), confluence && _jsxs("section", { children: [_jsx("h3", { children: "Confluence" }), _jsx("div", { className: "metrics", children: Object.keys(labels).filter(key => confluence[key] !== undefined).map(key => _jsxs("div", { className: "metric", children: [_jsx("small", { children: labels[key] }), _jsx("strong", { children: String(confluence[key]) })] }, key)) })] }), strategies.length > 0 && _jsxs("section", { children: [_jsx("h3", { children: "Strategy Evidence" }), _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Strategy" }), _jsx("th", { children: "Direction" }), _jsx("th", { children: "Strength" })] }) }), _jsx("tbody", { children: strategies.map((item, index) => _jsxs("tr", { children: [_jsx("td", { children: String(item.strategy_name) }), _jsx("td", { children: String(item.direction) }), _jsx("td", { children: String(item.evidence_strength) })] }, index)) })] })] }), Boolean(result.warnings) && String(result.warnings).includes('FNO_DATA') && _jsx("p", { className: "empty", children: "F&O DATA NOT AVAILABLE" })] });
}
