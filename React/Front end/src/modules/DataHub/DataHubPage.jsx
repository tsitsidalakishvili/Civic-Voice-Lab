import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
} from 'd3-force'
import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconChartDots,
  IconDatabase,
  IconGitBranch,
  IconLink,
} from '@tabler/icons-react'
import { getApiBaseUrl, getJson, requestJson } from '../../services/api'
import { CivicStatGrid, Field, FormSection, InfoHint, StatusMessage } from '../../ui'

const VIEWS = ['explorer', 'connectors']
const DEFAULT_LIMIT = 80
const INTAKE_MODULE_IDS = [
  'crm',
  'campaigns',
  'deliberation',
  'due-diligence',
  'audience-discovery',
]
const COLOR_PALETTE = [
  '#0ea5e9',
  '#22c55e',
  '#a855f7',
  '#f97316',
  '#f43f5e',
  '#14b8a6',
  '#eab308',
  '#6366f1',
  '#ec4899',
  '#84cc16',
  '#06b6d4',
  '#f59e0b',
]

const normalizeView = (viewId) => {
  if (viewId === 'nodes' || viewId === 'relationships') return 'explorer'
  return VIEWS.includes(viewId) ? viewId : 'connectors'
}

const formatNumber = (value) => {
  if (value === null || value === undefined) return '0'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return '0'
  return numeric.toLocaleString()
}

const truncateText = (value, limit = 120) => {
  if (!value) return ''
  const text = String(value)
  if (text.length <= limit) return text
  return `${text.slice(0, limit - 3)}...`
}

const stringifyProps = (props) => {
  if (!props || Object.keys(props).length === 0) return '{}'
  try {
    const json = JSON.stringify(props, null, 2)
    if (json.length > 900) {
      return `${json.slice(0, 900)}...`
    }
    return json
  } catch {
    return String(props)
  }
}

const getConnectorTone = (status) => {
  if (status === 'active') return 'success'
  if (status === 'pilot') return 'warning'
  return 'default'
}

const getDraftProgress = (module) => {
  const active = (module?.connectors || []).filter((c) => c.status === 'active').length
  const total = (module?.connectors || []).length
  if (!total) return 0
  return Math.round((active / total) * 100)
}

function DataHubGraph({
  nodes,
  edges,
  labelColors,
  onNodeSelect,
  onEdgeSelect,
  onClearSelection,
  selectedNodeId,
  selectedEdgeId,
}) {
  const containerRef = useRef(null)
  const svgRef = useRef(null)
  const simRef = useRef(null)
  const dragNodeRef = useRef(null)
  const panRef = useRef(null)
  const [renderedNodes, setRenderedNodes] = useState([])
  const [renderedEdges, setRenderedEdges] = useState([])
  const [, setTick] = useState(0)
  const [size, setSize] = useState({ width: 720, height: 460 })
  const [hoveredNodeId, setHoveredNodeId] = useState(null)
  const [viewTransform, setViewTransform] = useState({ x: 0, y: 0, k: 1 })

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.contentRect) {
          setSize({
            width: Math.max(320, Math.round(entry.contentRect.width)),
            height: Math.max(320, Math.round(entry.contentRect.height)),
          })
        }
      })
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const nextNodes = nodes.map((node) => ({ ...node }))
    const nextEdges = edges.map((edge) => ({ ...edge }))
    // D3 needs mutable copies before the force simulation starts mutating positions.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRenderedNodes(nextNodes)
    setRenderedEdges(nextEdges)
    if (!nextNodes.length) {
      return undefined
    }
    const simulation = forceSimulation(nextNodes)
      .force(
        'link',
        forceLink(nextEdges)
          .id((node) => node.id)
          .distance(90)
          .strength(0.65),
      )
      .force('charge', forceManyBody().strength(-220))
      .force('center', forceCenter(size.width / 2, size.height / 2))
      .force('collide', forceCollide(26))
      .on('tick', () => setTick((prev) => prev + 1))
    simRef.current = simulation
    return () => simulation.stop()
  }, [nodes, edges, size.width, size.height])

  const nodeLookup = useMemo(() => {
    const map = {}
    renderedNodes.forEach((node) => {
      map[node.id] = node
    })
    return map
  }, [renderedNodes])

  const degreeMap = useMemo(() => {
    const map = {}
    edges.forEach((edge) => {
      map[edge.source] = (map[edge.source] || 0) + 1
      map[edge.target] = (map[edge.target] || 0) + 1
    })
    return map
  }, [edges])

  const getNodeFromEdge = (value) => {
    if (!value) return null
    if (typeof value === 'object') return value
    return nodeLookup[value]
  }

  const getSvgPoint = (event) => {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const rect = svg.getBoundingClientRect()
    const screenX = event.clientX - rect.left
    const screenY = event.clientY - rect.top
    return {
      x: (screenX - viewTransform.x) / viewTransform.k,
      y: (screenY - viewTransform.y) / viewTransform.k,
    }
  }

  const handleWheel = (event) => {
    event.preventDefault()
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const pointerX = event.clientX - rect.left
    const pointerY = event.clientY - rect.top
    const nextK = Math.max(0.45, Math.min(2.8, viewTransform.k * (event.deltaY > 0 ? 0.9 : 1.1)))
    setViewTransform({
      k: nextK,
      x: pointerX - ((pointerX - viewTransform.x) / viewTransform.k) * nextK,
      y: pointerY - ((pointerY - viewTransform.y) / viewTransform.k) * nextK,
    })
  }

  const handleCanvasPointerDown = (event) => {
    if (event.target !== svgRef.current) return
    panRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: viewTransform.x,
      originY: viewTransform.y,
    }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const handlePointerDown = (event, node) => {
    event.stopPropagation()
    const point = getSvgPoint(event)
    dragNodeRef.current = node
    node.fx = point.x
    node.fy = point.y
    if (simRef.current) {
      simRef.current.alphaTarget(0.3).restart()
    }
  }

  const handlePointerMove = (event) => {
    if (dragNodeRef.current) {
      const point = getSvgPoint(event)
      dragNodeRef.current.fx = point.x
      dragNodeRef.current.fy = point.y
      return
    }
    if (panRef.current) {
      setViewTransform((current) => ({
        ...current,
        x: panRef.current.originX + event.clientX - panRef.current.startX,
        y: panRef.current.originY + event.clientY - panRef.current.startY,
      }))
    }
  }

  const handlePointerUp = () => {
    panRef.current = null
    if (!dragNodeRef.current) return
    dragNodeRef.current.fx = null
    dragNodeRef.current.fy = null
    dragNodeRef.current = null
    if (simRef.current) {
      simRef.current.alphaTarget(0)
    }
  }

  return (
    <div className="graph-canvas" ref={containerRef}>
      <svg
        ref={svgRef}
        className="graph-svg"
        role="img"
        aria-label="Neo4j graph snapshot"
        onWheel={handleWheel}
        onPointerDown={handleCanvasPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onClick={(event) => {
          if (event.target === svgRef.current && onClearSelection) {
            onClearSelection()
          }
        }}
      >
        <g transform={`translate(${viewTransform.x}, ${viewTransform.y}) scale(${viewTransform.k})`}>
          <g>
            {renderedEdges.map((edge) => {
            const source = getNodeFromEdge(edge.source)
            const target = getNodeFromEdge(edge.target)
            if (!source || !target) return null
            return (
              <line
                key={edge.id}
                className={`graph-link ${
                  selectedEdgeId === edge.id ? 'graph-link--active' : ''
                }`}
                x1={source.x || 0}
                y1={source.y || 0}
                x2={target.x || 0}
                y2={target.y || 0}
                onClick={(event) => {
                  event.stopPropagation()
                  if (onEdgeSelect) onEdgeSelect(edge)
                }}
              />
            )
          })}
          </g>
          <g>
            {renderedNodes.map((node) => {
            const label = node.labels?.[0] || 'Node'
            const color = labelColors[label] || '#94a3b8'
            const degree = degreeMap[node.id] || 0
            const radius = 6 + Math.min(12, degree * 2)
            const isSelected = selectedNodeId === node.id
            const shouldShowLabel = isSelected || hoveredNodeId === node.id || degree >= 2
            return (
              <g
                key={node.id}
                className={`graph-node ${isSelected ? 'graph-node--active' : ''}`}
                transform={`translate(${node.x || 0}, ${node.y || 0})`}
                onPointerDown={(event) => handlePointerDown(event, node)}
                onClick={(event) => {
                  event.stopPropagation()
                  if (onNodeSelect) onNodeSelect(node)
                }}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
              >
                <circle r={radius} fill={color} />
                {shouldShowLabel ? (
                  <text x={radius + 6} y="4">
                    {truncateText(node.display || label, 24)}
                  </text>
                ) : null}
              </g>
            )
            })}
          </g>
        </g>
      </svg>
    </div>
  )
}

export function DataHubPage({
  t,
  activeTabOverride,
  onTabChange,
  showTabs = true,
  showIntro = true,
}) {
  const translate = t || ((key) => key)
  const [activeView, setActiveView] = useState(normalizeView(activeTabOverride))
  const [graph, setGraph] = useState(null)
  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  const [labelFilter, setLabelFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [catalog, setCatalog] = useState(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [showAllLabels, setShowAllLabels] = useState(false)
  const [selectedModuleId, setSelectedModuleId] = useState('crm')
  const [graphFullscreen, setGraphFullscreen] = useState(false)

  const applyView = (viewId) => {
    if (!viewId) return
    const nextView = normalizeView(viewId)
    setActiveView(nextView)
    if (onTabChange) onTabChange(nextView)
  }

  useEffect(() => {
    const nextView = normalizeView(activeTabOverride)
    if (activeTabOverride && nextView !== activeView) {
      setActiveView(nextView)
    }
  }, [activeTabOverride, activeView])


  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.set('limit', String(limit || DEFAULT_LIMIT))
      if (labelFilter) {
        params.set('label', labelFilter)
      }
      const payload = await requestJson(`/data-hub/graph?${params.toString()}`, {
        method: 'GET',
      })
      setGraph(payload)
    } catch (err) {
      const message = err?.message || 'Unable to load Neo4j data.'
      if (message.includes('Failed to fetch')) {
        setError(`Unable to reach the backend at ${getApiBaseUrl()}. Check the API port and logs.`)
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }, [labelFilter, limit])

  useEffect(() => {
    loadGraph()
  }, [loadGraph])

  const loadConnectorCatalog = useCallback(async () => {
    setCatalogLoading(true)
    setCatalogError('')
    try {
      const payload = await getJson('/data-hub/connectors', {
        cacheMs: 0,
        forceRefresh: true,
      })
      setCatalog(payload || null)
    } catch (err) {
      const message = err?.message || 'Unable to load Data Hub connectors.'
      if (message.includes('Failed to fetch')) {
        setCatalogError(`Unable to reach the backend at ${getApiBaseUrl()}. Check the API port and logs.`)
      } else {
        setCatalogError(message)
      }
    } finally {
      setCatalogLoading(false)
    }
  }, [])

  useEffect(() => {
    loadConnectorCatalog()
  }, [loadConnectorCatalog])

  const nodes = useMemo(() => graph?.nodes || [], [graph])
  const edges = useMemo(() => graph?.edges || [], [graph])
  const summary = useMemo(() => graph?.summary || {}, [graph])
  const labelCounts = useMemo(() => summary.labelCounts || [], [summary])
  const relationshipCounts = useMemo(() => summary.relationshipCounts || [], [summary])
  const connectorModules = useMemo(() => catalog?.modules || [], [catalog])
  const intakeModules = useMemo(
    () => connectorModules.filter((module) => INTAKE_MODULE_IDS.includes(module.moduleId)),
    [connectorModules],
  )
  const intakeConnectorCount = useMemo(
    () =>
      intakeModules.reduce((total, module) => total + Number(module.connectors?.length || 0), 0),
    [intakeModules],
  )
  const intakeActiveConnectorCount = useMemo(
    () =>
      intakeModules.reduce(
        (total, module) =>
          total +
          (module.connectors || []).filter((connector) => connector.status === 'active').length,
        0,
      ),
    [intakeModules],
  )
  const selectedModule = useMemo(
    () =>
      intakeModules.find((module) => module.moduleId === selectedModuleId) ||
      intakeModules[0] ||
      null,
    [intakeModules, selectedModuleId],
  )

  useEffect(() => {
    if (!intakeModules.length) return
    if (!intakeModules.find((module) => module.moduleId === selectedModuleId)) {
      setSelectedModuleId(intakeModules[0].moduleId)
    }
  }, [intakeModules, selectedModuleId])

  const moduleWorkspaceStats = useMemo(
    () =>
      intakeModules.map((module) => ({
        module,
        progress: getDraftProgress(module),
      })),
    [intakeModules],
  )

  useEffect(() => {
    if (selectedNode && !nodes.find((node) => node.id === selectedNode.id)) {
      setSelectedNode(null)
    }
    if (selectedEdge && !edges.find((edge) => edge.id === selectedEdge.id)) {
      setSelectedEdge(null)
    }
  }, [nodes, edges, selectedNode, selectedEdge])

  useEffect(() => {
    document.body.classList.toggle('datahub-graph-is-expanded', graphFullscreen)
    if (!graphFullscreen) return () => document.body.classList.remove('datahub-graph-is-expanded')
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setGraphFullscreen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.body.classList.remove('datahub-graph-is-expanded')
    }
  }, [graphFullscreen])

  const labelOptions = useMemo(() => {
    const set = new Set(labelCounts.map((item) => item.label))
    if (!set.size) {
      nodes.forEach((node) => {
        ;(node.labels || []).forEach((label) => set.add(label))
      })
    }
    return Array.from(set)
  }, [labelCounts, nodes])

  const labelColors = useMemo(() => {
    const labels = labelOptions.length ? labelOptions : ['Node']
    const map = {}
    labels.forEach((label, index) => {
      map[label] = COLOR_PALETTE[index % COLOR_PALETTE.length]
    })
    return map
  }, [labelOptions])

  const nodeLookup = useMemo(() => {
    const map = {}
    nodes.forEach((node) => {
      map[node.id] = node
    })
    return map
  }, [nodes])

  const normalizedQuery = searchQuery.trim().toLowerCase()

  const filteredNodes = useMemo(() => {
    if (!normalizedQuery) return nodes
    const matches = (value) =>
      value !== null &&
      value !== undefined &&
      String(value).toLowerCase().includes(normalizedQuery)
    return nodes.filter((node) => {
      if (matches(node.display)) return true
      if ((node.labels || []).some((label) => matches(label))) return true
      const props = node.properties || {}
      return Object.values(props).some((value) => {
        if (Array.isArray(value)) {
          return value.some((item) => matches(item))
        }
        if (value && typeof value === 'object') {
          return matches(JSON.stringify(value))
        }
        return matches(value)
      })
    })
  }, [nodes, normalizedQuery])

  const filteredEdges = useMemo(() => {
    if (!normalizedQuery) return edges
    const matches = (value) =>
      value !== null &&
      value !== undefined &&
      String(value).toLowerCase().includes(normalizedQuery)
    return edges.filter((edge) => {
      if (matches(edge.type)) return true
      const source = nodeLookup[edge.source]
      const target = nodeLookup[edge.target]
      if (matches(source?.display) || matches(target?.display)) return true
      const props = edge.properties || {}
      return Object.values(props).some((value) => {
        if (Array.isArray(value)) {
          return value.some((item) => matches(item))
        }
        if (value && typeof value === 'object') {
          return matches(JSON.stringify(value))
        }
        return matches(value)
      })
    })
  }, [edges, normalizedQuery, nodeLookup])

  const renderEmptyState = (title, message) => (
    <div className="module-card module-card__wide">
      <div className="card-header">
        <div>
          <h3>{title}</h3>
          <p className="muted">{message}</p>
        </div>
      </div>
      <div className="filter-row">
        <button className="button-secondary" type="button" onClick={loadGraph} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh snapshot'}
        </button>
      </div>
    </div>
  )

  const dataHubPulse = useMemo(
    () => [
      {
        label: 'Platform modules',
        value: formatNumber(intakeModules.length),
        icon: <IconDatabase size={18} />,
        badge: 'Live',
      },
      {
        label: 'Connector catalog',
        value: formatNumber(intakeConnectorCount),
        icon: <IconLink size={18} />,
        note: 'Across all modules',
      },
      {
        label: 'Active connectors',
        value: formatNumber(intakeActiveConnectorCount),
        icon: <IconChartDots size={18} />,
        note: 'Ready to use',
      },
      {
        label: 'Graph nodes',
        value: formatNumber(summary.nodeCount),
        icon: <IconGitBranch size={18} />,
        note: 'Neo4j live graph',
      },
    ],
    [
      intakeActiveConnectorCount,
      intakeConnectorCount,
      intakeModules.length,
      summary.nodeCount,
    ],
  )

  return (
    <section className="module">
      {showIntro ? (
        <div className="module-card module-card__wide section-intro">
          <div className="card-header">
            <div>
              <h3>{translate('module.dataHub')}</h3>
              <p className="muted">{translate('module.dataHub.desc')}</p>
            </div>
            <div className="pill">Data Hub</div>
          </div>
        </div>
      ) : null}

      <StatusMessage tone="error" message={error} />
      <StatusMessage tone="error" message={catalogError} />
      <StatusMessage
        tone="info"
        message={loading ? 'Loading graph snapshot...' : ''}
      />
      <StatusMessage
        tone="info"
        message={catalogLoading ? 'Loading connector catalog...' : ''}
      />

      <CivicStatGrid
        title="Graph intelligence pulse"
        description="Snapshot of Neo4j size, relationships, and explorer readiness."
        items={dataHubPulse}
      />
      {showTabs ? (
        <div className="subtabs">
          {[
            { id: 'connectors', label: 'Data connectors' },
            { id: 'explorer', label: 'Graph explorer' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeView === tab.id ? 'subtab active' : 'subtab'}
              onClick={() => applyView(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {activeView === 'explorer' && (
        <div className="stack">
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Neo4j snapshot</h3>
                    <p className="muted">
                      High-level counts of nodes and relationships currently in the database.
                    </p>
                  </div>
                  <div className="pill">Graph</div>
                </div>
                <div className="report-metrics">
                  <div className="report-metric">
                    <span>Total nodes</span>
                    <strong>{formatNumber(summary.nodeCount)}</strong>
                  </div>
                  <div className="report-metric">
                    <span>Total relationships</span>
                    <strong>{formatNumber(summary.relationshipCount)}</strong>
                  </div>
                  <div className="report-metric">
                    <span>Snapshot nodes</span>
                    <strong>{formatNumber(nodes.length)}</strong>
                  </div>
                  <div className="report-metric">
                    <span>Snapshot relationships</span>
                    <strong>{formatNumber(edges.length)}</strong>
                  </div>
                </div>
                <div className="filter-row">
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={loadGraph}
                    disabled={loading}
                  >
                    {loading ? 'Refreshing...' : 'Refresh snapshot'}
                  </button>
                </div>
              </div>

              {nodes.length ? (
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>Neo4j graph explorer</h3>
                      <p className="muted">
                        Drag nodes to reposition the network. Click a node or relationship for
                        details, then inspect labels, nodes, and relationship records below.
                      </p>
                    </div>
                  </div>
                  <FormSection
                    title={
                      <span>
                        Snapshot settings{' '}
                        <InfoHint text="Limit controls how many relationships we pull from Neo4j." />
                      </span>
                    }
                    description="Filter by label to focus the graph."
                    actions={
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={loadGraph}
                        disabled={loading}
                      >
                        {loading ? 'Refreshing...' : 'Refresh snapshot'}
                      </button>
                    }
                  >
                    <div className="form-grid">
                      <Field id="datahub-label" label="Label filter">
                        <select
                          className="select"
                          value={labelFilter}
                          onChange={(event) => setLabelFilter(event.target.value)}
                        >
                          <option value="">All labels</option>
                          {labelOptions.map((label) => (
                            <option key={label} value={label}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field id="datahub-limit" label="Relationship limit" helper="Max 300 relationships.">
                        <input
                          className="input"
                          type="number"
                          min="10"
                          max="300"
                          value={limit}
                          onChange={(event) => setLimit(event.target.value)}
                        />
                      </Field>
                    </div>
                  </FormSection>
                  <div className={graphFullscreen ? 'graph-frame graph-frame--fullscreen' : 'graph-frame'}>
                    <div className="graph-frame__toolbar">
                      <div>
                        <h4>Interactive graph</h4>
                        <p className="muted">Drag nodes, select relationships, and inspect graph records.</p>
                      </div>
                      <div className="graph-frame__actions">
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={loadGraph}
                          disabled={loading}
                        >
                          {loading ? 'Refreshing...' : 'Refresh'}
                        </button>
                        <button
                          className="map-filters__toggle map-filters__icon-toggle"
                          type="button"
                          onClick={() => setGraphFullscreen((prev) => !prev)}
                          aria-pressed={graphFullscreen}
                          aria-label={graphFullscreen ? 'Exit expanded graph' : 'Expand graph'}
                          title={graphFullscreen ? 'Exit expanded graph' : 'Expand graph'}
                        >
                          {graphFullscreen ? <IconArrowsMinimize size={17} /> : <IconArrowsMaximize size={17} />}
                        </button>
                      </div>
                    </div>
                    <div className="graph-layout">
                      <DataHubGraph
                        nodes={nodes}
                        edges={edges}
                        labelColors={labelColors}
                        selectedNodeId={selectedNode?.id}
                        selectedEdgeId={selectedEdge?.id}
                        onNodeSelect={(node) => {
                          setSelectedNode(node)
                          setSelectedEdge(null)
                        }}
                        onEdgeSelect={(edge) => {
                          setSelectedEdge(edge)
                          setSelectedNode(null)
                        }}
                        onClearSelection={() => {
                          setSelectedNode(null)
                          setSelectedEdge(null)
                        }}
                      />
                      <aside className="graph-legend">
                        <div className="graph-details">
                          <h4>Selection</h4>
                          {selectedNode ? (
                            <>
                              <span className="pill">Node</span>
                              <h5>{selectedNode.display || selectedNode.id}</h5>
                              <p className="muted">
                                {(selectedNode.labels || []).join(', ') || 'No labels'}
                              </p>
                              <pre className="code-block">{stringifyProps(selectedNode.properties)}</pre>
                            </>
                          ) : null}
                          {selectedEdge ? (
                            <>
                              <span className="pill">Relationship</span>
                              <h5>{selectedEdge.type || 'Related to'}</h5>
                              <p className="muted">
                                {nodeLookup[selectedEdge.source]?.display || selectedEdge.source} {'->'}{' '}
                                {nodeLookup[selectedEdge.target]?.display || selectedEdge.target}
                              </p>
                              <pre className="code-block">{stringifyProps(selectedEdge.properties)}</pre>
                            </>
                          ) : null}
                          {!selectedNode && !selectedEdge ? (
                            <p className="muted">Click a node or relationship to inspect details.</p>
                          ) : null}
                        </div>
                        <div className="graph-details">
                          <h4>Labels</h4>
                          <div className="graph-legend__list">
                            {(labelOptions.length ? labelOptions : ['Node'])
                              .slice(0, showAllLabels ? labelOptions.length : 6)
                              .map((label) => (
                              <div className="graph-legend__item" key={label}>
                                <span
                                  className="graph-legend__swatch"
                                  style={{ background: labelColors[label] }}
                                />
                                <span>{label}</span>
                              </div>
                            ))}
                          </div>
                          {labelOptions.length > 6 ? (
                            <button
                              className="button-secondary button-secondary--small"
                              type="button"
                              onClick={() => setShowAllLabels((prev) => !prev)}
                            >
                              {showAllLabels ? 'See fewer' : 'See more'}
                            </button>
                          ) : null}
                        </div>
                      </aside>
                    </div>
                  </div>
                </div>
              ) : null}

              {labelCounts.length ? (
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>Label explorer</h3>
                      <p className="muted">
                        Distribution of labels across the Neo4j graph snapshot.
                      </p>
                    </div>
                  </div>
                  <div className="cluster-grid">
                    {labelCounts.map((item) => (
                      <div className="cluster-card" key={item.label}>
                        <div className="cluster-card__header">
                          <h4>{item.label}</h4>
                          <span className="pill">{formatNumber(item.count)}</span>
                        </div>
                        <p className="muted">Nodes carrying the {item.label} label.</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {relationshipCounts.length ? (
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>Relationship explorer</h3>
                      <p className="muted">
                        Most common relationship types currently present in Neo4j.
                      </p>
                    </div>
                  </div>
                  <div className="cluster-grid">
                    {relationshipCounts.map((item) => (
                      <div className="cluster-card" key={item.label}>
                        <div className="cluster-card__header">
                          <h4>{item.label}</h4>
                          <span className="pill">{formatNumber(item.count)}</span>
                        </div>
                        <p className="muted">Edges stored as {item.label}.</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {nodes.length ? (
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>Node browser</h3>
                      <p className="muted">
                        Search and inspect node records loaded into the current Neo4j snapshot.
                      </p>
                    </div>
                  </div>
                  <div className="filter-row">
                    <Field id="datahub-search-nodes" label="Search nodes">
                      <input
                        className="input"
                        placeholder="Search labels, names, or properties"
                        value={searchQuery}
                        onChange={(event) => setSearchQuery(event.target.value)}
                      />
                    </Field>
                    {searchQuery ? (
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => setSearchQuery('')}
                      >
                        Clear search
                      </button>
                    ) : null}
                  </div>
                  <div className="cluster-grid">
                    {filteredNodes.map((node) => (
                      <div className="cluster-card" key={node.id}>
                        <div className="cluster-card__header">
                          <h4>{node.display || node.id}</h4>
                          <div className="cluster-tags">
                            {(node.labels || []).length ? (
                              node.labels.map((label) => (
                                <span className="cluster-tag" key={`${node.id}-${label}`}>
                                  {label}
                                </span>
                              ))
                            ) : (
                              <span className="cluster-tag">No label</span>
                            )}
                          </div>
                        </div>
                        <pre className="code-block">{stringifyProps(node.properties)}</pre>
                      </div>
                    ))}
                    {!filteredNodes.length ? (
                      <p className="muted">No nodes match the search.</p>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {edges.length ? (
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>Relationship browser</h3>
                      <p className="muted">
                        Search relationship records extracted from the current Neo4j snapshot.
                      </p>
                    </div>
                  </div>
                  <div className="filter-row">
                    <Field id="datahub-search-edges" label="Search relationships">
                      <input
                        className="input"
                        placeholder="Search types, nodes, or properties"
                        value={searchQuery}
                        onChange={(event) => setSearchQuery(event.target.value)}
                      />
                    </Field>
                    {searchQuery ? (
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => setSearchQuery('')}
                      >
                        Clear search
                      </button>
                    ) : null}
                  </div>
                  <div className="cluster-grid">
                    {filteredEdges.map((edge) => (
                      <div className="cluster-card" key={edge.id}>
                        <div className="cluster-card__header">
                          <h4>{edge.type || 'Relationship'}</h4>
                          <span className="pill">Edge</span>
                        </div>
                        <p className="muted">
                          {nodeLookup[edge.source]?.display || edge.source} {'->'}{' '}
                          {nodeLookup[edge.target]?.display || edge.target}
                        </p>
                        <pre className="code-block">{stringifyProps(edge.properties)}</pre>
                      </div>
                    ))}
                    {!filteredEdges.length ? (
                      <p className="muted">No relationships match the search.</p>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {!nodes.length && !loading
                ? renderEmptyState(
                    'No graph data yet',
                    'Load nodes into Neo4j to visualize them in the graph explorer.',
                  )
                : null}
        </div>
      )}

      {activeView === 'connectors' && (
        <div className="stack">
          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Data connectors</h3>
                <p className="muted">
                  All active connectors across every module. Data flows into the shared Neo4j graph.
                </p>
              </div>
              <div className="pill">Neo4j</div>
            </div>
            <div className="report-metrics">
              <div className="report-metric">
                <span>Modules</span>
                <strong>{formatNumber(intakeModules.length)}</strong>
              </div>
              <div className="report-metric">
                <span>Total connectors</span>
                <strong>{formatNumber(intakeConnectorCount)}</strong>
              </div>
              <div className="report-metric">
                <span>Neo4j graph nodes</span>
                <strong>{formatNumber(summary.nodeCount)}</strong>
              </div>
            </div>
            <div className="filter-row">
              <button className="button-secondary" type="button" onClick={loadConnectorCatalog} disabled={catalogLoading}>
                {catalogLoading ? 'Refreshing...' : 'Refresh catalog'}
              </button>
              <button className="button-secondary" type="button" onClick={loadGraph} disabled={loading}>
                {loading ? 'Refreshing graph...' : 'Refresh graph'}
              </button>
              <button className="button-secondary" type="button" onClick={() => applyView('explorer')}>
                Open graph explorer
              </button>
            </div>
          </div>

          {intakeModules.length ? (
            <div className="datahub-upload-grid">
              {moduleWorkspaceStats.map(({ module, progress }) => (
                <div
                  className={`datahub-upload-tile ${
                    selectedModule?.moduleId === module.moduleId ? 'is-active' : ''
                  }`}
                  key={module.moduleId}
                >
                  <div className="cluster-card__header">
                    <h3>{module.moduleLabel}</h3>
                    <span
                      className={`pill ${
                        getConnectorTone(module.status) === 'success'
                          ? 'pill--success'
                          : getConnectorTone(module.status) === 'warning'
                            ? 'pill--warning'
                            : ''
                      }`}
                    >
                      {module.status}
                    </span>
                  </div>
                  <p className="muted">{module.description}</p>
                  <div className="report-metrics">
                    <div className="report-metric">
                      <span>Readiness</span>
                      <strong>{progress}%</strong>
                    </div>
                    <div className="report-metric">
                      <span>Connectors</span>
                      <strong>{formatNumber(module.connectors?.length)}</strong>
                    </div>
                    <div className="report-metric">
                      <span>Target</span>
                      <strong>Neo4j</strong>
                    </div>
                  </div>

                  <div className="cluster-tags">
                    {(module.connectors || []).map((connector) => (
                      <span className="cluster-tag" key={connector.connectorId}>
                        {connector.name}
                      </span>
                    ))}
                  </div>

                  <div className="datahub-upload-actions">
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => {
                        setSelectedModuleId(module.moduleId)
                        applyView('explorer')
                      }}
                    >
                      Inspect graph
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </section>
  )
}
