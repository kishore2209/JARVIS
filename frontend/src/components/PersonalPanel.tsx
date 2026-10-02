import React, {useState} from 'react';
import {api} from '../api/client';

type Kind = 'balances'|'expenses'|'budgets'|'bills'|'goals'|'tasks'|'events'|'notes'|'drafts';
type Item = Record<string, unknown>;
const labels: Record<Kind,string> = {balances:'Accounts & investments',expenses:'Expenses',budgets:'Budgets',bills:'Bills & EMIs',goals:'Savings goals',tasks:'Tasks & reminders',events:'Calendar',notes:'Notes',drafts:'Message drafts'};
const fields: Record<Kind,string[]> = {balances:['name','kind','value'],expenses:['account_id','amount','category','description'],budgets:['category','month','limit'],bills:['title','amount','due_at','kind'],goals:['title','target','saved','due_at'],tasks:['title','due_at','kind','recurrence_days'],events:['title','start_at','end_at'],notes:['title','body'],drafts:['title','body','recipient','channel']};
const choices: Record<string,string[]> = {'balances.kind':['CASH','INVESTMENT','MUTUAL_FUND','LIABILITY'],'bills.kind':['BILL','EMI'],'tasks.kind':['TASK','REMINDER','LEARNING','HABIT'],'drafts.channel':['MESSAGE','EMAIL']};
const title = (s:string) => s.replace(/_/g,' ').replace(/^./,c=>c.toUpperCase());
export function PersonalPanel({domain}:{domain:'finance'|'life'}) {
 const kinds:Kind[] = domain==='finance'?['balances','expenses','budgets','bills','goals']:['tasks','events','notes','drafts'];
 const [kind,setKind]=useState<Kind>(kinds[0]);
 const [values,setValues]=useState<Record<string,string>>({});
 const [records,setRecords]=useState<Item[]>([]);
 const [summary,setSummary]=useState<Item|null>(null);
 const [message,setMessage]=useState('');
 const [busy,setBusy]=useState(false);
 const [edit,setEdit]=useState<Item|null>(null);
 const refresh=async (selected=kind) => {const r=await api('/api/v1/personal/'+selected);if(r.status==='ERROR')throw new Error(r.message||r.code);setRecords(r.records||[]);};
 const action=async (fn:()=>Promise<void>) => {setBusy(true);try{await fn();}catch(e){setMessage(e instanceof Error?e.message:'Request failed');}finally{setBusy(false);}};
 const save=async () => {
  const payload:Item={id:edit?.id||crypto.randomUUID(),source:'USER_ENTERED',observed_at:new Date().toISOString()};
  for(const key of fields[kind]) {
   const v=values[key]||choices[kind+'.'+key]?.[0]||'';
   if(key==='recurrence_days'){payload[key]=v?Number(v):null;continue;}
   if(key.endsWith('_at')){payload[key]=new Date(v).toISOString();continue;}
   payload[key]=v;
  }
  if(edit&&kind==='tasks')payload.status=edit.status;
  if(edit&&kind==='bills')payload.paid=edit.paid;
  const r=await api('/api/v1/personal/'+kind+(edit?'?expected_version='+edit.version:''),{method:'POST',body:JSON.stringify(payload)});
  if(r.status==='ERROR'||r.detail)throw new Error(r.message||r.code||'Check the fields and try again.');
  setMessage('Saved locally.');setValues({});setEdit(null);await refresh();
 };
 return <div className="panel"><p>{domain==='finance'?'Track user-entered balances, spending, bills and savings. Accounts are not connected.':'Plan your day, track recurring tasks, and prepare drafts. Drafts are never sent automatically.'}</p>
  <div className="actions"><button disabled={busy} onClick={()=>action(async()=>{const r=await api('/api/v1/personal/'+(domain==='finance'?'finance-summary':'daily-plan'));if(r.status==='ERROR')throw new Error(r.code);setSummary(r.result);})}>{domain==='finance'?'Financial overview':'Today’s plan'}</button></div>
  {summary&&domain==='finance'&&<div><h3>Covered net worth: ₹{String(summary.covered_net_worth)}</h3><p>Assets ₹{String(summary.assets)} · Liabilities ₹{String(summary.liabilities)} · Expenses this month ₹{String(summary.monthly_expenses)}</p><p>Coverage: {String(summary.completeness)}. Stale, disconnected and missing balances are excluded.</p></div>}
  {summary&&domain==='life'&&<div><h3>{String(summary.date)}</h3><p>{(summary.tasks as Item[]).length} due tasks · {(summary.events as Item[]).length} events · {(summary.conflicts as unknown[]).length} calendar conflicts</p>{(summary.tasks as Item[]).map(t=><p key={String(t.id)}>{String(t.title)} — {new Date(String(t.due_at)).toLocaleString()}</p>)}</div>}
  <label>Record type<select value={kind} onChange={e=>{const k=e.target.value as Kind;setKind(k);setValues({});setEdit(null);setRecords([]);setMessage('');}}>{kinds.map(k=><option value={k} key={k}>{labels[k]}</option>)}</select></label>
  {fields[kind].map(key=><label key={key}>{title(key)}{choices[kind+'.'+key]?<select aria-label={title(key)} value={values[key]||choices[kind+'.'+key][0]} onChange={e=>setValues({...values,[key]:e.target.value})}>{choices[kind+'.'+key].map(c=><option key={c}>{c}</option>)}</select>:key==='body'?<textarea aria-label={title(key)} value={values[key]||''} onChange={e=>setValues({...values,[key]:e.target.value})}/>:<input aria-label={title(key)} type={key.endsWith('_at')?'datetime-local':key==='month'?'month':'text'} value={values[key]||''} onChange={e=>setValues({...values,[key]:e.target.value})}/>}</label>)}
  <div className="actions"><button disabled={busy} onClick={()=>action(save)}>{edit?'Save changes':'Add record'}</button><button disabled={busy} onClick={()=>action(()=>refresh())}>Refresh records</button>{edit&&<button onClick={()=>{setEdit(null);setValues({});}}>Cancel edit</button>}</div>
  <p role="status">{busy?'Working…':message}</p>
  {records.map(r=><div className="memory-row" key={String(r.id)}><strong>{String(r.name||r.title||r.category||r.id)}</strong><span>{String(r.value||r.amount||r.target||r.body||r.status||'')}</span><small>{String(r.source)} · {new Date(String(r.observed_at)).toLocaleString()}</small><button disabled={busy} onClick={()=>{setEdit(r);const v:Record<string,string>={};for(const f of fields[kind]){v[f]=String(r[f]??'');if(f.endsWith('_at')&&r[f]){const d=new Date(String(r[f]));v[f]=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}}setValues(v);}}>Edit</button>{kind==='tasks'&&r.status==='OPEN'&&<button disabled={busy} onClick={()=>action(async()=>{const result=await api('/api/v1/personal/tasks/'+r.id+'/complete?expected_version='+r.version,{method:'POST'});if(result.status==='ERROR')throw new Error(result.message);await refresh();})}>Complete</button>}<button disabled={busy} onClick={()=>action(async()=>{if(!window.confirm('Delete this local record?'))return;const result=await api('/api/v1/personal/'+kind+'/'+r.id+'?expected_version='+r.version,{method:'DELETE'});if(result.status==='ERROR')throw new Error(result.message);await refresh();})}>Delete</button></div>)}
 </div>;
}
