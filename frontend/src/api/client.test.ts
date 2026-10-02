import {afterEach, describe, expect, it, vi} from 'vitest';
import {api, setOwnerToken} from './client';

afterEach(()=>{setOwnerToken('');vi.unstubAllGlobals();});
describe('owner API connection',()=>{
  it('attaches the owner token and clears it without persistent storage',async()=>{
    const fetcher=vi.fn<typeof fetch>(async()=>new Response(JSON.stringify({status:'OK'}), {headers:{'Content-Type':'application/json'}}));
    vi.stubGlobal('fetch',fetcher);
    const token='owner-test-value-'.repeat(3);
    setOwnerToken(token); await api('/api/v1/status');
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer '+token);
    expect(localStorage.length).toBe(0);expect(sessionStorage.length).toBe(0);
    setOwnerToken('');await api('/api/v1/status');
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).has('Authorization')).toBe(false);
  });
  it('surfaces authentication failure and rejects non-API paths',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:401,json:async()=>({code:'AUTHENTICATION_REQUIRED'})})));
    await expect(api('/api/v1/tasks')).rejects.toThrow('Owner access token required');
    await expect(api('https://outside.example')).rejects.toThrow('Invalid API path');
  });
});
