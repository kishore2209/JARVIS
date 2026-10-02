import {useEffect, useState} from 'react';
import {api} from '../api/client';
type Row = Record<string, any>;

export function OperationsPanel({view}: {view: 'Knowledge' | 'Tasks' | 'Reviews'}) {
  const [data, setData] = useState<Row>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState('');
  const [source, setSource] = useState('');
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [period, setPeriod] = useState('daily');
  const request = async (path: string, body?: Row, method='POST') => {
    setBusy(true); setError('');
    try {
      const result = await api(path, body ? {method, body: JSON.stringify(body)} : method==='DELETE' ? {method} : {});
      if (result.status === 'ERROR') throw new Error(result.message || result.code);
      setData(result); return result;
    } catch (e) {setError(e instanceof Error ? e.message : 'Request failed.'); return null;}
    finally {setBusy(false);}
  };
  useEffect(() => {void request(view==='Knowledge' ? '/api/v1/knowledge' : view==='Tasks' ? '/api/v1/tasks' : '/api/v1/paper/review');}, [view]);
  return <div className="panel">
    {error && <p role="alert">{error}</p>}
    {view==='Knowledge' && <>
      <p>Save source text explicitly. Search returns cited excerpts; source text cannot authorize tools or trades.</p>
      <label>Document title<input value={title} onChange={e=>setTitle(e.target.value)} maxLength={200}/></label>
      <label>Source reference<input value={source} onChange={e=>setSource(e.target.value)} placeholder="Document name or original URL" maxLength={500}/></label>
      <label>Source text<textarea value={text} onChange={e=>setText(e.target.value)} maxLength={100000} rows={5}/></label>
      <button disabled={busy || !title.trim() || !text.trim() || !source.trim()} onClick={async()=>{
        if(await request('/api/v1/knowledge',{title,source,text})) {setText(''); await request('/api/v1/knowledge');}
      }}>Save document</button>
      <label>Search knowledge<input value={query} onChange={e=>setQuery(e.target.value)} maxLength={2000}/></label>
      <button disabled={busy || !query.trim()} onClick={()=>request('/api/v1/knowledge/search',{query})}>Search sources</button>
      <button disabled={busy} onClick={()=>request('/api/v1/knowledge')}>List documents</button>
      {data.result?.empty && <p>No matching accessible sources. No answer has been inferred.</p>}
      {(data.result?.matches || []).map((match: Row)=><article key={match.citation_id}>
        <h4>{match.title}</h4><p>{match.text}</p><small>{match.source} · Version {match.version} · Citation {match.citation_id}</small>
      </article>)}
      {(data.documents || []).map((doc: Row)=><article key={doc.id}><h4>{doc.title}</h4><p>{doc.source} · Version {doc.version}</p>
        <button disabled={busy} onClick={async()=>{if(window.confirm(`Delete ${doc.title}? Derived documents will no longer be retrievable.`)) {
          await request(`/api/v1/knowledge/${encodeURIComponent(doc.id)}?expected_version=${doc.version}`,undefined,'DELETE'); await request('/api/v1/knowledge');
        }}}>Delete document</button></article>)}
    </>}
    {view==='Tasks' && <>
      <p>Durable read-only tasks need persistence and a running worker. Queued work does not execute in your browser.</p>
      <button disabled={busy} onClick={()=>request('/api/v1/tasks')}>Refresh tasks</button>
      <button disabled={busy} onClick={async()=>{await request('/api/v1/tasks',{kind:'DAILY_PLAN',payload:{},idempotency_key:crypto.randomUUID(),seconds:30,tool_budget:1});}}>Queue daily plan</button>
      {(data.tasks || (data.task ? [data.task] : [])).map((task: Row)=><article key={task.id}><h4>{task.kind} · {task.state}</h4>
        <p>Tools: {task.tools_used}/{task.tool_budget} · Trace: {task.correlation_id}</p>
        <button disabled={busy} onClick={()=>request(`/api/v1/tasks/${task.id}`)}>Show task</button>
        {!['COMPLETED','FAILED','CANCELLED','VALIDATING','SYNTHESIS','ACTING','RECONCILING'].includes(task.state) && <button disabled={busy} onClick={()=>request(`/api/v1/tasks/${task.id}/cancel`,{})}>Cancel task</button>}
        {task.error && <p role="alert">{task.error}</p>}
        {task.result && <pre>{JSON.stringify(task.result,null,2)}</pre>}
        <details><summary>Execution history</summary><pre>{JSON.stringify(task.history,null,2)}</pre></details>
      </article>)}
    </>}
    {view==='Reviews' && <>
      <p>Paper outcomes and declared rule adherence are separate. Missing evidence stays visible.</p>
      <label>Review period<select value={period} onChange={e=>setPeriod(e.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
      <button disabled={busy} onClick={()=>request(`/api/v1/paper/review?period=${period}`)}>Generate review</button>
      {data.result && <><p>Closed trades: {data.result.metrics.sample_size} · Realized P&amp;L before costs: ₹{data.result.metrics.realized_pnl_before_costs}</p>
        {(data.result.warnings || []).map((warning: string)=><p key={warning}>{warning}</p>)}
        <pre>{JSON.stringify(data.result,null,2)}</pre></>}
    </>}
  </div>;
}
