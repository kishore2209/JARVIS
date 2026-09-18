import {afterEach,describe,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {ResultPanel} from './ResultPanel';
afterEach(cleanup);
describe('ResultPanel',()=>{
 it('renders backend portfolio values without recalculation',()=>{render(<ResultPanel data={{result:{portfolio_analysis:{total_equity:'100500',available_cash:'90000',capital_in_use:'10000',realized_pnl:'500',unrealized_pnl:'100',long_exposure:'10000',short_exposure:'0',gross_exposure:'10000',net_exposure:'10000',open_position_count:1}}}}/>);expect(screen.getByText('100500')).toBeTruthy();expect(screen.getByText('Open positions')).toBeTruthy()});
 it('renders historical replay metrics returned by backend',()=>{render(<ResultPanel data={{result:{backtest_result:{execution_mode:'HISTORICAL_REPLAY',total_trades:2,winning_trades:1,losing_trades:1,net_pnl:'50',total_return_percent:'0.05',maximum_drawdown:'20',profit_factor:'1.5',expectancy:'25'}}}}/>);expect(screen.getByText('HISTORICAL_REPLAY')).toBeTruthy();expect(screen.getByText('50')).toBeTruthy()});
 it('renders safe backend messages and empty state',()=>{const {rerender}=render(<ResultPanel data={{message:'Request unavailable.'}}/>);expect(screen.getByText('Request unavailable.')).toBeTruthy();rerender(<ResultPanel data={{}}/>);expect(screen.getByText('NOT_AVAILABLE')).toBeTruthy()});
 it('uses accessible table headings for strategy evidence',()=>{render(<ResultPanel data={{result:{strategy_evidence:[{strategy_name:'TREND',direction:'BULLISH',evidence_strength:'HIGH'}]}}}/>);expect(screen.getByRole('columnheader',{name:'Strategy'})).toBeTruthy()});
});