import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {OperationsPanel} from './OperationsPanel';
import {api} from '../api/client';
vi.mock('../api/client',()=>({api:vi.fn()}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

it('shows empty retrieval without an invented answer',async()=>{
  vi.mocked(api).mockResolvedValueOnce({status:'OK',documents:[]}).mockResolvedValueOnce({status:'OK',result:{empty:true,matches:[]}});
  render(<OperationsPanel view="Knowledge"/>);
  await waitFor(()=>expect(api).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByLabelText('Search knowledge'),{target:{value:'position sizing'}});
  await waitFor(()=>expect(screen.getByText('Search sources').hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByText('Search sources'));
  expect(await screen.findByText('No matching accessible sources. No answer has been inferred.')).toBeTruthy();
});

it('cancels a queued task through the exact task endpoint',async()=>{
  vi.mocked(api).mockResolvedValueOnce({status:'OK',tasks:[{id:'task1',kind:'DAILY_PLAN',state:'RECEIVED',history:[]}]}).mockResolvedValueOnce({status:'OK',task:{id:'task1',kind:'DAILY_PLAN',state:'RECEIVED',cancel_requested:true,history:[]}});
  render(<OperationsPanel view="Tasks"/>);
  fireEvent.click(await screen.findByText('Cancel task'));
  await waitFor(()=>expect(api).toHaveBeenLastCalledWith('/api/v1/tasks/task1/cancel',{method:'POST',body:'{}'}));
});
