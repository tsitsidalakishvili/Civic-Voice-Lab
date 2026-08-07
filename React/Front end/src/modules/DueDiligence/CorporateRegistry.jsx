import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  IconAlertTriangle,
  IconBuilding,
  IconCheck,
  IconClock,
  IconExternalLink,
  IconFileSearch,
  IconRefresh,
  IconShieldCheck,
} from '@tabler/icons-react'
import { getJson, requestJson } from '../../services/api'

const fmt = (value) => {
  if (!value) return 'Not available'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}
const pretty = (value) => String(value || '').replaceAll('-', ' ').replaceAll('_', ' ')

function AuthorityBadge({ level }) {
  return <span className={`corp-authority is-${level || 'unknown'}`}>{level === 'authoritative' ? <IconShieldCheck size={12}/> : <IconFileSearch size={12}/>} {pretty(level || 'unknown authority')}</span>
}

function RegistryState({ state }) {
  const normalized = state || 'unknown'
  return <span className={`corp-state is-${normalized}`}>{pretty(normalized)}</span>
}

export function CorporateRegistrySources({ caseId, onEnriched }) {
  const [capabilities, setCapabilities] = useState(null)
  const [sourcePayload, setSourcePayload] = useState(null)
  const [adapters, setAdapters] = useState([])
  const [identificationCode, setIdentificationCode] = useState('')
  const [forceRefresh, setForceRefresh] = useState(false)
  const [loading, setLoading] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const load = useCallback(async () => {
    if (!caseId) return
    setLoading(true); setError('')
    try {
      const [capabilityPayload, sources, adapterPayload] = await Promise.all([
        getJson('/due-diligence/connectors/georgian-company-registry/capabilities', { forceRefresh: true }),
        getJson(`/due-diligence/cases/${caseId}/corporate-enrichment/sources`, { forceRefresh: true }),
        getJson('/due-diligence/source-adapters', { forceRefresh: true }),
      ])
      setCapabilities(capabilityPayload)
      setSourcePayload(sources)
      setAdapters(Array.isArray(adapterPayload) ? adapterPayload : adapterPayload?.adapters || [])
    } catch (err) { setError(err.message || 'Unable to load registry source status.') }
    finally { setLoading(false) }
  }, [caseId])

  useEffect(() => { load() }, [load])

  const runEnrichment = async (refresh = forceRefresh) => {
    setEnriching(true); setError(''); setResult(null)
    try {
      const graph = await requestJson(`/due-diligence/cases/${caseId}/corporate-enrichment/companyinfo`, { method: 'POST', payload: { identificationCode, forceRefresh: refresh } })
      setResult(graph.enrichmentResult || null)
      await load()
      onEnriched?.(graph)
    } catch (err) { setError(err.message || 'Corporate enrichment failed.') }
    finally { setEnriching(false) }
  }

  const submit = (event) => { event.preventDefault(); runEnrichment() }

  const companyinfo = capabilities?.companyinfo
  const napr = capabilities?.napr
  const enabled = Boolean(companyinfo?.enabled)
  const sources = sourcePayload?.sources || []
  const governanceAdapters = adapters.filter((adapter) => ['companyinfo-ge', 'napr-manual-verification'].includes(adapter.adapterId))

  return <section className="corp-sources">
    <div className="corp-sources__heading"><div><span className="dd-card-kicker">Georgian company registry</span><h3>Corporate enrichment</h3><p>Identification-code lookup through governed backend adapters. The browser never contacts Companyinfo or NAPR directly.</p></div><button className="button-secondary" type="button" onClick={load} disabled={loading}><IconRefresh size={15}/>{loading?'Loading…':'Refresh status'}</button></div>
    {error ? <div className="module-alert">{error}</div> : null}
    <div className="corp-source-grid">{sources.map((source)=><article key={source.sourceId} className={`corp-source is-${source.authorityLevel}`}><div className="corp-source__top"><AuthorityBadge level={source.authorityLevel}/><RegistryState state={source.rateLimitState}/></div><h4>{source.name}</h4><p>{source.sourceType}</p><dl><div><dt>Freshness</dt><dd>{pretty(source.freshness?.state)} · {source.freshness?.cadence}</dd></div><div><dt>Source updated</dt><dd>{fmt(source.sourceUpdatedAt || source.freshness?.sourceUpdatedAt)}</dd></div><div><dt>Last attempt</dt><dd>{fmt(source.lastAttemptAt)}</dd></div><div><dt>Last success</dt><dd>{fmt(source.lastSuccessAt)}</dd></div><div><dt>Records / jobs</dt><dd>{source.recordCount || 0} / {source.jobCount || 0}</dd></div><div><dt>Errors</dt><dd>{source.errorCount || 0}</dd></div></dl><div className="corp-caveat"><IconAlertTriangle size={14}/>{source.caveat}</div></article>)}</div>
    <div className="corp-governance"><div><strong>Authority model</strong><span><b>NAPR</b> is the controlling official record. <b>Companyinfo</b> is a secondary, monthly-refreshed aggregator and never overrides an official statement.</span></div><div><strong>Personal identifiers</strong><span>Not accepted from the browser, returned by the API, or stored raw.</span></div>{governanceAdapters.length?<details><summary>Adapter governance and access rules ({governanceAdapters.length})</summary><div>{governanceAdapters.map(adapter=><article key={adapter.adapterId}><strong>{adapter.name || adapter.adapterId}</strong><span>{pretty(adapter.authorityLevel || adapter.governance?.authorityLevel)} · {pretty(adapter.access?.mode || adapter.accessMode || adapter.governance?.accessMode)}</span><small>{adapter.license?.name || adapter.license || adapter.governance?.license?.name || adapter.governance?.license || 'Licence not specified'} · {adapter.permissionState || adapter.governance?.permissionState || 'Permission state unknown'}</small></article>)}</div></details>:null}</div>
    <form className="corp-enrich-form" onSubmit={submit}><div><span className="dd-card-kicker">Backend-only lookup</span><h4>Enrich a Georgian company</h4><p>Enter the public company identification code—not a person’s identification number.</p></div><label>Company identification code<input inputMode="numeric" pattern="[0-9]{9,11}" minLength="9" maxLength="11" required value={identificationCode} onChange={(e)=>setIdentificationCode(e.target.value.replace(/\D/g,'').slice(0,11))} placeholder="9–11 digits" /></label><label className="corp-checkbox"><input type="checkbox" checked={forceRefresh} onChange={(e)=>setForceRefresh(e.target.checked)}/>Bypass the 24-hour cache</label><button className="button" type="submit" disabled={!enabled||enriching}>{enriching?'Enriching…':'Enrich company'}</button>{!enabled?<div className="corp-permission-state"><IconAlertTriangle size={15}/><div><strong>Lookup disabled by permission policy</strong><span>{pretty(companyinfo?.permissionState)}. {companyinfo?.caveat}</span></div></div>:null}</form>
    {result?<div className={`corp-enrichment-result is-${result.status}`}><IconCheck size={18}/><div><strong>{pretty(result.status)} enrichment</strong><span>{result.counts?.entityCount || 0} entities · {result.counts?.relationshipCount || 0} relationships · {result.counts?.evidenceCount || 0} evidence records</span>{result.errors?.map((item, index)=><small key={`${item.stage}-${index}`}>{pretty(item.stage)}: {item.message}</small>)}<small>{result.caveat}</small>{result.retryable?<button className="button-secondary" type="button" disabled={enriching} onClick={()=>runEnrichment(true)}>Retry enrichment</button>:null}</div></div>:null}
    {napr?<div className="corp-napr-note"><IconShieldCheck size={17}/><span><strong>NAPR verification is manual and authoritative.</strong> No automated scraping, CAPTCHA bypass, or authenticated access is performed. <a href={napr.url} target="_blank" rel="noreferrer">Open official registry <IconExternalLink size={12}/></a></span></div>:null}
  </section>
}

export function CorporateRegistryDossier({ caseId, entityId }) {
  const [dossier, setDossier] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [verification, setVerification] = useState({ status: 'verified', officialUrl: 'https://enreg.reestri.gov.ge/main.php?m=new_index', sourceDocumentUrl: '', registrationNumber: '', verifiedBy: '', notes: '', comparedFields: {} })

  const load = useCallback(async () => {
    if (!caseId || !entityId) return
    setLoading(true); setError('')
    try { setDossier(await getJson(`/due-diligence/cases/${caseId}/entities/${entityId}/corporate-registry`, { forceRefresh: true })) }
    catch (err) { setError(err.message || 'Unable to load corporate registry dossier.') }
    finally { setLoading(false) }
  }, [caseId, entityId])
  useEffect(() => { setDossier(null); load() }, [load])

  const submitVerification = async (event) => {
    event.preventDefault(); setVerifying(true); setError('')
    try { setDossier(await requestJson(`/due-diligence/cases/${caseId}/entities/${entityId}/corporate-registry/napr-verification`, { method:'POST', payload: verification })) }
    catch (err) { setError(err.message || 'Unable to record NAPR verification.') }
    finally { setVerifying(false) }
  }

  const company = dossier?.company || {}
  const hasRegistryProfile = Boolean(company.identificationCode || company.registrationNumber || company.fetchedAt || company.sourceUrl)
  const currentAffiliations = useMemo(() => (dossier?.affiliations || []).filter((item)=>item.current !== false), [dossier])
  const historicalAffiliations = useMemo(() => (dossier?.affiliations || []).filter((item)=>item.current === false), [dossier])
  if (loading && !dossier) return <div className="corp-dossier-loading"><IconClock size={16}/>Loading corporate registry dossier…</div>
  if (error && !dossier) return <div className="module-alert">{error}</div>
  if (!dossier) return null

  return <section className="corp-dossier">
    <div className="corp-dossier__header"><div><span className="dd-card-kicker">Corporate registry</span><h3>{hasRegistryProfile ? company.displayName : 'No registry profile'}</h3></div><AuthorityBadge level={hasRegistryProfile ? company.authorityLevel : 'unknown'}/></div>
    <div className="corp-caveat"><IconAlertTriangle size={14}/>{dossier.caveat}</div>
    <dl className="corp-company-facts">{[['Identification code',company.identificationCode],['Registration number',company.registrationNumber],['Legal form',company.legalForm],['Status',company.status],['Registration date',company.registrationDate],['Address',company.address],['Email',company.email],['Source updated',fmt(company.sourceUpdatedAt)],['Fetched',fmt(company.fetchedAt)]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||'Not available'}</dd></div>)}</dl>
    {hasRegistryProfile?<div className="corp-source-line"><AuthorityBadge level={company.authorityLevel || 'secondary'}/><span>Companyinfo snapshot · {fmt(company.fetchedAt)}</span>{company.sourceUrl?<a href={company.sourceUrl} target="_blank" rel="noreferrer">Source <IconExternalLink size={12}/></a>:null}</div>:<p className="muted">No Companyinfo snapshot has been attached to this entity.</p>}
    <h4>Enrichment indicators</h4><div className="corp-indicators">{(dossier.indicators||[]).length?dossier.indicators.map(indicator=><article key={indicator.indicatorId} className={`is-${indicator.status}`}><div><RegistryState state={indicator.status}/><AuthorityBadge level={indicator.authorityLevel}/></div><strong>{indicator.label}</strong><span>{indicator.recordCount || 0} source record{indicator.recordCount===1?'':'s'} · updated {fmt(indicator.sourceUpdatedAt)}</span><small>{indicator.caveat}</small></article>):<p className="muted">No enrichment indicators are available.</p>}</div>
    <h4>Current affiliations</h4><Affiliations rows={currentAffiliations}/>
    <details className="corp-history"><summary>Historical affiliations <span>{historicalAffiliations.length}</span></summary><Affiliations rows={historicalAffiliations}/></details>
    {(dossier.contradictions||[]).length?<section className="corp-contradictions"><h4>Source contradictions requiring review</h4>{dossier.contradictions.map(conflict=><article key={conflict.conflictId}><strong>{pretty(conflict.predicate)}</strong><span>{conflict.preferenceReason}</span>{conflict.statements.map(statement=><div key={statement.statementId}><AuthorityBadge level={statement.authorityLevel}/><b>{statement.value}</b><small>{fmt(statement.publishedAt||statement.retrievedAt)}</small></div>)}</article>)}</section>:null}
    <section className="corp-napr"><div className="corp-napr__status"><AuthorityBadge level="authoritative"/><div><strong>NAPR verification: {pretty(dossier.naprVerification?.status)}</strong><span>Verified {fmt(dossier.naprVerification?.verifiedAt)} by {dossier.naprVerification?.verifiedBy||'not yet reviewed'}</span></div>{dossier.naprVerification?.officialUrl?<a href={dossier.naprVerification.officialUrl} target="_blank" rel="noreferrer">Open NAPR <IconExternalLink size={12}/></a>:null}</div>{company.identificationCode?<details><summary>Record manual NAPR verification</summary><form onSubmit={submitVerification}><label>Status<select value={verification.status} onChange={(e)=>setVerification(v=>({...v,status:e.target.value}))}>{['verified','mismatch','not-found','inconclusive'].map(status=><option key={status} value={status}>{pretty(status)}</option>)}</select></label><label>Official URL<input type="url" required value={verification.officialUrl} onChange={(e)=>setVerification(v=>({...v,officialUrl:e.target.value}))}/></label><label>Source document URL<input type="url" value={verification.sourceDocumentUrl} onChange={(e)=>setVerification(v=>({...v,sourceDocumentUrl:e.target.value}))}/></label><label>Registration number<input value={verification.registrationNumber} onChange={(e)=>setVerification(v=>({...v,registrationNumber:e.target.value}))}/></label><label>Verified by<input required value={verification.verifiedBy} onChange={(e)=>setVerification(v=>({...v,verifiedBy:e.target.value}))}/></label><label>Notes<textarea required rows="3" value={verification.notes} onChange={(e)=>setVerification(v=>({...v,notes:e.target.value}))}/></label><button className="button" type="submit" disabled={verifying}>{verifying?'Saving…':'Save authoritative verification'}</button></form></details>:<p className="muted">This entity has no company identification code, so an authoritative verification cannot be recorded.</p>}</section>
    <div className="corp-privacy"><IconShieldCheck size={15}/><span>Personal identification numbers are not exposed or stored raw.</span></div>
  </section>
}

function Affiliations({ rows }) {
  if (!rows.length) return <p className="muted">No affiliations in this state.</p>
  return <div className="corp-affiliations">{rows.map(item=><article key={item.relationshipId}><div><strong>{item.label}</strong><span>{item.role||item.roleType||'Registry relationship'}</span></div><b>{item.displayName}</b><small>{item.startDate||'Unknown start'} → {item.endDate||'present'}{item.sharePercentage?` · ${item.sharePercentage}%`:''}</small><div><AuthorityBadge level={item.sourceAuthorityLevel}/><RegistryState state={item.verificationStatus}/>{item.sourceDocumentUrl?<a href={item.sourceDocumentUrl} target="_blank" rel="noreferrer">Document <IconExternalLink size={11}/></a>:null}</div></article>)}</div>
}
