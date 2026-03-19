import { useEffect, useMemo, useState } from 'react'
import { Bar, Doughnut } from 'react-chartjs-2'
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js'
import { getJson, requestJson } from '../../services/api'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

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

const formatPercent = (value) => `${Math.round((Number(value) || 0) * 100)}%`

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

export function DeliberationPage({
  t,
  activeTabOverride,
  onTabChange,
  showTabs = true,
}) {
  const translate = t || ((key, vars) => key)
  const [activeTab, setActiveTab] = useState('overview')
  const applyActiveTab = (nextTab) => {
    if (!nextTab) return
    setActiveTab(nextTab)
    if (onTabChange) onTabChange(nextTab)
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
    allowCommentSubmission: true,
    allowViz: true,
    moderationRequired: false,
    isOpen: true,
  })
  const [updateForm, setUpdateForm] = useState(null)
  const [seedText, setSeedText] = useState('')
  const [simulateForm, setSimulateForm] = useState({
    participants: 120,
    votesPerParticipant: 20,
    seed: 42,
  })
  const [report, setReport] = useState(null)
  const [reportError, setReportError] = useState('')
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
  const [sendingSlack, setSendingSlack] = useState(false)
  const [whatsappGroups, setWhatsappGroups] = useState([])
  const [whatsappGroupId, setWhatsappGroupId] = useState('')
  const [whatsappMessage, setWhatsappMessage] = useState('')
  const [whatsappError, setWhatsappError] = useState('')
  const [whatsappStatus, setWhatsappStatus] = useState('')
  const [sendingWhatsapp, setSendingWhatsapp] = useState(false)
  const [polisSiteId, setPolisSiteId] = useState('polis_site_id_dZO8TFLSfUGNe651NN')
  const [polisPageId, setPolisPageId] = useState('PAGE_ID')
  const [polisConversationId, setPolisConversationId] = useState('')

  useEffect(() => {
    if (activeTabOverride && activeTabOverride !== activeTab) {
      setActiveTab(activeTabOverride)
    }
  }, [activeTabOverride, activeTab])

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
    const clusterSummaries = report.cluster_summaries || []
    return {
      voteTotals,
      consensusTop,
      polarizingTop,
      clusterLabels: clusterSummaries.map((row) => row.cluster_id),
      clusterSizes: clusterSummaries.map((row) => Number(row?.size || 0)),
    }
  }, [report])

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
          summary,
        }
      })
      .sort((a, b) => b.size - a.size)
  }, [report])

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

  const verticalBarOptions = useMemo(
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
    if (!activeId) {
      setActiveConvo(null)
      setApprovedComments([])
      setPendingComments([])
      return
    }
    Promise.all([
      getJson(`/conversations/${activeId}`),
      getJson(`/conversations/${activeId}/comments?status=approved`),
      getJson(`/conversations/${activeId}/comments?status=pending`),
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
          moderationRequired: convo.moderation_required,
          isOpen: convo.is_open,
        })
      })
      .catch((err) =>
        setConvoError(err.message || 'Unable to load conversation data.'),
      )
  }, [activeId])

  const buildQuestionnaireLink = (questionnaireType, view) => {
    if (!activeId) return ''
    const url = new URL(window.location.href)
    url.search = ''
    url.searchParams.set('questionnaire', questionnaireType)
    url.searchParams.set('conversation_id', activeId)
    if (view) url.searchParams.set('view', view)
    return url.toString()
  }

  const questionnaireLink = useMemo(
    () => buildQuestionnaireLink('deliberation', 'participant'),
    [activeId],
  )

  const adminQuestionnaireLink = useMemo(
    () => buildQuestionnaireLink('deliberation_admin', 'admin'),
    [activeId],
  )

  useEffect(() => {
    if (!activeId || !questionnaireLink) {
      setSlackMessage('')
      setWhatsappMessage('')
      return
    }
    const message = `Survey questionnaire: ${
      activeConvo?.topic || 'Conversation'
    }\n\n${questionnaireLink}`
    setSlackMessage(message)
    setWhatsappMessage(message)
    setSlackStatus('')
    setSlackError('')
    setWhatsappStatus('')
    setWhatsappError('')
  }, [activeId, questionnaireLink, activeConvo?.topic])

  const handleSendSlack = async () => {
    if (!questionnaireLink) {
      setSlackError('Select a conversation first.')
      return
    }
    const message =
      slackMessage ||
      `Survey questionnaire: ${activeConvo?.topic || 'Conversation'}\n\n${questionnaireLink}`
    setSlackError('')
    setSlackStatus('')
    setSendingSlack(true)
    try {
      await requestJson('/crm/slack/send', {
        method: 'POST',
        payload: {
          message,
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
    if (!questionnaireLink) {
      setWhatsappError('Select a conversation first.')
      return
    }
    if (!whatsappGroupId) {
      setWhatsappError('Select a WhatsApp group.')
      return
    }
    const message =
      whatsappMessage ||
      `Survey questionnaire: ${activeConvo?.topic || 'Conversation'}\n\n${questionnaireLink}`
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

  const handleCreateConversation = async () => {
    if (!createForm.topic.trim()) {
      setConvoError('Topic must be at least 3 characters.')
      return
    }
    setConvoError('')
    try {
      const created = await requestJson('/conversations', {
        method: 'POST',
        payload: {
          topic: createForm.topic.trim(),
          description: createForm.description.trim(),
          allow_comment_submission: createForm.allowCommentSubmission,
          allow_viz: createForm.allowViz,
          moderation_required: createForm.moderationRequired,
          is_open: createForm.isOpen,
        },
      })
      setCreateForm({
        topic: '',
        description: '',
        allowCommentSubmission: true,
        allowViz: true,
        moderationRequired: false,
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
          moderation_required: updateForm.moderationRequired,
          is_open: updateForm.isOpen,
        },
      })
      loadConversations()
    } catch (err) {
      setConvoError(err.message || 'Unable to update conversation.')
    }
  }

  const handleSeedComments = async () => {
    if (!activeId) return
    const comments = seedText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
    if (!comments.length) {
      setConvoError('Add at least one comment.')
      return
    }
    setConvoError('')
    try {
      await requestJson(`/conversations/${activeId}/seed-comments:bulk`, {
        method: 'POST',
        payload: { comments },
      })
      setSeedText('')
    } catch (err) {
      setConvoError(err.message || 'Unable to seed comments.')
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

  const handleApprove = async (commentId, status) => {
    try {
      await requestJson(`/comments/${commentId}`, {
        method: 'PATCH',
        payload: { status },
      })
      const pending = await getJson(
        `/conversations/${activeId}/comments?status=pending`,
      )
      setPendingComments(Array.isArray(pending) ? pending : [])
    } catch (err) {
      setConvoError(err.message || 'Unable to update comment.')
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
      const approved = await getJson(
        `/conversations/${activeId}/comments?status=approved`,
      )
      setApprovedComments(Array.isArray(approved) ? approved : [])
    } catch (err) {
      setConvoError(err.message || 'Unable to submit comment.')
    }
  }

  const activeConversations = conversations.filter((convo) => convo.is_open)
  const closedConversations = conversations.filter((convo) => !convo.is_open)

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
  return (
    <section className="module">
      <details className="dashboard-detail">
        <summary>Survey stats</summary>
        <div className="dashboard-detail__body">
          <div className="module-header__meta">
            <div className="module-header__metric">
              <span>Conversations</span>
              <strong>{conversations.length}</strong>
            </div>
            <div className="module-header__metric">
              <span>Approved</span>
              <strong>{approvedComments.length}</strong>
            </div>
            <div className="module-header__metric">
              <span>Pending</span>
              <strong>{pendingComments.length}</strong>
            </div>
          </div>
        </div>
      </details>

      {convoError ? <div className="module-alert">{convoError}</div> : null}

      {showTabs ? (
        <div className="subtabs">
          {[
            { id: 'overview', label: translate('deliberation.tabs.overview') },
            { id: 'setup', label: translate('deliberation.tabs.setup') },
            { id: 'distribute', label: translate('deliberation.tabs.distribute') },
            { id: 'insights', label: translate('deliberation.tabs.insights') },
            { id: 'moderation', label: translate('deliberation.tabs.moderation') },
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
          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Quick start</h3>
                <p className="muted">
                  Set up a conversation, share the link, then review the results.
                </p>
              </div>
            </div>
            <ul className="compact-list">
              <li>
                <span>Step 1</span>
                <strong>Create a conversation and add starter statements.</strong>
              </li>
              <li>
                <span>Step 2</span>
                <strong>Share the participant link with supporters.</strong>
              </li>
              <li>
                <span>Step 3</span>
                <strong>Run analysis and review consensus insights.</strong>
              </li>
            </ul>
            <div className="filter-row">
              <button className="button" type="button" onClick={() => applyActiveTab('setup')}>
                Set up
              </button>
              <button
                className="button-secondary"
                type="button"
                onClick={() => applyActiveTab('distribute')}
              >
                Share link
              </button>
              <button
                className="button-secondary"
                type="button"
                onClick={() => applyActiveTab('insights')}
              >
                View insights
              </button>
            </div>
          </div>

          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Active conversation</h3>
                <p className="muted">This is the survey link you are sharing.</p>
              </div>
              {activeConvo ? (
                <span className="pill">{activeConvo.is_open ? 'Open' : 'Closed'}</span>
              ) : null}
            </div>
            {activeConvo ? (
              <div className="stack">
                <div>
                  <strong>{activeConvo.topic}</strong>
                  {activeConvo.description ? (
                    <p className="muted">{activeConvo.description}</p>
                  ) : (
                    <p className="muted">Add a short description to guide participants.</p>
                  )}
                </div>
                <div>
                  <label className="label">Participant link</label>
                  <input className="input" value={questionnaireLink} readOnly />
                </div>
                <div className="filter-row">
                  <button
                    className="button"
                    type="button"
                    onClick={() => applyActiveTab('distribute')}
                  >
                    Share link
                  </button>
                  <a
                    className="button-secondary"
                    href={questionnaireLink}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open participant view
                  </a>
                </div>
              </div>
            ) : (
              <p className="muted">Select a conversation below to activate it.</p>
            )}
          </div>

          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Conversations</h3>
                <p className="muted">Open, close, and select the active conversation.</p>
              </div>
            </div>
            <div className="table">
              <div className="table-row table-head">
                <span>Topic</span>
                <span>Status</span>
                <span>Action</span>
                <span>Set active</span>
              </div>
              {activeConversations.map((convo) => (
                <div className="table-row" key={convo.id}>
                  <span>{convo.topic}</span>
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
                      disabled={activeId === convo.id}
                    >
                      {activeId === convo.id ? 'Active' : 'Use'}
                    </button>
                  </div>
                </div>
              ))}
              {closedConversations.map((convo) => (
                <div className="table-row" key={convo.id}>
                  <span>{convo.topic}</span>
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
                      disabled={activeId === convo.id}
                    >
                      {activeId === convo.id ? 'Active' : 'Use'}
                    </button>
                  </div>
                </div>
              ))}
              {conversations.length === 0 && (
                <div className="table-row empty">No conversations yet.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'setup' && (
        <div className="stack">
          <details className="dashboard-detail">
            <summary>Setup checklist</summary>
            <div className="dashboard-detail__body">
              <ul className="compact-list">
                <li>
                  <span>Define the conversation</span>
                  <strong>Topic, description, settings</strong>
                </li>
                <li>
                  <span>Add starter statements</span>
                  <strong>One per line or import CSV</strong>
                </li>
                <li>
                  <span>Share the participant link</span>
                  <strong>Invite supporters and members</strong>
                </li>
              </ul>
            </div>
          </details>

          <div className="module-grid">
            <div className="module-card">
              <h3>Create a conversation</h3>
              <p className="muted">Give the survey a clear topic and description.</p>
              <input
                className="input"
                placeholder="Topic"
                value={createForm.topic}
                onChange={(event) =>
                  setCreateForm((prev) => ({ ...prev, topic: event.target.value }))
                }
              />
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
                  checked={createForm.moderationRequired}
                  onChange={(event) =>
                    setCreateForm((prev) => ({
                      ...prev,
                      moderationRequired: event.target.checked,
                    }))
                  }
                />
                Moderation required
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
              <button className="button" type="button" onClick={handleCreateConversation}>
                Create conversation
              </button>
            </div>

            <div className="module-card">
              <h3>Edit active conversation</h3>
              <p className="muted">Adjust the topic, description, and settings.</p>
              {updateForm ? (
                <div className="stack">
                  <input
                    className="input"
                    value={updateForm.topic}
                    onChange={(event) =>
                      setUpdateForm((prev) => ({ ...prev, topic: event.target.value }))
                    }
                  />
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
                      checked={updateForm.moderationRequired}
                      onChange={(event) =>
                        setUpdateForm((prev) => ({
                          ...prev,
                          moderationRequired: event.target.checked,
                        }))
                      }
                    />
                    Moderation required
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
                  <button className="button" type="button" onClick={handleUpdateConversation}>
                    Save settings
                  </button>
                </div>
              ) : (
                <p className="muted">Select a conversation in Overview.</p>
              )}
            </div>

            <div className="module-card">
              <h3>Add starter statements</h3>
              <p className="muted">One statement per line. Participants vote on these.</p>
              <textarea
                className="textarea"
                placeholder="One comment per line"
                value={seedText}
                onChange={(event) => setSeedText(event.target.value)}
              />
              <button className="button" type="button" onClick={handleSeedComments}>
                Add seed comments
              </button>
            </div>
          </div>

          <details className="dashboard-detail">
            <summary>Advanced setup</summary>
            <div className="dashboard-detail__body">
              <p className="muted">
                Optional tools for importing datasets or generating demo votes.
              </p>
              <ul className="compact-list">
                <li>
                  <span>Import votes and comments</span>
                  <strong>CSV upload</strong>
                </li>
                <li>
                  <span>Seed statements quickly</span>
                  <strong>Download templates</strong>
                </li>
                <li>
                  <span>Run analysis after import</span>
                  <strong>Optional</strong>
                </li>
              </ul>

              <div className="module-grid">
                <div className="module-card">
                  <h3>Generate demo votes</h3>
                  <p className="muted">Use mock participants to preview analytics.</p>
                  <input
                    className="input"
                    type="number"
                    value={simulateForm.participants}
                    onChange={(event) =>
                      setSimulateForm((prev) => ({
                        ...prev,
                        participants: event.target.value,
                      }))
                    }
                  />
                  <input
                    className="input"
                    type="number"
                    value={simulateForm.votesPerParticipant}
                    onChange={(event) =>
                      setSimulateForm((prev) => ({
                        ...prev,
                        votesPerParticipant: event.target.value,
                      }))
                    }
                  />
                  <input
                    className="input"
                    type="number"
                    value={simulateForm.seed}
                    onChange={(event) =>
                      setSimulateForm((prev) => ({ ...prev, seed: event.target.value }))
                    }
                  />
                  <button className="button" type="button" onClick={handleSimulateVotes}>
                    Generate votes
                  </button>
                </div>
              </div>

              <div className="module-card module-card__wide">
                <h3>Import data (CSV)</h3>
                <input
                  className="input"
                  type="file"
                  accept=".csv"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) parseCsvFile(file)
                  }}
                />
                <div className="stack">
                  <p className="muted">
                    Required columns: <strong>conversation_id</strong>,{' '}
                    <strong>participant_id</strong>, <strong>comment_id</strong>,{' '}
                    <strong>comment_text</strong>, <strong>is_seed</strong>,{' '}
                    <strong>vote</strong>.
                  </p>
                  <p className="muted">
                    Optional columns: comment_created_at, reaction_created_at, participant_cluster.
                  </p>
                  <p className="muted">
                    Seed comments CSV: <strong>comment_text</strong> column required.
                  </p>
                </div>
                {csvColumns.length ? (
                  <div className="form-grid">
                    <select
                      className="select"
                      value={csvMap.conversation_id || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, conversation_id: event.target.value }))
                      }
                    >
                      <option value="">Conversation ID column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.comment_id || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, comment_id: event.target.value }))
                      }
                    >
                      <option value="">Comment ID column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.participant_id || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, participant_id: event.target.value }))
                      }
                    >
                      <option value="">Participant ID column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.participant_cluster || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, participant_cluster: event.target.value }))
                      }
                    >
                      <option value="">Participant cluster column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.comment_text || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, comment_text: event.target.value }))
                      }
                    >
                      <option value="">Comment text column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.is_seed || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, is_seed: event.target.value }))
                      }
                    >
                      <option value="">Is seed column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.comment_created_at || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, comment_created_at: event.target.value }))
                      }
                    >
                      <option value="">Comment created_at column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.vote || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, vote: event.target.value }))
                      }
                    >
                      <option value="">Vote column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <select
                      className="select"
                      value={csvMap.reaction_created_at || ''}
                      onChange={(event) =>
                        setCsvMap((prev) => ({ ...prev, reaction_created_at: event.target.value }))
                      }
                    >
                      <option value="">Vote created_at column</option>
                      {csvColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : null}
                <div className="filter-row">
                  <select
                    className="select"
                    value={seedCsvColumn}
                    onChange={(event) => setSeedCsvColumn(event.target.value)}
                  >
                    <option value="">Seed comments from column</option>
                    {csvColumns.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                  <input
                    className="input"
                    type="number"
                    min="1"
                    placeholder="Max rows"
                    value={seedCsvLimit}
                    onChange={(event) => setSeedCsvLimit(event.target.value)}
                  />
                  <button className="button-secondary" type="button" onClick={handleSeedFromCsv}>
                    Seed comments
                  </button>
                  <button className="button" type="button" onClick={handleImportDataset}>
                    Import dataset
                  </button>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={runAnalysisAfterImport}
                      onChange={(event) => setRunAnalysisAfterImport(event.target.checked)}
                    />
                    Run analysis after import
                  </label>
                </div>
                {csvStatus ? <p className="muted">{csvStatus}</p> : null}
              </div>
            </div>
          </details>
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

          <div className="module-card module-card__wide">
            <h3>Participant link</h3>
            <p className="muted">This link opens the swipe experience.</p>
            {questionnaireLink ? (
              <div className="stack">
                <input className="input" value={questionnaireLink} readOnly />
                <div className="filter-row">
                  <a
                    className="button"
                    href={questionnaireLink}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open participant view
                  </a>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => applyActiveTab('setup')}
                  >
                    Edit setup
                  </button>
                </div>
              </div>
            ) : (
              <p className="muted">Select a conversation in Overview to generate a link.</p>
            )}
          </div>

          <details className="dashboard-detail">
            <summary>Team channels and admin link</summary>
            <div className="dashboard-detail__body">
              {slackError ? <div className="module-alert">{slackError}</div> : null}
              {slackStatus ? (
                <div className="module-alert module-alert--success">{slackStatus}</div>
              ) : null}
              {whatsappError ? <div className="module-alert">{whatsappError}</div> : null}
              {whatsappStatus ? (
                <div className="module-alert module-alert--success">{whatsappStatus}</div>
              ) : null}
              <div className="stack">
                <div>
                  <label className="label">Admin link</label>
                  <input className="input" value={adminQuestionnaireLink} readOnly />
                </div>
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
                  disabled={sendingSlack || !questionnaireLink}
                >
                  {sendingSlack ? 'Sending…' : 'Send to Slack'}
                </button>
                <div className="card-divider">
                  <h4>WhatsApp share</h4>
                </div>
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
                  disabled={sendingWhatsapp || !questionnaireLink}
                >
                  {sendingWhatsapp ? 'Sending…' : 'Send to WhatsApp'}
                </button>
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
            <summary>Embed on your site</summary>
            <div className="dashboard-detail__body">
              <p className="muted">
                Use a stable page id for persistent conversations, or embed a single
                conversation id.
              </p>
              <div className="stack">
                <input
                  className="input"
                  value={polisPageId}
                  onChange={(event) => setPolisPageId(event.target.value)}
                  placeholder="PAGE_ID"
                />
                <input
                  className="input"
                  value={polisSiteId}
                  onChange={(event) => setPolisSiteId(event.target.value)}
                  placeholder="Polis site id"
                />
                <pre className="code-block">{`<div class="polis" data-page_id="${polisPageId}" data-site_id="${polisSiteId}"></div>
<script async src="https://pol.is/embed.js"></script>`}</pre>
                <div className="card-divider">
                  <h4>Single conversation embed</h4>
                </div>
                <input
                  className="input"
                  value={polisConversationId}
                  onChange={(event) => setPolisConversationId(event.target.value)}
                  placeholder="Polis conversation id"
                />
                <pre className="code-block">{`<div class="polis" data-conversation_id="${polisConversationId || 'CONVERSATION_ID'}"></div>
<script async src="https://pol.is/embed.js"></script>`}</pre>
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
            <summary>Participant identity (XID)</summary>
            <div className="dashboard-detail__body">
              <p className="muted">
                If you have known users, attach an xid to match participants with your data.
              </p>
              <pre className="code-block">{`<div class="polis" data-page_id="${polisPageId}" data-site_id="${polisSiteId}" data-xid="user-123"></div>`}</pre>
              <p className="muted">
                Use a stable id like a GUID. Avoid personal emails unless required.
              </p>
            </div>
          </details>
        </div>
      )}

      {activeTab === 'moderation' && (
        <div className="module-card module-card__wide">
          <h3>Pending comments</h3>
          {pendingComments.length === 0 ? (
            <p className="muted">No pending comments.</p>
          ) : (
            pendingComments.map((comment) => (
              <div key={comment.id} className="comment-row">
                <p>{comment.text}</p>
                <div className="table-actions">
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleApprove(comment.id, 'approved')}
                  >
                    Approve
                  </button>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleApprove(comment.id, 'rejected')}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'insights' && (
        <div className="module-card module-card__wide">
          <div className="filter-row">
            <button className="button" type="button" onClick={handleRunAnalysis}>
              Run analysis
            </button>
            <button className="button-secondary" type="button" onClick={handleLoadReport}>
              Load report
            </button>
          </div>
          {reportError ? <div className="module-alert">{reportError}</div> : null}
          {report ? (
            <div className="stack report-stack">
              <div className="report-header">
                <div>
                  <h4>Survey report</h4>
                  <p className="muted">
                    A plain-language summary of participation, clusters, and top statements.
                  </p>
                </div>
                <span className="pill">Report loaded</span>
              </div>

              <div className="report-metrics">
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
              </div>

              <div className="report-highlights">
                <div className="module-card report-card">
                  <h4>Highlights</h4>
                  <ul className="compact-list">
                    <li>
                      <span>Largest cluster</span>
                      <strong>
                        {clusterCards[0]
                          ? `${clusterCards[0].id} (${formatPercent(clusterCards[0].share)})`
                          : '—'}
                      </strong>
                    </li>
                    <li>
                      <span>Top consensus</span>
                      <strong>
                        {reportCharts?.consensusTop?.[0]
                          ? truncateText(reportCharts.consensusTop[0].text, 70)
                          : '—'}
                      </strong>
                    </li>
                    <li>
                      <span>Top polarizing</span>
                      <strong>
                        {reportCharts?.polarizingTop?.[0]
                          ? truncateText(reportCharts.polarizingTop[0].text, 70)
                          : '—'}
                      </strong>
                    </li>
                  </ul>
                </div>
              </div>

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
                  <h4>Top consensus statements</h4>
                  <div className="chart-frame chart-frame--tall report-chart">
                    <Bar
                      data={{
                        labels: (reportCharts?.consensusTop || []).map((row) =>
                          truncateText(row.text, 56),
                        ),
                        datasets: [
                          {
                            label: 'Consensus score',
                            data: (reportCharts?.consensusTop || []).map((row) =>
                              Number(row?.consensus_score || 0),
                            ),
                            backgroundColor: '#34d399',
                            borderRadius: 6,
                          },
                        ],
                      }}
                      options={buildStatementChartOptions(
                        reportCharts?.consensusTop || [],
                        'Consensus score',
                      )}
                    />
                  </div>
                  <p className="muted">Statements with the strongest agreement.</p>
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

              {topicMap ? (
                <details className="dashboard-detail">
                  <summary>Advanced visualizations</summary>
                  <div className="dashboard-detail__body">
                    <div className="report-visual-grid">
                      <div className="module-card report-card polis-card">
                        <div className="polis-card__header">
                          <h4>Advanced statistical analysis</h4>
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
                                const y = 220 - Math.min(1, Math.max(0, point.consensus)) * 192
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
                                const y = 220 - Math.min(1, Math.max(0, point.consensus)) * 192
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
                    <div className="report-visual-grid">
                      <div className="module-card report-card polis-card">
                        <div className="polis-card__header">
                          <h4>AI-generated reports</h4>
                          <span className="pill">Summary</span>
                        </div>
                        <div className="polis-report-preview">
                          <div className="polis-report-preview__header">
                            <span className="polis-dot" />
                            <span className="polis-dot" />
                            <span className="polis-dot" />
                            <span className="polis-report-preview__title">Report</span>
                          </div>
                          <div className="polis-report-preview__body">
                            <div className="polis-report-preview__block" />
                            <div className="polis-report-preview__block polis-report-preview__block--tall" />
                            <div className="polis-report-preview__block" />
                          </div>
                        </div>
                        <p className="muted">
                          Let Survey and Consensus do the heavy lifting: generate summaries,
                          consensus statements, and topic insights.
                        </p>
                        <ul className="polis-feature-list">
                          <li>Conversation summaries</li>
                          <li>Automated topic reporting</li>
                          <li>Consensus statement identification</li>
                          <li>Divisive comment analysis</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </details>
              ) : null}

              {clusterCards.length || report.potential_agreements?.length || vennData ? (
                <details className="dashboard-detail">
                  <summary>Deep dive insights</summary>
                  <div className="dashboard-detail__body">
                    {clusterCards.length ? (
                      <>
                        <h4>Cluster profiles</h4>
                        <div className="cluster-grid">
                          {clusterCards.map((card) => (
                            <div className="cluster-card" key={card.id}>
                              <div className="cluster-card__header">
                                <strong>{card.id}</strong>
                                <span className="pill">{formatPercent(card.share)}</span>
                              </div>
                              <p className="muted">{card.summary}</p>
                              <div className="cluster-tags">
                                {card.agreeTopics.map((topic) => (
                                  <span
                                    className="cluster-tag cluster-tag--agree"
                                    key={`${card.id}-a-${topic}`}
                                  >
                                    {truncateText(topic, 36)}
                                  </span>
                                ))}
                                {card.disagreeTopics.map((topic) => (
                                  <span
                                    className="cluster-tag cluster-tag--disagree"
                                    key={`${card.id}-d-${topic}`}
                                  >
                                    {truncateText(topic, 36)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : null}

                    {report.potential_agreements?.length ? (
                      <div className="module-card report-card">
                        <h4>Potential agreement topics</h4>
                        <div className="cluster-tags">
                          {report.potential_agreements.map((topic) => (
                            <span className="cluster-tag" key={topic}>
                              {truncateText(sanitizeStatement(topic), 50)}
                            </span>
                          ))}
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
                                      style={{ background: clusterColor(item.cluster_id, idx + 1) }}
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

              <details className="dashboard-detail">
                <summary>Consensus statements ({report.metrics.consensus.length})</summary>
                <div className="dashboard-detail__body">
                  <div className="table">
                    <div className="table-row table-head">
                      <span>Text</span>
                      <span>Consensus</span>
                      <span>Participation</span>
                      <span>Status</span>
                    </div>
                    {report.metrics.consensus.map((row) => (
                      <div
                        className="table-row"
                        key={row.id}
                        title={buildStatementTooltipRows(row).join('\n')}
                      >
                        <span>{sanitizeStatement(row.text)}</span>
                        <span>{row.consensus_score?.toFixed?.(2) ?? row.consensus_score}</span>
                        <span>{row.participation}</span>
                        <span>{row.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </details>

              <details className="dashboard-detail">
                <summary>Polarizing statements ({report.metrics.polarizing.length})</summary>
                <div className="dashboard-detail__body">
                  <div className="table">
                    <div className="table-row table-head">
                      <span>Text</span>
                      <span>Polarity</span>
                      <span>Participation</span>
                      <span>Status</span>
                    </div>
                    {report.metrics.polarizing.map((row) => (
                      <div
                        className="table-row"
                        key={row.id}
                        title={buildStatementTooltipRows(row).join('\n')}
                      >
                        <span>{sanitizeStatement(row.text)}</span>
                        <span>{row.polarity_score?.toFixed?.(2) ?? row.polarity_score}</span>
                        <span>{row.participation}</span>
                        <span>{row.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </details>

            </div>
          ) : (
            <p className="muted">Run analysis or load a report to view insights.</p>
          )}
        </div>
      )}

      {activeTab === 'participate' && (
        <div className="module-card module-card__wide">
          <h3>Participate</h3>
          {questionnaireLink ? (
            <div className="module-alert module-alert--success">
              Use the swipe experience:{' '}
              <a href={questionnaireLink} target="_blank" rel="noreferrer">
                Open participant view
              </a>
            </div>
          ) : null}
          {approvedComments.length === 0 ? (
            <p className="muted">No approved comments yet.</p>
          ) : (
            approvedComments.map((comment) => (
              <div key={comment.id} className="comment-row">
                <p>{comment.text}</p>
                <div className="table-actions">
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleVote(comment.id, 1)}
                  >
                    Agree
                  </button>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleVote(comment.id, -1)}
                  >
                    Disagree
                  </button>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleVote(comment.id, 0)}
                  >
                    Pass
                  </button>
                </div>
              </div>
            ))
          )}
          <div className="card-divider">
            <h4>Submit comment</h4>
          </div>
          <textarea
            className="textarea"
            value={commentText}
            onChange={(event) => setCommentText(event.target.value)}
          />
          <button className="button" type="button" onClick={handleSubmitComment}>
            Submit comment
          </button>
        </div>
      )}

      <div className="module-footer">
        <span>Backend scope:</span>
        <strong>Survey API</strong>
      </div>
    </section>
  )
}
