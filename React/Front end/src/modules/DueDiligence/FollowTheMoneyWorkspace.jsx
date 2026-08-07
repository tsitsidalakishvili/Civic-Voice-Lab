import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCheck,
  IconDatabase,
  IconExternalLink,
  IconFileCheck,
  IconGitMerge,
  IconNetwork,
  IconPlayerPlay,
  IconSearch,
  IconSparkles,
} from '@tabler/icons-react'
import { getJson, requestJson } from '../../services/api'
import { InvestigationGraph } from './InvestigationGraph.jsx'
import { CorporateRegistryDossier, CorporateRegistrySources } from './CorporateRegistry.jsx'
import { ApifyFacebookConnector } from './ApifyFacebookConnector.jsx'

const pct = (value) => `${Math.round((Number(value) || 0) * 100)}%`
const pretty = (value) => String(value || '').replaceAll('-', ' ').replaceAll('_', ' ')
const isSensitivePredicate = (value) => /personal.?id|national.?id|personal.?number|passport/i.test(String(value || ''))

function EmptyCase({ title }) {
  return <div className="module-card module-card__wide ftm-empty"><IconNetwork size={34} /><h3>{title}</h3><p className="muted">Select a case above to open its sourced investigation workspace.</p></div>
}

function WorkspaceHeader({ eyebrow, title, description, aside }) {
  return <header className="ftm-stage-header"><div><span className="dd-card-kicker">{eyebrow}</span><h3>{title}</h3><p>{description}</p></div>{aside}</header>
}

function SourceTopology({ datasets }) {
  const [selectedId, setSelectedId] = useState('')
  const nodes = datasets.map((dataset, index) => {
    const angle = (index / Math.max(datasets.length, 1)) * Math.PI * 2 - Math.PI / 2
    return {
      ...dataset,
      x: 500 + Math.cos(angle) * 350,
      y: 245 + Math.sin(angle) * 170,
    }
  })
  const selected = datasets.find((dataset) => (dataset.datasetId || dataset.sourceId) === selectedId) || datasets[0]
  const shorten = (value, limit = 24) => String(value || 'Unnamed source').length > limit ? `${String(value).slice(0, limit - 1)}…` : String(value || 'Unnamed source')
  const selectSource = (dataset) => setSelectedId(dataset.datasetId || dataset.sourceId)

  return <section className="ftm-source-topology">
    <div className="ftm-source-topology__header"><div><span className="dd-card-kicker">Connected data model</span><h3>Sources feeding Due Diligence</h3><p>Each connection represents a registered dataset. Hover, focus, or tap a source to inspect its records, evidence, freshness, and provenance.</p></div><div className="ftm-source-topology__legend"><span><i className="is-ready"/>Ready</span><span><i className="is-registered"/>Registered</span><span><i className="is-error"/>Needs attention</span></div></div>
    {nodes.length ? <div className="ftm-source-topology__canvas"><svg viewBox="0 0 1000 490" role="img" aria-label={`${nodes.length} data sources connected to the Due Diligence workspace`}>
      <g className="ftm-source-topology__edges">{nodes.map(node=><line key={`edge-${node.datasetId || node.sourceId}`} x1="500" y1="245" x2={node.x} y2={node.y}/>)}</g>
      <g className="ftm-source-topology__core"><circle cx="500" cy="245" r="68"/><circle cx="500" cy="245" r="54"/><text x="500" y="237">DUE DILIGENCE</text><text className="is-subtitle" x="500" y="260">evidence workspace</text></g>
      {nodes.map(node=>{const id=node.datasetId||node.sourceId; return <g className={`ftm-source-topology__node is-${node.status || 'registered'} ${selected && id === (selected.datasetId || selected.sourceId) ? 'is-selected' : ''}`} key={id} transform={`translate(${node.x - 92} ${node.y - 34})`} role="button" tabIndex="0" aria-label={`Inspect ${node.name}`} onMouseEnter={()=>selectSource(node)} onFocus={()=>selectSource(node)} onClick={()=>selectSource(node)} onKeyDown={(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectSource(node)}}}><title>{node.name} — {pretty(node.status || 'registered')}</title><rect width="184" height="68" rx="13"/><circle cx="18" cy="18" r="5"/><text x="31" y="22">{shorten(node.name)}</text><text className="is-meta" x="18" y="45">{shorten(node.type || node.ingestionMode || 'Data source', 27)}</text><text className="is-status" x="18" y="59">{pretty(node.status || 'registered')}</text></g>})}
    </svg></div> : <div className="ftm-source-topology__empty"><IconDatabase size={26}/><span>No datasets are registered for this case yet.</span></div>}
    {selected?<div className="ftm-source-topology__selection"><div><span className={`ftm-status is-${selected.status || 'registered'}`}>{pretty(selected.status || 'registered')}</span><strong>{selected.name}</strong><small>{selected.type || 'Data source'} · {selected.ingestionMode || 'registered ingestion'}</small></div><dl><div><dt>Records</dt><dd>{selected.recordCount ?? '—'}</dd></div><div><dt>Statements</dt><dd>{selected.statementCount ?? '—'}</dd></div><div><dt>Evidence</dt><dd>{selected.evidenceCount ?? '—'}</dd></div><div><dt>Errors</dt><dd>{selected.errorCount ?? 0}</dd></div><div><dt>Provenance</dt><dd>{pct(selected.provenanceCompleteness)}</dd></div><div><dt>Freshness</dt><dd>{pretty(selected.freshness || 'not reported')}</dd></div></dl>{selected.url?<a className="button-secondary" href={selected.url} target="_blank" rel="noreferrer">Open source <IconExternalLink size={13}/></a>:<span className="ftm-source-topology__no-link">No public source link</span>}</div>:null}
    <div className="ftm-source-topology__flow" aria-label="Data integration flow"><span>1. Source records</span><IconArrowRight size={14}/><span>2. Sourced statements</span><IconArrowRight size={14}/><span>3. Resolved entities</span><IconArrowRight size={14}/><span>4. Evidence paths</span><IconArrowRight size={14}/><strong>5. Reviewed findings</strong></div>
  </section>
}

export function FollowTheMoneyWorkspace({ caseId, activeStage, reportId }) {
  const [workspace, setWorkspace] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [entities, setEntities] = useState([])
  const [entityDossier, setEntityDossier] = useState(null)
  const [candidates, setCandidates] = useState(null)
  const [queries, setQueries] = useState([])
  const [selectedQueryId, setSelectedQueryId] = useState('official-relative-contract')
  const [queryRun, setQueryRun] = useState(null)
  const [findings, setFindings] = useState(null)
  const [publications, setPublications] = useState([])
  const [selectedPublication, setSelectedPublication] = useState(null)
  const [publicationForm, setPublicationForm] = useState({ title: '', executiveSummary: '', preparedBy: '' })
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [entityQuery, setEntityQuery] = useState('')
  const [entityType, setEntityType] = useState('')
  const [resolutionState, setResolutionState] = useState('')
  const [reviewRationale, setReviewRationale] = useState({})
  const [queryParams, setQueryParams] = useState({ startEntityId: '', targetEntityId: '', maxDepth: 4, includeCandidateMatches: false })
  const [findingRationale, setFindingRationale] = useState({})

  const refreshWorkspace = useCallback(async () => {
    if (!caseId) { setWorkspace(null); return }
    try { setWorkspace(await getJson(`/due-diligence/cases/${caseId}/workspace`, { forceRefresh: true })) }
    catch { setWorkspace(null) }
  }, [caseId])

  useEffect(() => { refreshWorkspace() }, [refreshWorkspace])

  useEffect(() => {
    if (!caseId) return
    let current = true
    setLoading(true); setError(''); setNotice('')
    const load = async () => {
      try {
        if (activeStage === 'sources') setDatasets(await getJson(`/due-diligence/cases/${caseId}/datasets`, { forceRefresh: true }))
        if (activeStage === 'entities') {
          const params = new URLSearchParams({ limit: '100', offset: '0' })
          if (entityQuery) params.set('q', entityQuery)
          if (entityType) params.set('entityType', entityType)
          if (resolutionState) params.set('resolutionState', resolutionState)
          setEntities(await getJson(`/due-diligence/cases/${caseId}/entities?${params}`, { forceRefresh: true }))
        }
        if (activeStage === 'resolve') setCandidates(await getJson(`/due-diligence/cases/${caseId}/resolution-candidates`, { forceRefresh: true }))
        if (activeStage === 'follow-the-money') {
          const [queryCatalog, entityInventory] = await Promise.all([
            getJson('/due-diligence/investigation-queries', { forceRefresh: true }),
            getJson(`/due-diligence/cases/${caseId}/entities?limit=100&offset=0`, { forceRefresh: true }),
          ])
          setQueries(queryCatalog)
          setEntities(entityInventory)
        }
        if (activeStage === 'findings') setFindings(await getJson(`/due-diligence/cases/${caseId}/findings`, { forceRefresh: true }))
        if (activeStage === 'publish') {
          const [findingPayload, publicationRows] = await Promise.all([
            getJson(`/due-diligence/cases/${caseId}/findings`, { forceRefresh: true }),
            getJson(`/due-diligence/cases/${caseId}/publications`, { forceRefresh: true }),
          ])
          setFindings(findingPayload)
          setPublications(publicationRows)
        }
      } catch (err) { if (current) setError(err.message || 'Unable to load investigation workspace.') }
      finally { if (current) setLoading(false) }
    }
    load()
    return () => { current = false }
  }, [caseId, activeStage, entityQuery, entityType, resolutionState])

  const entityTypes = useMemo(() => [...new Set(entities.map((entity) => entity.type).filter(Boolean))], [entities])

  const openEntity = async (entityId) => {
    setActionLoading(true); setError('')
    try { setEntityDossier(await getJson(`/due-diligence/cases/${caseId}/entities/${entityId}`, { forceRefresh: true })) }
    catch (err) { setError(err.message || 'Unable to load entity dossier.') }
    finally { setActionLoading(false) }
  }

  const reviewCandidate = async (candidate, decision) => {
    setActionLoading(true); setError(''); setNotice('')
    try {
      const result = await requestJson(`/due-diligence/cases/${caseId}/resolution-candidates/${candidate.candidateId}/review`, { method: 'POST', payload: { leftEntityId: candidate.left.id, rightEntityId: candidate.right.id, decision, rationale: reviewRationale[candidate.candidateId] || '' } })
      setNotice(result.message)
      setCandidates(await getJson(`/due-diligence/cases/${caseId}/resolution-candidates`, { forceRefresh: true }))
      refreshWorkspace()
    } catch (err) { setError(err.message || 'Unable to save resolution review.') }
    finally { setActionLoading(false) }
  }

  const executeQuery = async () => {
    setActionLoading(true); setError(''); setNotice('')
    try {
      const payload = { maxDepth: Number(queryParams.maxDepth), limit: 25, includeCandidateMatches: Boolean(queryParams.includeCandidateMatches) }
      if (queryParams.startEntityId) payload.startEntityId = queryParams.startEntityId
      if (queryParams.targetEntityId) payload.targetEntityId = queryParams.targetEntityId
      const result = await requestJson(`/due-diligence/cases/${caseId}/investigation-queries/${selectedQueryId}/execute`, { method: 'POST', payload })
      setQueryRun(result); setNotice(`${result.paths.length} evidence path${result.paths.length === 1 ? '' : 's'} found.`); refreshWorkspace()
    } catch (err) { setError(err.message || 'Unable to run investigation query.') }
    finally { setActionLoading(false) }
  }

  const reviewFinding = async (finding, status) => {
    const rationale = findingRationale[finding.findingId] || finding.analystRationale || ''
    if (status === 'accepted' && !rationale.trim()) { setError('Add analyst rationale before accepting a finding.'); return }
    setActionLoading(true); setError(''); setNotice('')
    try {
      await requestJson(`/due-diligence/cases/${caseId}/findings/${finding.findingId}`, { method: 'PATCH', payload: { status, analystRationale: rationale } })
      setFindings(await getJson(`/due-diligence/cases/${caseId}/findings`, { forceRefresh: true }))
      setNotice(`Finding marked ${pretty(status)}.`); refreshWorkspace()
    } catch (err) { setError(err.message || 'Unable to review finding.') }
    finally { setActionLoading(false) }
  }

  const createFindingFromPath = async (path) => {
    setActionLoading(true); setError(''); setNotice('')
    try {
      await requestJson(`/due-diligence/cases/${caseId}/findings`, { method: 'POST', payload: { title: 'Review evidence path', claim: path.summary, findingType: selectedQueryId, status: 'open', priority: path.verificationStatus === 'requires-review' ? 1 : 2, confidence: path.confidence, supportingStatementIds: path.statementIds, contradictingStatementIds: [], pathRunIds: [queryRun.runId], evidenceIds: path.evidenceIds, nodeIds: path.nodeIds, relationshipIds: path.relationshipIds, analystRationale: '', recommendedNextSteps: ['Review each cited statement and source', 'Confirm entity resolution before accepting'] } })
      setNotice('Path preserved as an open finding.'); refreshWorkspace()
    } catch (err) { setError(err.message || 'Unable to preserve the path as a finding.') }
    finally { setActionLoading(false) }
  }

  const createPublication = async (event) => {
    event.preventDefault()
    setActionLoading(true); setError(''); setNotice('')
    try {
      const publication = await requestJson(`/due-diligence/cases/${caseId}/publications`, { method: 'POST', payload: publicationForm })
      setSelectedPublication(publication)
      setPublications(await getJson(`/due-diligence/cases/${caseId}/publications`, { forceRefresh: true }))
      setNotice('Publication snapshot created from the accepted findings.')
      refreshWorkspace()
    } catch (err) { setError(err.message || 'Unable to create publication snapshot.') }
    finally { setActionLoading(false) }
  }

  const openPublication = async (publicationId) => {
    setActionLoading(true); setError('')
    try { setSelectedPublication(await getJson(`/due-diligence/cases/${caseId}/publications/${publicationId}`, { forceRefresh: true })) }
    catch (err) { setError(err.message || 'Unable to open publication snapshot.') }
    finally { setActionLoading(false) }
  }

  if (!caseId) return <EmptyCase title="Select a case to begin" />

  return <div className="ftm-workspace">
    <div className="ftm-principle"><IconAlertTriangle size={16} /> Sourced facts, inferred links, and hypotheses remain distinct. Patterns are leads until an investigator reviews and accepts them.</div>
    {error ? <div className="module-alert">{error}</div> : null}
    {notice ? <div className="dd-graph-notice">{notice}</div> : null}

    {activeStage === 'sources' ? <>
      <WorkspaceHeader eyebrow="01 · Inputs" title="Sources and datasets" description="Register, import, and monitor the datasets that make this investigation defensible." aside={<div className="ftm-count"><strong>{workspace?.counts?.datasets || datasets.length}</strong><span>datasets</span></div>} />
      <SourceTopology datasets={datasets} />
      <ApifyFacebookConnector caseId={caseId} onImported={refreshWorkspace} />
      <CorporateRegistrySources caseId={caseId} onEnriched={refreshWorkspace} />
    </> : null}

    {activeStage === 'entities' ? <>
      <WorkspaceHeader eyebrow="02 · Normalize" title="Entity inventory" description="Inspect normalized people, organizations, assets, addresses, jurisdictions, and their source identities." aside={<div className="ftm-count"><strong>{workspace?.counts?.entities || entities.length}</strong><span>entities</span></div>} />
      <div className="ftm-filterbar"><label><IconSearch size={15} /><input placeholder="Search entities" value={entityQuery} onChange={(e)=>setEntityQuery(e.target.value)} /></label><select value={entityType} onChange={(e)=>setEntityType(e.target.value)}><option value="">All types</option>{entityTypes.map((type)=><option key={type}>{type}</option>)}</select><select value={resolutionState} onChange={(e)=>setResolutionState(e.target.value)}><option value="">All resolution states</option><option value="candidate">Candidate</option><option value="resolved">Resolved</option><option value="unresolved">Unresolved</option></select></div>
      <div className="ftm-split">
        <div className="ftm-entity-list">
          {entities.map((entity) => <button key={entity.id} type="button" className={entityDossier?.entity?.id === entity.id ? 'is-active' : ''} onClick={() => openEntity(entity.id)}><span className="ftm-entity-type">{entity.type}</span><strong>{entity.displayName}</strong><small>{entity.entityRole || 'Unclassified role'} · {entity.statementCount} statements</small><span className={`ftm-resolution is-${entity.resolutionState}`}>{entity.resolutionState}</span></button>)}
        </div>
        <aside className="ftm-dossier">
          {actionLoading && !entityDossier ? <p>Loading dossier…</p> : entityDossier ? <>
            <span className="dd-card-kicker">{entityDossier.entity.type} · {entityDossier.entity.entityRole || 'Entity'}</span>
            <h3>{entityDossier.entity.displayName}</h3>
            <p>{entityDossier.provenance.statementCount} statements across {entityDossier.provenance.sourceIds.length} sources.</p>
            {entityDossier.statementGroups.filter((group) => !isSensitivePredicate(group.predicate)).map((group) => <details key={group.predicate}><summary>{pretty(group.predicate)} <span>{group.statements.length}</span></summary>{group.statements.slice(0, 8).map((statement) => <div className={`ftm-statement is-${statement.assertionKind}`} key={statement.statementId}><strong>{statement.object?.value || statement.object?.entityId || '—'}</strong><small>{pretty(statement.assertionKind)} · {pretty(statement.verificationStatus)} · {pct(statement.confidence)}</small>{statement.sourceExcerpt ? <em>{statement.sourceExcerpt}</em> : null}</div>)}</details>)}
            {entityDossier.statementGroups.some((group) => isSensitivePredicate(group.predicate)) ? <div className="ftm-restricted-field"><IconAlertTriangle size={14}/>Sensitive personal identifiers are restricted and not rendered.</div> : null}
            {['organization', 'company', 'publicbody', 'public body'].includes(String(entityDossier.entity.type || '').toLowerCase()) ? <CorporateRegistryDossier caseId={caseId} entityId={entityDossier.entity.id} /> : null}
          </> : <div className="ftm-dossier__empty"><IconFileCheck size={28}/><h3>Select an entity</h3><p>Review its statements, identifiers, connections, and provenance.</p></div>}
        </aside>
      </div>
    </> : null}

    {activeStage === 'resolve' ? <>
      <WorkspaceHeader eyebrow="03 · Resolve" title="Identity resolution" description="Compare source identities without destroying original records or provenance." aside={<div className="ftm-count"><strong>{candidates?.summary?.pending || 0}</strong><span>pending</span></div>} />
      {!candidates?.candidates?.length ? <div className="ftm-empty"><IconCheck size={34}/><h3>No resolution candidates</h3><p className="muted">There are no identity pairs waiting for review.</p></div> : <div className="ftm-candidates">{candidates.candidates.map(candidate=><article key={candidate.candidateId}><div className="ftm-candidate-pair"><div><span>{candidate.left.type}</span><strong>{candidate.left.displayName}</strong><small>{candidate.left.sourceIds.join(', ')}</small></div><IconGitMerge size={24}/><div><span>{candidate.right.type}</span><strong>{candidate.right.displayName}</strong><small>{candidate.right.sourceIds.join(', ')}</small></div></div><div className="ftm-candidate-score"><strong>{pct(candidate.score)}</strong><span>match confidence</span></div><div className="ftm-signals">{candidate.signals.map(signal=><span key={`${candidate.candidateId}-${signal.type}`}>{signal.label}: {signal.values.join(' · ')}</span>)}</div>{candidate.conflicts.length?<div className="ftm-conflicts">{candidate.conflicts.map(conflict=><span key={conflict.type}>Conflict: {pretty(conflict.type)} ({conflict.left} / {conflict.right})</span>)}</div>:null}<textarea placeholder="Review rationale" value={reviewRationale[candidate.candidateId]||''} onChange={(e)=>setReviewRationale(v=>({...v,[candidate.candidateId]:e.target.value}))}/><div className="ftm-review-actions"><button className="button-secondary" disabled={actionLoading} onClick={()=>reviewCandidate(candidate,'rejected')}>Keep separate</button><button className="button-secondary" disabled={actionLoading} onClick={()=>reviewCandidate(candidate,'deferred')}>Needs research</button><button className="button" disabled={actionLoading} onClick={()=>reviewCandidate(candidate,'accepted')}>Resolve identity</button></div></article>)}</div>}
    </> : null}

    {activeStage === 'follow-the-money' ? <>
      <WorkspaceHeader eyebrow="04 · Investigate" title="Follow the money" description="Ask repeatable graph questions, inspect evidence paths, and preserve promising leads." aside={<IconNetwork size={32}/>} />
      <div className="ftm-query-builder"><div className="ftm-query-catalog">{queries.map(query=><button key={query.queryId} type="button" className={selectedQueryId===query.queryId?'is-active':''} onClick={()=>setSelectedQueryId(query.queryId)}><strong>{query.title}</strong><span>{query.question}</span></button>)}</div><div className="ftm-query-controls"><label>Start entity<select value={queryParams.startEntityId} onChange={(e)=>setQueryParams(v=>({...v,startEntityId:e.target.value}))}><option value="">Use case subject</option>{entities.map(entity=><option key={entity.id} value={entity.id}>{entity.displayName}</option>)}</select></label><label>Target entity<select value={queryParams.targetEntityId} onChange={(e)=>setQueryParams(v=>({...v,targetEntityId:e.target.value}))}><option value="">Any matching entity</option>{entities.map(entity=><option key={entity.id} value={entity.id}>{entity.displayName}</option>)}</select></label><label>Maximum depth <strong>{queryParams.maxDepth}</strong><input type="range" min="1" max="6" value={queryParams.maxDepth} onChange={(e)=>setQueryParams(v=>({...v,maxDepth:e.target.value}))}/></label><label className="ftm-checkbox"><input type="checkbox" checked={queryParams.includeCandidateMatches} onChange={(e)=>setQueryParams(v=>({...v,includeCandidateMatches:e.target.checked}))}/> Include name-only candidate matches</label><button className="button" type="button" disabled={actionLoading} onClick={executeQuery}><IconPlayerPlay size={16}/>{actionLoading?'Tracing paths…':'Run path query'}</button></div></div>
      {queryRun?.paths?.length?<section className="ftm-paths"><div className="ftm-paths__header"><h3>Evidence paths</h3><span>{queryRun.paths.length}{queryRun.truncated?'+' : ''} found</span></div>{queryRun.paths.map(path=><article key={path.pathId}><div><span className={`dd-graph-status is-${path.verificationStatus}`}>{pretty(path.verificationStatus)}</span><strong>{path.summary}</strong><small>{path.length} hops · {path.evidenceIds.length} evidence records · {pct(path.confidence)} confidence</small></div><div className="ftm-path-kinds"><span className="is-sourced">{path.assertionKindCounts.sourced} sourced</span><span className="is-analyst">{path.assertionKindCounts.analyst} analyst</span><span className="is-inferred">{path.assertionKindCounts.inferred} inferred</span><span className="is-hypothesis">{path.assertionKindCounts.hypothesis} hypotheses</span></div><button className="button-secondary" type="button" onClick={()=>createFindingFromPath(path)}>Preserve as finding <IconArrowRight size={14}/></button></article>)}</section>:null}
      <InvestigationGraph caseId={caseId} reportId={reportId}/>
    </> : null}

    {activeStage === 'findings' ? <>
      <WorkspaceHeader eyebrow="05 · Review" title="Findings and hypotheses" description="Accept, reject, or keep researching evidence-backed claims. Nothing becomes a finding automatically." aside={<div className="ftm-count"><strong>{findings?.summary?.accepted || 0}</strong><span>accepted</span></div>} />
      {!findings?.findings?.length?<div className="ftm-empty"><IconSparkles size={32}/><h3>No findings preserved yet</h3><p className="muted">Run a path query and preserve an evidence path for analyst review.</p></div>:<div className="ftm-findings">{findings.findings.map(finding=><article key={finding.findingId} className={`is-${finding.status}`}><div className="ftm-finding__top"><span className={`ftm-finding-status is-${finding.status}`}>{pretty(finding.status)}</span><span>Priority {finding.priority} · {pct(finding.confidence)}</span></div><h3>{finding.title}</h3><p>{finding.claim}</p><div className="ftm-evidence-counts"><span>{finding.supportingStatementIds.length} supporting statements</span><span>{finding.contradictingStatementIds.length} contradictions</span><span>{finding.evidenceIds.length} evidence records</span></div><textarea placeholder="Analyst rationale required to accept" value={findingRationale[finding.findingId]??finding.analystRationale??''} onChange={(e)=>setFindingRationale(v=>({...v,[finding.findingId]:e.target.value}))}/><div className="ftm-review-actions"><button className="button-secondary" disabled={actionLoading} onClick={()=>reviewFinding(finding,'rejected')}>Reject</button><button className="button-secondary" disabled={actionLoading} onClick={()=>reviewFinding(finding,'needs-research')}>Needs research</button><button className="button" disabled={actionLoading} onClick={()=>reviewFinding(finding,'accepted')}>Accept finding</button></div></article>)}</div>}
    </> : null}

    {activeStage === 'publish' ? <>
      <WorkspaceHeader eyebrow="06 · Output" title="Publish a defensible report" description="Reports are generated from analyst-accepted findings, with sources, caveats, and provenance preserved." aside={<div className={`ftm-readiness ${workspace?.publishReady?'is-ready':''}`}>{workspace?.publishReady?<IconCheck size={18}/>:<IconAlertTriangle size={18}/>}<strong>{workspace?.publishReady?'Ready to publish':'Not ready'}</strong></div>} />
      <div className="ftm-publish-grid"><section><h3>Publication checks</h3>{workspace?.blockers?.length?workspace.blockers.map(blocker=><div className="ftm-blocker" key={blocker}><IconAlertTriangle size={15}/>{blocker}</div>):<div className="ftm-check"><IconCheck size={16}/>Identity resolution and finding review are complete.</div>}<dl className="ftm-publish-counts"><div><dt>Accepted findings</dt><dd>{workspace?.counts?.acceptedFindings||0}</dd></div><div><dt>Evidence</dt><dd>{workspace?.counts?.evidence||0}</dd></div><div><dt>Publications</dt><dd>{workspace?.counts?.publications||0}</dd></div></dl></section><section><h3>Accepted finding dossier</h3>{(findings?.findings||[]).filter(f=>f.status==='accepted').map(f=><article key={f.findingId}><strong>{f.title}</strong><p>{f.claim}</p><small>{f.evidenceIds.length} evidence records · {f.supportingStatementIds.length} statements</small></article>)}{!(findings?.findings||[]).some(f=>f.status==='accepted')?<p className="muted">Accept at least one evidence-backed finding before publishing.</p>:null}</section></div>
      <div className="ftm-publication-layout">
        <form className="ftm-publication-form" onSubmit={createPublication}><span className="dd-card-kicker">Immutable evidence snapshot</span><h3>Create publication</h3><p>A publication freezes the exact accepted findings, statements, paths, evidence, nodes, and relationships used at this moment.</p><label>Title<input value={publicationForm.title} onChange={(e)=>setPublicationForm(v=>({...v,title:e.target.value}))} placeholder="Optional — defaults to case subject" /></label><label>Executive summary<textarea rows="4" value={publicationForm.executiveSummary} onChange={(e)=>setPublicationForm(v=>({...v,executiveSummary:e.target.value}))} placeholder="Summarize only what the accepted findings support" /></label><label>Prepared by<input value={publicationForm.preparedBy} onChange={(e)=>setPublicationForm(v=>({...v,preparedBy:e.target.value}))} /></label><button className="button" type="submit" disabled={!workspace?.publishReady||actionLoading}>{actionLoading?'Creating snapshot…':'Create publication snapshot'}</button>{!workspace?.publishReady?<small>Resolve all publication blockers before creating a snapshot.</small>:null}</form>
        <section className="ftm-publication-history"><div className="card-header"><div><span className="dd-card-kicker">Archive</span><h3>Publication history</h3></div><span>{publications.length}</span></div>{publications.length?publications.map(publication=><button type="button" key={publication.publicationId} onClick={()=>openPublication(publication.publicationId)}><div><strong>{publication.title}</strong><small>{publication.preparedBy||'Unassigned author'} · {publication.createdAt ? new Date(publication.createdAt).toLocaleDateString() : 'Unknown date'}</small></div><span>{publication.findingCount} findings · {publication.evidenceCount} evidence</span><IconArrowRight size={15}/></button>):<p className="muted">No publication snapshots yet.</p>}</section>
      </div>
      {selectedPublication?<section className="ftm-publication-snapshot"><div className="card-header"><div><span className="dd-card-kicker">Published evidence snapshot</span><h3>{selectedPublication.title}</h3></div><span className="ftm-status is-ready">{selectedPublication.status}</span></div>{selectedPublication.executiveSummary?<p>{selectedPublication.executiveSummary}</p>:null}<div className="ftm-snapshot-counts"><span>{selectedPublication.findingIds?.length||0} findings</span><span>{selectedPublication.statementIds?.length||0} statements</span><span>{selectedPublication.pathRunIds?.length||0} path runs</span><span>{selectedPublication.evidenceIds?.length||0} evidence</span></div>{(selectedPublication.findings||[]).map(finding=><article key={finding.findingId}><strong>{finding.title}</strong><p>{finding.claim}</p><small>Analyst rationale: {finding.analystRationale||'Not recorded'}</small></article>)}</section>:null}
    </> : null}
    {loading ? <div className="ftm-loading">Loading investigation data…</div> : null}
  </div>
}
