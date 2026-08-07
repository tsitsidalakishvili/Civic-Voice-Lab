import { useCallback, useEffect, useMemo, useState } from 'react'
import { IconAlertTriangle, IconBrandFacebook, IconCheck, IconClock, IconExternalLink, IconRefresh, IconShieldLock } from '@tabler/icons-react'
import { getJson, requestJson } from '../../services/api'

const pretty = (value) => String(value || '').replaceAll('-', ' ').replaceAll('_', ' ')
const fmt = (value) => value ? new Date(value).toLocaleString() : 'Not available'

function RunState({ status }) {
  return <span className={`social-run-state is-${status || 'unknown'}`}>{pretty(status || 'unknown')}</span>
}

export function ApifyFacebookConnector({ caseId, onImported }) {
  const [capabilities, setCapabilities] = useState(null)
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [mode, setMode] = useState('runId')
  const [form, setForm] = useState({ identifier: '', maxItems: 50, lawfulBasis: '', investigationPurpose: '', retentionDays: 180, includeTopComments: true, promotePostsToGraph: true })
  const [managed, setManaged] = useState({ groupUrls: '', maxItems: 50, maxTotalChargeUsd: 1, onlyPostsNewerThan: '', lawfulBasis: '', investigationPurpose: '', retentionDays: 180, includeTopComments: true, promotePostsToGraph: true, operatorId: '', confirmed: false })

  const load = useCallback(async () => {
    if (!caseId) return
    setLoading(true); setError('')
    try {
      const [caps, runPayload] = await Promise.all([
        getJson('/due-diligence/connectors/apify-facebook/capabilities', { forceRefresh: true }),
        getJson(`/due-diligence/cases/${caseId}/social/apify-facebook/runs?limit=50`, { forceRefresh: true }).catch(() => []),
      ])
      setCapabilities(caps)
      setRuns(Array.isArray(runPayload) ? runPayload : runPayload?.runs || [])
    } catch (err) { setError(err.message || 'Unable to load the public Facebook connector.') }
    finally { setLoading(false) }
  }, [caseId])

  useEffect(() => { load() }, [load])

  const importExisting = async (event) => {
    event.preventDefault(); setWorking(true); setError(''); setResult(null)
    try {
      const payload = { actorId: capabilities?.actor?.actorId, [mode]: form.identifier.trim(), maxItems: Number(form.maxItems), lawfulBasis: form.lawfulBasis.trim(), investigationPurpose: form.investigationPurpose.trim(), retentionDays: Number(form.retentionDays), includeTopComments: form.includeTopComments, promotePostsToGraph: form.promotePostsToGraph }
      const graph = await requestJson(`/due-diligence/cases/${caseId}/social/import/apify-facebook`, { method: 'POST', payload })
      setResult(graph.importResult); onImported?.(graph); await load()
    } catch (err) { setError(err.message || 'Import failed. No records were added.') }
    finally { setWorking(false) }
  }

  const startManaged = async (event) => {
    event.preventDefault(); setWorking(true); setError(''); setResult(null)
    try {
      const groupUrls = managed.groupUrls.split(/\r?\n/).map((url) => url.trim()).filter(Boolean)
      const run = await requestJson(`/due-diligence/cases/${caseId}/social/apify-facebook/runs`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID(), 'X-FS-Operator-Id': managed.operatorId.trim() }, payload: { actorId: capabilities?.actor?.actorId, groupUrls, maxItems: Number(managed.maxItems), maxTotalChargeUsd: Number(managed.maxTotalChargeUsd), ...(managed.onlyPostsNewerThan ? { onlyPostsNewerThan: managed.onlyPostsNewerThan } : {}), includeTopComments: managed.includeTopComments, promotePostsToGraph: managed.promotePostsToGraph, lawfulBasis: managed.lawfulBasis.trim(), investigationPurpose: managed.investigationPurpose.trim(), retentionDays: Number(managed.retentionDays) } })
      setRuns((rows) => [run, ...rows.filter((row) => row.connectorRunId !== run.connectorRunId)])
    } catch (err) { setError(err.message || 'The managed run was not started.') }
    finally { setWorking(false) }
  }

  const refreshRun = async (run) => {
    setWorking(true); setError('')
    try {
      const updated = await requestJson(`/due-diligence/cases/${caseId}/social/apify-facebook/runs/${run.connectorRunId}/refresh`, { method: 'POST', headers: { 'X-FS-Operator-Id': managed.operatorId.trim() } })
      setRuns((rows) => rows.map((row) => row.connectorRunId === updated.connectorRunId ? updated : row)); onImported?.(updated)
    } catch (err) { setError(err.message || 'Unable to refresh this run.') }
    finally { setWorking(false) }
  }

  const importsEnabled = capabilities?.killSwitch?.importsEnabled !== false && capabilities?.enabled !== false
  const managedEnabled = Boolean(capabilities?.managedRuns?.enabled)
  const maxImport = capabilities?.maxItemsPerImport || 1000
  const maxRun = capabilities?.managedRuns?.maxItemsPerRun || 500
  const maxCharge = capabilities?.managedRuns?.maxRunChargeUsd || 1
  const activeRun = useMemo(() => runs.find((run) => !['completed', 'failed', 'start-failed'].includes(run.status)), [runs])

  return <section className="social-connector">
    <header className="social-connector__header"><div><span className="dd-card-kicker">Discovery source · public content</span><h3><IconBrandFacebook size={19}/> Facebook public-group evidence</h3><p>Import verified output through the Freedom Square backend. Display names are source aliases—not confirmed people—and absence of a result is not evidence.</p></div><button className="button-secondary" type="button" onClick={load} disabled={loading}><IconRefresh size={14}/>{loading ? 'Checking…' : 'Refresh'}</button></header>
    {error?<div className="module-alert"><IconAlertTriangle size={15}/>{error}</div>:null}
    <div className="social-connector__policy"><IconShieldLock size={17}/><span><strong>No Facebook or Apify credentials are collected here.</strong> Public groups only. No private groups, member lists, cookies, discovery mode, or direct browser calls. Raw records are not retained.</span></div>

    <div className="social-connector__meta"><div><span>Actor</span><strong>{capabilities?.actor?.name || 'Not available'}</strong><small>Schema {capabilities?.actor?.schemaVersion || 'unknown'}</small></div><div><span>Import access</span><strong>{importsEnabled ? 'Available' : 'Disabled'}</strong><small>{capabilities?.configured ? 'Server connector configured' : 'Run/dataset import requires server token'}</small></div><div><span>Managed runs</span><strong>{managedEnabled ? 'Allowed' : 'Disabled by policy'}</strong><small>Monthly budget ${capabilities?.managedRuns?.monthlyProjectBudgetUsd ?? '—'}</small></div>{capabilities?.actor?.url?<a href={capabilities.actor.url} target="_blank" rel="noreferrer">Actor information <IconExternalLink size={12}/></a>:null}</div>

    <form className="social-import" onSubmit={importExisting}><div className="social-import__intro"><span className="dd-card-kicker">Free-safe workflow</span><h4>Import an existing successful run</h4><p>Run a small capped job for known public-group URLs in the approved Actor, then paste its run or dataset ID here.</p></div><div className="social-mode" role="group" aria-label="Existing output type"><button type="button" className={mode==='runId'?'is-active':''} onClick={()=>setMode('runId')}>Run ID</button><button type="button" className={mode==='datasetId'?'is-active':''} onClick={()=>setMode('datasetId')}>Dataset ID</button></div><label>{mode==='runId'?'Successful run ID':'Dataset ID'}<input required value={form.identifier} onChange={(e)=>setForm(v=>({...v,identifier:e.target.value}))}/></label><label>Maximum items<input type="number" min="1" max={maxImport} value={form.maxItems} onChange={(e)=>setForm(v=>({...v,maxItems:e.target.value}))}/><small>Backend limit: {maxImport}</small></label><label>Lawful basis<textarea required minLength="10" maxLength="500" rows="2" value={form.lawfulBasis} onChange={(e)=>setForm(v=>({...v,lawfulBasis:e.target.value}))}/></label><label>Case-specific investigation purpose<textarea required minLength="10" maxLength="500" rows="2" value={form.investigationPurpose} onChange={(e)=>setForm(v=>({...v,investigationPurpose:e.target.value}))}/></label><label>Retention days<input type="number" min="7" max="730" value={form.retentionDays} onChange={(e)=>setForm(v=>({...v,retentionDays:e.target.value}))}/></label><div className="social-import__checks"><label><input type="checkbox" checked={form.includeTopComments} onChange={(e)=>setForm(v=>({...v,includeTopComments:e.target.checked}))}/>Include top comments</label><label><input type="checkbox" checked={form.promotePostsToGraph} onChange={(e)=>setForm(v=>({...v,promotePostsToGraph:e.target.checked}))}/>Add posts to graph</label></div><button className="button" disabled={!importsEnabled||working}>{working?'Validating and importing…':'Validate and import evidence'}</button>{!importsEnabled?<p className="muted">Imports are disabled by the server kill switch.</p>:null}</form>

    {result?<section className="social-import-result"><IconCheck size={18}/><div><strong>{result.message || 'Import completed'}</strong><span>{result.itemsAccepted || 0} accepted · {result.itemsRejected || 0} rejected · {result.duplicateItems || 0} duplicates</span><span>{result.entitiesProcessed || 0} entities · {result.relationshipsProcessed || 0} relationships · {result.evidenceProcessed || 0} evidence</span><small>Fetched {fmt(result.fetchedAt)} · expires {fmt(result.retentionExpiresAt)} · {result.truncated?'truncated':'complete within requested cap'}</small>{result.schemaRejectedItems?<small className="is-warning">{result.schemaRejectedItems} diagnostic/schema rows rejected and not treated as evidence.</small>:null}</div></section>:null}

    <details className="social-managed"><summary>Managed paid run <span>{managedEnabled?'available':'disabled'}</span></summary><div className="social-managed__body"><div className="corp-caveat"><IconAlertTriangle size={14}/>{managedEnabled?'Starting a run may incur a charge. Both item and dollar caps are enforced by the backend.':'Managed starts fail closed until the server token, feature flag, case allowlist, operator allowlist and budgets are configured.'}</div>{managedEnabled?<form onSubmit={startManaged}><label>Public group URLs (one per line)<textarea required rows="3" value={managed.groupUrls} onChange={(e)=>setManaged(v=>({...v,groupUrls:e.target.value}))}/></label><label>Maximum posts<input type="number" min="1" max={maxRun} value={managed.maxItems} onChange={(e)=>setManaged(v=>({...v,maxItems:e.target.value}))}/></label><label>Maximum charge (USD)<input type="number" min="0.01" max={maxCharge} step="0.01" value={managed.maxTotalChargeUsd} onChange={(e)=>setManaged(v=>({...v,maxTotalChargeUsd:e.target.value}))}/></label><label>Only posts newer than<input type="date" value={managed.onlyPostsNewerThan} onChange={(e)=>setManaged(v=>({...v,onlyPostsNewerThan:e.target.value}))}/></label><label>Lawful basis<textarea required minLength="10" maxLength="500" value={managed.lawfulBasis} onChange={(e)=>setManaged(v=>({...v,lawfulBasis:e.target.value}))}/></label><label>Investigation purpose<textarea required minLength="10" maxLength="500" value={managed.investigationPurpose} onChange={(e)=>setManaged(v=>({...v,investigationPurpose:e.target.value}))}/></label><label>Retention days<input type="number" min="7" max="730" value={managed.retentionDays} onChange={(e)=>setManaged(v=>({...v,retentionDays:e.target.value}))}/></label><label>Operator ID<input required value={managed.operatorId} onChange={(e)=>setManaged(v=>({...v,operatorId:e.target.value}))}/></label><label className="social-managed__confirm"><input type="checkbox" checked={managed.confirmed} onChange={(e)=>setManaged(v=>({...v,confirmed:e.target.checked}))}/>I confirm these are known public groups and authorize a capped run up to ${managed.maxTotalChargeUsd}.</label><button className="button" disabled={!managed.confirmed||working||Boolean(activeRun)}>Start capped run</button>{activeRun?<small>Another run is active for this case.</small>:null}</form>:null}</div></details>

    <section className="social-runs"><div><h4>Managed run history</h4><span>{runs.length}</span></div>{runs.length?runs.map(run=><article key={run.connectorRunId}><div><RunState status={run.status}/><strong>{run.actor?.name || 'Facebook groups Actor'}</strong><small>{fmt(run.timestamps?.createdAt)} · cap ${run.request?.maxTotalChargeUsd ?? '—'} · {run.request?.maxItems ?? '—'} items</small></div><div><span>{run.import?.itemsAccepted || 0} imported</span><span>${run.usage?.usageTotalUsd || 0} used</span>{run.retryable?<button className="button-secondary" type="button" disabled={working||!managed.operatorId.trim()} onClick={()=>refreshRun(run)}>Refresh / retry</button>:null}</div>{run.error?<p className="module-alert">{run.error.message || pretty(run.error.code)}</p>:null}</article>):<p className="muted">No managed runs have been started for this case.</p>}</section>
  </section>
}
