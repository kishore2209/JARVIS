import { jsx as _jsx } from "react/jsx-runtime";
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from './main';
vi.mock(import('./api/client'), () => ({ api: vi.fn(async () => ({ status: 'OK', message: 'F&O DATA NOT AVAILABLE' })) }));
afterEach(cleanup);
describe('JARVIS UI', () => {
    it('renders dashboard safety and diagnostics state', async () => { render(_jsx(App, {})); expect(screen.getByText('LIVE EXECUTION: UNSUPPORTED')).toBeTruthy(); await waitFor(() => expect(screen.getByText(/F&O DATA NOT AVAILABLE/)).toBeTruthy()); });
    it('sends one chat request and preserves Telugu text', async () => { render(_jsx(App, {})); fireEvent.click(screen.getByText('Chat')); const input = screen.getByLabelText('Message'); fireEvent.change(input, { target: { value: 'నా portfolio చూపించు' } }); fireEvent.click(screen.getByText('Send')); await waitFor(() => expect(screen.getByDisplayValue('నా portfolio చూపించు')).toBeTruthy()); });
    it('shows analysis, paper, backtest and automation safety views', () => { render(_jsx(App, {})); fireEvent.click(screen.getByText('Analysis')); expect(screen.getByText('Full Analysis')).toBeTruthy(); fireEvent.click(screen.getByText('Paper Trading')); expect(screen.getByText(/PAPER TRADING only/)).toBeTruthy(); fireEvent.click(screen.getByText('Backtests')); expect(screen.getByText(/HISTORICAL REPLAY/)).toBeTruthy(); fireEvent.click(screen.getByText('Automation')); expect(screen.getByText('Run Tick')).toBeTruthy(); });
});
