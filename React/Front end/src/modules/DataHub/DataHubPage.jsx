import { useEffect, useMemo, useRef, useState } from 'react'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
} from 'd3-force'
import { IconChartDots, IconDatabase, IconGitBranch, IconLink } from '@tabler/icons-react'
import { API_BASE, requestJson } from '../../services/api'
import { CivicStatGrid, Field, FormSection, InfoHint, StatusMessage } from '../../ui'

const VIEWS = ['overview', 'explorer', 'connectors', 'nodes', 'relationships']
const DEFAULT_LIMIT = 80
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
  } catch (err) {
    return String(props)
  }
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
  const [renderedNodes, setRenderedNodes] = useState([])
  const [renderedEdges, setRenderedEdges] = useState([])
  const [tick, setTick] = useState(0)
  const [size, setSize] = useState({ width: 720, height: 460 })
  const [hoveredNodeId, setHoveredNodeId] = useState(null)

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
  }, [renderedNodes, tick])

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
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
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
    if (!dragNodeRef.current) return
    const point = getSvgPoint(event)
    dragNodeRef.current.fx = point.x
    dragNodeRef.current.fy = point.y
  }

  const handlePointerUp = () => {
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
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onClick={(event) => {
          if (event.target === svgRef.current && onClearSelection) {
            onClearSelection()
          }
        }}
      >
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
      </svg>
    </div>
  )
}

export function DataHubPage({
  t,
  activeTabOverride,
  onTabChange,
  showTabs = true,
}) {
  const translate = t || ((key) => key)
  const [activeView, setActiveView] = useState(
    VIEWS.includes(activeTabOverride) ? activeTabOverride : 'overview',
  )
  const [graph, setGraph] = useState(null)
  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  const [labelFilter, setLabelFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [showAllLabels, setShowAllLabels] = useState(false)

  const applyView = (viewId) => {
    if (!viewId) return
    setActiveView(viewId)
    if (onTabChange) onTabChange(viewId)
  }

  useEffect(() => {
    if (activeTabOverride && activeTabOverride !== activeView) {
      setActiveView(activeTabOverride)
    }
  }, [activeTabOverride, activeView])

  const loadGraph = async () => {
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
        setError(`Unable to reach the backend at ${API_BASE}. Check the API port and logs.`)
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGraph()
  }, [limit, labelFilter])

  const nodes = graph?.nodes || []
  const edges = graph?.edges || []
  const summary = graph?.summary || {}
  const labelCounts = summary.labelCounts || []
  const relationshipCounts = summary.relationshipCounts || []

  useEffect(() => {
    if (selectedNode && !nodes.find((node) => node.id === selectedNode.id)) {
      setSelectedNode(null)
    }
    if (selectedEdge && !edges.find((edge) => edge.id === selectedEdge.id)) {
      setSelectedEdge(null)
    }
  }, [nodes, edges, selectedNode, selectedEdge])

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
        label: 'Total nodes',
        value: formatNumber(summary.nodeCount),
        icon: <IconDatabase size={18} />,
        badge: 'Live',
      },
      {
        label: 'Relationships',
        value: formatNumber(summary.relationshipCount),
        icon: <IconLink size={18} />,
        note: 'Graph edges',
      },
      {
        label: 'Snapshot nodes',
        value: formatNumber(nodes.length),
        icon: <IconChartDots size={18} />,
        note: 'Explorer view',
      },
      {
        label: 'Snapshot edges',
        value: formatNumber(edges.length),
        icon: <IconGitBranch size={18} />,
        note: 'In memory',
      },
    ],
    [edges.length, nodes.length, summary.nodeCount, summary.relationshipCount],
  )

  const connectorCatalog = useMemo(
    () => [
      {
        id: 'dbms',
        title: 'Database APIs',
        description: 'Connect to external DBMS sources before writing to Neo4j.',
        items: ['PostgreSQL', 'MySQL', 'MongoDB', 'BigQuery'],
      },
      {
        id: 'public',
        title: 'Public sources',
        description: 'Pull data from open data portals and public APIs.',
        items: ['OpenStreetMap', 'World Bank', 'UN Data', 'OpenSanctions'],
      },
      {
        id: 'streams',
        title: 'Event streams',
        description: 'Ingest streaming updates to keep Neo4j current.',
        items: ['Webhook feed', 'Kafka topic', 'CSV drop'],
      },
    ],
    [],
  )

  return (
    <section className="module">
      <CivicStatGrid
        title="Graph intelligence pulse"
        description="Snapshot of Neo4j size, relationships, and explorer readiness."
        items={dataHubPulse}
      />
      {showTabs ? (
        <div className="subtabs">
          {[
            { id: 'overview', label: 'Overview' },
            { id: 'explorer', label: 'Explorer' },
            { id: 'connectors', label: 'Data connectors' },
            { id: 'nodes', label: 'Nodes' },
            { id: 'relationships', label: 'Relationships' },
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

      <StatusMessage tone="error" message={error} />
      <StatusMessage
        tone="info"
        message={loading ? 'Loading graph snapshot...' : ''}
      />

      {activeView === 'overview' && (
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
              <button className="button-secondary" type="button" onClick={loadGraph} disabled={loading}>
                {loading ? 'Refreshing...' : 'Refresh snapshot'}
              </button>
            </div>
          </div>

          {labelCounts.length ? (
            <div className="module-card module-card__wide">
              <div className="card-header">
                <div>
                  <h3>Node labels</h3>
                  <p className="muted">Distribution of labels across the full graph.</p>
                </div>
              </div>
              <div className="cluster-grid">
                {labelCounts.map((item) => (
                  <div className="cluster-card" key={item.label}>
                    <div className="cluster-card__header">
                      <h4>{item.label}</h4>
                      <span className="pill">{formatNumber(item.count)}</span>
                    </div>
                    <p className="muted">Nodes with the {item.label} label.</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {relationshipCounts.length ? (
            <div className="module-card module-card__wide">
              <div className="card-header">
                <div>
                  <h3>Relationship types</h3>
                  <p className="muted">Most common relationship types in Neo4j.</p>
                </div>
              </div>
              <div className="cluster-grid">
                {relationshipCounts.map((item) => (
                  <div className="cluster-card" key={item.label}>
                    <div className="cluster-card__header">
                      <h4>{item.label}</h4>
                      <span className="pill">{formatNumber(item.count)}</span>
                    </div>
                    <p className="muted">Edges of type {item.label}.</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {activeView === 'overview' && !nodes.length && !loading
        ? renderEmptyState('No graph data yet', 'Load data into Neo4j to see a snapshot.')
        : null}

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
                      <h3>Graph explorer</h3>
                      <p className="muted">
                        Drag nodes to reposition the network. Click a node or relationship for details.
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
                  <div className="graph-frame">
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
                <h3>Connector staging layer</h3>
                <p className="muted">
                  Neo4j is the system of record. Use connectors to pull from DBMS APIs or public
                  sources, validate them, then promote into Neo4j.
                </p>
              </div>
              <div className="pill">Staging</div>
            </div>
            <div className="report-metrics">
              <div className="report-metric">
                <span>Sources connected</span>
                <strong>0</strong>
              </div>
              <div className="report-metric">
                <span>Pending imports</span>
                <strong>0</strong>
              </div>
              <div className="report-metric">
                <span>Last sync</span>
                <strong>—</strong>
              </div>
              <div className="report-metric">
                <span>Neo4j status</span>
                <strong>Ready</strong>
              </div>
            </div>
            <div className="filter-row">
              <button className="button-secondary" type="button">
                Add connector
              </button>
              <button className="button-secondary" type="button">
                Review staging queue
              </button>
            </div>
          </div>

          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Connector catalog</h3>
                <p className="muted">
                  Choose a source type, map fields, and validate before ingesting to Neo4j.
                </p>
              </div>
            </div>
            <div className="cluster-grid">
              {connectorCatalog.map((group) => (
                <div className="cluster-card" key={group.id}>
                  <div className="cluster-card__header">
                    <h4>{group.title}</h4>
                    <span className="pill">{group.items.length}</span>
                  </div>
                  <p className="muted">{group.description}</p>
                  <ul className="compact-list">
                    {group.items.map((item) => (
                      <li key={item}>
                        <span>{item}</span>
                        <strong>Configure</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeView === 'nodes' && nodes.length ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Nodes in snapshot</h3>
              <p className="muted">Nodes loaded into the current graph snapshot.</p>
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
              <button className="button-secondary" type="button" onClick={() => setSearchQuery('')}>
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
            {!filteredNodes.length ? <p className="muted">No nodes match the search.</p> : null}
          </div>
        </div>
      ) : null}

      {activeView === 'nodes' && !nodes.length && !loading
        ? renderEmptyState(
            'No nodes in snapshot',
            'Increase the snapshot limit or load data into Neo4j to see nodes.',
          )
        : null}

      {activeView === 'relationships' && edges.length ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Relationships in snapshot</h3>
              <p className="muted">Relationships extracted from Neo4j.</p>
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
              <button className="button-secondary" type="button" onClick={() => setSearchQuery('')}>
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

      {activeView === 'relationships' && !edges.length && !loading
        ? renderEmptyState(
            'No relationships in snapshot',
            'Load relationships into Neo4j or increase the snapshot limit.',
          )
        : null}
    </section>
  )
}
