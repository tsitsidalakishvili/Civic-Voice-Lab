import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  IconAlertTriangle,
  IconArrowsExchange,
  IconArrowRight,
  IconBuilding,
  IconBuildingBank,
  IconCar,
  IconCircle,
  IconDatabaseSearch,
  IconExternalLink,
  IconFileSearch,
  IconFileDescription,
  IconFileText,
  IconHome,
  IconMapPin,
  IconMessageCircle,
  IconNews,
  IconPlane,
  IconPlus,
  IconRefresh,
  IconRoute,
  IconShip,
  IconUser,
  IconUserCircle,
  IconUsers,
  IconWallet,
  IconWorld,
  IconX,
} from '@tabler/icons-react'
import { getJson, requestJson } from '../../services/api'

const EMPTY_GRAPH = {
  nodes: [],
  relationships: [],
  evidence: [],
  sources: [],
  stats: { entities: 0, relationships: 0, evidence: 0, sources: 0, candidateMatches: 0 },
}

const TYPE_COLORS = {
  Person: '#2563eb',
  Organization: '#7c3aed',
  Asset: '#d97706',
  Contract: '#059669',
  Article: '#64748b',
  'Screening record': '#dc2626',
  Address: '#0891b2',
  Jurisdiction: '#be185d',
  'Social profile': '#1877f2',
  'Social group': '#4267b2',
  'Social post': '#5b6b88',
  'Social comment': '#6b7280',
  Vehicle: '#ea580c',
  'Real estate': '#15803d',
  Property: '#15803d',
  Vessel: '#0369a1',
  Airplane: '#4f46e5',
  BankAccount: '#0f766e',
  Payment: '#0f766e',
}

const normalizeType = (value) => String(value || '').trim().toLowerCase()

function iconForType(type) {
  const value = normalizeType(type)
  if (value === 'person') return IconUser
  if (value === 'social profile') return IconUserCircle
  if (value === 'social group') return IconUsers
  if (value === 'social post') return IconFileText
  if (value === 'social comment') return IconMessageCircle
  if (['organization', 'company', 'publicbody', 'public body'].includes(value)) return IconBuilding
  if (value === 'vehicle') return IconCar
  if (['real estate', 'property'].includes(value)) return IconHome
  if (value === 'vessel') return IconShip
  if (value === 'airplane') return IconPlane
  if (value === 'contract') return IconFileDescription
  if (value === 'address') return IconMapPin
  if (value === 'jurisdiction') return IconBuildingBank
  if (value === 'bankaccount' || value === 'bank account') return IconWallet
  if (value === 'payment') return IconArrowsExchange
  if (value === 'document') return IconFileSearch
  if (value === 'article') return IconNews
  if (value === 'screening record') return IconWorld
  return IconCircle
}

const statusLabel = (status) => String(status || 'unverified').replaceAll('-', ' ')

function makeLayout(nodes, width = 920, height = 560) {
  if (!nodes.length) return []
  const root = nodes.find((node) => node.isRoot) || nodes[0]
  const others = nodes.filter((node) => node.id !== root.id)
  const center = { x: width / 2, y: height / 2 }
  return [
    { ...root, ...center },
    ...others.map((node, index) => {
      const ring = index < 10 ? 1 : 2
      const ringItems = ring === 1 ? Math.min(10, others.length) : Math.max(1, others.length - 10)
      const ringIndex = ring === 1 ? index : index - 10
      const angle = (ringIndex / ringItems) * Math.PI * 2 - Math.PI / 2
      const radius = ring === 1 ? 180 : 255
      return {
        ...node,
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius,
      }
    }),
  ]
}

export function InvestigationGraph({ caseId, reportId }) {
  const [graph, setGraph] = useState(EMPTY_GRAPH)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState('')
  const [graphEnriching, setGraphEnriching] = useState(false)
  const [graphAdding, setGraphAdding] = useState(false)
  const [notice, setNotice] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [selectedRelationshipId, setSelectedRelationshipId] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [insights, setInsights] = useState(null)
  const [form, setForm] = useState({
    fromEntityId: '',
    targetName: '',
    targetType: 'Person',
    relationshipType: '',
    sourceName: '',
    sourceUrl: '',
    evidenceNote: '',
    confidence: 0.8,
    verificationStatus: 'analyst-added',
  })

  const loadGraph = useCallback(async () => {
    if (!caseId) {
      setGraph(EMPTY_GRAPH)
      return
    }
    setGraphLoading(true)
    setGraphError('')
    try {
      const payload = await getJson(`/due-diligence/cases/${caseId}/graph`, {
        forceRefresh: true,
      })
      setGraph(payload || EMPTY_GRAPH)
      getJson(`/due-diligence/cases/${caseId}/graph/insights`, { forceRefresh: true })
        .then((insightPayload) => setInsights(insightPayload))
        .catch(() => setInsights(null))
    } catch (error) {
      setGraphError(error.message || 'Unable to load the relationship graph.')
    } finally {
      setGraphLoading(false)
    }
  }, [caseId])

  useEffect(() => {
    setSelectedNodeId('')
    setSelectedRelationshipId('')
    setNotice('')
    loadGraph()
  }, [caseId, loadGraph])

  const positionedNodes = useMemo(() => makeLayout(graph.nodes || []), [graph.nodes])
  const nodeById = useMemo(
    () => new Map((positionedNodes || []).map((node) => [node.id, node])),
    [positionedNodes],
  )
  const evidenceById = useMemo(
    () => new Map((graph.evidence || []).map((item) => [item.evidenceId, item])),
    [graph.evidence],
  )
  const selectedNode = nodeById.get(selectedNodeId) || null
  const selectedRelationship = (graph.relationships || []).find(
    (item) => item.id === selectedRelationshipId,
  )
  const selectedEvidence = selectedRelationship
    ? (selectedRelationship.evidenceIds || []).map((id) => evidenceById.get(id)).filter(Boolean)
    : []
  const presentTypes = useMemo(
    () => [...new Set((graph.nodes || []).map((node) => node.type || 'Other'))],
    [graph.nodes],
  )

  const handleEnrich = async () => {
    if (!caseId) return
    setGraphEnriching(true)
    setGraphError('')
    setNotice('')
    try {
      const payload = await requestJson(`/due-diligence/cases/${caseId}/graph/enrich`, {
        method: 'POST',
        payload: reportId ? { reportId } : {},
      })
      setGraph(payload)
      setNotice(payload?.enrichment?.message || 'Evidence graph enriched.')
    } catch (error) {
      setGraphError(error.message || 'Unable to enrich the graph.')
    } finally {
      setGraphEnriching(false)
    }
  }

  const updateForm = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  const handleAddRelationship = async (event) => {
    event.preventDefault()
    if (!caseId) return
    setGraphAdding(true)
    setGraphError('')
    setNotice('')
    try {
      const payload = await requestJson(`/due-diligence/cases/${caseId}/graph/relationships`, {
        method: 'POST',
        payload: {
          ...form,
          fromEntityId: form.fromEntityId || undefined,
          sourceUrl: form.sourceUrl || undefined,
          confidence: Number(form.confidence),
        },
      })
      setGraph(payload)
      setNotice(payload?.enrichment?.message || 'Documented connection added.')
      setShowAddForm(false)
      setForm((current) => ({
        ...current,
        targetName: '',
        relationshipType: '',
        sourceName: '',
        sourceUrl: '',
        evidenceNote: '',
      }))
    } catch (error) {
      setGraphError(error.message || 'Unable to add the documented connection.')
    } finally {
      setGraphAdding(false)
    }
  }

  if (!caseId) {
    return (
      <div className="module-card module-card__wide dd-graph-empty">
        <IconRoute size={32} />
        <h3>Select a case to map relationships</h3>
        <p className="muted">The graph belongs to a case so every connection keeps its evidence trail.</p>
      </div>
    )
  }

  const hasGraph = Boolean(graph.nodes?.length)

  return (
    <div className="dd-graph-workspace">
      <header className="dd-graph-header">
        <div>
          <span className="dd-card-kicker">Evidence network</span>
          <h3>Relationship graph</h3>
          <p className="muted">Trace people, organizations, assets, contracts, and the evidence connecting them.</p>
        </div>
        <div className="dd-graph-header__actions">
          <button className="button-secondary" type="button" onClick={loadGraph} disabled={graphLoading}>
            <IconRefresh size={16} /> {graphLoading ? 'Loading…' : 'Refresh'}
          </button>
          <button className="button-secondary" type="button" onClick={() => setShowAddForm(true)}>
            <IconPlus size={16} /> Add connection
          </button>
          <button className="button" type="button" onClick={handleEnrich} disabled={graphEnriching}>
            <IconDatabaseSearch size={16} /> {graphEnriching ? 'Enriching…' : hasGraph ? 'Enrich again' : 'Build from evidence'}
          </button>
        </div>
      </header>

      <div className="dd-graph-disclaimer">
        <IconAlertTriangle size={17} />
        Connections and patterns are investigative leads, not proof of corruption. Verify every claim against its cited source.
      </div>
      {graphError ? <div className="module-alert">{graphError}</div> : null}
      {notice ? <div className="dd-graph-notice">{notice}</div> : null}

      <div className="dd-graph-stats" aria-label="Graph summary">
        {[
          ['Entities', graph.stats?.entities || 0],
          ['Connections', graph.stats?.relationships || 0],
          ['Evidence', graph.stats?.evidence || 0],
          ['Sources', graph.stats?.sources || 0],
          ['Candidate matches', graph.stats?.candidateMatches || 0],
        ].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}
      </div>

      {insights?.insights?.length ? (
        <section className="dd-graph-leads" aria-labelledby="dd-graph-leads-title">
          <div className="dd-graph-leads__heading">
            <div><span className="dd-card-kicker">Requires analyst review</span><h3 id="dd-graph-leads-title">Investigative leads</h3></div>
            <span>{insights.summary?.total || insights.insights.length} signals</span>
          </div>
          <div className="dd-graph-leads__list">
            {insights.insights.map((insight) => (
              <button
                key={insight.insightId}
                type="button"
                className={`dd-graph-lead is-${insight.severity || 'low'}`}
                onClick={() => {
                  setSelectedRelationshipId(insight.relationshipIds?.[0] || '')
                  setSelectedNodeId(insight.relationshipIds?.length ? '' : insight.nodeIds?.[0] || '')
                }}
              >
                <span className="dd-graph-lead__meta">Priority {insight.priority} · {statusLabel(insight.leadType)}</span>
                <strong>{insight.title}</strong>
                <p>{insight.summary}</p>
                <span className="dd-graph-lead__review">Review evidence <IconArrowRight size={14} /></span>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {!hasGraph && !graphLoading ? (
        <div className="dd-graph-zero">
          <IconDatabaseSearch size={38} />
          <h3>No entities mapped yet</h3>
          <p>Build the graph from the latest saved investigation report, or add a documented connection manually.</p>
          <button className="button" type="button" onClick={handleEnrich} disabled={graphEnriching}>
            {graphEnriching ? 'Building graph…' : 'Build graph from saved evidence'}
          </button>
        </div>
      ) : (
        <div className="dd-graph-layout">
          <div className="dd-graph-canvas" role="img" aria-label={`Relationship graph with ${graph.stats?.entities || 0} entities`}>
            <svg viewBox="0 0 920 560" preserveAspectRatio="xMidYMid meet">
              <defs>
                <marker id="dd-graph-arrow" viewBox="0 0 10 10" refX="19" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" />
                </marker>
              </defs>
              {(graph.relationships || []).map((relationship) => {
                const source = nodeById.get(relationship.source)
                const target = nodeById.get(relationship.target)
                if (!source || !target) return null
                const candidate = relationship.verificationStatus === 'candidate-match'
                return (
                  <g key={relationship.id} className={`dd-graph-edge${candidate ? ' is-candidate' : ''}${selectedRelationshipId === relationship.id ? ' is-selected' : ''}`} onClick={() => { setSelectedRelationshipId(relationship.id); setSelectedNodeId('') }}>
                    <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} markerEnd="url(#dd-graph-arrow)" />
                    <title>{relationship.label} · {statusLabel(relationship.verificationStatus)}</title>
                  </g>
                )
              })}
              {positionedNodes.map((node) => {
                const selected = selectedNodeId === node.id
                const NodeIcon = iconForType(node.type)
                return (
                  <g key={node.id} className={`dd-graph-node${node.isRoot ? ' is-root' : ''}${selected ? ' is-selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => { setSelectedNodeId(node.id); setSelectedRelationshipId('') }}>
                    <circle r={node.isRoot ? 30 : 22} fill={TYPE_COLORS[node.type] || '#475569'} />
                    <NodeIcon className="dd-graph-node__icon" x={-10} y={-10} width={20} height={20} strokeWidth={2} />
                    <text y={node.isRoot ? 48 : 38} textAnchor="middle">{String(node.label || 'Untitled').slice(0, 24)}</text>
                    <title>{node.label} · {node.type}</title>
                  </g>
                )
              })}
            </svg>
            <div className="dd-graph-legend">
              {presentTypes.map((type) => {
                const LegendIcon = iconForType(type)
                return <span key={type}><i style={{ backgroundColor: TYPE_COLORS[type] || '#475569' }}><LegendIcon size={9} strokeWidth={2.2} /></i>{type}</span>
              })}
            </div>
          </div>

          <aside className="dd-graph-inspector">
            {selectedRelationship ? (
              <>
                <span className={`dd-graph-status is-${selectedRelationship.verificationStatus}`}>{statusLabel(selectedRelationship.verificationStatus)}</span>
                <h3>{selectedRelationship.label}</h3>
                <div className="dd-graph-connection-title">
                  <strong>{nodeById.get(selectedRelationship.source)?.label || 'Unknown'}</strong>
                  <IconArrowRight size={16} />
                  <strong>{nodeById.get(selectedRelationship.target)?.label || 'Unknown'}</strong>
                </div>
                <p>{selectedRelationship.details || 'No additional relationship details.'}</p>
                <div className="dd-graph-confidence"><span style={{ width: `${Math.round((selectedRelationship.confidence || 0) * 100)}%` }} /></div>
                <small>{Math.round((selectedRelationship.confidence || 0) * 100)}% confidence</small>
                <h4>Supporting evidence</h4>
                {selectedEvidence.length ? selectedEvidence.map((item) => (
                  <article className="dd-evidence-card" key={item.evidenceId}>
                    <strong>{item.title || item.sourceName}</strong>
                    <span>{item.sourceName} · {item.evidenceType}</span>
                    {item.note ? <p>{item.note}</p> : null}
                    {item.sourceUrl ? <a href={item.sourceUrl} target="_blank" rel="noreferrer">Open source <IconExternalLink size={13} /></a> : null}
                  </article>
                )) : <p className="muted">No evidence record is attached.</p>}
              </>
            ) : selectedNode ? (
              <>
                <span className="dd-card-kicker">{selectedNode.type}</span>
                <h3>{selectedNode.label}</h3>
                <p>{selectedNode.description || 'No description available.'}</p>
                {Object.keys(selectedNode.properties || {}).length ? (
                  <dl className="dd-node-properties">
                    {Object.entries(selectedNode.properties).slice(0, 12).map(([key, value]) => (
                      <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>
                    ))}
                  </dl>
                ) : null}
              </>
            ) : (
              <div className="dd-graph-inspector__empty">
                <IconRoute size={28} />
                <h3>Inspect the network</h3>
                <p>Select an entity or connection to review its details, confidence, and supporting evidence.</p>
              </div>
            )}
          </aside>
        </div>
      )}

      {(graph.sources || []).length ? (
        <details className="dd-source-registry">
          <summary>Source registry <span>{graph.sources.length}</span></summary>
          <div className="dd-source-registry__grid">
            {graph.sources.map((source) => (
              <article key={source.sourceId}>
                <span>{source.sourceType || 'Source'}</span>
                <strong>{source.name}</strong>
                {source.url ? <a href={source.url} target="_blank" rel="noreferrer">Visit source <IconExternalLink size={13} /></a> : null}
              </article>
            ))}
          </div>
        </details>
      ) : null}

      {showAddForm ? (
        <div className="dd-graph-modal" role="dialog" aria-modal="true" aria-labelledby="dd-add-connection-title">
          <form className="dd-graph-form" onSubmit={handleAddRelationship}>
            <div className="card-header">
              <div><span className="dd-card-kicker">Analyst evidence</span><h3 id="dd-add-connection-title">Add documented connection</h3></div>
              <button className="dd-graph-form__close" type="button" onClick={() => setShowAddForm(false)} aria-label="Close"><IconX /></button>
            </div>
            <p className="muted">Record what the source states. This creates an analyst-added lead, not a verified finding.</p>
            <div className="dd-graph-form__grid">
              <label>From entity<select value={form.fromEntityId} onChange={(event) => updateForm('fromEntityId', event.target.value)}><option value="">Case subject (root)</option>{graph.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label>
              <label>Target name<input required value={form.targetName} onChange={(event) => updateForm('targetName', event.target.value)} /></label>
              <label>Target type<select value={form.targetType} onChange={(event) => updateForm('targetType', event.target.value)}>{['Person', 'Organization', 'Asset', 'Contract', 'Other'].map((type) => <option key={type}>{type}</option>)}</select></label>
              <label>Relationship<input required placeholder="e.g. FAMILY_MEMBER_OF" value={form.relationshipType} onChange={(event) => updateForm('relationshipType', event.target.value)} /></label>
              <label>Source name<input required value={form.sourceName} onChange={(event) => updateForm('sourceName', event.target.value)} /></label>
              <label>Source URL<input type="url" value={form.sourceUrl} onChange={(event) => updateForm('sourceUrl', event.target.value)} /></label>
              <label className="is-wide">Evidence note<textarea required rows="4" value={form.evidenceNote} onChange={(event) => updateForm('evidenceNote', event.target.value)} /></label>
              <label>Confidence <strong>{Math.round(Number(form.confidence) * 100)}%</strong><input type="range" min="0" max="1" step="0.05" value={form.confidence} onChange={(event) => updateForm('confidence', event.target.value)} /></label>
            </div>
            <div className="dd-graph-form__actions"><button className="button-secondary" type="button" onClick={() => setShowAddForm(false)}>Cancel</button><button className="button" type="submit" disabled={graphAdding}>{graphAdding ? 'Saving…' : 'Add documented connection'}</button></div>
          </form>
        </div>
      ) : null}
    </div>
  )
}
