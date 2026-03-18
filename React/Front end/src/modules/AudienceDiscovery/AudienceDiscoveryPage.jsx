import React, { useEffect, useMemo, useState } from 'react'
import { Bar } from 'react-chartjs-2'
import { Chart as ChartJS, BarElement, CategoryScale, Legend, LinearScale, Tooltip } from 'chart.js'
import { API_BASE, requestJson } from '../../services/api'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const DEFAULT_URL = ''

export function AudienceDiscoveryPage({ t }) {
  const translate = t || ((key) => key)
  const [targetUrl, setTargetUrl] = useState(DEFAULT_URL)
  const [manualUrls, setManualUrls] = useState('')
  const [description, setDescription] = useState('')
  const [brand, setBrand] = useState('')
  const [locale, setLocale] = useState('')
  const [crawlDepth, setCrawlDepth] = useState(1)
  const [allowedDomains, setAllowedDomains] = useState('')
  const [productRules, setProductRules] = useState('')
  const [crawlTimeout, setCrawlTimeout] = useState(12)
  const [maxPages, setMaxPages] = useState(200)
  const [clusterCount, setClusterCount] = useState('')
  const [languagePreset, setLanguagePreset] = useState('auto')
  const [analysis, setAnalysis] = useState(null)
  const [segments, setSegments] = useState([])
  const [pages, setPages] = useState([])
  const [clusters, setClusters] = useState([])
  const [messaging, setMessaging] = useState([])
  const [selectedPageId, setSelectedPageId] = useState('')
  const [pageChunks, setPageChunks] = useState([])
  const [selectedClusterId, setSelectedClusterId] = useState('')
  const [clusterChunks, setClusterChunks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)
  const [activeView, setActiveView] = useState('overview')
  const [exportStatus, setExportStatus] = useState('')
  const [runNotice, setRunNotice] = useState('')
  const [copyNotice, setCopyNotice] = useState('')
  const [sitemapNotice, setSitemapNotice] = useState('')
  const [pageFilter, setPageFilter] = useState('')
  const [segmentGroupBy, setSegmentGroupBy] = useState('cluster')
  const [segmentClusterFilter, setSegmentClusterFilter] = useState('')

  const metrics = useMemo(() => {
    if (!analysis?.summary) return []
    return [
      { label: 'Coverage', value: analysis.summary.coverage ?? '—' },
      { label: 'Explainability', value: analysis.summary.explainability ?? '—' },
      { label: 'Evidence pass rate', value: analysis.summary.evidencePassRate ?? '—' },
      { label: 'Runtime (sec)', value: analysis.summary.runtimeSeconds ?? '—' },
      { label: 'P95 runtime (sec)', value: analysis.summary.p95RuntimeSeconds ?? '—' },
      { label: 'Pages crawled', value: analysis.summary.pagesCrawled ?? '—' },
      { label: 'Segments', value: analysis.summary.segmentsGenerated ?? '—' },
      { label: 'Verified segments', value: analysis.summary.verifiedSegments ?? '—' },
      { label: 'Chunks', value: analysis.summary.chunksCreated ?? '—' },
      { label: 'Clusters', value: analysis.summary.clustersCreated ?? '—' },
    ]
  }, [analysis])

  const progress = useMemo(() => {
    const stages = status?.stages || analysis?.stages || []
    if (!stages.length) return 0
    const done = stages.filter((stage) => stage.status === 'success').length
    return Math.round((done / stages.length) * 100)
  }, [status, analysis])

  const clusterLookup = useMemo(() => {
    const map = {}
    clusters.forEach((cluster) => {
      (cluster.chunkIds || []).forEach((chunkId) => {
        map[chunkId] = cluster.clusterId
      })
    })
    return map
  }, [clusters])

  const filteredPages = useMemo(() => {
    if (!pageFilter.trim()) return pages
    const query = pageFilter.toLowerCase()
    return pages.filter(
      (page) =>
        page.title?.toLowerCase().includes(query) ||
        page.url?.toLowerCase().includes(query),
    )
  }, [pages, pageFilter])

  const segmentsByGroup = useMemo(() => {
    const grouped = {}
    segments.forEach((segment) => {
      const evidence = segment.evidence || []
      let groupId = 'unclustered'
      if (segmentGroupBy === 'cluster') {
        groupId = evidence.map((item) => clusterLookup[item.chunkId]).find(Boolean) || 'unclustered'
      } else if (segmentGroupBy === 'page') {
        groupId = segment.pageUrl || evidence.map((item) => item.url).find(Boolean) || 'unassigned'
      }
      if (segmentGroupBy === 'cluster' && segmentClusterFilter && groupId !== segmentClusterFilter) {
        return
      }
      if (!grouped[groupId]) grouped[groupId] = []
      grouped[groupId].push(segment)
    })
    return grouped
  }, [segments, clusterLookup, segmentGroupBy, segmentClusterFilter])

  const segmentCountsByCluster = useMemo(() => {
    const counts = {}
    segments.forEach((segment) => {
      const evidence = segment.evidence || []
      const clusterId = evidence.map((item) => clusterLookup[item.chunkId]).find(Boolean)
      if (!clusterId) return
      counts[clusterId] = (counts[clusterId] || 0) + 1
    })
    return counts
  }, [segments, clusterLookup])

  const metricsChart = useMemo(() => {
    if (!analysis?.summary) return null
    const coverage = Number(analysis.summary.coverage || 0) * 100
    const explainability = Number(analysis.summary.explainability || 0) * 100
    const evidencePass = Number(analysis.summary.evidencePassRate || 0) * 100
    return {
      data: {
        labels: ['Coverage', 'Explainability', 'Evidence pass'],
        datasets: [
          {
            label: 'Quality (%)',
            data: [coverage, explainability, evidencePass],
            backgroundColor: ['#93c5fd', '#86efac', '#fdba74'],
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
        scales: {
          y: { min: 0, max: 100 },
        },
      },
    }
  }, [analysis])

  const formatPercent = (value) => {
    if (value === null || value === undefined) return '—'
    const numeric = Number(value)
    if (Number.isNaN(numeric)) return '—'
    return `${Math.round(numeric * 100)}%`
  }

  const runSnapshot = useMemo(() => {
    if (!analysis?.summary) return []
    const summary = analysis.summary
    return [
      { label: 'Pages', value: summary.pagesCrawled ?? '—' },
      { label: 'Chunks', value: summary.chunksCreated ?? '—' },
      { label: 'Segments', value: summary.segmentsGenerated ?? '—' },
      { label: 'Verified', value: summary.verifiedSegments ?? '—' },
      { label: 'Evidence pass', value: formatPercent(summary.evidencePassRate) },
      {
        label: 'Runtime',
        value: summary.runtimeSeconds ? `${summary.runtimeSeconds}s` : '—',
      },
    ]
  }, [analysis])

  const topSegments = useMemo(() => {
    if (!segments.length) return []
    return [...segments]
      .sort((a, b) => {
        const confidenceDelta = (b.confidence || 0) - (a.confidence || 0)
        if (confidenceDelta !== 0) return confidenceDelta
        return (b.evidence?.length || 0) - (a.evidence?.length || 0)
      })
      .slice(0, 3)
  }, [segments])

  const truncateText = (text, limit = 140) => {
    if (!text) return ''
    const cleaned = String(text).replace(/\s+/g, ' ').trim()
    if (cleaned.length <= limit) return cleaned
    return `${cleaned.slice(0, limit - 3)}...`
  }

  const analysisSource = useMemo(() => {
    if (analysis?.url) return analysis.url
    if (targetUrl.trim()) return targetUrl.trim()
    const firstManual = manualUrls
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find(Boolean)
    return firstManual || ''
  }, [analysis?.url, manualUrls, targetUrl])

  useEffect(() => {
    if (!analysis?.runId) return
    let timer
    const poll = async () => {
      try {
        const payload = await requestJson(
          `/audience-discovery/analysis/${analysis.runId}/status`,
          { method: 'GET' },
        )
        setStatus(payload)
        if (payload.status === 'completed' || payload.status === 'failed') {
          if (timer) clearInterval(timer)
        }
      } catch (err) {
        // Ignore polling errors.
      }
    }
    poll()
    timer = setInterval(poll, 2000)
    return () => {
      if (timer) clearInterval(timer)
    }
  }, [analysis?.runId])

  const handleAnalyze = async () => {
    const trimmedUrl = targetUrl.trim()
    const manualList = manualUrls
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean)
    const domainList = allowedDomains
      .split(/[\s,]+/)
      .map((item) => item.trim())
      .filter(Boolean)
    const ruleList = productRules
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean)
    if (!trimmedUrl && manualList.length === 0) {
      setError('Enter a sitemap URL or at least one product URL.')
      return
    }
    setError('')
    setLoading(true)
    setAnalysis(null)
    setSegments([])
    setPages([])
    setClusters([])
    setMessaging([])
    setSelectedPageId('')
    setPageChunks([])
    setSelectedClusterId('')
    setClusterChunks([])
    setStatus(null)
    setExportStatus('')
    setRunNotice('')
    setSitemapNotice('')
    try {
      const result = await requestJson('/audience-discovery/analysis/start', {
        payload: {
          url: trimmedUrl,
          urls: manualList,
          description: description.trim(),
          brand: brand.trim(),
          locale: locale.trim(),
          crawlDepth: Number(crawlDepth) || 1,
          crawlTimeoutS: Number(crawlTimeout) || 12,
          maxPages: Number(maxPages) || 200,
          allowedDomains: domainList,
          productRules: ruleList,
          clusterCount: clusterCount ? Number(clusterCount) : undefined,
        },
      })
      setAnalysis(result)
      setRunNotice(`Run created: ${result.runId}`)
      const [pagesPayload, segmentsPayload, clustersPayload, metricsPayload] = await Promise.all([
        requestJson(`/audience-discovery/analysis/${result.runId}/pages`, { method: 'GET' }),
        requestJson(`/audience-discovery/analysis/${result.runId}/segments`, { method: 'GET' }),
        requestJson(`/audience-discovery/analysis/${result.runId}/clusters`, { method: 'GET' }),
        requestJson(`/audience-discovery/analysis/${result.runId}/metrics`, { method: 'GET' }),
      ])
      setPages(pagesPayload.pages || [])
      setSegments(segmentsPayload.segments || [])
      setClusters(clustersPayload.clusters || [])
      setAnalysis((prev) => ({ ...(prev || {}), summary: metricsPayload.summary }))
    } catch (err) {
      const message = err?.message || 'Audience discovery failed.'
      if (message.includes('Failed to fetch')) {
        setError(
          `Unable to reach the backend at ${API_BASE}. Check the API port and backend logs.`,
        )
      } else if (message.includes('Internal Server Error')) {
        setError('Backend error while running discovery. Check backend logs for details.')
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSegmentAction = async (segmentId, action) => {
    if (!analysis?.runId) return
    try {
      const payload = await requestJson(
        `/audience-discovery/analysis/${analysis.runId}/segments/confirm`,
        {
          payload: {
            segmentIds: [segmentId],
            action,
          },
        },
      )
      setSegments(payload.segments || [])
      if (action === 'confirm') {
        const messagingPayload = await requestJson(
          `/audience-discovery/analysis/${analysis.runId}/messaging`,
          { method: 'GET' },
        )
        setMessaging(messagingPayload.messaging || [])
      }
    } catch (err) {
      setError(err.message || 'Unable to update segment.')
    }
  }

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopyNotice('Copied to clipboard.')
      setTimeout(() => setCopyNotice(''), 1500)
    } catch (err) {
      setCopyNotice('Copy failed.')
    }
  }

  const handleSitemapFile = (file) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const text = String(reader.result || '')
        const parser = new DOMParser()
        const xml = parser.parseFromString(text, 'application/xml')
        const locs = Array.from(xml.getElementsByTagName('loc'))
          .map((node) => node.textContent?.trim())
          .filter(Boolean)
        if (!locs.length) {
          setSitemapNotice('No URLs found in sitemap file.')
          return
        }
        setManualUrls(locs.slice(0, 200).join('\n'))
        setSitemapNotice(`Loaded ${Math.min(locs.length, 200)} URLs from sitemap.`)
      } catch (err) {
        setSitemapNotice('Unable to parse sitemap file.')
      }
    }
    reader.readAsText(file)
  }

  const loadPageChunks = async (pageId) => {
    if (!analysis?.runId || !pageId) return
    try {
      const payload = await requestJson(
        `/audience-discovery/analysis/${analysis.runId}/pages/${pageId}/chunks`,
        { method: 'GET' },
      )
      setSelectedPageId(pageId)
      setPageChunks(payload.chunks || [])
    } catch (err) {
      setError(err.message || 'Unable to load page chunks.')
    }
  }

  const loadClusterChunks = async (clusterId) => {
    if (!analysis?.runId || !clusterId) return
    try {
      const payload = await requestJson(
        `/audience-discovery/analysis/${analysis.runId}/clusters/${clusterId}/chunks`,
        { method: 'GET' },
      )
      setSelectedClusterId(clusterId)
      setClusterChunks(payload.chunks || [])
    } catch (err) {
      setError(err.message || 'Unable to load cluster chunks.')
    }
  }

  const stageSnapshot = useMemo(() => {
    if (status?.stages?.length) return status.stages
    return analysis?.stages || []
  }, [status, analysis])

  const stageTitle = status?.stages?.length ? 'Live status' : 'Run status'
  const stageSubtitle = status?.stages?.length
    ? 'Updated every 2 seconds while the run is active.'
    : 'Pipeline progress for this analysis.'

  return (
    <section className="module">
      <header className="module-header">
        <div className="module-header__text">
          <h2>{translate('module.audienceDiscovery')}</h2>
          <p>{translate('module.audienceDiscovery.desc')}</p>
        </div>
      </header>

      <div className="subtabs">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'pages', label: 'Pages' },
          { id: 'segments', label: 'Segments' },
          { id: 'clusters', label: 'Clusters' },
          { id: 'messaging', label: 'Messaging' },
          { id: 'metrics', label: 'Metrics' },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeView === tab.id ? 'subtab active' : 'subtab'}
            onClick={() => setActiveView(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeView === 'overview' && (
        <div className="dashboard-layout">
          <div className="dashboard-main">
            <div className="module-card module-card__wide section-intro ade-hero">
              <div className="card-header">
                <div>
                  <span className="eyebrow">Predictive Intelligence</span>
                  <h3>Audience Discovery Engine</h3>
                  <p className="muted">
                    AI is the engine. ADE is the roadmap that turns content into audience
                    decisions with evidence-backed insights.
                  </p>
                </div>
                <div className="pill">PI</div>
              </div>
              <div className="journey-grid">
                <div className="journey-card">
                  <h4>Inputs</h4>
                  <p className="muted">Sitemaps, PDFs, product pages, and positioning notes.</p>
                </div>
                <div className="journey-card">
                  <h4>Intelligence</h4>
                  <p className="muted">
                    Chunking, clustering, evidence verification, and segment validation.
                  </p>
                </div>
                <div className="journey-card">
                  <h4>Outputs</h4>
                  <p className="muted">
                    Audience segments, cited evidence, and messaging recommendations.
                  </p>
                </div>
              </div>
            </div>

            <div className="module-card module-card__wide section-intro">
              <div className="card-header">
                <div>
                  <h3>Run discovery</h3>
                  <p className="muted">
                    Provide a sitemap URL, product pages, or a PDF. The analysis returns
                    audience segments with evidence and messaging recommendations.
                  </p>
                </div>
                <div className="pill">ADE</div>
              </div>
              <div className="filter-row">
                <input
                  className="input"
                  placeholder="Sitemap or seed URL (https://company.com/sitemap.xml)"
                  value={targetUrl}
                  onChange={(event) => setTargetUrl(event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Short description (optional)"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Brand (optional)"
                  value={brand}
                  onChange={(event) => setBrand(event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Locale (optional)"
                  value={locale}
                  onChange={(event) => setLocale(event.target.value)}
                />
                <select
                  className="select"
                  value={languagePreset}
                  onChange={(event) => {
                    const value = event.target.value
                    setLanguagePreset(value)
                    if (value === 'auto') setLocale('')
                    if (value === 'en') setLocale('en')
                    if (value === 'ka') setLocale('ka')
                  }}
                >
                  <option value="auto">Language: Auto</option>
                  <option value="en">Language: English</option>
                  <option value="ka">Language: Georgian</option>
                </select>
                <button
                  className="button"
                  type="button"
                  onClick={handleAnalyze}
                  disabled={loading}
                >
                  {loading ? 'Running...' : 'Run analysis'}
                </button>
              </div>
              <div className="stack">
                <label className="label">Manual product URLs (one per line)</label>
                <textarea
                  className="textarea"
                  placeholder="https://company.com/products/widget-a"
                  value={manualUrls}
                  onChange={(event) => setManualUrls(event.target.value)}
                />
              </div>
              <div
                className="drop-zone"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault()
                  handleSitemapFile(event.dataTransfer.files?.[0] || null)
                }}
              >
                <p className="muted">Drag and drop a sitemap XML file here.</p>
                <input
                  className="input"
                  type="file"
                  accept=".xml"
                  onChange={(event) => handleSitemapFile(event.target.files?.[0] || null)}
                />
                {sitemapNotice ? <p className="muted">{sitemapNotice}</p> : null}
              </div>
              <details className="dashboard-detail">
                <summary>Advanced crawl settings</summary>
                <div className="dashboard-detail__body">
                  <label className="label">Crawl depth (0-2)</label>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    max="2"
                    value={crawlDepth}
                    onChange={(event) => setCrawlDepth(event.target.value)}
                  />
                  <label className="label">Crawl timeout (seconds)</label>
                  <input
                    className="input"
                    type="number"
                    min="3"
                    max="60"
                    value={crawlTimeout}
                    onChange={(event) => setCrawlTimeout(event.target.value)}
                  />
                  <label className="label">Max pages</label>
                  <input
                    className="input"
                    type="number"
                    min="10"
                    max="1000"
                    value={maxPages}
                    onChange={(event) => setMaxPages(event.target.value)}
                  />
                  <label className="label">Allowed domains (comma separated)</label>
                  <input
                    className="input"
                    placeholder="freedomsquare.ge"
                    value={allowedDomains}
                    onChange={(event) => setAllowedDomains(event.target.value)}
                  />
                  <label className="label">Product URL rules (regex, one per line)</label>
                  <textarea
                    className="textarea"
                    placeholder="/product\n/services\n/program"
                    value={productRules}
                    onChange={(event) => setProductRules(event.target.value)}
                  />
                  <label className="label">Cluster count (optional)</label>
                  <input
                    className="input"
                    type="number"
                    min="2"
                    max="12"
                    value={clusterCount}
                    onChange={(event) => setClusterCount(event.target.value)}
                  />
                  <label className="label">Clustering granularity</label>
                  <input
                    className="input"
                    type="range"
                    min="2"
                    max="12"
                    value={clusterCount || 6}
                    onChange={(event) => setClusterCount(event.target.value)}
                  />
                </div>
              </details>
              {error ? <div className="module-alert">{error}</div> : null}
              {runNotice ? (
                <div className="module-alert module-alert--success">{runNotice}</div>
              ) : null}
            </div>

            {stageSnapshot.length ? (
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>{stageTitle}</h3>
                    <p className="muted">{stageSubtitle}</p>
                  </div>
                </div>
                {progress > 0 ? (
                  <div className="questionnaire-progress">
                    <div className="questionnaire-progress__track">
                      <div
                        className="questionnaire-progress__bar"
                        style={{ width: `${Math.min(progress, 100)}%` }}
                      />
                    </div>
                    <span className="questionnaire-progress__label">{progress}%</span>
                  </div>
                ) : null}
                <div className="table">
                  <div className="table-row table-head">
                    <span>Stage</span>
                    <span>Status</span>
                    <span>Count</span>
                    <span>Duration</span>
                  </div>
                  {stageSnapshot.map((stage) => (
                    <div className="table-row" key={stage.id}>
                      <span>{stage.label}</span>
                      <span>{stage.status}</span>
                      <span>{stage.count ?? '—'}</span>
                      <span>{stage.durationSec ? `${stage.durationSec}s` : '—'}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {analysis?.notes?.length ? (
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Notes</h3>
                    <p className="muted">Context for this run.</p>
                  </div>
                </div>
                <ul className="polis-feature-list">
                  {analysis.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {analysis?.errors?.length ? (
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Errors</h3>
                    <p className="muted">Issues encountered during the run.</p>
                  </div>
                </div>
                <ul className="polis-feature-list">
                  {analysis.errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {!analysis && !loading ? (
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>What you will get</h3>
                    <p className="muted">
                      The output includes segments, evidence snippets, and messaging
                      recommendations ready for marketing teams.
                    </p>
                  </div>
                </div>
                <div className="module-grid">
                  <div className="module-card">
                    <h3>Segments</h3>
                    <p className="muted">
                      2 to 5 audience segments with names, rationale, and confidence.
                    </p>
                  </div>
                  <div className="module-card">
                    <h3>Evidence</h3>
                    <p className="muted">
                      Verified quotes tied to source URLs to support each segment.
                    </p>
                  </div>
                  <div className="module-card">
                    <h3>Messaging</h3>
                    <p className="muted">
                      3 to 5 headlines, tone notes, and calls-to-action per segment.
                    </p>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <aside className="dashboard-sidebar">
            <div className="sidebar-card sidebar-card--accent">
              <h4>Predictive Intelligence lens</h4>
              <p className="muted">
                Build future-ready audience profiles by combining evidence, clustering, and
                messaging intent.
              </p>
              <ul className="polis-feature-list">
                <li>Stakeholder priorities and policy narratives.</li>
                <li>Signals that map to beliefs, needs, and objections.</li>
                <li>Messaging angles tailored to each segment.</li>
              </ul>
            </div>

            {analysis?.runId ? (
              <div className="sidebar-card">
                <h4>Run snapshot</h4>
                <div className="report-metrics">
                  {runSnapshot.map((item) => (
                    <div className="report-metric" key={item.label}>
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {analysis?.runId ? (
              <div className="sidebar-card">
                <h4>Run details</h4>
                <div className="stack">
                  <div>
                    <span className="label">Run ID</span>
                    <div className="filter-row">
                      <span className="muted">{analysis.runId}</span>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => copyText(analysis.runId)}
                      >
                        Copy
                      </button>
                    </div>
                  </div>
                  <div>
                    <span className="label">Created at</span>
                    <p className="muted">{analysis.createdAt || '—'}</p>
                  </div>
                  <div>
                    <span className="label">Source</span>
                    <p className="muted">
                      {analysisSource ? (
                        <a href={analysisSource} target="_blank" rel="noreferrer">
                          {analysisSource}
                        </a>
                      ) : (
                        '—'
                      )}
                    </p>
                  </div>
                  <div className="filter-row">
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => setActiveView('segments')}
                    >
                      Review segments
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => setActiveView('metrics')}
                    >
                      View metrics
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => setActiveView('messaging')}
                    >
                      Messaging
                    </button>
                  </div>
                  <div className="filter-row">
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() =>
                        (window.open(
                          `${API_BASE}/audience-discovery/analysis/${analysis.runId}/export/json`,
                          '_blank',
                        ),
                        setExportStatus('Opened JSON export in a new tab.'))
                      }
                    >
                      Export JSON
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() =>
                        (window.open(
                          `${API_BASE}/audience-discovery/analysis/${analysis.runId}/export/csv`,
                          '_blank',
                        ),
                        setExportStatus('Opened CSV export in a new tab.'))
                      }
                    >
                      Export CSV
                    </button>
                  </div>
                  {exportStatus ? <p className="muted">{exportStatus}</p> : null}
                </div>
              </div>
            ) : null}

            {topSegments.length ? (
              <div className="sidebar-card">
                <h4>Top segments</h4>
                <div className="stack">
                  {topSegments.map((segment) => {
                    const evidence = segment.evidence || []
                    const firstQuote = evidence[0]?.quote
                    return (
                      <div className="segment-preview" key={segment.segmentId}>
                        <div className="segment-preview__header">
                          <h5 className="segment-preview__title">{segment.name}</h5>
                          <div className="cluster-tags">
                            <span className="cluster-tag">
                              {Math.round((segment.confidence || 0) * 100)}% confident
                            </span>
                            <span className="cluster-tag">
                              {evidence.length} evidence
                            </span>
                          </div>
                        </div>
                        <p className="muted">
                          {truncateText(segment.rationale, 120) || 'No rationale provided.'}
                        </p>
                        {firstQuote ? (
                          <p className="segment-preview__quote">
                            “{truncateText(firstQuote, 160)}”
                          </p>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </aside>
        </div>
      )}

      {activeView === 'metrics' && metrics.length ? (
        <div className="stack">
          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Run summary</h3>
                <p className="muted">Key metrics for the current run.</p>
              </div>
            </div>
            <div className="filter-row">
              <div>
                <span className="label">Run ID</span>
                <p>{analysis?.runId || '—'}</p>
              </div>
              <div>
                <span className="label">Created at</span>
                <p>{analysis?.createdAt || '—'}</p>
              </div>
            </div>
          </div>
          <div className="report-metrics">
            {metrics.map((metric) => (
              <div className="report-metric" key={metric.label}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
          {metricsChart ? (
            <div className="module-card module-card__wide chart-frame chart-frame--short">
              <Bar data={metricsChart.data} options={metricsChart.options} />
            </div>
          ) : null}
        </div>
      ) : null}

      {activeView === 'metrics' && analysis?.runId ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Exports</h3>
              <p className="muted">Download JSON or CSV for this run.</p>
            </div>
          </div>
          <div className="filter-row">
            <button
              className="button-secondary"
              type="button"
              onClick={() =>
                (window.open(
                  `${API_BASE}/audience-discovery/analysis/${analysis.runId}/export/json`,
                  '_blank',
                ),
                setExportStatus('Opened JSON export in a new tab.'))
              }
            >
              Export JSON
            </button>
            <button
              className="button-secondary"
              type="button"
              onClick={() =>
                (window.open(
                  `${API_BASE}/audience-discovery/analysis/${analysis.runId}/export/csv`,
                  '_blank',
                ),
                setExportStatus('Opened CSV export in a new tab.'))
              }
            >
              Export CSV
            </button>
          </div>
          {exportStatus ? <p className="muted">{exportStatus}</p> : null}
        </div>
      ) : null}
      {activeView === 'pages' && pages.length ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Pages analyzed</h3>
              <p className="muted">Product-like URLs discovered from the input.</p>
            </div>
          </div>
          <div className="filter-row">
            <input
              className="input"
              placeholder="Filter pages by title or URL"
              value={pageFilter}
              onChange={(event) => setPageFilter(event.target.value)}
            />
          </div>
          <div className="table">
            <div className="table-row table-head">
              <span>Title</span>
              <span>URL</span>
              <span>Status</span>
              <span>Chunks</span>
              <span>Words</span>
              <span>Inspect</span>
            </div>
            {filteredPages.map((page) => (
              <div className="table-row" key={page.url}>
                <span>{page.title || 'Untitled'}</span>
                <span>
                  <a href={page.url} target="_blank" rel="noreferrer">
                    {page.url}
                  </a>
                </span>
                <span>{page.crawlStatus || '—'}</span>
                <span>{page.chunkCount ?? '—'}</span>
                <span>{page.wordCount ?? '—'}</span>
                <span>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => loadPageChunks(page.pageId)}
                  >
                    View chunks
                  </button>
                </span>
              </div>
            ))}
          </div>
          {selectedPageId && pageChunks.length ? (
            <div className="card-divider">
              <h4>Chunks for selected page</h4>
            </div>
          ) : null}
          {selectedPageId && pageChunks.length ? (
            <div className="cluster-grid">
              {pageChunks.map((chunk) => (
                <div className="cluster-card" key={chunk.chunkId}>
                  <p className="muted">
                    Offsets: {chunk.startOffset} → {chunk.endOffset}
                  </p>
                  <p>{chunk.text}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {activeView === 'pages' && !pages.length && analysis?.runId ? (
        <div className="module-card module-card__wide">
          <p className="muted">No pages detected yet. Try a sitemap URL.</p>
        </div>
      ) : null}

      {activeView === 'clusters' && clusters.length ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Clusters</h3>
              <p className="muted">Cross-page themes derived from chunk embeddings.</p>
            </div>
          </div>
          <div className="cluster-grid">
            {clusters.map((cluster) => (
              <div className="cluster-card" key={cluster.clusterId}>
                <div className="cluster-card__header">
                  <h4>{cluster.clusterId}</h4>
                  <span className="pill">{cluster.clusterSize} chunks</span>
                </div>
                <p className="muted">
                  Segments: {segmentCountsByCluster[cluster.clusterId] || 0}
                </p>
                {cluster.sampleSnippets?.length ? (
                  <ul className="polis-feature-list">
                    {cluster.sampleSnippets.map((snippet, idx) => (
                      <li key={`${cluster.clusterId}-${idx}`}>{snippet}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No snippets available.</p>
                )}
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => loadClusterChunks(cluster.clusterId)}
                >
                  View cluster chunks
                </button>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => {
                    setActiveView('segments')
                    setSegmentGroupBy('cluster')
                    setSegmentClusterFilter(cluster.clusterId)
                  }}
                >
                  View related segments
                </button>
              </div>
            ))}
          </div>
          {selectedClusterId && clusterChunks.length ? (
            <div className="card-divider">
              <h4>Chunks for {selectedClusterId}</h4>
            </div>
          ) : null}
          {selectedClusterId && clusterChunks.length ? (
            <p className="muted">
              Related pages:{' '}
              {new Set(clusterChunks.map((chunk) => chunk.url)).size}
            </p>
          ) : null}
          {selectedClusterId && clusterChunks.length ? (
            <div className="cluster-grid">
              {clusterChunks.map((chunk) => (
                <div className="cluster-card" key={chunk.chunkId}>
                  <p className="muted">{chunk.url}</p>
                  <p>{chunk.text}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {activeView === 'clusters' && !clusters.length && analysis?.runId ? (
        <div className="module-card module-card__wide">
          <p className="muted">Clusters will appear once embeddings are created.</p>
        </div>
      ) : null}

      {activeView === 'segments' && segments.length ? (
        <>
          <div className="card-divider">
            <h4>Audience segments</h4>
          </div>
          <div className="filter-row">
            <button
              className={segmentGroupBy === 'cluster' ? 'button' : 'button-secondary'}
              type="button"
              onClick={() => {
                setSegmentGroupBy('cluster')
                setSegmentClusterFilter('')
              }}
            >
              Group by cluster
            </button>
            <button
              className={segmentGroupBy === 'page' ? 'button' : 'button-secondary'}
              type="button"
              onClick={() => {
                setSegmentGroupBy('page')
                setSegmentClusterFilter('')
              }}
            >
              Group by page
            </button>
            {segmentGroupBy === 'cluster' ? (
              <select
                className="select"
                value={segmentClusterFilter}
                onChange={(event) => setSegmentClusterFilter(event.target.value)}
              >
                <option value="">All clusters</option>
                {clusters.map((cluster) => (
                  <option key={cluster.clusterId} value={cluster.clusterId}>
                    {cluster.clusterId}
                  </option>
                ))}
              </select>
            ) : null}
            {segmentClusterFilter ? (
              <button
                className="button-secondary"
                type="button"
                onClick={() => setSegmentClusterFilter('')}
              >
                Clear cluster filter
              </button>
            ) : null}
          </div>
          {Object.keys(segmentsByGroup).map((groupId) => (
            <div className="module-card module-card__wide" key={groupId}>
              <div className="card-header">
                <div>
                  <h3>{groupId === 'unclustered' ? 'Unclustered' : groupId}</h3>
                  <p className="muted">
                    {segmentGroupBy === 'cluster'
                      ? 'Grouped by cluster membership.'
                      : 'Grouped by source page.'}
                  </p>
                </div>
              </div>
              <div className="cluster-grid">
                {segmentsByGroup[groupId].map((segment) => (
                  <div className="cluster-card" key={segment.segmentId}>
                <div className="cluster-card__header">
                  <h4>{segment.name}</h4>
                  <div className="cluster-tags">
                    {segment.confidence !== undefined ? (
                      <span className="cluster-tag">
                        {Math.round(segment.confidence * 100)}% confident
                      </span>
                    ) : null}
                    {segment.verified ? (
                      <span className="cluster-tag cluster-tag--agree">Verified</span>
                    ) : (
                      <span className="cluster-tag cluster-tag--disagree">Unverified</span>
                    )}
                  </div>
                </div>
                <p className="muted">{segment.rationale}</p>
                {segment.pageUrl ? (
                  <p className="muted">
                    Source page:{' '}
                    <a href={segment.pageUrl} target="_blank" rel="noreferrer">
                      {segment.pageUrl}
                    </a>
                  </p>
                ) : null}

                <div className="card-divider">
                  <h5>Evidence</h5>
                </div>
                {segment.evidence?.length ? (
                  <ul className="polis-feature-list">
                    {segment.evidence.map((item, evidenceIdx) => (
                      <li key={`${segment.name}-evidence-${evidenceIdx}`}>
                        “{item.quote}” {item.url ? `(${item.url})` : ''}
                        {item.isSample ? ' (sample)' : ''}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No verified evidence yet.</p>
                )}

                <div className="card-divider">
                  <h5>Review</h5>
                </div>
                <div className="filter-row">
                  <button
                    className="button"
                    type="button"
                    onClick={() => handleSegmentAction(segment.segmentId, 'confirm')}
                    disabled={segment.confirmed}
                  >
                    {segment.confirmed ? 'Confirmed' : 'Confirm'}
                  </button>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleSegmentAction(segment.segmentId, 'discard')}
                  >
                    Discard
                  </button>
                </div>

                <div className="card-divider">
                  <h5>Recommendations</h5>
                </div>
                <p className="muted">
                  Confirm the segment to generate messaging recommendations.
                </p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </>
      ) : null}

      {activeView === 'segments' && !segments.length && analysis?.runId ? (
        <div className="module-card module-card__wide">
          <p className="muted">No segments generated yet.</p>
        </div>
      ) : null}

      {activeView === 'messaging' && messaging.length ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Messaging recommendations</h3>
              <p className="muted">Generated for confirmed segments only.</p>
            </div>
          </div>
          {copyNotice ? <p className="muted">{copyNotice}</p> : null}
          <div className="report-grid">
            {messaging.map((item) => (
              <div className="module-card" key={item.segmentId}>
                <h4>{item.name}</h4>
                <p className="muted">{item.tone}</p>
                <div className="card-divider">
                  <h5>Headlines</h5>
                </div>
                <ul className="polis-feature-list">
                  {item.headlines.map((headline) => (
                    <li key={headline}>{headline}</li>
                  ))}
                </ul>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => copyText(item.headlines.join('\n'))}
                >
                  Copy headlines
                </button>
                <div className="card-divider">
                  <h5>CTAs</h5>
                </div>
                <ul className="polis-feature-list">
                  {item.ctas.map((cta) => (
                    <li key={cta}>{cta}</li>
                  ))}
                </ul>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => copyText(item.ctas.join('\n'))}
                >
                  Copy CTAs
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeView === 'messaging' && !messaging.length && analysis?.runId ? (
        <div className="module-card module-card__wide">
          <p className="muted">Confirm segments to unlock messaging.</p>
        </div>
      ) : null}

    </section>
  )
}
