import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { HistoricalDataPanel, HistoricalChart } from './HistoricalDataPanel';
import { api } from '../api/client';
vi.mock('../api/client', () => ({api: vi.fn()}));
afterEach(() => {cleanup(); vi.clearAllMocks();});
describe('Historical file workflow', () => {
  it('submits file content and selected interval', async () => {
    vi.mocked(api).mockResolvedValue({status:'OK'});
    const done=vi.fn(); render(<HistoricalDataPanel onResult={done}/>);
    const file=new File(['[]'],'history.csv',{type:'text/csv'});
    Object.defineProperty(file,'text',{value:async ()=>'symbol,exchange,timestamp,open,high,low,close,volume,source'});
    fireEvent.change(screen.getByLabelText('Candle interval'),{target:{value:'1d'}});
    fireEvent.change(screen.getByLabelText('Candle file'),{target:{files:[file]}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Analyse candle file'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button',{name:'Analyse candle file'}));
    await waitFor(()=>expect(done).toHaveBeenCalled());
    const args=vi.mocked(api).mock.calls[0];
    expect(args[0]).toBe('/api/v1/analysis/file');
    expect(JSON.parse(String(args[1]?.body))).toMatchObject({format:'csv',interval:'1d'});
    expect(String(args[1]?.body)).not.toContain('history.csv');
  });
  it('blocks oversized input before submitting', async () => {
    render(<HistoricalDataPanel onResult={vi.fn()}/>);
    const file=new File([''],'large.json');Object.defineProperty(file,'size',{value:5000001});
    fireEvent.change(screen.getByLabelText('Candle file'),{target:{files:[file]}});
    expect(await screen.findByRole('alert')).toHaveTextContent('5 MB');
    expect(api).not.toHaveBeenCalled();
  });
  it('labels charts as historical and unverified', () => {
    render(<HistoricalChart data={{provenance:{symbol:'TEST',interval:'15m',declared_source:'FIXTURE',data_timestamp:'2026-01-02T04:00:00Z',content_sha256:'abc'},chart_candles:[{timestamp:'2026-01-02T04:00:00Z',open:100,high:102,low:99,close:101}]}}/>);
    expect(screen.getByRole('img')).toHaveAttribute('aria-label','Historical OHLC candlestick chart');
    expect(screen.getByText(/NOT LIVE/)).toBeInTheDocument();
    expect(screen.getByText(/Declared source: FIXTURE/)).toBeInTheDocument();
  });
});
