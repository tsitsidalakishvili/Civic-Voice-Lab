import { useEffect, useMemo, useState } from 'react'
import { Bar, Doughnut, Line } from 'react-chartjs-2'
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { IconChartDots, IconMessage2, IconUsers } from '@tabler/icons-react'
import { API_BASE, getJson, requestJson } from '../../services/api'
import { CivicStatGrid } from '../../ui'

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
)

const normalizeColumn = (value) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_]/g, '')

const guessColumn = (columns, candidates) => {
  const normalized = columns.reduce((acc, col) => {
    acc[normalizeColumn(col)] = col
    return acc
  }, {})
  for (const candidate of candidates) {
    const key = normalizeColumn(candidate)
    if (normalized[key]) return normalized[key]
  }
  return ''
}

const truncateText = (value, limit = 64) => {
  const text = String(value || '').trim()
  if (text.length <= limit) return text
  return `${text.slice(0, Math.max(0, limit - 3))}...`
}

const buildStatementPreview = (comments = []) => {
  if (!comments.length) return 'No approved statements yet.'
  const lines = comments.slice(0, 3).map((comment, index) => {
    const agree = comment.agree_count ?? 0
    const disagree = comment.disagree_count ?? 0
    const pass = comment.pass_count ?? 0
    return `${index + 1}. ${truncateText(comment.text, 84)} (${agree}/${disagree}/${pass})`
  })
  const extra = comments.length > 3 ? `\n+${comments.length - 3} more` : ''
  return `Approved statements:\n${lines.join('\n')}${extra}`
}

const sanitizeStatement = (value) => {
  const text = String(value || '').trim()
  if (!text) return ''
  return text
    .replace(/^[-*•]\s+/, '')
    .replace(/^#+\s+/, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

const STATEMENT_SLOT_COUNT = 5
const buildStatementSlots = () => Array.from({ length: STATEMENT_SLOT_COUNT }, () => '')
const buildExistingStatementSlots = () =>
  Array.from({ length: STATEMENT_SLOT_COUNT }, () => ({ id: '', text: '' }))

const formatPercent = (value) => `${Math.round((Number(value) || 0) * 100)}%`

const buildClusterTooltip = (card) => {
  if (!card) return []
  const lines = [`${formatPercent(card.share)} of participants (${card.size})`]
  if (card.agreeTopics.length) {
    lines.push(`Agree: ${card.agreeTopics.join(', ')}`)
  }
  if (card.disagreeTopics.length) {
    lines.push(`Disagree: ${card.disagreeTopics.join(', ')}`)
  }
  return lines
}


const buildStatementTooltipRows = (item) => {
  const agree = Number(item?.agree_count || 0)
  const disagree = Number(item?.disagree_count || 0)
  const pass = Number(item?.pass_count || 0)
  const total = agree + disagree + pass
  return [
    `Votes: ${total}`,
    `Positive (agree): ${agree}`,
    `Negative (disagree): ${disagree}`,
    `Neutral (pass): ${pass}`,
  ]
}

const parseCsvText = (text) => {
  const rows = []
  let row = []
  let field = ''
  let inQuotes = false

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i += 1
        } else {
          inQuotes = false
        }
      } else {
        field += char
      }
      continue
    }

    if (char === '"') {
      inQuotes = true
      continue
    }

    if (char === ',') {
      row.push(field)
      field = ''
      continue
    }

    if (char === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
      continue
    }

    if (char === '\r') continue

    field += char
  }

  if (field.length || row.length) {
    row.push(field)
    rows.push(row)
  }

  if (!rows.length) return { fields: [], data: [] }

  const fields = rows[0].map((col, idx) => {
    const cleaned = String(col || '')
    if (idx === 0) return cleaned.replace(/^\uFEFF/, '').trim()
    return cleaned.trim()
  })

  const data = rows
    .slice(1)
    .map((values) => {
      const entry = {}
      fields.forEach((fieldName, idx) => {
        entry[fieldName] = values[idx] ?? ''
      })
      return entry
    })
    .filter((entry) =>
      fields.some((fieldName) => String(entry[fieldName] ?? '').trim()),
    )

  return { fields, data }
}

const clusterColor = (clusterId, fallbackIndex = 1) => {
  const numeric = Number(String(clusterId || '').replace(/\D/g, '')) || fallbackIndex
  const hue = (numeric * 57) % 360
  return `hsl(${hue} 70% 45%)`
}

const intersectSets = (setA, setB) => {
  const result = new Set()
  setA.forEach((item) => {
    if (setB.has(item)) {
      result.add(item)
    }
  })
  return result
}

const DELIBERATION_TAB_STORAGE_KEY = 'fs.deliberation.activeTab'
const DELIBERATION_DEFAULT_TAB = 'overview'
const DELIBERATION_PRIMARY_TABS = new Set([
  'overview',
  'setup',
  'distribute',
  'insights',
  'moderation',
])

const normalizeDeliberationTab = (tabId) => {
  if (!tabId) return DELIBERATION_DEFAULT_TAB
  return DELIBERATION_PRIMARY_TABS.has(tabId) ? tabId : DELIBERATION_DEFAULT_TAB
}

function ActiveConversationRequired({ message, onOpenOverview }) {
  return (
    <div className="module-card module-card__wide">
      <h3>Select an active conversation</h3>
      <p className="muted">{message}</p>
      <button className="button-secondary" type="button" onClick={onOpenOverview}>
        Go to Overview
      </button>
    </div>
  )
}

export function DeliberationPage({
  t,
  language,
  activeTabOverride,
  onTabChange,
  showTabs = true,
}) {
  const translate = t || ((key, vars) => key)
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window === 'undefined') return DELIBERATION_DEFAULT_TAB
    return normalizeDeliberationTab(
      window.localStorage.getItem(DELIBERATION_TAB_STORAGE_KEY),
    )
  })
  const [setupMode, setSetupMode] = useState('new')
  const [publicReportLinks, setPublicReportLinks] = useState({})
  const applyActiveTab = (nextTab) => {
    const normalized = normalizeDeliberationTab(nextTab)
    setActiveTab(normalized)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(DELIBERATION_TAB_STORAGE_KEY, normalized)
    }
    if (onTabChange) onTabChange(normalized)
  }
  const [conversations, setConversations] = useState([])
  const [convoError, setConvoError] = useState('')
  const [activeId, setActiveId] = useState('')
  const [activeConvo, setActiveConvo] = useState(null)
  const [approvedComments, setApprovedComments] = useState([])
  const [pendingComments, setPendingComments] = useState([])
  const [commentText, setCommentText] = useState('')
  const [createForm, setCreateForm] = useState({
    topic: '',
    description: '',
    initialStatements: buildStatementSlots(),
    allowCommentSubmission: true,
    allowViz: true,
    moderationProfile: 'lazy',
    moderationRequired: false,
    allowVoting: true,
    minVotesForInclusion: 3,
    profanityFilterEnabled: false,
    rateLimitPerMinute: 0,
    identityMode: 'anonymous',
    inviteOnly: false,
    isOpen: true,
  })
  const [updateForm, setUpdateForm] = useState(null)
  const [existingStatementSlots, setExistingStatementSlots] = useState(buildExistingStatementSlots())
  const [savingExistingStatements, setSavingExistingStatements] = useState(false)
  const [seedEditId, setSeedEditId] = useState('')
  const [seedEditText, setSeedEditText] = useState('')
  const [seedStatus, setSeedStatus] = useState('')
  const [moderationNotes, setModerationNotes] = useState({})
  const [simulateForm, setSimulateForm] = useState({
    participants: 120,
    votesPerParticipant: 20,
    seed: 42,
  })
  const [report, setReport] = useState(null)
  const [reportError, setReportError] = useState('')
  const [statementMode, setStatementMode] = useState('consensus')
  const [clusterStatementIndex, setClusterStatementIndex] = useState({})
  const [moderationLog, setModerationLog] = useState([])
  const [moderationLogError, setModerationLogError] = useState('')
  const [inviteForm, setInviteForm] = useState({
    name: 'Wave 1',
    count: 50,
    parentCode: '',
  })
  const [inviteWaves, setInviteWaves] = useState([])
  const [inviteError, setInviteError] = useState('')
  const [ingestText, setIngestText] = useState('')
  const [ingestItems, setIngestItems] = useState([])
  const [ingestSelection, setIngestSelection] = useState({})
  const [ingestStatus, setIngestStatus] = useState('')
  const [ingestStrategy, setIngestStrategy] = useState('auto')
  const [themes, setThemes] = useState([])
  const [themeSummary, setThemeSummary] = useState(null)
  const [themeForm, setThemeForm] = useState({ name: '', description: '' })
  const [themeAssign, setThemeAssign] = useState({ commentId: '', themeIds: [] })
  const [themeError, setThemeError] = useState('')
  const [reportBuilder, setReportBuilder] = useState({
    name: '',
    themeIds: [],
    includeUnassigned: true,
  })
  const [reportLinks, setReportLinks] = useState([])
  const [exportJob, setExportJob] = useState(null)
  const [budgetTotal, setBudgetTotal] = useState(5000)
  const [budgetInput, setBudgetInput] = useState(
    'Community training,1200,5\nTown hall series,2000,4\nMobile outreach,800,3',
  )
  const [criteriaInput, setCriteriaInput] = useState(
    'Impact,0.5\nFeasibility,0.3\nEquity,0.2',
  )
  const [optionsInput, setOptionsInput] = useState(
    'Option A,4,3,5\nOption B,3,5,2\nOption C,5,2,4',
  )
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState('')
  const [loadingStats, setLoadingStats] = useState(false)
  const [exportStatus, setExportStatus] = useState('')
  const [exporting, setExporting] = useState(false)
  const [tableExportingConversationId, setTableExportingConversationId] = useState('')
  const [csvColumns, setCsvColumns] = useState([])
  const [csvRows, setCsvRows] = useState([])
  const [csvMap, setCsvMap] = useState({})
  const [csvStatus, setCsvStatus] = useState('')
  const [seedCsvColumn, setSeedCsvColumn] = useState('')
  const [seedCsvLimit, setSeedCsvLimit] = useState(200)
  const [runAnalysisAfterImport, setRunAnalysisAfterImport] = useState(false)
  const [slackMessage, setSlackMessage] = useState('')
  const [slackStatus, setSlackStatus] = useState('')
  const [slackError, setSlackError] = useState('')
  const [slackChannelMode, setSlackChannelMode] = useState('default')
  const [slackChannelValue, setSlackChannelValue] = useState('')
  const [sendingSlack, setSendingSlack] = useState(false)
  const [shareAudience, setShareAudience] = useState('verified')
  const [whatsappGroups, setWhatsappGroups] = useState([])
  const [whatsappGroupId, setWhatsappGroupId] = useState('')
  const [whatsappMessage, setWhatsappMessage] = useState('')
  const [whatsappError, setWhatsappError] = useState('')
  const [whatsappStatus, setWhatsappStatus] = useState('')
  const [sendingWhatsapp, setSendingWhatsapp] = useState(false)
  const [polisSiteId, setPolisSiteId] = useState('polis_site_id_dZO8TFLSfUGNe651NN')
  const [polisPageId, setPolisPageId] = useState('PAGE_ID')
  const [polisConversationId, setPolisConversationId] = useState('')
  const [copyStatus, setCopyStatus] = useState(null)
  const [discussionCommentsByStatement, setDiscussionCommentsByStatement] = useState({})
  const [discussionDraftByStatement, setDiscussionDraftByStatement] = useState({})
  const [discussionErrorByStatement, setDiscussionErrorByStatement] = useState({})
  const [discussionLoadingByStatement, setDiscussionLoadingByStatement] = useState({})
  const [discussionSavingByStatement, setDiscussionSavingByStatement] = useState({})
  const [discussionReactionBusyByStatement, setDiscussionReactionBusyByStatement] = useState({})

  useEffect(() => {
    if (!activeTabOverride) return
    const normalized = normalizeDeliberationTab(activeTabOverride)
    if (normalized !== activeTab) {
      applyActiveTab(normalized)
    }
  }, [activeTabOverride, activeTab])

  useEffect(() => {
    if (!copyStatus) return
    const timer = setTimeout(() => setCopyStatus(null), 2400)
    return () => clearTimeout(timer)
  }, [copyStatus])

  const vennData = useMemo(() => {
    const summaries = report?.cluster_summaries || []
    if (!summaries.length) return null
    const selected = [...summaries]
      .sort((a, b) => Number(b?.size || 0) - Number(a?.size || 0))
      .slice(0, 3)
    if (selected.length < 2) {
      return { selected, sets: [], overlaps: {}, hasOverlap: false }
    }
    const sets = selected.map(
      (item) =>
        new Set(
          (item.top_agree || [])
            .map((value) => String(value || '').trim())
            .filter(Boolean),
        ),
    )
    const hasAny = sets.some((set) => set.size > 0)
    if (!hasAny) {
      return { selected, sets, overlaps: {}, hasOverlap: false }
    }
    const overlaps = {}
    overlaps.ab = intersectSets(sets[0], sets[1])
    if (sets[2]) {
      overlaps.ac = intersectSets(sets[0], sets[2])
      overlaps.bc = intersectSets(sets[1], sets[2])
      overlaps.abc = intersectSets(overlaps.ab, sets[2])
    }
    const hasOverlap =
      (overlaps.ab && overlaps.ab.size) ||
      (overlaps.ac && overlaps.ac.size) ||
      (overlaps.bc && overlaps.bc.size) ||
      (overlaps.abc && overlaps.abc.size)
    return { selected, sets, overlaps, hasOverlap: Boolean(hasOverlap) }
  }, [report])

  const reportCharts = useMemo(() => {
    if (!report?.metrics) return null
    const consensus = report.metrics.consensus || []
    const polarizing = report.metrics.polarizing || []
    const allRows = [...consensus, ...polarizing]
    const voteTotals = allRows.reduce(
      (acc, row) => {
        acc.agree += Number(row?.agree_count || 0)
        acc.disagree += Number(row?.disagree_count || 0)
        acc.pass += Number(row?.pass_count || 0)
        return acc
      },
      { agree: 0, disagree: 0, pass: 0 },
    )
    const consensusTop = [...consensus]
      .map((row) => ({ ...row, text: sanitizeStatement(row.text) }))
      .sort((a, b) => Number(b?.consensus_score || 0) - Number(a?.consensus_score || 0))
      .slice(0, 6)
    const polarizingTop = [...polarizing]
      .map((row) => ({ ...row, text: sanitizeStatement(row.text) }))
      .sort((a, b) => Number(b?.polarity_score || 0) - Number(a?.polarity_score || 0))
      .slice(0, 6)
    const majorityTop = [...allRows]
      .map((row) => ({ ...row, text: sanitizeStatement(row.text) }))
      .sort((a, b) => {
        const ratioDiff = Number(b?.agreement_ratio || 0) - Number(a?.agreement_ratio || 0)
        if (ratioDiff !== 0) return ratioDiff
        return Number(b?.participation || 0) - Number(a?.participation || 0)
      })
      .slice(0, 6)
    const importantTop = [...allRows]
      .map((row) => ({ ...row, text: sanitizeStatement(row.text) }))
      .sort((a, b) => Number(b?.important_count || 0) - Number(a?.important_count || 0))
      .slice(0, 6)
    const clusterSummaries = report.cluster_summaries || []
    return {
      voteTotals,
      consensusTop,
      polarizingTop,
      majorityTop,
      importantTop,
      clusterLabels: clusterSummaries.map((row) => row.cluster_id),
      clusterSizes: clusterSummaries.map((row) => Number(row?.size || 0)),
    }
  }, [report])

  const discussionStatementOptions = useMemo(() => {
    const rows = [...(reportCharts?.consensusTop || []), ...(reportCharts?.polarizingTop || [])]
    const unique = new Map()
    rows.forEach((row) => {
      if (!row?.id || unique.has(row.id)) return
      unique.set(row.id, row)
    })
    return Array.from(unique.values())
  }, [reportCharts])

  const getDiscussionStateForStatement = (statementId) => ({
    comments: discussionCommentsByStatement[statementId] || [],
    draft: discussionDraftByStatement[statementId] || '',
    error: discussionErrorByStatement[statementId] || '',
    loading: Boolean(discussionLoadingByStatement[statementId]),
    saving: Boolean(discussionSavingByStatement[statementId]),
    reactionBusyId: discussionReactionBusyByStatement[statementId] || '',
  })

  const topicMap = useMemo(() => {
    const points = report?.points || []
    if (!points.length) return null
    const summaries = report?.cluster_summaries || []
    const summaryMap = new Map(
      summaries.map((row) => [
        row.cluster_id,
        {
          size: Number(row?.size || 0),
          labelTopic: sanitizeStatement(
            row?.top_agree?.[0] || row?.top_disagree?.[0] || row?.cluster_id || 'Cluster',
          ),
        },
      ]),
    )
    const minX = Math.min(...points.map((point) => Number(point?.x || 0)))
    const maxX = Math.max(...points.map((point) => Number(point?.x || 0)))
    const minY = Math.min(...points.map((point) => Number(point?.y || 0)))
    const maxY = Math.max(...points.map((point) => Number(point?.y || 0)))
    const spanX = maxX - minX || 1
    const spanY = maxY - minY || 1
    const scaleX = (value) => 0.08 + ((value - minX) / spanX) * 0.84
    const scaleY = (value) => 0.08 + ((value - minY) / spanY) * 0.84

    const clusterAgg = new Map()
    points.forEach((point) => {
      const id = point.cluster_id || 'cluster-0'
      if (!clusterAgg.has(id)) {
        clusterAgg.set(id, { sumX: 0, sumY: 0, count: 0 })
      }
      const entry = clusterAgg.get(id)
      entry.sumX += Number(point.x || 0)
      entry.sumY += Number(point.y || 0)
      entry.count += 1
    })

    const totalFromSummaries = summaries.reduce(
      (acc, row) => acc + Number(row?.size || 0),
      0,
    )
    const totalParticipants =
      Number(report.metrics?.total_participants || 0) || totalFromSummaries || points.length || 1

    const clusters = Array.from(clusterAgg.entries()).map(([clusterId, agg], idx) => {
      const summary = summaryMap.get(clusterId)
      const size = summary?.size || agg.count
      const share = size / totalParticipants
      const label = `${share.toFixed(2)}: ${truncateText(summary?.labelTopic || clusterId, 32)}`
      return {
        id: clusterId,
        size,
        share,
        centerX: scaleX(agg.sumX / agg.count),
        centerY: scaleY(agg.sumY / agg.count),
        label,
        index: idx,
      }
    })

    const colorById = clusters.reduce((acc, cluster, idx) => {
      acc[cluster.id] = idx + 1
      return acc
    }, {})

    const scaledPoints = points.map((point) => ({
      x: scaleX(Number(point?.x || 0)),
      y: scaleY(Number(point?.y || 0)),
      clusterId: point.cluster_id || 'cluster-0',
    }))

    return { clusters, points: scaledPoints, colorById }
  }, [report])

  const statementLandscape = useMemo(() => {
    if (!report?.metrics) return null
    const rows = [...(report.metrics.consensus || []), ...(report.metrics.polarizing || [])]
    if (!rows.length) return null
    const points = rows.map((row) => ({
      id: row.id,
      text: sanitizeStatement(row.text),
      consensus: Number(row?.consensus_score || 0),
      polarity: Number(row?.polarity_score || 0),
      participation: Number(row?.participation || 0),
    }))
    const labelIds = new Set()
    const addLabels = (items) => items.forEach((item) => labelIds.add(item.id))
    addLabels([...points].sort((a, b) => b.consensus - a.consensus).slice(0, 3))
    addLabels([...points].sort((a, b) => b.polarity - a.polarity).slice(0, 3))
    addLabels([...points].sort((a, b) => b.participation - a.participation).slice(0, 3))
    const labels = points.filter((point) => labelIds.has(point.id))
    return { points, labels }
  }, [report])

  const clusterCards = useMemo(() => {
    if (!report?.cluster_summaries?.length) return []
    const fallbackTotal = report.cluster_summaries.reduce(
      (sum, row) => sum + Number(row?.size || 0),
      0,
    )
    const totalParticipants = Number(report.metrics?.total_participants || 0) || fallbackTotal || 1
    return [...report.cluster_summaries]
      .map((row) => {
        const size = Number(row?.size || 0)
        const share = size / totalParticipants
        const sizeLabel = share >= 0.35 ? 'Large' : share >= 0.2 ? 'Medium' : 'Small'
        const agreeTopics = (row.top_agree || [])
          .map((item) => sanitizeStatement(item))
          .filter(Boolean)
          .slice(0, 3)
        const disagreeTopics = (row.top_disagree || [])
          .map((item) => sanitizeStatement(item))
          .filter(Boolean)
          .slice(0, 3)
        const statements = [
          ...agreeTopics.map((topic) => ({ text: topic, sentiment: 'agree' })),
          ...disagreeTopics.map((topic) => ({ text: topic, sentiment: 'disagree' })),
        ]
        let summary = `${sizeLabel} cluster with ${formatPercent(share)} of participants.`
        if (agreeTopics.length) {
          summary += ` Strong agreement on ${agreeTopics.join(', ')}.`
        }
        if (disagreeTopics.length) {
          summary += ` Pushback on ${disagreeTopics.join(', ')}.`
        }
        return {
          id: row.cluster_id,
          size,
          share,
          agreeTopics,
          disagreeTopics,
          statements,
          summary,
        }
      })
      .sort((a, b) => b.size - a.size)
  }, [report])

  const clusterCardById = useMemo(
    () =>
      clusterCards.reduce((acc, card) => {
        acc[String(card.id)] = card
        return acc
      }, {}),
    [clusterCards],
  )

  const verticalBarOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          callbacks: {
            afterBody: (items) => {
              const label = items?.[0]?.label
              const card = label ? clusterCardById[label] : null
              return buildClusterTooltip(card)
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b' },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#64748b' },
          grid: { color: 'rgba(148, 163, 184, 0.2)' },
        },
      },
    }),
    [clusterCardById],
  )

  const seedComments = useMemo(
    () => approvedComments.filter((comment) => comment.is_seed),
    [approvedComments],
  )

  useEffect(() => {
    const nextSlots = buildExistingStatementSlots()
    seedComments.slice(0, STATEMENT_SLOT_COUNT).forEach((comment, index) => {
      nextSlots[index] = {
        id: comment.id || '',
        text: String(comment.text || ''),
      }
    })
    setExistingStatementSlots(nextSlots)
  }, [activeId, seedComments])

  const reportSummary = useMemo(() => {
    if (!report?.metrics) return null
    return {
      participants: Number(report.metrics.total_participants || 0),
      statements: Number(report.metrics.total_comments || 0),
      votes: Number(report.metrics.total_votes || 0),
      topConsensus: reportCharts?.consensusTop?.[0]?.text || '',
      topPolarizing: reportCharts?.polarizingTop?.[0]?.text || '',
      largestCluster: clusterCards[0]?.id || '',
      agreementTopics: report.potential_agreements?.length || 0,
    }
  }, [clusterCards, report, reportCharts])

  const statsSeries = useMemo(() => {
    if (!stats) return null
    const buildSeries = (items = []) => {
      const labels = items.map((item) => item.date)
      const data = items.map((item) => Number(item.count || 0))
      return { labels, data }
    }
    return {
      views: buildSeries(stats.views_over_time),
      comments: buildSeries(stats.comments_over_time),
      votes: buildSeries(stats.votes_over_time),
    }
  }, [stats])

  const budgetPlan = useMemo(() => {
    const rows = budgetInput
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [name, cost, impact] = line.split(',').map((part) => part.trim())
        return {
          name,
          cost: Number(cost || 0),
          impact: Number(impact || 0),
        }
      })
      .filter((row) => row.name)
    const ranked = [...rows].sort((a, b) => {
      const scoreA = a.cost ? a.impact / a.cost : 0
      const scoreB = b.cost ? b.impact / b.cost : 0
      return scoreB - scoreA
    })
    let remaining = Number(budgetTotal) || 0
    const selected = []
    ranked.forEach((row) => {
      if (row.cost <= remaining) {
        selected.push(row)
        remaining -= row.cost
      }
    })
    return { ranked, selected, remaining }
  }, [budgetInput, budgetTotal])

  const decisionScores = useMemo(() => {
    const criteria = criteriaInput
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [name, weight] = line.split(',').map((part) => part.trim())
        return { name, weight: Number(weight || 0) }
      })
    const options = optionsInput
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [name, ...scores] = line.split(',').map((part) => part.trim())
        return {
          name,
          scores: scores.map((score) => Number(score || 0)),
        }
      })
    const totals = options.map((option) => {
      const weighted = criteria.reduce((sum, criterion, index) => {
        const score = option.scores[index] ?? 0
        return sum + score * (criterion.weight || 0)
      }, 0)
      return { ...option, weighted }
    })
    return { criteria, options: totals }
  }, [criteriaInput, optionsInput])

  const horizontalBarOptions = useMemo(
    () => ({
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: true },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { color: '#64748b' },
          grid: { color: 'rgba(148, 163, 184, 0.2)' },
        },
        y: {
          ticks: { color: '#0f172a' },
          grid: { display: false },
        },
      },
    }),
    [],
  )

  const doughnutOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12 } },
        tooltip: { enabled: true },
      },
    }),
    [],
  )

  const lineOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: true },
      },
      scales: {
        x: {
          ticks: { color: '#64748b' },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#64748b' },
          grid: { color: 'rgba(148, 163, 184, 0.2)' },
        },
      },
    }),
    [],
  )

  const buildStatementChartOptions = (items, scoreLabel) => ({
    ...horizontalBarOptions,
    plugins: {
      ...horizontalBarOptions.plugins,
      tooltip: {
        callbacks: {
          title: (contexts) => {
            const idx = contexts?.[0]?.dataIndex ?? 0
            const item = items?.[idx]
            return item?.text ? truncateText(item.text, 90) : ''
          },
          label: (context) => {
            const idx = context?.dataIndex ?? 0
            const item = items?.[idx]
            const scoreValue =
              typeof context?.parsed?.x === 'number'
                ? context.parsed.x
                : typeof context?.parsed?.y === 'number'
                  ? context.parsed.y
                  : 0
            return [
              `${scoreLabel}: ${Number(scoreValue).toFixed(2)}`,
              ...buildStatementTooltipRows(item),
            ]
          },
        },
      },
    },
  })

  const loadConversations = () => {
    setConvoError('')
    getJson('/conversations')
      .then((payload) => setConversations(Array.isArray(payload) ? payload : []))
      .catch((err) =>
        setConvoError(err.message || 'Unable to load conversations.'),
      )
  }

  useEffect(() => {
    loadConversations()
  }, [])

  useEffect(() => {
    if (activeId || conversations.length === 0) return
    const open = conversations.find((convo) => convo.is_open)
    const fallback = open || conversations[0]
    if (fallback?.id) setActiveId(fallback.id)
  }, [activeId, conversations])

  useEffect(() => {
    if (activeTab !== 'setup' && activeTab !== 'distribute') return
    getJson('/crm/whatsapp-groups')
      .then((payload) => {
        setWhatsappGroups(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setWhatsappError(err.message || 'Unable to load WhatsApp groups.')
      })
  }, [activeTab])

  useEffect(() => {
    if (activeTab !== 'setup' || !activeId) return
    handleLoadInviteWaves()
    getJson(`/conversations/${activeId}/comments?status=approved`)
      .then((approved) => {
        setApprovedComments(Array.isArray(approved) ? approved : [])
      })
      .catch(() => null)
  }, [activeTab, activeId])

  useEffect(() => {
    if (activeTab !== 'moderation' || !activeId) return
    handleStartModeration()
    handleLoadModerationLog()
  }, [activeTab, activeId])

  useEffect(() => {
    if (activeTab !== 'insights' || !activeId) return
    handleLoadStats()
    handleLoadThemes()
    handleLoadThemeSummary()
  }, [activeTab, activeId])


  useEffect(() => {
    if (!activeId) {
      setActiveConvo(null)
      setApprovedComments([])
      setPendingComments([])
      return
    }
    Promise.all([
      getJson(`/conversations/${activeId}`),
      getJson(`/conversations/${activeId}/comments?status=approved`),
      getJson(`/conversations/${activeId}/comments?status=pending&include_stats=false`),
    ])
      .then(([convo, approved, pending]) => {
        setActiveConvo(convo)
        setApprovedComments(Array.isArray(approved) ? approved : [])
        setPendingComments(Array.isArray(pending) ? pending : [])
        setUpdateForm({
          topic: convo.topic,
          description: convo.description || '',
          allowCommentSubmission: convo.allow_comment_submission,
          allowViz: convo.allow_viz,
          moderationProfile: convo.moderation_profile || (convo.moderation_required ? 'strict' : 'lazy'),
          moderationRequired: convo.moderation_required,
          allowVoting: convo.allow_voting ?? true,
          minVotesForInclusion: convo.min_votes_for_inclusion ?? 3,
          profanityFilterEnabled: convo.profanity_filter_enabled ?? false,
          rateLimitPerMinute: convo.rate_limit_per_minute ?? 0,
          identityMode: convo.identity_mode || 'anonymous',
          inviteOnly: convo.invite_only ?? false,
          isOpen: convo.is_open,
        })
      })
      .catch((err) =>
        setConvoError(err.message || 'Unable to load conversation data.'),
      )
  }, [activeId])

  const buildQuestionnaireLink = (questionnaireType, view, conversationId = activeId) => {
    if (!conversationId || typeof window === 'undefined') return ''
    const origin = window.location.origin
    const currentPath = window.location.pathname || '/'
    const cleanPath = currentPath.replace(/\/index\.html$/, '/')
    const basePath = cleanPath.endsWith('/') ? cleanPath : `${cleanPath}/`
    const url = new URL(basePath, origin)
    url.searchParams.set('questionnaire', questionnaireType)
    url.searchParams.set('conversation_id', conversationId)
    if (view) url.searchParams.set('view', view)
    if (language) url.searchParams.set('lang', language)
    return url.toString()
  }

  const buildPublicReportLink = (shareId) => {
    if (!shareId || typeof window === 'undefined') return ''
    const origin = window.location.origin
    const currentPath = window.location.pathname || '/'
    const cleanPath = currentPath.replace(/\/index\.html$/, '/')
    const basePath = cleanPath.endsWith('/') ? cleanPath : `${cleanPath}/`
    const url = new URL(basePath, origin)
    url.searchParams.set('report_share', shareId)
    if (language) url.searchParams.set('lang', language)
    return url.toString()
  }

  const questionnaireLink = useMemo(
    () => buildQuestionnaireLink('deliberation', 'participant'),
    [activeId, language],
  )
  const getShareAudienceLabel = (audience) => {
    if (audience === 'unverified') return 'Unverified users'
    if (audience === 'registered') return 'Registered users'
    return 'Verified users'
  }
  const audienceQuestionnaireLink = useMemo(() => {
    if (!questionnaireLink) return ''
    try {
      const url = new URL(questionnaireLink)
      url.searchParams.set('audience', shareAudience)
      return url.toString()
    } catch {
      return questionnaireLink
    }
  }, [questionnaireLink, shareAudience])
  const verifiedQuestionnaireLink = useMemo(() => {
    if (!questionnaireLink) return ''
    const url = new URL(questionnaireLink)
    url.searchParams.set('audience', 'verified')
    return url.toString()
  }, [questionnaireLink])
  const unverifiedQuestionnaireLink = useMemo(() => {
    if (!questionnaireLink) return ''
    const url = new URL(questionnaireLink)
    url.searchParams.set('audience', 'unverified')
    return url.toString()
  }, [questionnaireLink])
  const registeredQuestionnaireLink = useMemo(() => {
    if (!questionnaireLink) return ''
    const url = new URL(questionnaireLink)
    url.searchParams.set('audience', 'registered')
    return url.toString()
  }, [questionnaireLink])

  const adminQuestionnaireLink = useMemo(
    () => buildQuestionnaireLink('deliberation_admin', 'admin'),
    [activeId, language],
  )

  const pageEmbedCode = useMemo(
    () =>
      `<div class="polis" data-page_id="${polisPageId}" data-site_id="${polisSiteId}"></div>
<script async src="https://pol.is/embed.js"></script>`,
    [polisPageId, polisSiteId],
  )

  const conversationEmbedCode = useMemo(
    () =>
      `<div class="polis" data-conversation_id="${polisConversationId || 'CONVERSATION_ID'}"></div>
<script async src="https://pol.is/embed.js"></script>`,
    [polisConversationId],
  )

  const questionnaireEmbedCode = useMemo(() => {
    const embedLink = buildQuestionnaireLink('deliberation', 'embed')
    if (!embedLink) return ''
    return `<iframe src="${embedLink}&xid=YOUR_USER_ID" style="width:100%;min-height:720px;border:0;" title="Survey & Consensus widget"></iframe>`
  }, [activeId, language])

  useEffect(() => {
    if (!activeId || !audienceQuestionnaireLink) {
      setSlackMessage('')
      setWhatsappMessage('')
      return
    }
    const message = `Survey questionnaire (${getShareAudienceLabel(shareAudience)}): ${
      activeConvo?.topic || 'Conversation'
    }\n\n${audienceQuestionnaireLink}`
    setSlackMessage(message)
    setWhatsappMessage(message)
    setSlackStatus('')
    setSlackError('')
    setWhatsappStatus('')
    setWhatsappError('')
  }, [activeId, audienceQuestionnaireLink, activeConvo?.topic, shareAudience])

  const handleSendSlack = async () => {
    if (!audienceQuestionnaireLink) {
      setSlackError('Select a conversation first.')
      return
    }
    if (slackChannelMode === 'custom' && !slackChannelValue.trim()) {
      setSlackError('Enter a Slack channel.')
      return
    }
    const message =
      slackMessage ||
      `Survey questionnaire (${getShareAudienceLabel(shareAudience)}): ${
        activeConvo?.topic || 'Conversation'
      }\n\n${audienceQuestionnaireLink}`
    setSlackError('')
    setSlackStatus('')
    setSendingSlack(true)
    try {
      await requestJson('/crm/slack/send', {
        method: 'POST',
        payload: {
          message,
          channel: slackChannelMode === 'custom' ? slackChannelValue.trim() : '',
          source: 'deliberation_share',
        },
      })
      setSlackStatus('Sent to Slack.')
    } catch (err) {
      setSlackError(err.message || 'Unable to send to Slack.')
    } finally {
      setSendingSlack(false)
    }
  }

  const handleSendWhatsapp = async () => {
    if (!audienceQuestionnaireLink) {
      setWhatsappError('Select a conversation first.')
      return
    }
    if (!whatsappGroupId) {
      setWhatsappError('Select a WhatsApp group.')
      return
    }
    const message =
      whatsappMessage ||
      `Survey questionnaire (${getShareAudienceLabel(shareAudience)}): ${
        activeConvo?.topic || 'Conversation'
      }\n\n${audienceQuestionnaireLink}`
    setWhatsappError('')
    setWhatsappStatus('')
    setSendingWhatsapp(true)
    try {
      await requestJson(`/crm/whatsapp-groups/${whatsappGroupId}/send`, {
        method: 'POST',
        payload: {
          message,
          appendInvite: false,
          source: 'deliberation_share',
        },
      })
      setWhatsappStatus('Sent to WhatsApp.')
    } catch (err) {
      setWhatsappError(err.message || 'Unable to send to WhatsApp.')
    } finally {
      setSendingWhatsapp(false)
    }
  }

  const handleCopy = async (value, label) => {
    if (!value) return
    if (!navigator?.clipboard) {
      setCopyStatus({
        message: 'Clipboard unavailable in this browser.',
        tone: 'error',
      })
      return
    }
    try {
      await navigator.clipboard.writeText(value)
      setCopyStatus({ message: `${label} copied.`, tone: 'success' })
    } catch (err) {
      setCopyStatus({ message: 'Unable to copy to clipboard.', tone: 'error' })
    }
  }

  const handleCreateConversation = async () => {
    if (!createForm.topic.trim()) {
      setConvoError('Topic must be at least 3 characters.')
      return
    }
    const initialStatements = (createForm.initialStatements || [])
      .map((line) => sanitizeStatement(line))
      .filter(Boolean)
    if (initialStatements.length !== STATEMENT_SLOT_COUNT) {
      setConvoError(`Please provide ${STATEMENT_SLOT_COUNT} statements.`)
      return
    }
    setConvoError('')
    try {
      const created = await requestJson('/conversations', {
        method: 'POST',
        payload: {
          topic: createForm.topic.trim(),
          description: createForm.description.trim(),
          initial_statements: initialStatements,
          allow_comment_submission: createForm.allowCommentSubmission,
          allow_viz: createForm.allowViz,
          moderation_required: createForm.moderationProfile === 'strict',
          moderation_profile: createForm.moderationProfile,
          allow_voting: createForm.allowVoting,
          min_votes_for_inclusion: Number(createForm.minVotesForInclusion) || 0,
          profanity_filter_enabled: createForm.profanityFilterEnabled,
          rate_limit_per_minute: Number(createForm.rateLimitPerMinute) || 0,
          identity_mode: createForm.identityMode,
          invite_only: createForm.inviteOnly,
          is_open: createForm.isOpen,
        },
      })
      setCreateForm({
        topic: '',
        description: '',
        initialStatements: buildStatementSlots(),
        allowCommentSubmission: true,
        allowViz: true,
        moderationProfile: 'lazy',
        moderationRequired: false,
        allowVoting: true,
        minVotesForInclusion: 3,
        profanityFilterEnabled: false,
        rateLimitPerMinute: 0,
        identityMode: 'anonymous',
        inviteOnly: false,
        isOpen: true,
      })
      if (created?.id) {
        setActiveId(created.id)
      }
      loadConversations()
    } catch (err) {
      setConvoError(err.message || 'Unable to create conversation.')
    }
  }


  const handleToggleConversation = async (conversationId, nextOpen) => {
    if (!conversationId) return
    try {
      await requestJson(`/conversations/${conversationId}`, {
        method: 'PATCH',
        payload: { is_open: nextOpen },
      })
      loadConversations()
      if (activeId === conversationId && !nextOpen) {
        setActiveId('')
      }
    } catch (err) {
      setConvoError(err.message || 'Unable to update conversation status.')
    }
  }

  const handleUpdateConversation = async () => {
    if (!activeId || !updateForm) return
    setConvoError('')
    try {
      await requestJson(`/conversations/${activeId}`, {
        method: 'PATCH',
        payload: {
          topic: updateForm.topic,
          description: updateForm.description,
          allow_comment_submission: updateForm.allowCommentSubmission,
          allow_viz: updateForm.allowViz,
          moderation_required: updateForm.moderationProfile === 'strict',
          moderation_profile: updateForm.moderationProfile,
          allow_voting: updateForm.allowVoting,
          min_votes_for_inclusion: Number(updateForm.minVotesForInclusion) || 0,
          profanity_filter_enabled: updateForm.profanityFilterEnabled,
          rate_limit_per_minute: Number(updateForm.rateLimitPerMinute) || 0,
          identity_mode: updateForm.identityMode,
          invite_only: updateForm.inviteOnly,
          is_open: updateForm.isOpen,
        },
      })
      loadConversations()
    } catch (err) {
      setConvoError(err.message || 'Unable to update conversation.')
    }
  }

  const handleSaveExistingStatements = async () => {
    if (!activeId) return
    const normalizedSlots = existingStatementSlots.map((slot) => ({
      id: slot.id || '',
      text: sanitizeStatement(slot.text),
    }))
    if (normalizedSlots.filter((slot) => slot.text).length !== STATEMENT_SLOT_COUNT) {
      setSeedStatus(`Please fill all ${STATEMENT_SLOT_COUNT} statements.`)
      return
    }
    setSavingExistingStatements(true)
    setSeedStatus('')
    try {
      const updates = normalizedSlots.filter((slot) => slot.id && slot.text)
      const creates = normalizedSlots.filter((slot) => !slot.id && slot.text).map((slot) => slot.text)
      if (updates.length) {
        await Promise.all(
          updates.map((slot) =>
            requestJson(`/comments/${slot.id}/edit`, {
              method: 'PATCH',
              payload: { text: slot.text, is_seed: true },
            }),
          ),
        )
      }
      if (creates.length) {
        await requestJson(`/conversations/${activeId}/seed-comments:bulk`, {
          method: 'POST',
          payload: { comments: creates },
        })
      }
      const approved = await getJson(`/conversations/${activeId}/comments?status=approved`)
      setApprovedComments(Array.isArray(approved) ? approved : [])
      setSeedStatus('Saved 5 statements.')
    } catch (err) {
      setSeedStatus(err.message || 'Unable to save statements.')
    } finally {
      setSavingExistingStatements(false)
    }
  }

  const handleSimulateVotes = async () => {
    if (!activeId) return
    try {
      await requestJson(`/conversations/${activeId}/simulate-votes`, {
        method: 'POST',
        payload: {
          participants: Number(simulateForm.participants),
          votes_per_participant: Number(simulateForm.votesPerParticipant),
          seed: Number(simulateForm.seed),
        },
      })
    } catch (err) {
      setConvoError(err.message || 'Unable to simulate votes.')
    }
  }

  const handleApprove = async (commentId, status, options = {}) => {
    try {
      await requestJson(`/comments/${commentId}`, {
        method: 'PATCH',
        payload: {
          status,
          rejection_reason: options.rejectionReason,
          copy_to_seed: options.copyToSeed,
        },
      })
      const pending = await getJson(
        `/conversations/${activeId}/comments?status=pending&include_stats=false`,
      )
      setPendingComments(Array.isArray(pending) ? pending : [])
      const approved = await getJson(
        `/conversations/${activeId}/comments?status=approved`,
      )
      setApprovedComments(Array.isArray(approved) ? approved : [])
    } catch (err) {
      setConvoError(err.message || 'Unable to update comment.')
    }
  }

  const handleUpdateSeedComment = async (commentId, text) => {
    if (!commentId || !text.trim()) {
      setSeedStatus('Seed comment cannot be empty.')
      return
    }
    setSeedStatus('')
    try {
      await requestJson(`/comments/${commentId}/edit`, {
        method: 'PATCH',
        payload: { text: text.trim() },
      })
      const approved = await getJson(
        `/conversations/${activeId}/comments?status=approved`,
      )
      setApprovedComments(Array.isArray(approved) ? approved : [])
      setSeedEditId('')
      setSeedEditText('')
      setSeedStatus('Seed comment updated.')
    } catch (err) {
      setSeedStatus(err.message || 'Unable to update seed comment.')
    }
  }

  const handleDeleteComment = async (commentId) => {
    if (!commentId) return
    try {
      await requestJson(`/comments/${commentId}`, { method: 'DELETE' })
      const approved = await getJson(
        `/conversations/${activeId}/comments?status=approved`,
      )
      setApprovedComments(Array.isArray(approved) ? approved : [])
    } catch (err) {
      setConvoError(err.message || 'Unable to delete comment.')
    }
  }

  const handleToggleSeed = async (commentId, nextIsSeed) => {
    if (!commentId) return
    try {
      await requestJson(`/comments/${commentId}/edit`, {
        method: 'PATCH',
        payload: { is_seed: nextIsSeed },
      })
      const approved = await getJson(
        `/conversations/${activeId}/comments?status=approved`,
      )
      setApprovedComments(Array.isArray(approved) ? approved : [])
    } catch (err) {
      setConvoError(err.message || 'Unable to update seed status.')
    }
  }

  const handleVote = async (commentId, choice) => {
    try {
      await requestJson('/vote', {
        method: 'POST',
        payload: { conversation_id: activeId, comment_id: commentId, choice },
      })
    } catch (err) {
      setConvoError(err.message || 'Unable to vote.')
    }
  }

  const handleSubmitComment = async () => {
    if (!activeId) return
    if (!commentText.trim()) {
      setConvoError('Comment cannot be empty.')
      return
    }
    setConvoError('')
    try {
      await requestJson(`/conversations/${activeId}/comments`, {
        method: 'POST',
        payload: { text: commentText.trim() },
      })
      setCommentText('')
      const [approved, pending] = await Promise.all([
        getJson(`/conversations/${activeId}/comments?status=approved`),
        getJson(`/conversations/${activeId}/comments?status=pending&include_stats=false`),
      ])
      setApprovedComments(Array.isArray(approved) ? approved : [])
      setPendingComments(Array.isArray(pending) ? pending : [])
    } catch (err) {
      setConvoError(err.message || 'Unable to submit comment.')
    }
  }

  const getPublicReportLink = (convo) => {
    if (!convo) return ''
    const shareId =
      convo.report_share_id ||
      convo.reportShareId ||
      convo.report_share ||
      convo.reportShare ||
      ''
    if (shareId) return buildPublicReportLink(shareId)
    return publicReportLinks[convo.id] || ''
  }

  const handleOpenPublicReport = async (convo) => {
    if (!convo?.id) return
    const existingLink = getPublicReportLink(convo)
    if (existingLink) {
      window.open(existingLink, '_blank', 'noopener,noreferrer')
      return
    }
    try {
      const payload = await requestJson(`/conversations/${convo.id}/reports`, {
        method: 'POST',
        payload: {
          name: `${convo.topic || 'Survey'} report`,
          theme_ids: [],
          include_unassigned: true,
        },
      })
      const shareId = payload?.share_id
      if (!shareId) {
        throw new Error('Public report link unavailable.')
      }
      const link = buildPublicReportLink(shareId)
      setPublicReportLinks((prev) => ({ ...prev, [convo.id]: link }))
      window.open(link, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setConvoError(err.message || 'Unable to open public report.')
    }
  }

  const activeConversations = conversations.filter((convo) => convo.is_open)
  const closedConversations = conversations.filter((convo) => !convo.is_open)

  const getDiscussionParticipantId = () => {
    if (typeof window === 'undefined') return `insights_${Date.now()}`
    const key = `fs.deliberation.discussion.participant.${activeId || 'default'}`
    const existing = window.localStorage.getItem(key)
    if (existing) return existing
    const created = `insights_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
    window.localStorage.setItem(key, created)
    return created
  }

  const loadStatementDiscussionComments = async (statementId) => {
    if (!activeId || !statementId) return
    setDiscussionLoadingByStatement((prev) => ({ ...prev, [statementId]: true }))
    setDiscussionErrorByStatement((prev) => ({ ...prev, [statementId]: '' }))
    try {
      const participantId = getDiscussionParticipantId()
      const payload = await requestJson(
        `/conversations/${activeId}/statements/${statementId}/discussion-comments`,
        {
          method: 'GET',
          headers: { 'X-Participant-Id': participantId },
        },
      )
      setDiscussionCommentsByStatement((prev) => ({
        ...prev,
        [statementId]: Array.isArray(payload) ? payload : [],
      }))
    } catch (err) {
      setDiscussionErrorByStatement((prev) => ({
        ...prev,
        [statementId]: err.message || 'Unable to load statement comments.',
      }))
    } finally {
      setDiscussionLoadingByStatement((prev) => ({ ...prev, [statementId]: false }))
    }
  }

  const handleCreateStatementDiscussionComment = async (statementId) => {
    const draft = discussionDraftByStatement[statementId] || ''
    if (activeConvo?.is_open === false) {
      setDiscussionErrorByStatement((prev) => ({
        ...prev,
        [statementId]: 'Conversation is closed. Reopen it to add statement comments.',
      }))
      return
    }
    if (!activeId || !statementId) {
      setDiscussionErrorByStatement((prev) => ({ ...prev, [statementId]: 'Select a statement first.' }))
      return
    }
    if (!draft.trim()) {
      setDiscussionErrorByStatement((prev) => ({ ...prev, [statementId]: 'Comment text is required.' }))
      return
    }
    setDiscussionSavingByStatement((prev) => ({ ...prev, [statementId]: true }))
    setDiscussionErrorByStatement((prev) => ({ ...prev, [statementId]: '' }))
    try {
      const participantId = getDiscussionParticipantId()
      await requestJson(
        `/conversations/${activeId}/statements/${statementId}/discussion-comments`,
        {
          method: 'POST',
          payload: { text: draft.trim(), author_id: participantId },
          headers: { 'X-Participant-Id': participantId },
        },
      )
      setDiscussionDraftByStatement((prev) => ({ ...prev, [statementId]: '' }))
      await loadStatementDiscussionComments(statementId)
    } catch (err) {
      setDiscussionErrorByStatement((prev) => ({
        ...prev,
        [statementId]: err.message || 'Unable to post statement comment.',
      }))
    } finally {
      setDiscussionSavingByStatement((prev) => ({ ...prev, [statementId]: false }))
    }
  }

  const handleReactToStatementDiscussionComment = async (statementId, commentId, reaction) => {
    if (activeConvo?.is_open === false) {
      setDiscussionErrorByStatement((prev) => ({
        ...prev,
        [statementId]: 'Conversation is closed. Reopen it to react on comments.',
      }))
      return
    }
    if (!activeId || !statementId || !commentId) return
    setDiscussionReactionBusyByStatement((prev) => ({ ...prev, [statementId]: commentId }))
    setDiscussionErrorByStatement((prev) => ({ ...prev, [statementId]: '' }))
    try {
      const participantId = getDiscussionParticipantId()
      const updated = await requestJson(
        `/conversations/${activeId}/statements/${statementId}/discussion-comments/${commentId}/reactions`,
        {
          method: 'POST',
          payload: { reaction, author_id: participantId },
          headers: { 'X-Participant-Id': participantId },
        },
      )
      setDiscussionCommentsByStatement((prev) => ({
        ...prev,
        [statementId]: (prev[statementId] || []).map((item) =>
          item.id === commentId ? { ...item, ...(updated || {}) } : item,
        ),
      }))
    } catch (err) {
      setDiscussionErrorByStatement((prev) => ({
        ...prev,
        [statementId]: err.message || 'Unable to react to comment.',
      }))
    } finally {
      setDiscussionReactionBusyByStatement((prev) => ({ ...prev, [statementId]: '' }))
    }
  }

  useEffect(() => {
    if (activeTab !== 'insights') return
    if (!activeId) return
    discussionStatementOptions.forEach((row) => {
      if (!row?.id) return
      if (discussionCommentsByStatement[row.id]) return
      loadStatementDiscussionComments(row.id)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, activeId, discussionStatementOptions])

  const handleRunAnalysis = async () => {
    if (!activeId) return
    setReportError('')
    try {
      const reportPayload = await requestJson(
        `/conversations/${activeId}/analyze`,
        { method: 'POST', payload: {} },
      )
      setReport(reportPayload)
    } catch (err) {
      setReportError(err.message || 'Unable to run analysis.')
    }
  }

  const handleLoadReport = async () => {
    if (!activeId) return
    setReportError('')
    try {
      const reportPayload = await getJson(
        `/conversations/${activeId}/report`,
      )
      setReport(reportPayload)
    } catch (err) {
      setReportError(err.message || 'Unable to load report.')
    }
  }

  const handleLoadStats = async () => {
    if (!activeId) return
    setStatsError('')
    setLoadingStats(true)
    try {
      const payload = await getJson(`/conversations/${activeId}/stats`)
      setStats(payload)
    } catch (err) {
      setStatsError(err.message || 'Unable to load monitoring stats.')
    } finally {
      setLoadingStats(false)
    }
  }

  const handleDownloadExport = async () => {
    if (!activeId) return
    setExportStatus('')
    setExporting(true)
    try {
      const response = await fetch(`${API_BASE}/conversations/${activeId}/export`)
      if (!response.ok) {
        throw new Error('Export failed.')
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `conversation_${activeId}_export.zip`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setExportStatus('Export downloaded.')
    } catch (err) {
      setExportStatus(err.message || 'Unable to download export.')
    } finally {
      setExporting(false)
    }
  }

  const handleDownloadConversationCsv = async (conversationId) => {
    if (!conversationId) return
    setTableExportingConversationId(conversationId)
    setConvoError('')
    try {
      const response = await fetch(`${API_BASE}/conversations/${conversationId}/export.csv`)
      if (!response.ok) {
        throw new Error('Conversation CSV export failed.')
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `conversation_${conversationId}_dataset.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setConvoError(err.message || 'Unable to export conversation CSV.')
    } finally {
      setTableExportingConversationId('')
    }
  }

  const handleLoadModerationLog = async () => {
    if (!activeId) return
    setModerationLogError('')
    try {
      const payload = await getJson(`/conversations/${activeId}/moderation-log`)
      setModerationLog(Array.isArray(payload?.entries) ? payload.entries : [])
    } catch (err) {
      setModerationLogError(err.message || 'Unable to load moderation log.')
    }
  }

  const handleLoadInviteWaves = async () => {
    if (!activeId) return
    setInviteError('')
    try {
      const payload = await getJson(`/conversations/${activeId}/invite-waves`)
      setInviteWaves(Array.isArray(payload?.waves) ? payload.waves : [])
    } catch (err) {
      setInviteError(err.message || 'Unable to load invite waves.')
    }
  }

  const handleCreateInviteWave = async () => {
    if (!activeId) return
    setInviteError('')
    try {
      await requestJson(`/conversations/${activeId}/invite-waves`, {
        method: 'POST',
        payload: {
          name: inviteForm.name.trim(),
          count: Number(inviteForm.count) || 0,
          parent_code: inviteForm.parentCode.trim() || null,
        },
      })
      handleLoadInviteWaves()
      setInviteForm((prev) => ({ ...prev, parentCode: '' }))
    } catch (err) {
      setInviteError(err.message || 'Unable to create invite wave.')
    }
  }

  const handleRevokeInvite = async (inviteId, cascade = false) => {
    if (!inviteId) return
    try {
      await requestJson(`/invites/${inviteId}/revoke?cascade=${cascade ? 'true' : 'false'}`)
      handleLoadInviteWaves()
    } catch (err) {
      setInviteError(err.message || 'Unable to revoke invite.')
    }
  }

  const handleIngestText = async () => {
    if (!activeId || !ingestText.trim()) return
    setIngestStatus('')
    try {
      const payload = await requestJson(`/conversations/${activeId}/ingest`, {
        method: 'POST',
        payload: { text: ingestText.trim(), strategy: ingestStrategy, max_items: 200 },
      })
      const items = Array.isArray(payload?.items) ? payload.items : []
      setIngestItems(items)
      const nextSelection = {}
      items.forEach((item) => {
        nextSelection[item] = true
      })
      setIngestSelection(nextSelection)
      setIngestStatus(`Prepared ${items.length} statements.`)
    } catch (err) {
      setIngestStatus(err.message || 'Unable to ingest text.')
    }
  }

  const handleSeedFromIngest = async () => {
    if (!activeId) return
    const selected = ingestItems.filter((item) => ingestSelection[item])
    if (!selected.length) {
      setIngestStatus('Select at least one statement to seed.')
      return
    }
    try {
      await requestJson(`/conversations/${activeId}/seed-comments:bulk`, {
        method: 'POST',
        payload: { comments: selected },
      })
      setIngestStatus('Seed comments added.')
      setSeedStatus('Seed comments added.')
      const approved = await getJson(
        `/conversations/${activeId}/comments?status=approved`,
      )
      setApprovedComments(Array.isArray(approved) ? approved : [])
    } catch (err) {
      setIngestStatus(err.message || 'Unable to seed statements.')
    }
  }

  const handleLoadThemes = async () => {
    if (!activeId) return
    setThemeError('')
    try {
      const payload = await getJson(`/conversations/${activeId}/themes`)
      setThemes(Array.isArray(payload?.themes) ? payload.themes : [])
    } catch (err) {
      setThemeError(err.message || 'Unable to load themes.')
    }
  }

  const handleLoadThemeSummary = async () => {
    if (!activeId) return
    try {
      const payload = await getJson(`/conversations/${activeId}/themes/summary`)
      setThemeSummary(payload)
    } catch (err) {
      setThemeSummary(null)
    }
  }

  const handleCreateTheme = async () => {
    if (!activeId || !themeForm.name.trim()) return
    setThemeError('')
    try {
      await requestJson(`/conversations/${activeId}/themes`, {
        method: 'POST',
        payload: {
          name: themeForm.name.trim(),
          description: themeForm.description.trim() || null,
        },
      })
      setThemeForm({ name: '', description: '' })
      handleLoadThemes()
      handleLoadThemeSummary()
    } catch (err) {
      setThemeError(err.message || 'Unable to create theme.')
    }
  }

  const handleDeleteTheme = async (themeId) => {
    if (!themeId) return
    try {
      await requestJson(`/themes/${themeId}`, { method: 'DELETE' })
      handleLoadThemes()
      handleLoadThemeSummary()
    } catch (err) {
      setThemeError(err.message || 'Unable to delete theme.')
    }
  }

  const handleAssignThemes = async () => {
    if (!themeAssign.commentId) return
    try {
      await requestJson(`/comments/${themeAssign.commentId}/themes`, {
        method: 'POST',
        payload: { theme_ids: themeAssign.themeIds },
      })
      handleLoadThemeSummary()
    } catch (err) {
      setThemeError(err.message || 'Unable to assign themes.')
    }
  }

  const handleCreateReport = async () => {
    if (!activeId || !reportBuilder.name.trim()) return
    try {
      const payload = await requestJson(`/conversations/${activeId}/reports`, {
        method: 'POST',
        payload: {
          name: reportBuilder.name.trim(),
          theme_ids: reportBuilder.themeIds,
          include_unassigned: reportBuilder.includeUnassigned,
        },
      })
      const shareId = payload?.share_id
      if (shareId) {
        const link = `${window.location.origin}/?report_share=${shareId}`
        setReportLinks((prev) => [{ name: reportBuilder.name.trim(), link }, ...prev])
      }
      setReportBuilder((prev) => ({ ...prev, name: '' }))
    } catch (err) {
      setThemeError(err.message || 'Unable to generate report.')
    }
  }

  const pollExportJob = async (jobId, attempt = 0) => {
    if (!jobId || attempt > 20) return
    try {
      const payload = await getJson(`/exports/${jobId}`)
      setExportJob(payload)
      if (payload?.status === 'pending') {
        setTimeout(() => pollExportJob(jobId, attempt + 1), 2000)
      }
    } catch (err) {
      setExportStatus(err.message || 'Unable to fetch export job status.')
    }
  }

  const handleCreateExportJob = async () => {
    if (!activeId) return
    setExportStatus('')
    try {
      const payload = await requestJson(`/conversations/${activeId}/exports`, {
        method: 'POST',
      })
      if (payload?.job_id) {
        setExportJob({ id: payload.job_id, status: payload.status })
        pollExportJob(payload.job_id)
      }
    } catch (err) {
      setExportStatus(err.message || 'Unable to start export job.')
    }
  }

  const handleDownloadExportJob = async () => {
    if (!exportJob?.id) return
    try {
      const response = await fetch(`${API_BASE}/exports/${exportJob.id}/download`)
      if (!response.ok) {
        throw new Error('Export not ready.')
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `conversation_${activeId}_export.zip`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setExportStatus(err.message || 'Unable to download export.')
    }
  }

  const parseCsvFile = (file) => {
    setCsvStatus('')
    if (!file) {
      setCsvStatus('Select a CSV file.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const text = String(reader.result || '')
        const { data, fields } = parseCsvText(text)
        setCsvRows(data)
        setCsvColumns(fields)
        setCsvMap({
          conversation_id: guessColumn(fields, ['conversation_id', 'conversation']),
          participant_id: guessColumn(fields, ['participant_id', 'participant', 'voter_id']),
          participant_cluster: guessColumn(fields, ['participant_cluster', 'cluster']),
          comment_id: guessColumn(fields, ['comment_id', 'statement_id', 'seed_id']),
          comment_text: guessColumn(fields, ['comment_text', 'comment', 'text']),
          is_seed: guessColumn(fields, ['is_seed', 'seed']),
          comment_created_at: guessColumn(fields, ['comment_created_at', 'created_at']),
          vote: guessColumn(fields, ['vote', 'choice', 'reaction']),
          reaction_created_at: guessColumn(fields, ['reaction_created_at', 'voted_at']),
        })
      } catch (err) {
        setCsvStatus(err.message || 'CSV parse failed.')
      }
    }
    reader.onerror = () => setCsvStatus('CSV parse failed.')
    reader.readAsText(file)
  }

  const handleImportDataset = async () => {
    if (!activeId) return
    if (!csvRows.length) {
      setCsvStatus('Upload a CSV first.')
      return
    }
    if (!csvMap.comment_id) {
      setCsvStatus('Select a comment_id column.')
      return
    }
    const rows = csvRows.map((row) => ({
      conversation_id: csvMap.conversation_id ? row[csvMap.conversation_id] : undefined,
      participant_id: csvMap.participant_id ? row[csvMap.participant_id] : undefined,
      participant_cluster: csvMap.participant_cluster
        ? row[csvMap.participant_cluster]
        : undefined,
      comment_id: row[csvMap.comment_id],
      comment_text: csvMap.comment_text ? row[csvMap.comment_text] : undefined,
      is_seed: csvMap.is_seed ? row[csvMap.is_seed] : undefined,
      comment_created_at: csvMap.comment_created_at
        ? row[csvMap.comment_created_at]
        : undefined,
      vote: csvMap.vote ? row[csvMap.vote] : undefined,
      reaction_created_at: csvMap.reaction_created_at
        ? row[csvMap.reaction_created_at]
        : undefined,
    }))
    setCsvStatus('Importing...')
    try {
      const result = await requestJson(
        `/conversations/${activeId}/dataset:bulk`,
        { method: 'POST', payload: { rows } },
      )
      if (runAnalysisAfterImport) {
        await requestJson(`/conversations/${activeId}/analyze`, { method: 'POST' })
      }
      setCsvStatus(
        `Imported ${result?.comments_created ?? 0} comments and ${result?.votes_imported ?? 0} votes.`,
      )
    } catch (err) {
      setCsvStatus(err.message || 'Import failed.')
    }
  }

  const handleSeedFromCsv = async () => {
    if (!activeId) return
    if (!seedCsvColumn) {
      setCsvStatus('Select a column to seed.')
      return
    }
    const values = csvRows
      .map((row) => String(row[seedCsvColumn] || '').trim())
      .filter(Boolean)
      .slice(0, Math.max(1, Number(seedCsvLimit) || 0))
    if (!values.length) {
      setCsvStatus('No valid values found in that column.')
      return
    }
    try {
      await requestJson(`/conversations/${activeId}/seed-comments:bulk`, {
        method: 'POST',
        payload: { comments: values },
      })
      setCsvStatus(`Seeded ${values.length} comments.`)
    } catch (err) {
      setCsvStatus(err.message || 'Seeding failed.')
    }
  }

  const vennSelected = vennData?.selected || []
  const vennSets = vennData?.sets || []
  const vennOverlaps = vennData?.overlaps || {}
  const vennA = vennSets[0] || new Set()
  const vennB = vennSets[1] || new Set()
  const vennC = vennSets[2] || new Set()
  const vennAB = vennOverlaps.ab || new Set()
  const vennAC = vennOverlaps.ac || new Set()
  const vennBC = vennOverlaps.bc || new Set()
  const vennABC = vennOverlaps.abc || new Set()
  const vennAOnly = new Set(
    [...vennA].filter((item) => !vennB.has(item) && !vennC.has(item)),
  )
  const vennBOnly = new Set(
    [...vennB].filter((item) => !vennA.has(item) && !vennC.has(item)),
  )
  const vennCOnly = new Set(
    [...vennC].filter((item) => !vennA.has(item) && !vennB.has(item)),
  )
  const vennABOnly = new Set([...vennAB].filter((item) => !vennC.has(item)))
  const vennACOnly = new Set([...vennAC].filter((item) => !vennB.has(item)))
  const vennBCOnly = new Set([...vennBC].filter((item) => !vennA.has(item)))
  const useMajority = statementMode === 'majority'
  const statementItems = useMajority
    ? reportCharts?.majorityTop || []
    : reportCharts?.consensusTop || []
  const statementScoreLabel = useMajority ? 'Agreement ratio' : 'Consensus score'
  const deliberationPulse = useMemo(
    () => [
      {
        label: 'Conversations',
        value: conversations.length,
        icon: <IconMessage2 size={18} />,
        badge: 'Live',
      },
      {
        label: 'Approved comments',
        value: approvedComments.length,
        icon: <IconUsers size={18} />,
        note: 'Ready for review',
      },
      {
        label: 'Pending moderation',
        value: pendingComments.length,
        icon: <IconChartDots size={18} />,
        badge: 'Review',
      },
      {
        label: 'Voting',
        value: activeConvo?.allow_voting === false ? 'Off' : 'On',
        icon: <IconChartDots size={18} />,
        note: 'Live reactions',
      },
    ],
    [activeConvo?.allow_voting, approvedComments.length, conversations.length, pendingComments.length],
  )
  return (
    <section className="module module--delib-radical">
      {convoError ? <div className="module-alert">{convoError}</div> : null}
      {copyStatus ? (
        <div
          className={`module-alert ${copyStatus.tone === 'success' ? 'module-alert--success' : ''}`}
        >
          {copyStatus.message}
        </div>
      ) : null}

      {showTabs ? (
        <div className="subtabs">
          {[
            { id: 'overview', label: 'Overview' },
            { id: 'setup', label: 'Survey setup' },
            { id: 'distribute', label: 'Share' },
            { id: 'moderation', label: 'Review queue' },
            { id: 'insights', label: 'Insights' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={tab.id === activeTab ? 'subtab active' : 'subtab'}
              onClick={() => applyActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {activeTab === 'overview' && (
        <div className="stack">
          <CivicStatGrid
            title="Deliberation pulse"
            description="Track active conversations, moderation load, and participation signals."
            items={deliberationPulse}
          />
          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Conversations</h3>
                <p className="muted">Open, close, and select the active conversation.</p>
              </div>
            </div>
            <div className="table">
              <div className="table-row table-row--conversations table-head">
                <span>Topic</span>
                <span>Status</span>
                <span>Action</span>
                <span>Active</span>
                <span>Link</span>
                <span>Statements</span>
                <span>Export CSV</span>
              </div>
              {activeConversations.map((convo) => {
                const isActive = activeId === convo.id
                const conversationLink = buildQuestionnaireLink(
                  'deliberation',
                  'participant',
                  convo.id,
                )
                const publicReportLink = getPublicReportLink(convo)
                const statementsTitle = isActive
                  ? buildStatementPreview(approvedComments)
                  : 'Set active to preview statements.'
                return (
                  <div className="table-row table-row--conversations" key={convo.id}>
                    <span>
                      <a
                        className="table-link"
                        href={publicReportLink || '#'}
                        target={publicReportLink ? '_blank' : undefined}
                        rel={publicReportLink ? 'noreferrer' : undefined}
                        title="Open public report"
                        onClick={(event) => {
                          if (publicReportLink) return
                          event.preventDefault()
                          handleOpenPublicReport(convo)
                        }}
                      >
                        {convo.topic}
                      </a>
                    </span>
                    <span>Open</span>
                    <div className="table-actions">
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => handleToggleConversation(convo.id, false)}
                      >
                        Close
                      </button>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button"
                        type="button"
                        onClick={() => setActiveId(convo.id)}
                        disabled={isActive}
                      >
                        {isActive ? 'Active' : 'Use'}
                      </button>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button-secondary button-secondary--small"
                        type="button"
                        title={conversationLink || 'Select a conversation to generate a link.'}
                        onClick={() => handleCopy(conversationLink, 'Participant link')}
                        disabled={!conversationLink}
                      >
                        Copy
                      </button>
                      <a
                        className="button-secondary button-secondary--small"
                        href={conversationLink}
                        target="_blank"
                        rel="noreferrer"
                        title={conversationLink || 'Select a conversation to generate a link.'}
                      >
                        Open
                      </a>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button-secondary button-secondary--small"
                        type="button"
                        title={statementsTitle}
                        onClick={() => {
                          if (!isActive) setActiveId(convo.id)
                        }}
                      >
                        Statements
                      </button>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button-secondary button-secondary--small"
                        type="button"
                        onClick={() => handleDownloadConversationCsv(convo.id)}
                        disabled={tableExportingConversationId === convo.id}
                      >
                        {tableExportingConversationId === convo.id ? 'Exporting…' : 'Download CSV'}
                      </button>
                    </div>
                  </div>
                )
              })}
              {closedConversations.map((convo) => {
                const isActive = activeId === convo.id
                const conversationLink = buildQuestionnaireLink(
                  'deliberation',
                  'participant',
                  convo.id,
                )
                const publicReportLink = getPublicReportLink(convo)
                const statementsTitle = isActive
                  ? buildStatementPreview(approvedComments)
                  : 'Set active to preview statements.'
                return (
                  <div className="table-row table-row--conversations" key={convo.id}>
                    <span>
                      <a
                        className="table-link"
                        href={publicReportLink || '#'}
                        target={publicReportLink ? '_blank' : undefined}
                        rel={publicReportLink ? 'noreferrer' : undefined}
                        title="Open public report"
                        onClick={(event) => {
                          if (publicReportLink) return
                          event.preventDefault()
                          handleOpenPublicReport(convo)
                        }}
                      >
                        {convo.topic}
                      </a>
                    </span>
                    <span>Closed</span>
                    <div className="table-actions">
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => handleToggleConversation(convo.id, true)}
                      >
                        Reopen
                      </button>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button"
                        type="button"
                        onClick={() => setActiveId(convo.id)}
                        disabled={isActive}
                      >
                        {isActive ? 'Active' : 'Use'}
                      </button>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button-secondary button-secondary--small"
                        type="button"
                        title={conversationLink || 'Select a conversation to generate a link.'}
                        onClick={() => handleCopy(conversationLink, 'Participant link')}
                        disabled={!conversationLink}
                      >
                        Copy
                      </button>
                      <a
                        className="button-secondary button-secondary--small"
                        href={conversationLink}
                        target="_blank"
                        rel="noreferrer"
                        title={conversationLink || 'Select a conversation to generate a link.'}
                      >
                        Open
                      </a>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button-secondary button-secondary--small"
                        type="button"
                        title={statementsTitle}
                        onClick={() => {
                          if (!isActive) setActiveId(convo.id)
                        }}
                      >
                        Statements
                      </button>
                    </div>
                    <div className="table-actions">
                      <button
                        className="button-secondary button-secondary--small"
                        type="button"
                        onClick={() => handleDownloadConversationCsv(convo.id)}
                        disabled={tableExportingConversationId === convo.id}
                      >
                        {tableExportingConversationId === convo.id ? 'Exporting…' : 'Download CSV'}
                      </button>
                    </div>
                  </div>
                )
              })}
              {conversations.length === 0 && (
                <div className="table-row table-row--conversations empty">
                  No conversations yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'setup' && (
        <div className="stack">
          <div className="module-card module-card__wide">
            <h3>Start setup</h3>
            <p className="muted">Create a new conversation or update an existing one.</p>
            <div className="filter-row">
              <button
                className={setupMode === 'new' ? 'button' : 'button-secondary'}
                type="button"
                onClick={() => setSetupMode('new')}
              >
                New conversation
              </button>
              <button
                className={setupMode === 'existing' ? 'button' : 'button-secondary'}
                type="button"
                onClick={() => setSetupMode('existing')}
              >
                Existing conversation
              </button>
            </div>
          </div>

          {setupMode === 'new' ? (
          <div className="module-card module-card__wide">
            <h3>Create survey</h3>
            <p className="muted">Give the survey a clear topic and description.</p>
            <div className="form-grid">
              <div className="form-grid__full">
                <input
                  className="input"
                  placeholder="Topic"
                  value={createForm.topic}
                  onChange={(event) =>
                    setCreateForm((prev) => ({ ...prev, topic: event.target.value }))
                  }
                />
              </div>
              <div className="form-grid__full">
                <label className="label">Statements for voting cards</label>
                <div className="stack">
                  {buildStatementSlots().map((_, index) => (
                    <input
                      key={`new-statement-${index + 1}`}
                      className="input"
                      placeholder={`Statement ${index + 1}`}
                      value={createForm.initialStatements?.[index] || ''}
                      onChange={(event) =>
                        setCreateForm((prev) => {
                          const next = Array.isArray(prev.initialStatements)
                            ? [...prev.initialStatements]
                            : buildStatementSlots()
                          next[index] = event.target.value
                          return { ...prev, initialStatements: next }
                        })
                      }
                    />
                  ))}
                </div>
                <p className="muted">Add all 5 statements now. These become participant voting cards.</p>
              </div>
              <div className="form-grid__full">
                <textarea
                  className="textarea"
                  placeholder="Description"
                  value={createForm.description}
                  onChange={(event) =>
                    setCreateForm((prev) => ({
                      ...prev,
                      description: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="field">
                <label className="label">Moderation profile</label>
                <select
                  className="select"
                  value={createForm.moderationProfile}
                  onChange={(event) =>
                    setCreateForm((prev) => ({
                      ...prev,
                      moderationProfile: event.target.value,
                    }))
                  }
                >
                  <option value="lazy">Lazy (auto-approve)</option>
                  <option value="strict">Strict (requires approval)</option>
                </select>
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={createForm.allowCommentSubmission}
                  onChange={(event) =>
                    setCreateForm((prev) => ({
                      ...prev,
                      allowCommentSubmission: event.target.checked,
                    }))
                  }
                />
                Allow comments
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={createForm.allowVoting}
                  onChange={(event) =>
                    setCreateForm((prev) => ({
                      ...prev,
                      allowVoting: event.target.checked,
                    }))
                  }
                />
                Allow voting
              </label>
              <div className="form-grid__full">
                <details className="dashboard-detail">
                  <summary>Advanced settings (optional)</summary>
                  <div className="dashboard-detail__body form-grid">
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={createForm.allowViz}
                        onChange={(event) =>
                          setCreateForm((prev) => ({ ...prev, allowViz: event.target.checked }))
                        }
                      />
                      Allow visualization
                    </label>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={createForm.profanityFilterEnabled}
                        onChange={(event) =>
                          setCreateForm((prev) => ({
                            ...prev,
                            profanityFilterEnabled: event.target.checked,
                          }))
                        }
                      />
                      Profanity filter
                    </label>
                    <div className="field">
                      <label className="label">Rate limit (per minute)</label>
                      <input
                        className="input"
                        type="number"
                        min="0"
                        max="120"
                        value={createForm.rateLimitPerMinute}
                        onChange={(event) =>
                          setCreateForm((prev) => ({
                            ...prev,
                            rateLimitPerMinute: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="field">
                      <label className="label">Min votes for inclusion</label>
                      <input
                        className="input"
                        type="number"
                        min="0"
                        max="1000"
                        value={createForm.minVotesForInclusion}
                        onChange={(event) =>
                          setCreateForm((prev) => ({
                            ...prev,
                            minVotesForInclusion: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="field">
                      <label className="label">Identity mode</label>
                      <select
                        className="select"
                        value={createForm.identityMode}
                        onChange={(event) =>
                          setCreateForm((prev) => ({
                            ...prev,
                            identityMode: event.target.value,
                          }))
                        }
                      >
                        <option value="anonymous">Anonymous</option>
                        <option value="xid_optional">Anonymous but verified</option>
                        <option value="xid_required">Login required</option>
                      </select>
                    </div>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={createForm.inviteOnly}
                        onChange={(event) =>
                          setCreateForm((prev) => ({
                            ...prev,
                            inviteOnly: event.target.checked,
                          }))
                        }
                      />
                      Invite-only participation
                    </label>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={createForm.isOpen}
                        onChange={(event) =>
                          setCreateForm((prev) => ({ ...prev, isOpen: event.target.checked }))
                        }
                      />
                      Open for participation
                    </label>
                  </div>
                </details>
              </div>
              <div className="form-grid__full">
                <button className="button" type="button" onClick={handleCreateConversation}>
                  Create conversation
                </button>
              </div>
            </div>
          </div>
          ) : null}

          {setupMode === 'existing' ? (
            <div className="module-card module-card__wide">
              <h3>Edit survey settings</h3>
              <p className="muted">Update the topic, description, and participation rules.</p>
              {conversations.length === 0 ? (
                <p className="muted">No conversations yet. Create one first.</p>
              ) : (
                <>
                  <div className="form-grid">
                    <div className="field form-grid__full">
                      <label className="label">Conversation</label>
                      <select
                        className="select"
                        value={activeId}
                        onChange={(event) => setActiveId(event.target.value)}
                      >
                        <option value="">Select a conversation</option>
                        {conversations.map((convo) => (
                          <option key={convo.id} value={convo.id}>
                            {convo.topic} {convo.is_open ? '(Open)' : '(Closed)'}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  {updateForm ? (
                    <div className="form-grid">
                      <div className="form-grid__full">
                        <input
                          className="input"
                          value={updateForm.topic}
                          onChange={(event) =>
                            setUpdateForm((prev) => ({ ...prev, topic: event.target.value }))
                          }
                        />
                      </div>
                      <div className="form-grid__full">
                        <textarea
                          className="textarea"
                          value={updateForm.description}
                          onChange={(event) =>
                            setUpdateForm((prev) => ({
                              ...prev,
                              description: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="form-grid__full">
                        <label className="label">Statements for voting cards</label>
                        <div className="stack">
                          {existingStatementSlots.map((slot, index) => (
                            <input
                              key={`existing-statement-${index + 1}`}
                              className="input"
                              placeholder={`Statement ${index + 1}`}
                              value={slot.text}
                              onChange={(event) =>
                                setExistingStatementSlots((prev) =>
                                  prev.map((item, itemIndex) =>
                                    itemIndex === index ? { ...item, text: event.target.value } : item,
                                  ),
                                )
                              }
                            />
                          ))}
                        </div>
                        <div className="filter-row">
                          <button
                            className="button-secondary"
                            type="button"
                            onClick={handleSaveExistingStatements}
                            disabled={savingExistingStatements}
                          >
                            {savingExistingStatements ? 'Saving...' : 'Save 5 statements'}
                          </button>
                          <span className="muted">Edit and save the first 5 statements used for voting cards.</span>
                        </div>
                        {seedStatus ? <p className="muted">{seedStatus}</p> : null}
                      </div>
                      <div className="field">
                        <label className="label">Moderation profile</label>
                        <select
                          className="select"
                          value={updateForm.moderationProfile}
                          onChange={(event) =>
                            setUpdateForm((prev) => ({
                              ...prev,
                              moderationProfile: event.target.value,
                            }))
                          }
                        >
                          <option value="lazy">Lazy (auto-approve)</option>
                          <option value="strict">Strict (requires approval)</option>
                        </select>
                      </div>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={updateForm.allowCommentSubmission}
                          onChange={(event) =>
                            setUpdateForm((prev) => ({
                              ...prev,
                              allowCommentSubmission: event.target.checked,
                            }))
                          }
                        />
                        Allow comments
                      </label>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={updateForm.allowVoting}
                          onChange={(event) =>
                            setUpdateForm((prev) => ({
                              ...prev,
                              allowVoting: event.target.checked,
                            }))
                          }
                        />
                        Allow voting
                      </label>
                      <div className="form-grid__full">
                        <details className="dashboard-detail">
                          <summary>Advanced settings (optional)</summary>
                          <div className="dashboard-detail__body form-grid">
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={updateForm.allowViz}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    allowViz: event.target.checked,
                                  }))
                                }
                              />
                              Allow visualization
                            </label>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={updateForm.profanityFilterEnabled}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    profanityFilterEnabled: event.target.checked,
                                  }))
                                }
                              />
                              Profanity filter
                            </label>
                            <div className="field">
                              <label className="label">Rate limit (per minute)</label>
                              <input
                                className="input"
                                type="number"
                                min="0"
                                max="120"
                                value={updateForm.rateLimitPerMinute}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    rateLimitPerMinute: event.target.value,
                                  }))
                                }
                              />
                            </div>
                            <div className="field">
                              <label className="label">Min votes for inclusion</label>
                              <input
                                className="input"
                                type="number"
                                min="0"
                                max="1000"
                                value={updateForm.minVotesForInclusion}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    minVotesForInclusion: event.target.value,
                                  }))
                                }
                              />
                            </div>
                            <div className="field">
                              <label className="label">Identity mode</label>
                              <select
                                className="select"
                                value={updateForm.identityMode}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    identityMode: event.target.value,
                                  }))
                                }
                              >
                                <option value="anonymous">Anonymous</option>
                                <option value="xid_optional">Anonymous but verified</option>
                                <option value="xid_required">Login required</option>
                              </select>
                            </div>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={updateForm.inviteOnly}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    inviteOnly: event.target.checked,
                                  }))
                                }
                              />
                              Invite-only participation
                            </label>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={updateForm.isOpen}
                                onChange={(event) =>
                                  setUpdateForm((prev) => ({
                                    ...prev,
                                    isOpen: event.target.checked,
                                  }))
                                }
                              />
                              Open for participation
                            </label>
                          </div>
                        </details>
                      </div>
                      <div className="form-grid__full">
                        <button className="button" type="button" onClick={handleUpdateConversation}>
                          Save settings
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="muted">Select a conversation to edit.</p>
                  )}
                  {updateForm ? (
                    <details className="dashboard-detail">
                      <summary>Invite-only waves (optional)</summary>
                      <div className="dashboard-detail__body">
                        <p className="muted">
                          Issue invites in waves. When invite-only is enabled, participation requires
                          a valid code.
                        </p>
                        <label className="label">Wave name</label>
                        <input
                          className="input"
                          value={inviteForm.name}
                          onChange={(event) =>
                            setInviteForm((prev) => ({ ...prev, name: event.target.value }))
                          }
                        />
                        <label className="label">Invite count</label>
                        <input
                          className="input"
                          type="number"
                          min="1"
                          max="1000"
                          value={inviteForm.count}
                          onChange={(event) =>
                            setInviteForm((prev) => ({ ...prev, count: event.target.value }))
                          }
                        />
                        <label className="label">Parent invite (optional)</label>
                        <input
                          className="input"
                          placeholder="Invite code for referral tree"
                          value={inviteForm.parentCode}
                          onChange={(event) =>
                            setInviteForm((prev) => ({ ...prev, parentCode: event.target.value }))
                          }
                        />
                        <button className="button" type="button" onClick={handleCreateInviteWave}>
                          Create invite wave
                        </button>
                        {inviteError ? <p className="muted">{inviteError}</p> : null}
                        {inviteWaves.length ? (
                          <div className="stack">
                            {inviteWaves.map((wave) => (
                              <div className="card-divider" key={wave.id}>
                                <div className="split-row">
                                  <div>
                                    <strong>{wave.name}</strong>
                                    <p className="muted">
                                      {wave.count} invites • {wave.created_at}
                                    </p>
                                  </div>
                                </div>
                                <div className="invite-grid">
                                  {wave.invites.map((invite) => (
                                    <div key={invite.id} className="invite-pill">
                                      <span>{invite.code}</span>
                                      <button
                                        className="button-secondary button-secondary--small"
                                        type="button"
                                        onClick={() => handleRevokeInvite(invite.id, true)}
                                      >
                                        Revoke
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </details>
                  ) : null}
                </>
              )}
            </div>
          ) : null}
        </div>
      )}


      {activeTab === 'distribute' && (
        <div className="stack">
          <details className="dashboard-detail">
            <summary>Share the survey</summary>
            <div className="dashboard-detail__body">
              <p className="muted">Send the participant link or embed the survey into your site.</p>
            </div>
          </details>

          {!activeConvo ? (
            <ActiveConversationRequired
              message="Choose a conversation in Overview to generate sharing links."
              onOpenOverview={() => applyActiveTab('overview')}
            />
          ) : (
            <>
              <div className="module-card module-card__wide">
                <h3>Share survey link</h3>
                <p className="muted">Choose audience and send the matching survey link.</p>
                {questionnaireLink ? (
                  <div className="stack">
                    <label className="label">Audience</label>
                    <select
                      className="select"
                      value={shareAudience}
                      onChange={(event) => setShareAudience(event.target.value)}
                    >
                      <option value="verified">Verified users</option>
                      <option value="unverified">Unverified users</option>
                      <option value="registered">Registered users</option>
                    </select>
                    <input className="input" value={audienceQuestionnaireLink} readOnly />
                    <div className="filter-row">
                      <a
                        className="button"
                        href={audienceQuestionnaireLink}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open participant view
                      </a>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => handleCopy(audienceQuestionnaireLink, 'Participant link')}
                      >
                        Copy link
                      </button>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => applyActiveTab('setup')}
                      >
                        Edit setup
                      </button>
                    </div>
                    <div className="stack">
                      <div className="metric-row">
                        <span>Verified users</span>
                        <button
                          className="button-secondary button-secondary--small"
                          type="button"
                          onClick={() => handleCopy(verifiedQuestionnaireLink, 'Verified audience link')}
                        >
                          Copy
                        </button>
                      </div>
                      <input className="input" value={verifiedQuestionnaireLink} readOnly />
                      <div className="metric-row">
                        <span>Unverified users</span>
                        <button
                          className="button-secondary button-secondary--small"
                          type="button"
                          onClick={() => handleCopy(unverifiedQuestionnaireLink, 'Unverified audience link')}
                        >
                          Copy
                        </button>
                      </div>
                      <input className="input" value={unverifiedQuestionnaireLink} readOnly />
                      <div className="metric-row">
                        <span>Registered users</span>
                        <button
                          className="button-secondary button-secondary--small"
                          type="button"
                          onClick={() => handleCopy(registeredQuestionnaireLink, 'Registered audience link')}
                        >
                          Copy
                        </button>
                      </div>
                      <input className="input" value={registeredQuestionnaireLink} readOnly />
                    </div>
                  </div>
                ) : (
                  <p className="muted">Select a conversation in Overview to generate a link.</p>
                )}
              </div>

              <div className="module-grid">
                <div className="module-card">
                  <h3>Share to Slack</h3>
                  {slackError ? <div className="module-alert">{slackError}</div> : null}
                  {slackStatus ? (
                    <div className="module-alert module-alert--success">{slackStatus}</div>
                  ) : null}
                  <div className="stack">
                    <label className="label">Slack channel</label>
                    <select
                      className="select"
                      value={slackChannelMode}
                      onChange={(event) => setSlackChannelMode(event.target.value)}
                    >
                      <option value="default">Default channel</option>
                      <option value="custom">Custom channel</option>
                    </select>
                    {slackChannelMode === 'custom' ? (
                      <input
                        className="input"
                        value={slackChannelValue}
                        onChange={(event) => setSlackChannelValue(event.target.value)}
                        placeholder="#general"
                      />
                    ) : null}
                    <label className="label">Slack message</label>
                    <textarea
                      className="textarea"
                      value={slackMessage}
                      onChange={(event) => setSlackMessage(event.target.value)}
                      placeholder="Slack message"
                    />
                    <button
                      className="button"
                      type="button"
                      onClick={handleSendSlack}
                      disabled={sendingSlack || !audienceQuestionnaireLink}
                    >
                      {sendingSlack ? 'Sending…' : 'Send to Slack'}
                    </button>
                  </div>
                </div>
                <div className="module-card">
                  <h3>Share to WhatsApp</h3>
                  {whatsappError ? <div className="module-alert">{whatsappError}</div> : null}
                  {whatsappStatus ? (
                    <div className="module-alert module-alert--success">{whatsappStatus}</div>
                  ) : null}
                  <div className="stack">
                    <label className="label">WhatsApp group</label>
                    <select
                      className="select"
                      value={whatsappGroupId}
                      onChange={(event) => setWhatsappGroupId(event.target.value)}
                    >
                      <option value="">Select WhatsApp group</option>
                      {whatsappGroups.map((group) => (
                        <option key={group.groupId} value={group.groupId}>
                          {group.name}
                        </option>
                      ))}
                    </select>
                    <label className="label">WhatsApp message</label>
                    <textarea
                      className="textarea"
                      value={whatsappMessage}
                      onChange={(event) => setWhatsappMessage(event.target.value)}
                      placeholder="WhatsApp message"
                    />
                    <button
                      className="button"
                      type="button"
                      onClick={handleSendWhatsapp}
                      disabled={sendingWhatsapp || !audienceQuestionnaireLink}
                    >
                      {sendingWhatsapp ? 'Sending…' : 'Send to WhatsApp'}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === 'moderation' && (
        <div className="stack">
          {!activeConvo ? (
            <ActiveConversationRequired
              message="Choose a conversation in Overview to moderate comments."
              onOpenOverview={() => applyActiveTab('overview')}
            />
          ) : (
            <div className="module-card module-card__wide">
              <h3>Review queue</h3>
              {pendingComments.length === 0 ? (
                <p className="muted">No pending comments.</p>
              ) : (
                pendingComments.map((comment) => (
                  <div key={comment.id} className="comment-row">
                    <p>{comment.text}</p>
                  <textarea
                    className="textarea"
                    placeholder="Moderation note (optional)"
                    value={moderationNotes[comment.id] || ''}
                    onChange={(event) =>
                      setModerationNotes((prev) => ({
                        ...prev,
                        [comment.id]: event.target.value,
                      }))
                    }
                  />
                    <div className="table-actions">
                      <button
                        className="button-secondary"
                        type="button"
                      onClick={() =>
                        handleApprove(comment.id, 'approved', {
                          rejectionReason: moderationNotes[comment.id],
                        })
                      }
                      >
                        Approve
                      </button>
                      <button
                        className="button-secondary"
                        type="button"
                      onClick={() =>
                        handleApprove(comment.id, 'rejected', {
                          rejectionReason: moderationNotes[comment.id],
                        })
                      }
                      >
                        Reject
                      </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() =>
                        handleApprove(comment.id, 'rejected', {
                          rejectionReason: moderationNotes[comment.id],
                          copyToSeed: true,
                        })
                      }
                    >
                      Reject + seed
                    </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'insights' && (
        <div className="stack">
          {!activeConvo ? (
            <ActiveConversationRequired
              message="Choose a conversation in Overview to run insights."
              onOpenOverview={() => applyActiveTab('overview')}
            />
          ) : (
            <div className="module-card module-card__wide">
              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h4>Conversation in focus</h4>
                    <p className="muted">{activeConvo?.topic || 'Untitled conversation'}</p>
                  </div>
                  <span className="pill">{activeConvo?.is_open ? 'Open' : 'Closed'}</span>
                </div>
                <div className="module-footer">
                  <span>
                    <strong>ID:</strong> {activeConvo?.id || activeId}
                  </span>
                </div>
              </div>
              <div className="filter-row">
                <button className="button" type="button" onClick={handleRunAnalysis}>
                  Run analysis
                </button>
                <button className="button-secondary" type="button" onClick={handleLoadReport}>
                  Load report
                </button>
              <button
                className="button-secondary"
                type="button"
                onClick={handleLoadStats}
                disabled={loadingStats}
              >
                {loadingStats ? 'Refreshing stats…' : 'Refresh stats'}
              </button>
              <button
                className="button-secondary"
                type="button"
                onClick={handleDownloadExport}
                disabled={exporting}
              >
                {exporting ? 'Preparing export…' : 'Download export'}
              </button>
              </div>
              {reportError ? <div className="module-alert">{reportError}</div> : null}
            {statsError ? <div className="module-alert">{statsError}</div> : null}
            {exportStatus ? (
              <div className="module-alert module-alert--success">{exportStatus}</div>
            ) : null}
            {stats || report ? (
              <div className="stack report-stack">
                <div className="report-header">
                  <div>
                    <h4>Key insights</h4>
                    <p className="muted">Live participation signals and report totals.</p>
                    {report && activeConvo?.min_votes_for_inclusion ? (
                      <p className="muted">
                        Inclusion threshold: {activeConvo.min_votes_for_inclusion} votes per
                        statement.
                      </p>
                    ) : null}
                  </div>
                  {report ? (
                    <span className="pill">Report loaded</span>
                  ) : stats ? (
                    <span className="pill">Live</span>
                  ) : null}
                </div>
                <div className="report-metrics">
                  {stats ? (
                    <>
                      <div className="report-metric">
                        <span>Views</span>
                        <strong>{stats.views}</strong>
                        <span className="muted">Survey page visits</span>
                      </div>
                      <div className="report-metric">
                        <span>Voters</span>
                        <strong>{stats.voters}</strong>
                        <span className="muted">Participants who voted</span>
                      </div>
                      <div className="report-metric">
                        <span>Commenters</span>
                        <strong>{stats.commenters}</strong>
                        <span className="muted">Unique comment authors</span>
                      </div>
                      <div className="report-metric">
                        <span>Votes per voter</span>
                        <strong>{stats.votes_per_participant}</strong>
                        <span className="muted">Average depth</span>
                      </div>
                    </>
                  ) : null}
                  {report ? (
                    <>
                      <div className="report-metric">
                        <span>Participants</span>
                        <strong>{report.metrics.total_participants}</strong>
                        <span className="muted">Active in this survey</span>
                      </div>
                      <div className="report-metric">
                        <span>Statements</span>
                        <strong>{report.metrics.total_comments}</strong>
                        <span className="muted">Included in analysis</span>
                      </div>
                      <div className="report-metric">
                        <span>Votes</span>
                        <strong>{report.metrics.total_votes}</strong>
                        <span className="muted">Total cast</span>
                      </div>
                      <div className="report-metric">
                        <span>Potential agreement</span>
                        <strong>{report.potential_agreements?.length || 0}</strong>
                        <span className="muted">Shared topics</span>
                      </div>
                    </>
                  ) : null}
                </div>
                <div className="module-card report-card">
                  <div className="card-header">
                    <div>
                      <h4>Statement discussion</h4>
                      <p className="muted">
                        Each statement card has its own comments directly below it.
                      </p>
                    </div>
                  </div>
                  <div className="stack">
                    {activeConvo?.is_open === false ? (
                      <div className="module-alert">
                        Conversation is closed. Reopen it in Overview to add statement comments or reactions.
                      </div>
                    ) : null}
                    {discussionStatementOptions.length === 0 ? (
                      <p className="muted">No statements available yet. Run analysis first.</p>
                    ) : (
                      discussionStatementOptions.map((statement) => {
                        const discussion = getDiscussionStateForStatement(statement.id)
                        return (
                          <article className="module-card" key={`statement-discussion-${statement.id}`}>
                            <div className="card-header">
                              <div>
                                <h4>{truncateText(statement.text, 120)}</h4>
                                <p className="muted">Statement ID: {statement.id}</p>
                              </div>
                              <div className="filter-row">
                                <span className="pill">{discussion.comments.length} comments</span>
                                <button
                                  className="button-secondary"
                                  type="button"
                                  onClick={() => loadStatementDiscussionComments(statement.id)}
                                  disabled={discussion.loading}
                                >
                                  {discussion.loading ? 'Refreshing…' : 'Refresh'}
                                </button>
                              </div>
                            </div>
                            {discussion.error ? <div className="module-alert">{discussion.error}</div> : null}
                            <div className="module-footer">
                              <span>
                                <strong>Participation:</strong> {statement.participation || 0}
                              </span>
                              <span>
                                <strong>Agreement:</strong>{' '}
                                {Math.round(Number(statement.agreement_ratio || 0) * 100)}%
                              </span>
                              <span>
                                <strong>Consensus:</strong>{' '}
                                {Math.round(Number(statement.consensus_score || 0) * 100)}
                              </span>
                              <span>
                                <strong>Polarity:</strong>{' '}
                                {Math.round(Number(statement.polarity_score || 0) * 100)}
                              </span>
                            </div>
                            {discussion.comments.length === 0 ? (
                              <p className="muted">No comments yet for this statement.</p>
                            ) : (
                              discussion.comments.map((item) => (
                                <div className="module-card" key={item.id}>
                                  <p>{item.text}</p>
                                  <div className="module-footer">
                                    <span className="muted">{item.created_at || 'Live'}</span>
                                    <span>
                                      <strong>Like</strong> {item.like_count || 0}
                                    </span>
                                    <span>
                                      <strong>Agree</strong> {item.agree_count || 0}
                                    </span>
                                    <span>
                                      <strong>Disagree</strong> {item.disagree_count || 0}
                                    </span>
                                    <span>
                                      <strong>Insightful</strong> {item.insightful_count || 0}
                                    </span>
                                    {item.my_reaction ? (
                                      <span>
                                        <strong>Your reaction:</strong> {item.my_reaction}
                                      </span>
                                    ) : null}
                                  </div>
                                  <div className="filter-row">
                                    <button
                                      className="button-secondary"
                                      type="button"
                                      onClick={() =>
                                        handleReactToStatementDiscussionComment(statement.id, item.id, 'like')
                                      }
                                      disabled={discussion.reactionBusyId === item.id || activeConvo?.is_open === false}
                                    >
                                      👍 Like
                                    </button>
                                    <button
                                      className="button-secondary"
                                      type="button"
                                      onClick={() =>
                                        handleReactToStatementDiscussionComment(statement.id, item.id, 'agree')
                                      }
                                      disabled={discussion.reactionBusyId === item.id || activeConvo?.is_open === false}
                                    >
                                      ✅ Agree
                                    </button>
                                    <button
                                      className="button-secondary"
                                      type="button"
                                      onClick={() =>
                                        handleReactToStatementDiscussionComment(statement.id, item.id, 'disagree')
                                      }
                                      disabled={discussion.reactionBusyId === item.id || activeConvo?.is_open === false}
                                    >
                                      ❌ Disagree
                                    </button>
                                    <button
                                      className="button-secondary"
                                      type="button"
                                      onClick={() =>
                                        handleReactToStatementDiscussionComment(statement.id, item.id, 'insightful')
                                      }
                                      disabled={discussion.reactionBusyId === item.id || activeConvo?.is_open === false}
                                    >
                                      💡 Insightful
                                    </button>
                                  </div>
                                </div>
                              ))
                            )}
                            <div className="stack">
                              <textarea
                                className="textarea"
                                value={discussion.draft}
                                onChange={(event) =>
                                  setDiscussionDraftByStatement((prev) => ({
                                    ...prev,
                                    [statement.id]: event.target.value,
                                  }))
                                }
                                placeholder="Write a comment on this statement"
                                disabled={activeConvo?.is_open === false}
                              />
                              <button
                                className="button"
                                type="button"
                                onClick={() => handleCreateStatementDiscussionComment(statement.id)}
                                disabled={discussion.saving || activeConvo?.is_open === false}
                              >
                                {discussion.saving ? 'Posting…' : 'Post comment'}
                              </button>
                            </div>
                          </article>
                        )
                      })
                    )}
                  </div>
                </div>
              </div>
            ) : null}

              {(statsSeries || reportCharts || topicMap || vennData) ? (
                <details className="dashboard-detail">
                  <summary>Charts & visualizations</summary>
                  <div className="dashboard-detail__body">
                    {statsSeries ? (
                      <div className="report-chart-row">
                          <div className="module-card report-card">
                            <h4>Votes over time</h4>
                            <div className="chart-frame chart-frame--short report-chart">
                              <Line
                                data={{
                                  labels: statsSeries.votes.labels,
                                  datasets: [
                                    {
                                      label: 'Votes',
                                      data: statsSeries.votes.data,
                                      borderColor: '#2563eb',
                                      backgroundColor: 'rgba(37, 99, 235, 0.2)',
                                      tension: 0.3,
                                    },
                                  ],
                                }}
                                options={lineOptions}
                              />
                            </div>
                          </div>
                          <div className="module-card report-card">
                            <h4>Comments over time</h4>
                            <div className="chart-frame chart-frame--short report-chart">
                              <Line
                                data={{
                                  labels: statsSeries.comments.labels,
                                  datasets: [
                                    {
                                      label: 'Comments',
                                      data: statsSeries.comments.data,
                                      borderColor: '#16a34a',
                                      backgroundColor: 'rgba(22, 163, 74, 0.2)',
                                      tension: 0.3,
                                    },
                                  ],
                                }}
                                options={lineOptions}
                              />
                            </div>
                          </div>
                        </div>
                    ) : null}
                    {reportCharts ? (
                      <div className="report-chart-row">
                    <div className="module-card report-card">
                      <h4>Vote sentiment</h4>
                      <div className="chart-frame chart-frame--short report-chart">
                        <Doughnut
                          data={{
                            labels: ['Agree', 'Disagree', 'Pass'],
                            datasets: [
                              {
                                data: [
                                  reportCharts?.voteTotals?.agree || 0,
                                  reportCharts?.voteTotals?.disagree || 0,
                                  reportCharts?.voteTotals?.pass || 0,
                                ],
                                backgroundColor: ['#22c55e', '#ef4444', '#94a3b8'],
                                borderWidth: 0,
                              },
                            ],
                          }}
                          options={doughnutOptions}
                        />
                      </div>
                      <p className="muted">Share of agree, disagree, and pass votes.</p>
                    </div>

                    <div className="module-card report-card">
                      <h4>Cluster sizes</h4>
                      <div className="chart-frame chart-frame--short report-chart">
                        <Bar
                          data={{
                            labels: reportCharts?.clusterLabels || [],
                            datasets: [
                              {
                                label: 'Participants',
                                data: reportCharts?.clusterSizes || [],
                                backgroundColor: '#60a5fa',
                                borderRadius: 6,
                              },
                            ],
                          }}
                          options={verticalBarOptions}
                        />
                      </div>
                      <p className="muted">Distribution of participants by cluster.</p>
                    </div>

                    <div className="module-card report-card">
                      <div className="card-header">
                        <div>
                          <h4>{useMajority ? 'Majority statements' : 'Top consensus statements'}</h4>
                          <p className="muted">
                            {useMajority
                              ? 'Statements with strong majority agreement.'
                              : 'Statements with the strongest consensus.'}
                          </p>
                        </div>
                        <div className="filter-row">
                          <button
                            className={useMajority ? 'button-secondary' : 'button'}
                            type="button"
                            onClick={() => setStatementMode('consensus')}
                          >
                            Consensus
                          </button>
                          <button
                            className={useMajority ? 'button' : 'button-secondary'}
                            type="button"
                            onClick={() => setStatementMode('majority')}
                          >
                            Majority
                          </button>
                        </div>
                      </div>
                      <div className="chart-frame chart-frame--tall report-chart">
                        <Bar
                          data={{
                            labels: statementItems.map((row) => truncateText(row.text, 56)),
                            datasets: [
                              {
                                label: statementScoreLabel,
                                data: statementItems.map((row) =>
                                  useMajority
                                    ? Number(row?.agreement_ratio || 0)
                                    : Number(row?.consensus_score || 0),
                                ),
                                backgroundColor: useMajority ? '#38bdf8' : '#34d399',
                                borderRadius: 6,
                              },
                            ],
                          }}
                          options={buildStatementChartOptions(statementItems, statementScoreLabel)}
                        />
                      </div>
                    </div>

                    <div className="module-card report-card">
                      <h4>Top polarizing statements</h4>
                      <div className="chart-frame chart-frame--tall report-chart">
                        <Bar
                          data={{
                            labels: (reportCharts?.polarizingTop || []).map((row) =>
                              truncateText(row.text, 56),
                            ),
                            datasets: [
                              {
                                label: 'Polarity score',
                                data: (reportCharts?.polarizingTop || []).map((row) =>
                                  Number(row?.polarity_score || 0),
                                ),
                                backgroundColor: '#f97316',
                                borderRadius: 6,
                              },
                            ],
                          }}
                          options={buildStatementChartOptions(
                            reportCharts?.polarizingTop || [],
                            'Polarity score',
                          )}
                        />
                      </div>
                      <p className="muted">Statements that split opinion the most.</p>
                    </div>

                      </div>
                    ) : null}
                    {topicMap ? (
                      <div className="stack">
                        <div className="report-visual-grid">
                          <div className="module-card report-card polis-card">
                            <div className="polis-card__header">
                              <h4>Topic map</h4>
                              <span className="pill">Topic map</span>
                            </div>
                            <p className="muted">Layer 0 interactive visualization</p>
                            <div className="polis-map">
                              <svg viewBox="0 0 360 260" xmlns="http://www.w3.org/2000/svg">
                                <rect
                                  x="8"
                                  y="8"
                                  width="344"
                                  height="244"
                                  rx="14"
                                  fill="#ffffff"
                                  stroke="#E2E8F0"
                                />
                                {topicMap.points.map((point, idx) => (
                                  <circle
                                    key={`${point.clusterId}-${idx}`}
                                    cx={point.x * 360}
                                    cy={point.y * 260}
                                    r="2.4"
                                    fill={clusterColor(
                                      point.clusterId,
                                      topicMap.colorById?.[point.clusterId] || idx + 1,
                                    )}
                                    opacity="0.75"
                                  />
                                ))}
                                {topicMap.clusters.map((cluster) => (
                                  <text
                                    key={`label-${cluster.id}`}
                                    x={cluster.centerX * 360}
                                    y={cluster.centerY * 260}
                                    textAnchor="middle"
                                    fontSize="10"
                                    fill="#334155"
                                  >
                                    {cluster.label}
                                  </text>
                                ))}
                              </svg>
                            </div>
                            <p className="muted">
                              Go beyond opinion groups with topic maps and cluster overlays.
                            </p>
                          </div>
                          {statementLandscape ? (
                            <div className="module-card report-card polis-card">
                              <div className="polis-card__header">
                                <h4>Statement landscape</h4>
                                <span className="pill">Consensus vs divisive</span>
                              </div>
                              <div className="polis-map">
                                <svg viewBox="0 0 360 260" xmlns="http://www.w3.org/2000/svg">
                                  <rect
                                    x="8"
                                    y="8"
                                    width="344"
                                    height="244"
                                    rx="14"
                                    fill="#ffffff"
                                    stroke="#E2E8F0"
                                  />
                                  <line x1="36" y1="220" x2="320" y2="220" stroke="#E2E8F0" />
                                  <line x1="36" y1="220" x2="36" y2="28" stroke="#E2E8F0" />
                                  {statementLandscape.points.map((point) => {
                                    const x = 36 + Math.min(1, Math.max(0, point.polarity)) * 284
                                    const y =
                                      220 - Math.min(1, Math.max(0, point.consensus)) * 192
                                    const size = 3 + Math.min(5, point.participation / 12)
                                    const color =
                                      point.polarity > point.consensus
                                        ? '#f97316'
                                        : point.consensus > 0.35
                                          ? '#22c55e'
                                          : '#94a3b8'
                                    return (
                                      <circle
                                        key={point.id}
                                        cx={x}
                                        cy={y}
                                        r={size}
                                        fill={color}
                                        opacity="0.75"
                                      />
                                    )
                                  })}
                                  {statementLandscape.labels.map((point) => {
                                    const x = 36 + Math.min(1, Math.max(0, point.polarity)) * 284
                                    const y =
                                      220 - Math.min(1, Math.max(0, point.consensus)) * 192
                                    return (
                                      <text
                                        key={`label-${point.id}`}
                                        x={x}
                                        y={y - 6}
                                        textAnchor="middle"
                                        fontSize="9"
                                        fill="#0f172a"
                                      >
                                        {truncateText(point.text, 28)}
                                      </text>
                                    )
                                  })}
                                  <text x="36" y="236" fontSize="9" fill="#64748b">
                                    Divisive →
                                  </text>
                                  <text x="10" y="32" fontSize="9" fill="#64748b">
                                    ↑ Consensus
                                  </text>
                                </svg>
                              </div>
                              <p className="muted">
                                See which statements build consensus versus spark polarization.
                              </p>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                    {vennData ? (
                      <div className="report-visual-grid">
                        <div className="module-card report-card">
                          <h4>Shared agreement topics</h4>
                            {vennSelected.length < 2 ? (
                              <p className="muted">
                                Need at least two clusters with agreement topics.
                              </p>
                            ) : !vennData.hasOverlap ? (
                              <p className="muted">No overlapping agreement topics yet.</p>
                            ) : (
                              <div className="venn-wrap">
                                <svg viewBox="0 0 360 260" className="venn-diagram">
                                  <rect x="0" y="0" width="360" height="260" rx="16" fill="#f8fafc" />
                                  {vennSelected.length >= 2 ? (
                                    <>
                                      <circle
                                        cx={vennSelected.length >= 3 ? 140 : 150}
                                        cy={vennSelected.length >= 3 ? 120 : 130}
                                        r="90"
                                        fill={clusterColor(vennSelected[0]?.cluster_id, 1)}
                                        opacity="0.28"
                                      />
                                      <circle
                                        cx={vennSelected.length >= 3 ? 220 : 210}
                                        cy={vennSelected.length >= 3 ? 120 : 130}
                                        r="90"
                                        fill={clusterColor(vennSelected[1]?.cluster_id, 2)}
                                        opacity="0.28"
                                      />
                                    </>
                                  ) : null}
                                  {vennSelected.length >= 3 ? (
                                    <circle
                                      cx="180"
                                      cy="200"
                                      r="90"
                                      fill={clusterColor(vennSelected[2]?.cluster_id, 3)}
                                      opacity="0.28"
                                    />
                                  ) : null}

                                  {vennSelected.length >= 2 ? (
                                    <>
                                      <text x="110" y="130" textAnchor="middle" className="venn-count">
                                        {vennAOnly.size}
                                      </text>
                                      <text x="250" y="130" textAnchor="middle" className="venn-count">
                                        {vennBOnly.size}
                                      </text>
                                      <text x="180" y="130" textAnchor="middle" className="venn-count">
                                        {vennSelected.length >= 3 ? vennABOnly.size : vennAB.size}
                                      </text>
                                    </>
                                  ) : null}
                                  {vennSelected.length >= 3 ? (
                                    <>
                                      <text x="180" y="220" textAnchor="middle" className="venn-count">
                                        {vennCOnly.size}
                                      </text>
                                      <text x="145" y="175" textAnchor="middle" className="venn-count">
                                        {vennACOnly.size}
                                      </text>
                                      <text x="215" y="175" textAnchor="middle" className="venn-count">
                                        {vennBCOnly.size}
                                      </text>
                                      <text x="180" y="155" textAnchor="middle" className="venn-count">
                                        {vennABC.size}
                                      </text>
                                    </>
                                  ) : null}
                                </svg>
                                <div className="venn-legend">
                                  {vennSelected.map((item, idx) => (
                                    <span className="venn-legend__item" key={item.cluster_id || idx}>
                                      <span
                                        className="venn-legend__dot"
                                        style={{
                                          background: clusterColor(item.cluster_id, idx + 1),
                                        }}
                                      />
                                      {item.cluster_id} ({item.size || 0})
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </details>
              ) : null}
            </div>
          )}
        </div>
      )}


      <div className="module-footer">
        <span>Backend scope:</span>
        <strong>Survey API</strong>
      </div>
    </section>
  )
}
