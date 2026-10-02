import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {PersonalPanel} from './PersonalPanel';
import {api} from '../api/client';
vi.mock('../api/client',()=>({api:vi.fn()}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
test('saves a balance with explicit source and never connects an account',async()=>{
 vi.mocked(api).mockResolvedValueOnce({status:'OK',record:{}}).mockResolvedValueOnce({status:'OK',records:[]});
 render(<PersonalPanel domain='finance'/>);
 fireEvent.change(screen.getByLabelText('Name'),{target:{value:'Savings'}});
 fireEvent.change(screen.getByLabelText('Value'),{target:{value:'1500.25'}});
 fireEvent.click(screen.getByText('Add record'));
 await waitFor(()=>expect(api).toHaveBeenCalledTimes(2));
 const payload=JSON.parse(vi.mocked(api).mock.calls[0][1]?.body as string);
 expect(payload.value).toBe('1500.25');expect(payload.source).toBe('USER_ENTERED');expect(payload.kind).toBe('CASH');
});
test('failed writes stay visible',async()=>{
 vi.mocked(api).mockResolvedValueOnce({status:'ERROR',message:'VERSION_CONFLICT'});
 render(<PersonalPanel domain='finance'/>);fireEvent.click(screen.getByText('Add record'));
 await waitFor(()=>expect(screen.getByRole('status').textContent).toBe('VERSION_CONFLICT'));
});
test('draft creation never sends a message',async()=>{
 vi.mocked(api).mockResolvedValue({status:'OK',records:[]});
 render(<PersonalPanel domain='life'/>);
 fireEvent.change(screen.getByLabelText('Record type'),{target:{value:'drafts'}});
 fireEvent.change(screen.getByLabelText('Title'),{target:{value:'Hello'}});
 fireEvent.change(screen.getByLabelText('Body'),{target:{value:'Draft only'}});
 fireEvent.click(screen.getByText('Add record'));
 await waitFor(()=>expect(api).toHaveBeenCalledTimes(2));
 expect(vi.mocked(api).mock.calls[0][0]).toBe('/api/v1/personal/drafts');
 expect(vi.mocked(api).mock.calls.some(c=>c[0].includes('send'))).toBe(false);
});
