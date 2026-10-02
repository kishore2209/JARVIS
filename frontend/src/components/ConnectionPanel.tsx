import {useState} from 'react';
import {api, setOwnerToken} from '../api/client';

export function ConnectionPanel() {
  const [token, setToken] = useState('');
  const [message, setMessage] = useState('Local access works without a token. Remote access needs HTTPS and the server owner token.');
  const [busy, setBusy] = useState(false);
  return <div className="panel"><h3>Connection</h3><p>No broker PIN or Gemini key belongs here. The owner token stays in this page’s memory and clears on reload.</p>
    <label>Owner access token<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)}/></label>
    <button disabled={busy} onClick={async () => {
      setBusy(true);
      try {setOwnerToken(token); setToken(''); await api('/api/v1/status'); setMessage('Connected.');}
      catch (e) {setOwnerToken(''); setMessage(e instanceof Error ? e.message : 'Connection failed.');}
      finally {setBusy(false);}
    }}>Connect</button>
    <button onClick={() => {setOwnerToken(''); setToken(''); window.location.reload();}}>Disconnect and clear view</button>
    <p role="status">{message}</p>
  </div>;
}
