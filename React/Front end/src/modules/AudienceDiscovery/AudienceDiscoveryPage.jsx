import React, { useEffect, useMemo, useState } from 'react'
import { Badge, Group } from '@mantine/core'
import { IconBolt, IconChartDots, IconTarget, IconUsers } from '@tabler/icons-react'
import { Bar } from 'react-chartjs-2'
import { Chart as ChartJS, BarElement, CategoryScale, Legend, LinearScale, Tooltip } from 'chart.js'
import { getApiBaseUrl, requestForm, requestJson } from '../../services/api'
import { CivicStatGrid, Field, FormSection, InfoBox, InfoHint, StatusMessage } from '../../ui'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const DEFAULT_URL = 'https://www.hubspot.com/sitemap.xml'
const DEFAULT_LOCALE = 'en'
const DEFAULT_LANGUAGE_PRESET = 'en'
const VIEWS = ['overview', 'segments', 'evidence', 'messaging']
const EVIDENCE_VIEWS = ['pages', 'clusters']
const SUGGESTED_LINKS = [
  'https://freedomsquare.ge/wp-content/uploads/2025/02/FS_PROGRAM.pdf',
  'https://freedomsquare.ge',
  'https://transparency.ge',
  'https://ombudsman.ge',
  'https://geostat.ge',
  'https://nbg.gov.ge',
  'https://europa.eu',
  'https://ec.europa.eu',
]

export function AudienceDiscoveryPage({
  t,
  activeViewOverride,
  onViewChange,
  showTabs = true,
  showIntro = true,
}) {
  const translate = t || ((key) => key)
  const [targetUrl, setTargetUrl] = useState(DEFAULT_URL)
  const [manualUrls, setManualUrls] = useState('')
  const [description, setDescription] = useState('')
  const [brand, setBrand] = useState('')
  const [locale, setLocale] = useState(DEFAULT_LOCALE)
  const [crawlDepth, setCrawlDepth] = useState(1)
  const [allowedDomains, setAllowedDomains] = useState('')
  const [productRules, setProductRules] = useState('')
  const [crawlTimeout, setCrawlTimeout] = useState(12)
  const [maxPages, setMaxPages] = useState(2)
  const [clusterCount, setClusterCount] = useState('')
  const [languagePreset, setLanguagePreset] = useState(DEFAULT_LANGUAGE_PRESET)
  const [suggestedUrl, setSuggestedUrl] = useState('')
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
  const getViewFromUrl = () => {
    const search = new URLSearchParams(window.location.search)
    const view = search.get('audience_view')
    if (view === 'pages' || view === 'clusters') return 'evidence'
    if (view === 'metrics') return 'overview'
    return view
  }
  const getEvidenceViewFromUrl = () => {
    const search = new URLSearchParams(window.location.search)
    const view = search.get('audience_view')
    const evidenceView = search.get('audience_evidence')
    if (view === 'clusters' || evidenceView === 'clusters') return 'clusters'
    if (view === 'pages' || evidenceView === 'pages') return 'pages'
    return 'pages'
  }
  const [activeView, setActiveView] = useState(() => {
    const fromUrl = getViewFromUrl()
    return VIEWS.includes(fromUrl) ? fromUrl : 'overview'
  })
  const [evidenceView, setEvidenceView] = useState(() => {
    const fromUrl = getEvidenceViewFromUrl()
    return EVIDENCE_VIEWS.includes(fromUrl) ? fromUrl : 'pages'
  })
  const applyActiveView = (nextView) => {
    if (!nextView) return
    if (nextView === 'metrics') {
      setActiveView('overview')
      if (onViewChange) onViewChange('overview')
      return
    }
    if (nextView === 'pages' || nextView === 'clusters') {
      setEvidenceView(nextView)
      setActiveView('evidence')
      if (onViewChange) onViewChange('evidence')
      return
    }
    setActiveView(nextView)
    if (onViewChange) onViewChange(nextView)
  }
  const applyEvidenceView = (nextView) => {
    const targetView = EVIDENCE_VIEWS.includes(nextView) ? nextView : 'pages'
    setEvidenceView(targetView)
    applyActiveView('evidence')
  }
  const [exportStatus, setExportStatus] = useState('')
  const [runNotice, setRunNotice] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [viewLoading, setViewLoading] = useState('')
  const [pdfFile, setPdfFile] = useState(null)
  const [pdfNotice, setPdfNotice] = useState('')
  const [copyNotice, setCopyNotice] = useState('')
  const [sitemapNotice, setSitemapNotice] = useState('')
  const [pageFilter, setPageFilter] = useState('')
  const [segmentGroupBy, setSegmentGroupBy] = useState('cluster')
  const [segmentClusterFilter, setSegmentClusterFilter] = useState('')

  useEffect(() => {
    if (!VIEWS.includes(activeView)) return
    const url = new URL(window.location.href)
    if (activeView === 'evidence') {
      url.searchParams.set('audience_view', 'evidence')
      url.searchParams.set('audience_evidence', evidenceView)
    } else {
      url.searchParams.set('audience_view', activeView)
      url.searchParams.delete('audience_evidence')
    }
    window.history.replaceState({}, '', url)
  }, [activeView, evidenceView])

  useEffect(() => {
    if (!activeViewOverride || activeViewOverride === activeView) return
    if (activeViewOverride === 'metrics') {
      setActiveView('overview')
      return
    }
    if (activeViewOverride === 'pages' || activeViewOverride === 'clusters') {
      setEvidenceView(activeViewOverride)
      setActiveView('evidence')
      return
    }
    if (VIEWS.includes(activeViewOverride)) {
      setActiveView(activeViewOverride)
    }
  }, [activeViewOverride, activeView])

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

  const discoveryPulse = useMemo(
    () => [
      {
        label: 'Coverage',
        value: formatPercent(analysis?.summary?.coverage),
        icon: <IconTarget size={18} />,
        progress: Math.round(Number(analysis?.summary?.coverage || 0) * 100),
      },
      {
        label: 'Segments',
        value: analysis?.summary?.segmentsGenerated ?? segments.length,
        icon: <IconUsers size={18} />,
        badge: 'Draft',
      },
      {
        label: 'Clusters',
        value: analysis?.summary?.clustersCreated ?? clusters.length,
        icon: <IconChartDots size={18} />,
        note: 'Topic families',
      },
      {
        label: 'Pages crawled',
        value: analysis?.summary?.pagesCrawled ?? pages.length,
        icon: <IconBolt size={18} />,
        note: 'Source depth',
      },
    ],
    [analysis?.summary, clusters.length, pages.length, segments.length],
  )

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
    if (pdfFile?.name) return pdfFile.name
    const firstManual = manualUrls
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find(Boolean)
    return firstManual || ''
  }, [analysis?.url, manualUrls, targetUrl, pdfFile])

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
    if (!pdfFile && !trimmedUrl && manualList.length === 0) {
      setError('Enter a sitemap URL, upload a PDF, or add product URLs.')
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
    setPdfNotice('')
    try {
      let result
      if (pdfFile) {
        const formData = new FormData()
        formData.append('file', pdfFile)
        formData.append('description', description.trim())
        formData.append('brand', brand.trim())
        formData.append('locale', locale.trim())
        result = await requestForm('/audience-discovery/analysis/upload', { formData })
      } else {
        result = await requestJson('/audience-discovery/analysis/start', {
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
      }
      setAnalysis(result)
      setRunNotice(`Run created: ${result.runId}`)
      await refreshRunData(result.runId)
    } catch (err) {
      const message = err?.message || 'Audience discovery failed.'
      if (message.includes('Failed to fetch')) {
        setError(
          `Unable to reach the backend at ${getApiBaseUrl()}. Check the API port and backend logs.`,
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
        setPdfFile(null)
        setPdfNotice('')
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

  const refreshRunData = async (runId) => {
    if (!runId) return
    setRefreshing(true)
    setError('')
    try {
      const [pagesPayload, segmentsPayload, clustersPayload, metricsPayload] = await Promise.all([
        requestJson(`/audience-discovery/analysis/${runId}/pages`, { method: 'GET' }),
        requestJson(`/audience-discovery/analysis/${runId}/segments`, { method: 'GET' }),
        requestJson(`/audience-discovery/analysis/${runId}/clusters`, { method: 'GET' }),
        requestJson(`/audience-discovery/analysis/${runId}/metrics`, { method: 'GET' }),
      ])
      setPages(pagesPayload.pages || [])
      setSegments(segmentsPayload.segments || [])
      setClusters(clustersPayload.clusters || [])
      setAnalysis((prev) => ({ ...(prev || {}), summary: metricsPayload.summary }))
    } catch (err) {
      const message = err?.message || 'Unable to refresh analysis results.'
      if (message.includes('Failed to fetch')) {
        setError(`Unable to reach the backend at ${getApiBaseUrl()}. Check the API port and backend logs.`)
      } else if (message.includes('Internal Server Error')) {
        setError('Backend error while running discovery. Check backend logs for details.')
      } else {
        setError(message)
      }
    } finally {
      setRefreshing(false)
    }
  }

  const renderEmptyState = (title, message, viewId) => (
    <div className="module-card module-card__wide">
      <div className="card-header">
        <div>
          <h3>{title}</h3>
          <p className="muted">{viewLoading === viewId ? 'Loading…' : message}</p>
        </div>
      </div>
      <div className="filter-row">
        {!analysis?.runId ? (
          <button
            className="button-secondary"
            type="button"
            onClick={() => applyActiveView('overview')}
          >
            Go to overview
          </button>
        ) : null}
        {analysis?.runId ? (
          <button
            className="button-secondary"
            type="button"
            onClick={() => refreshRunData(analysis.runId)}
            disabled={refreshing || viewLoading === viewId}
          >
            {refreshing || viewLoading === viewId ? 'Refreshing...' : 'Refresh results'}
          </button>
        ) : null}
      </div>
    </div>
  )

  const fetchViewData = async (viewId, runId) => {
    if (!runId) return
    setViewLoading(viewId)
    setError('')
    try {
      if (viewId === 'pages') {
        const payload = await requestJson(`/audience-discovery/analysis/${runId}/pages`, {
          method: 'GET',
        })
        setPages(payload.pages || [])
      }
      if (viewId === 'segments') {
        const payload = await requestJson(`/audience-discovery/analysis/${runId}/segments`, {
          method: 'GET',
        })
        setSegments(payload.segments || [])
      }
      if (viewId === 'clusters') {
        const payload = await requestJson(`/audience-discovery/analysis/${runId}/clusters`, {
          method: 'GET',
        })
        setClusters(payload.clusters || [])
      }
      if (viewId === 'metrics') {
        const payload = await requestJson(`/audience-discovery/analysis/${runId}/metrics`, {
          method: 'GET',
        })
        setAnalysis((prev) => ({ ...(prev || {}), summary: payload.summary }))
      }
      if (viewId === 'messaging') {
        const payload = await requestJson(`/audience-discovery/analysis/${runId}/messaging`, {
          method: 'GET',
        })
        setMessaging(payload.messaging || [])
      }
    } catch (err) {
      const message = err?.message || 'Unable to load analysis results.'
      if (message.includes('Failed to fetch')) {
        setError(`Unable to reach the backend at ${getApiBaseUrl()}. Check the API port and backend logs.`)
      } else if (message.includes('Internal Server Error')) {
        setError('Backend error while running discovery. Check backend logs for details.')
      } else {
        setError(message)
      }
    } finally {
      setViewLoading('')
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

  useEffect(() => {
    if (!analysis?.runId) return
    if (activeView === 'overview' && !analysis?.summary) {
      fetchViewData('metrics', analysis.runId)
    }
    if (activeView === 'overview' && !segments.length) {
      fetchViewData('segments', analysis.runId)
    }
    if (activeView === 'evidence' && evidenceView === 'pages' && !pages.length) {
      fetchViewData('pages', analysis.runId)
    }
    if (activeView === 'evidence' && evidenceView === 'clusters' && !clusters.length) {
      fetchViewData('clusters', analysis.runId)
    }
    if (activeView === 'segments' && !segments.length) {
      fetchViewData('segments', analysis.runId)
    }
    if (activeView === 'messaging' && !messaging.length) {
      fetchViewData('messaging', analysis.runId)
    }
  }, [
    activeView,
    analysis?.runId,
    analysis?.summary,
    evidenceView,
    pages.length,
    segments.length,
    clusters.length,
    messaging.length,
  ])

  return (
    <section className="module">
      {showIntro ? (
        <div className="module-card module-card__wide section-intro">
          <div className="card-header">
            <div>
              <h3>{translate('module.audienceDiscovery')}</h3>
              <p className="muted">{translate('module.audienceDiscovery.desc')}</p>
            </div>
            <div className="pill">Audience</div>
          </div>
        </div>
      ) : null}

      <StatusMessage tone="error" message={error} />

      <CivicStatGrid
        title="Discovery pulse"
        description="Quality, coverage, and scale of the latest audience run."
        items={discoveryPulse}
      />
      <Group gap="xs" mb="md">
        <Badge variant="light" color="civic">
          Evidence-first
        </Badge>
        <Badge variant="light" color="civic">
          Civic-safe messaging
        </Badge>
        <Badge variant="light" color="civic">
          Segment ready
        </Badge>
      </Group>
      {showTabs ? (
        <div className="subtabs">
          {[
            { id: 'overview', label: 'Overview' },
            { id: 'segments', label: 'Segments' },
            { id: 'evidence', label: 'Evidence' },
            { id: 'messaging', label: 'Messaging' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeView === tab.id ? 'subtab active' : 'subtab'}
              onClick={() => applyActiveView(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {activeView === 'overview' && (
        <div className="dashboard-layout">
          <div className="dashboard-main">
            <details className="dashboard-detail">
              <summary>Predictive intelligence overview</summary>
              <div className="dashboard-detail__body">
                <div className="card-header">
                  <div>
                    <span className="eyebrow">Predictive Intelligence</span>
                    <h3>Signal to segment</h3>
                    <p className="muted">
                      Turn content into evidence-backed audience insight.
                      <InfoHint text="AI is the engine. ADE is the roadmap that turns content into audience decisions with evidence-backed insights." />
                    </p>
                  </div>
                  <div className="pill">PI</div>
                </div>
                <div className="journey-grid">
                  <div className="journey-card">
                    <h4>Inputs</h4>
                    <p className="muted">
                      Sitemaps, PDFs, product pages, and positioning notes.
                    </p>
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
            </details>

            <div className="module-card module-card__wide section-intro">
              <div className="card-header">
                <div>
                  <h3>Start a run</h3>
                  <p className="muted">
                    Add a sitemap, product URLs, or a PDF to generate segments.
                    <InfoHint text="The run will extract evidence, cluster content, and generate messaging recommendations for each segment." />
                  </p>
                </div>
                <div className="pill">Run</div>
              </div>
              <FormSection
                title={
                  <span>
                    Sources <InfoHint text="Add at least one source to start the run." />
                  </span>
                }
                description="Start with a sitemap URL or upload files."
              >
                <div className="form-grid">
                  <Field
                    id="ade-url"
                    label="Sitemap or seed URL"
                    helper="Use a sitemap or single URL. Leave blank if uploading a PDF or manual URLs."
                  >
                    <input
                      className="input"
                      placeholder="https://company.com/sitemap.xml"
                      value={targetUrl}
                      onChange={(event) => {
                        setTargetUrl(event.target.value)
                        if (pdfFile) {
                          setPdfFile(null)
                          setPdfNotice('')
                        }
                      }}
                    />
                  </Field>
                  <Field id="ade-description" label="Short description" helper="Optional.">
                    <input
                      className="input"
                      placeholder="Civic engagement platform for local communities"
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                    />
                  </Field>
                  <Field id="ade-brand" label="Brand" helper="Optional.">
                    <input
                      className="input"
                      placeholder="Freedom Square"
                      value={brand}
                      onChange={(event) => setBrand(event.target.value)}
                    />
                  </Field>
                  <Field id="ade-locale" label="Locale" helper="Optional. e.g., en, ka.">
                    <input
                      className="input"
                      placeholder="en"
                      value={locale}
                      onChange={(event) => setLocale(event.target.value)}
                    />
                  </Field>
                  <Field id="ade-language" label="Language preset" helper="Auto or forced.">
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
                      <option value="auto">Auto</option>
                      <option value="en">English</option>
                      <option value="ka">Georgian</option>
                    </select>
                  </Field>
                  <div className="field field--action">
                    <label className="label">Run</label>
                    <button
                      className="button"
                      type="button"
                      onClick={handleAnalyze}
                      disabled={loading}
                    >
                      {loading ? 'Running...' : 'Run analysis'}
                    </button>
                    <div className="field__helper">Starts the run.</div>
                  </div>
                </div>
                <StatusMessage
                  tone="info"
                  message={loading ? 'Analysis running. You can switch tabs to monitor progress.' : ''}
                />
                <StatusMessage tone="success" message={runNotice} />
              </FormSection>
              <details className="dashboard-detail">
                <summary>Suggested sources</summary>
                <div className="dashboard-detail__body">
                  <div className="form-grid">
                    <Field id="ade-suggested" label="Suggested link" helper="Optional demo link.">
                      <select
                        className="select"
                        value={suggestedUrl}
                        onChange={(event) => {
                          const value = event.target.value
                          setSuggestedUrl(value)
                          if (value) {
                            setTargetUrl(value)
                            setManualUrls('')
                            setSitemapNotice('')
                            setPdfFile(null)
                            setPdfNotice('')
                          }
                        }}
                      >
                        <option value="">Try a suggested source…</option>
                        {SUGGESTED_LINKS.map((link) => (
                          <option key={link} value={link}>
                            {link}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <div className="field field--action">
                      <label className="label">Apply</label>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => {
                          if (suggestedUrl) {
                            setTargetUrl(suggestedUrl)
                            setManualUrls('')
                            setSitemapNotice('')
                            setPdfFile(null)
                            setPdfNotice('')
                          }
                        }}
                      >
                        Use link
                      </button>
                      <div className="field__helper">Prefills sitemap URL.</div>
                    </div>
                  </div>
                </div>
              </details>
              <details className="dashboard-detail">
                <summary>Manual URLs</summary>
                <div className="dashboard-detail__body">
                  <Field id="ade-manual-urls" label="Product URLs" helper="One per line.">
                    <textarea
                      className="textarea"
                      placeholder="https://company.com/products/widget-a"
                      value={manualUrls}
                      onChange={(event) => {
                        setManualUrls(event.target.value)
                        if (pdfFile) {
                          setPdfFile(null)
                          setPdfNotice('')
                        }
                      }}
                    />
                  </Field>
                </div>
              </details>
              <details className="dashboard-detail">
                <summary>Upload files</summary>
                <div className="dashboard-detail__body">
                  <div className="form-grid">
                    <div className="drop-zone">
                      <label className="label">Sitemap XML</label>
                      <input
                        className="input"
                        type="file"
                        accept=".xml"
                        onChange={(event) => handleSitemapFile(event.target.files?.[0] || null)}
                      />
                      <StatusMessage tone="info" message={sitemapNotice} />
                    </div>
                    <div className="drop-zone">
                      <label className="label">PDF file</label>
                      <input
                        className="input"
                        type="file"
                        accept=".pdf"
                        onChange={(event) => {
                          const file = event.target.files?.[0] || null
                          setPdfFile(file)
                          if (file) {
                            setTargetUrl('')
                            setManualUrls('')
                            setSitemapNotice('')
                            setSuggestedUrl('')
                            setLanguagePreset('ka')
                            setLocale('ka')
                            setPdfNotice('PDF selected. Locale set to Georgian (ka).')
                          } else {
                            setPdfNotice('')
                          }
                        }}
                      />
                      {pdfFile ? <p className="muted">Selected: {pdfFile.name}</p> : null}
                      <StatusMessage tone="info" message={pdfNotice} />
                      {pdfFile ? (
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => {
                            setPdfFile(null)
                            setPdfNotice('')
                          }}
                        >
                          Clear PDF
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              </details>
              <details className="dashboard-detail">
                <summary>Advanced settings</summary>
                <div className="dashboard-detail__body">
                  <Field
                    id="ade-crawl-depth"
                    label="Crawl depth (0-2)"
                    helper="0 = only provided URLs. 2 = include linked pages."
                  >
                    <input
                      className="input"
                      type="number"
                      min="0"
                      max="2"
                      value={crawlDepth}
                      onChange={(event) => setCrawlDepth(event.target.value)}
                    />
                  </Field>
                  <Field
                    id="ade-crawl-timeout"
                    label="Crawl timeout (seconds)"
                    helper="How long to wait before timing out each page."
                  >
                    <input
                      className="input"
                      type="number"
                      min="3"
                      max="60"
                      value={crawlTimeout}
                      onChange={(event) => setCrawlTimeout(event.target.value)}
                    />
                  </Field>
                  <Field id="ade-max-pages" label="Max pages (limit 2)" helper="Upper limit.">
                    <input
                      className="input"
                      type="number"
                      min="1"
                      max="2"
                      value={maxPages}
                      onChange={(event) => setMaxPages(event.target.value)}
                    />
                  </Field>
                  <Field
                    id="ade-allowed-domains"
                    label="Allowed domains"
                    helper="Comma-separated list of domains to include."
                  >
                    <input
                      className="input"
                      placeholder="freedomsquare.ge"
                      value={allowedDomains}
                      onChange={(event) => setAllowedDomains(event.target.value)}
                    />
                  </Field>
                  <Field
                    id="ade-product-rules"
                    label="Product URL rules"
                    helper="Regex patterns, one per line."
                  >
                    <textarea
                      className="textarea"
                      placeholder="/product\n/services\n/program"
                      value={productRules}
                      onChange={(event) => setProductRules(event.target.value)}
                    />
                  </Field>
                  <Field
                    id="ade-cluster-count"
                    label="Cluster count (optional)"
                    helper="Override default cluster count."
                  >
                    <input
                      className="input"
                      type="number"
                      min="2"
                      max="12"
                      value={clusterCount}
                      onChange={(event) => setClusterCount(event.target.value)}
                    />
                  </Field>
                  <Field
                    id="ade-cluster-range"
                    label="Clustering granularity"
                    helper="Adjust how coarse the clusters should be."
                  >
                    <input
                      className="input"
                      type="range"
                      min="2"
                      max="12"
                      value={clusterCount || 6}
                      onChange={(event) => setClusterCount(event.target.value)}
                    />
                  </Field>
                </div>
              </details>
              <p className="muted">
                If a run returns no segments, try a different source or a PDF with dense content.
              </p>
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
                <div className="table table--stacked">
                  <div className="table-row table-head">
                    <span>Stage</span>
                    <span>Status</span>
                    <span>Count</span>
                    <span>Duration</span>
                  </div>
                  {stageSnapshot.map((stage) => (
                    <div className="table-row" key={stage.id}>
                      <span data-label="Stage">{stage.label}</span>
                      <span data-label="Status">{stage.status}</span>
                      <span data-label="Count">{stage.count ?? '—'}</span>
                      <span data-label="Duration">
                        {stage.durationSec ? `${stage.durationSec}s` : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {analysis?.summary ? (
              <>
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>Run quality</h3>
                      <p className="muted">Coverage, explainability, and evidence health.</p>
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
                </div>
                {metricsChart ? (
                  <div className="module-card module-card__wide chart-frame chart-frame--short">
                    <Bar data={metricsChart.data} options={metricsChart.options} />
                  </div>
                ) : null}
              </>
            ) : null}

            {analysis?.runId && !analysis?.summary ? (
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Run quality pending</h3>
                    <p className="muted">
                      Quality metrics appear once the run completes. Refresh to check again.
                    </p>
                  </div>
                </div>
                <div className="filter-row">
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => refreshRunData(analysis.runId)}
                    disabled={refreshing}
                  >
                    {refreshing ? 'Refreshing...' : 'Refresh results'}
                  </button>
                </div>
              </div>
            ) : null}

            {analysis?.runId && !segments.length ? (
              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>No insights yet</h3>
                    <p className="muted">
                      This run did not produce segments. Try a different source or a PDF with
                      dense content.
                    </p>
                  </div>
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
              <details className="dashboard-detail">
                <summary>What you will get</summary>
                <div className="dashboard-detail__body">
                  <InfoBox
                    title="Outputs"
                    summary="Segments, evidence, and messaging suggestions."
                    hint="Outputs include 2–5 segments with rationale, verified quotes tied to URLs, and 3–5 headlines + CTAs per segment."
                    actions={
                      <>
                        <button className="button-secondary" type="button">
                          View sample outputs
                        </button>
                        <button className="button-secondary" type="button">
                          See demo run
                        </button>
                      </>
                    }
                  />
                </div>
              </details>
            ) : null}
          </div>

          <aside className="dashboard-sidebar">
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
                      {analysisSource
                        ? analysisSource.startsWith('http')
                          ? (
                              <a href={analysisSource} target="_blank" rel="noreferrer">
                                {analysisSource}
                              </a>
                            )
                          : analysisSource
                        : '—'}
                    </p>
                  </div>
                  <div className="filter-row">
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => applyActiveView('segments')}
                    >
                      Review segments
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => applyEvidenceView('pages')}
                    >
                      Browse evidence
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => applyActiveView('messaging')}
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
                          `${getApiBaseUrl()}/audience-discovery/analysis/${analysis.runId}/export/json`,
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
                          `${getApiBaseUrl()}/audience-discovery/analysis/${analysis.runId}/export/csv`,
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

      {activeView === 'evidence' ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Evidence library</h3>
              <p className="muted">Switch between source pages and clustered themes.</p>
            </div>
          </div>
          <div className="filter-row">
            <button
              className={evidenceView === 'pages' ? 'button' : 'button-secondary'}
              type="button"
              onClick={() => setEvidenceView('pages')}
            >
              Pages
            </button>
            <button
              className={evidenceView === 'clusters' ? 'button' : 'button-secondary'}
              type="button"
              onClick={() => setEvidenceView('clusters')}
            >
              Themes
            </button>
            {analysis?.runId ? (
              <button
                className="button-secondary"
                type="button"
                onClick={() => refreshRunData(analysis.runId)}
                disabled={refreshing}
              >
                {refreshing ? 'Refreshing...' : 'Refresh results'}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {activeView === 'evidence' && evidenceView === 'pages' && pages.length ? (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Pages analyzed</h3>
              <p className="muted">Product-like URLs discovered from the input.</p>
            </div>
          </div>
          <div className="filter-row">
            <Field
              id="ade-page-filter"
              label="Filter pages"
              helper="Search by title or URL."
            >
              <input
                className="input"
                placeholder="e.g., donation or /about"
                value={pageFilter}
                onChange={(event) => setPageFilter(event.target.value)}
              />
            </Field>
          </div>
          <div className="table table--stacked">
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
                <span data-label="Title">{page.title || 'Untitled'}</span>
                <span data-label="URL">
                  <a href={page.url} target="_blank" rel="noreferrer">
                    {page.url}
                  </a>
                </span>
                <span data-label="Status">{page.crawlStatus || '—'}</span>
                <span data-label="Chunks">{page.chunkCount ?? '—'}</span>
                <span data-label="Words">{page.wordCount ?? '—'}</span>
                <span data-label="Inspect">
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

      {activeView === 'evidence' && evidenceView === 'pages' && !pages.length
        ? renderEmptyState(
            analysis?.runId ? 'No pages detected' : 'No analysis yet',
            analysis?.runId
              ? 'No pages detected yet. Try a sitemap URL or adjust crawl settings.'
              : 'Run analysis in Overview to see discovered pages.',
            'pages',
          )
        : null}

      {activeView === 'evidence' && evidenceView === 'clusters' && clusters.length ? (
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
                <h4>{cluster.label || cluster.clusterId}</h4>
                  <span className="pill">{cluster.clusterSize} chunks</span>
                </div>
              {cluster.label ? <p className="muted">Cluster ID: {cluster.clusterId}</p> : null}
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
                    applyActiveView('segments')
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

      {activeView === 'evidence' && evidenceView === 'clusters' && !clusters.length
        ? renderEmptyState(
            analysis?.runId ? 'No clusters yet' : 'No analysis yet',
            analysis?.runId
              ? 'Clusters will appear once embeddings are created.'
              : 'Run analysis in Overview to see clustering results.',
            'clusters',
          )
        : null}

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

      {activeView === 'segments' && !segments.length
        ? renderEmptyState(
            analysis?.runId ? 'No segments yet' : 'No analysis yet',
            analysis?.runId
              ? 'No segments generated yet. Try a different source or a content-rich PDF.'
              : 'Run analysis in Overview to see audience segments.',
            'segments',
          )
        : null}

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

      {activeView === 'messaging' && !messaging.length
        ? renderEmptyState(
            analysis?.runId ? 'Messaging not ready' : 'No analysis yet',
            analysis?.runId
              ? 'Confirm segments to unlock messaging recommendations.'
              : 'Run analysis in Overview to generate messaging ideas.',
            'messaging',
          )
        : null}

    </section>
  )
}
