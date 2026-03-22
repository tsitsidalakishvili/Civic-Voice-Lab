import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, Group, RingProgress, Text } from '@mantine/core'
import { IconAlertTriangle, IconFileSearch, IconShieldCheck, IconUsers } from '@tabler/icons-react'
import { API_BASE, getJson, requestJson } from '../../services/api'
import { CivicStatGrid, InfoBox } from '../../ui'

export function DueDiligencePage({
  t,
  activeTabOverride,
  onTabChange,
  showTabs = true,
}) {
  const translate = t || ((key, vars) => key)
  const [activeTab, setActiveTab] = useState('analysis')
  const applyActiveTab = (nextTab) => {
    if (!nextTab) return
    setActiveTab(nextTab)
    if (onTabChange) onTabChange(nextTab)
  }
  const [summary, setSummary] = useState(null)
  const [crmSummary, setCrmSummary] = useState(null)
  const [competitors, setCompetitors] = useState([])
  const [error, setError] = useState('')
  const [importStatus, setImportStatus] = useState('')
  const [importError, setImportError] = useState('')
  const [importing, setImporting] = useState(false)
  const [name, setName] = useState('')
  const [competitorType, setCompetitorType] = useState('Person')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [subjectName, setSubjectName] = useState('')
  const [subjectType, setSubjectType] = useState('Person')
  const [startMode, setStartMode] = useState('Analysis')
  const [crmMatches, setCrmMatches] = useState([])
  const [competitorMatches, setCompetitorMatches] = useState([])
  const [internalChecksRan, setInternalChecksRan] = useState(false)
  const [analysisNotice, setAnalysisNotice] = useState('')
  const [analysisError, setAnalysisError] = useState('')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [reportHistory, setReportHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [analysisSteps, setAnalysisSteps] = useState([])
  const [analysisProgress, setAnalysisProgress] = useState(0)
  const progressTimerRef = useRef(null)
  const autoPrefillRef = useRef(false)
  const [cases, setCases] = useState([])
  const [casesLoading, setCasesLoading] = useState(false)
  const [casesError, setCasesError] = useState('')
  const [activeCaseId, setActiveCaseId] = useState('')
  const [activeCase, setActiveCase] = useState(null)
  const [caseSubject, setCaseSubject] = useState('')
  const [caseSubjectType, setCaseSubjectType] = useState('Person')
  const [newCaseOwner, setNewCaseOwner] = useState('')
  const [newCaseStatus, setNewCaseStatus] = useState('Draft')
  const [caseOwner, setCaseOwner] = useState('')
  const [caseStatus, setCaseStatus] = useState('Draft')
  const [caseNotice, setCaseNotice] = useState('')
  const [caseCreating, setCaseCreating] = useState(false)
  const [caseSaving, setCaseSaving] = useState(false)
  const [caseTasks, setCaseTasks] = useState([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [taskLabel, setTaskLabel] = useState('')
  const [taskAssignee, setTaskAssignee] = useState('')
  const [taskDueDate, setTaskDueDate] = useState('')
  const [taskError, setTaskError] = useState('')
  const [taskSaving, setTaskSaving] = useState(false)
  const [decisionOutcome, setDecisionOutcome] = useState('Approve')
  const [decisionRationale, setDecisionRationale] = useState('')
  const [decisionSaving, setDecisionSaving] = useState(false)
  const [decisionNotice, setDecisionNotice] = useState('')
  const [decisionError, setDecisionError] = useState('')
  const [debateOpponent, setDebateOpponent] = useState('')
  const [debateTopic, setDebateTopic] = useState('education')
  const [debateYears, setDebateYears] = useState(2)
  const [debateMaxResults, setDebateMaxResults] = useState(25)
  const [debateLoading, setDebateLoading] = useState(false)
  const [debateError, setDebateError] = useState('')
  const [debateResult, setDebateResult] = useState(null)
  const [debateUseDemo, setDebateUseDemo] = useState(false)
  const [debateUseWikipedia, setDebateUseWikipedia] = useState(true)
  const [debateUseGoogle, setDebateUseGoogle] = useState(true)
  const [debateUseLocalMedia, setDebateUseLocalMedia] = useState(true)
  const [useWikidata, setUseWikidata] = useState(true)
  const [useOpenSanctions, setUseOpenSanctions] = useState(true)
  const [useNews, setUseNews] = useState(true)
  const [useDemo, setUseDemo] = useState(true)
  const [ddAppUrl, setDdAppUrl] = useState(
    () => localStorage.getItem('ddAppUrl') || '',
  )
  const [embedApp, setEmbedApp] = useState(false)
  const [gmailTo, setGmailTo] = useState(
    () => localStorage.getItem('ddGmailTo') || '',
  )

  useEffect(() => {
    if (activeTabOverride && activeTabOverride !== activeTab) {
      setActiveTab(activeTabOverride)
    }
  }, [activeTabOverride, activeTab])

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

  useEffect(() => {
    let mounted = true
    Promise.all([
      getJson('/due-diligence/summary'),
      getJson('/due-diligence/competitors?limit=5'),
      getJson('/crm/summary'),
    ])
      .then(([summaryPayload, listPayload, crmSummaryPayload]) => {
        if (!mounted) return
        setSummary(summaryPayload)
        setCompetitors(Array.isArray(listPayload) ? listPayload : [])
        setCrmSummary(crmSummaryPayload)
      })
      .catch((err) => {
        if (!mounted) return
        setError(err.message || 'Unable to load due diligence data.')
      })
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    loadCases()
  }, [])

  const loadCompetitors = () => {
    setError('')
    getJson('/due-diligence/competitors?limit=50')
      .then((payload) => {
        setCompetitors(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setError(err.message || 'Unable to load competitors.')
      })
  }

  const loadCases = () => {
    setCasesError('')
    setCasesLoading(true)
    getJson('/due-diligence/cases?limit=50')
      .then((payload) => {
        setCases(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setCasesError(err.message || 'Unable to load cases.')
      })
      .finally(() => {
        setCasesLoading(false)
      })
  }

  const loadCaseTasks = (caseId) => {
    if (!caseId) {
      setCaseTasks([])
      return
    }
    setTasksLoading(true)
    setTaskError('')
    getJson(`/due-diligence/cases/${caseId}/tasks`)
      .then((payload) => {
        setCaseTasks(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setTaskError(err.message || 'Unable to load case tasks.')
      })
      .finally(() => {
        setTasksLoading(false)
      })
  }

  const refreshActiveCase = (caseId, nextCases = cases) => {
    if (!caseId) {
      setActiveCase(null)
      return
    }
    const found = nextCases.find((item) => item.caseId === caseId)
    if (!found) {
      setActiveCaseId('')
      setActiveCase(null)
      setSubjectName('')
      setSubjectType('Person')
      setCaseStatus('Draft')
      setCaseOwner('')
      return
    }
    setActiveCase(found)
    setSubjectName(found.subject || '')
    setSubjectType(found.subjectType || 'Person')
    setStartMode('Analysis')
    setCaseStatus(found.status || 'Draft')
    setCaseOwner(found.owner || '')
  }

  const setActiveSubject = (nameValue, typeValue, modeValue) => {
    setSubjectName(nameValue)
    setSubjectType(typeValue)
    setStartMode(modeValue)
  }

  const handleSelectCase = (caseId) => {
    setActiveCaseId(caseId || '')
    setCaseNotice('')
    if (!caseId) {
      setActiveCase(null)
      return
    }
    refreshActiveCase(caseId)
  }

  const handleClearCase = () => {
    setActiveCaseId('')
    setActiveCase(null)
    setCaseStatus('Draft')
    setCaseOwner('')
    setCaseNotice('Case selection cleared. You can start a new case.')
    setCaseTasks([])
  }

  const handleCreateCase = async () => {
    if (!caseSubject.trim()) {
      setCaseNotice('Enter a subject to create a case.')
      return
    }
    setCaseCreating(true)
    setCaseNotice('')
    try {
      const payload = await requestJson('/due-diligence/cases', {
        method: 'POST',
        payload: {
          subject: caseSubject.trim(),
          subjectType: caseSubjectType,
          owner: newCaseOwner.trim(),
          status: newCaseStatus || 'Draft',
        },
      })
      setCases((prev) => [payload, ...prev])
      setActiveCaseId(payload.caseId)
      setActiveCase(payload)
      setSubjectName(payload.subject || '')
      setSubjectType(payload.subjectType || 'Person')
      setStartMode('Analysis')
      setCaseStatus(payload.status || 'Draft')
      setCaseOwner(payload.owner || '')
      setCaseSubject('')
      setCaseSubjectType('Person')
      setNewCaseOwner('')
      setNewCaseStatus('Draft')
      setCaseNotice('Case created and selected.')
      loadCaseTasks(payload.caseId)
    } catch (err) {
      setCaseNotice(err.message || 'Unable to create case.')
    } finally {
      setCaseCreating(false)
    }
  }

  const handleUpdateCase = async () => {
    if (!activeCaseId) return
    setCaseSaving(true)
    setCaseNotice('')
    try {
      const payload = await requestJson(`/due-diligence/cases/${activeCaseId}`, {
        method: 'PATCH',
        payload: {
          status: caseStatus,
          owner: caseOwner.trim(),
        },
      })
      setCases((prev) =>
        prev.map((item) => (item.caseId === activeCaseId ? payload : item)),
      )
      setActiveCase(payload)
      setSubjectName(payload.subject || '')
      setSubjectType(payload.subjectType || 'Person')
      setStartMode('Analysis')
      setCaseStatus(payload.status || 'Draft')
      setCaseOwner(payload.owner || '')
      setCaseNotice('Case updated.')
    } catch (err) {
      setCaseNotice(err.message || 'Unable to update case.')
    } finally {
      setCaseSaving(false)
    }
  }

  const ensureActiveCase = async () => {
    if (activeCaseId) return activeCaseId
    if (!subjectName.trim()) return ''
    setCaseCreating(true)
    try {
      const payload = await requestJson('/due-diligence/cases', {
        method: 'POST',
        payload: {
          subject: subjectName.trim(),
          subjectType,
          status: 'Draft',
        },
      })
      setCases((prev) => [payload, ...prev])
      setActiveCaseId(payload.caseId)
      setActiveCase(payload)
      setSubjectName(payload.subject || '')
      setSubjectType(payload.subjectType || 'Person')
      setCaseStatus(payload.status || 'Draft')
      setCaseOwner(payload.owner || '')
      loadCaseTasks(payload.caseId)
      return payload.caseId
    } catch (err) {
      setCaseNotice(err.message || 'Unable to auto-create case.')
      return ''
    } finally {
      setCaseCreating(false)
    }
  }

  const handleCreateTask = async () => {
    if (!activeCaseId) {
      setTaskError('Select a case first.')
      return
    }
    if (!taskLabel.trim()) {
      setTaskError('Task title is required.')
      return
    }
    setTaskSaving(true)
    setTaskError('')
    try {
      const payload = await requestJson(`/due-diligence/cases/${activeCaseId}/tasks`, {
        method: 'POST',
        payload: {
          label: taskLabel.trim(),
          assignee: taskAssignee.trim(),
          dueDate: taskDueDate || null,
          status: 'Open',
        },
      })
      setCaseTasks((prev) => [payload, ...prev])
      setTaskLabel('')
      setTaskAssignee('')
      setTaskDueDate('')
      loadCases()
    } catch (err) {
      setTaskError(err.message || 'Unable to create task.')
    } finally {
      setTaskSaving(false)
    }
  }

  const handleUpdateTaskStatus = async (taskId, nextStatus) => {
    if (!activeCaseId || !taskId) return
    try {
      const payload = await requestJson(
        `/due-diligence/cases/${activeCaseId}/tasks/${taskId}`,
        {
          method: 'PATCH',
          payload: { status: nextStatus },
        },
      )
      setCaseTasks((prev) =>
        prev.map((item) => (item.taskId === taskId ? payload : item)),
      )
      loadCases()
    } catch (err) {
      setTaskError(err.message || 'Unable to update task.')
    }
  }

  const handleCreateDecision = async () => {
    setDecisionError('')
    setDecisionNotice('')
    if (!activeCaseId) {
      setDecisionError('Select a case first.')
      return
    }
    if (!decisionOutcome.trim()) {
      setDecisionError('Decision outcome is required.')
      return
    }
    setDecisionSaving(true)
    try {
      await requestJson(`/due-diligence/cases/${activeCaseId}/decision`, {
        method: 'POST',
        payload: {
          outcome: decisionOutcome.trim(),
          rationale: decisionRationale.trim(),
        },
      })
      setDecisionRationale('')
      setDecisionNotice('Decision saved. Case moved to Decided.')
      setCaseStatus('Decided')
      setCaseNotice('Case status updated to Decided.')
      loadCases()
    } catch (err) {
      setDecisionError(err.message || 'Unable to save decision.')
    } finally {
      setDecisionSaving(false)
    }
  }

  const runInternalChecks = async () => {
    const query = subjectName.trim()
    if (!query) {
      setError('Enter a subject first.')
      return
    }
    setStartMode('Analysis')
    setError('')
    setInternalChecksRan(true)
    try {
      const people = await getJson(
        `/crm/people/summary?q=${encodeURIComponent(query)}&limit=200`,
      )
      const competitorMatchesList = competitors.filter((item) =>
        item.name?.toLowerCase().includes(query.toLowerCase()),
      )
      setCrmMatches(Array.isArray(people) ? people : [])
      setCompetitorMatches(competitorMatchesList)
    } catch (err) {
      setError(err.message || 'Unable to run internal checks.')
    }
  }

  const handleRunAnalysis = async () => {
    if (!subjectName.trim()) {
      setAnalysisNotice('Enter a subject first.')
      return
    }
    setStartMode('Analysis')
    setAnalysisError('')
    setAnalysisResult(null)
    setAnalysisProgress(5)
    const caseId = await ensureActiveCase()
    const enabled = []
    if (useWikidata) enabled.push('Wikidata')
    if (useOpenSanctions) enabled.push('OpenSanctions')
    if (useNews) enabled.push('News/Web')
    const steps = [
      { id: 'validate', label: 'Validate subject', status: 'success' },
      {
        id: 'wikidata',
        label: 'Query Wikidata',
        status: useWikidata ? 'running' : 'skipped',
      },
      {
        id: 'opensanctions',
        label: 'Query OpenSanctions',
        status: useOpenSanctions ? 'running' : 'skipped',
      },
      { id: 'news', label: 'Query News / Web', status: useNews ? 'running' : 'skipped' },
      { id: 'store', label: 'Store report', status: 'pending' },
      { id: 'compile', label: 'Compile report', status: 'pending' },
    ]
    setAnalysisSteps(steps)
    setAnalysisNotice('Running external analysis...')
    setAnalysisLoading(true)
    if (progressTimerRef.current) {
      clearInterval(progressTimerRef.current)
    }
    progressTimerRef.current = setInterval(() => {
      setAnalysisProgress((prev) => Math.min(prev + 6, 70))
    }, 400)
    try {
      const result = await requestJson('/due-diligence/analyze', {
        method: 'POST',
        payload: {
          subject: subjectName.trim(),
          subjectType,
          caseId: caseId || undefined,
          useWikidata,
          useOpenSanctions,
          useNews,
          maxNews: 8,
          demo: useDemo,
        },
      })
      setAnalysisResult(result)
      const warningsText = (result?.warnings || []).join(' ').toLowerCase()
      const hasWikidataWarning = warningsText.includes('wikidata request failed')
      const hasOpenSanctionsWarning =
        warningsText.includes('opensanctions') &&
        (warningsText.includes('failed') ||
          warningsText.includes('not configured') ||
          warningsText.includes('api key'))
      const hasNewsWarning = warningsText.includes('gdelt news request failed')
      setAnalysisSteps((prev) =>
        prev.map((step) => {
          if (step.id === 'wikidata') {
            if (!useWikidata) return { ...step, status: 'skipped' }
            return { ...step, status: hasWikidataWarning ? 'warning' : 'success' }
          }
          if (step.id === 'opensanctions') {
            if (!useOpenSanctions) return { ...step, status: 'skipped' }
            return { ...step, status: hasOpenSanctionsWarning ? 'warning' : 'success' }
          }
          if (step.id === 'news') {
            if (!useNews) return { ...step, status: 'skipped' }
            return { ...step, status: hasNewsWarning ? 'warning' : 'success' }
          }
          if (step.id === 'store') {
            return { ...step, status: result?.reportId ? 'success' : 'warning' }
          }
          if (step.id === 'compile') {
            return { ...step, status: 'success' }
          }
          return step
        }),
      )
      setAnalysisProgress(100)
      if (subjectName.trim()) {
        loadReportHistory(subjectName.trim(), caseId)
      }
      loadCases()
      setAnalysisNotice(
        `Analysis complete for ${subjectName} (${subjectType}) using: ${
          enabled.length ? enabled.join(', ') : 'no sources'
        }.`,
      )
    } catch (err) {
      setAnalysisError(err.message || 'External analysis failed.')
      setAnalysisNotice('')
      setAnalysisSteps((prev) =>
        prev.map((step) => {
          if (step.status === 'running' || step.status === 'pending') {
            return { ...step, status: 'error' }
          }
          return step
        }),
      )
      setAnalysisProgress(100)
    } finally {
      setAnalysisLoading(false)
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current)
      }
    }
  }

  const loadReportHistory = async (subject, caseId) => {
    if (!subject && !caseId) {
      setReportHistory([])
      return
    }
    setHistoryLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('limit', '8')
      if (caseId) {
        params.set('caseId', caseId)
      } else if (subject) {
        params.set('subject', subject)
      }
      const history = await getJson(`/due-diligence/reports?${params.toString()}`)
      setReportHistory(Array.isArray(history) ? history : [])
    } catch (err) {
      setReportHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (activeCaseId) {
      loadReportHistory(subjectName.trim(), activeCaseId)
      return
    }
    if (!subjectName.trim()) {
      setReportHistory([])
      return
    }
    loadReportHistory(subjectName.trim(), '')
  }, [subjectName, activeCaseId])

  useEffect(() => {
    if (!cases.length) return
    if (!activeCaseId && !subjectName.trim()) {
      setActiveCaseId(cases[0].caseId)
      return
    }
    if (!activeCaseId && subjectName.trim()) {
      const match = cases.find((item) => item.subject === subjectName.trim())
      if (match) {
        setActiveCaseId(match.caseId)
      }
      return
    }
    if (!activeCaseId) return
    const found = cases.find((item) => item.caseId === activeCaseId)
    if (!found) return
    setActiveCase(found)
    setSubjectName(found.subject || '')
    setSubjectType(found.subjectType || 'Person')
    setCaseStatus(found.status || 'Draft')
    setCaseOwner(found.owner || '')
  }, [cases, activeCaseId, subjectName])

  useEffect(() => {
    if (activeCaseId) {
      loadCaseTasks(activeCaseId)
    } else {
      setCaseTasks([])
    }
  }, [activeCaseId])

  useEffect(() => {
    setInternalChecksRan(false)
    setCrmMatches([])
    setCompetitorMatches([])
  }, [subjectName, subjectType])

  useEffect(() => {
    if (!debateOpponent && subjectName) {
      setDebateOpponent(subjectName)
    }
  }, [debateOpponent, subjectName])

  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    localStorage.setItem('ddAppUrl', ddAppUrl)
  }, [ddAppUrl])

  useEffect(() => {
    localStorage.setItem('ddGmailTo', gmailTo)
  }, [gmailTo])

  const launchUrl = useMemo(() => {
    if (!ddAppUrl) return ''
    const params = new URLSearchParams({
      subject: subjectName || '',
      subject_type: subjectType || '',
      start_mode: startMode.replace(/\s+/g, '_').toLowerCase(),
      use_wikidata: useWikidata ? '1' : '0',
      use_opensanctions: useOpenSanctions ? '1' : '0',
      use_news: useNews ? '1' : '0',
    })
    const base = ddAppUrl.includes('?') ? `${ddAppUrl}&` : `${ddAppUrl}?`
    return `${base}${params.toString()}`
  }, [ddAppUrl, subjectName, subjectType, startMode, useWikidata, useOpenSanctions, useNews])

  const subjectStatus = subjectName.trim()
    ? internalChecksRan
      ? crmMatches.length + competitorMatches.length > 0
        ? 'Known'
        : 'New'
      : 'Not checked'
    : '—'

  const gmailUrl = useMemo(() => {
    const subjectLine = encodeURIComponent(
      `Due Diligence subject review: ${subjectName || 'Subject'}`,
    )
    const body = encodeURIComponent(
      `Subject: ${subjectName || ''}\nType: ${subjectType}\nStart mode: ${startMode}\n\nDD app:\n${
        launchUrl || ddAppUrl
      }`,
    )
    const to = encodeURIComponent(gmailTo || '')
    return `https://mail.google.com/mail/?view=cm&fs=1&to=${to}&su=${subjectLine}&body=${body}`
  }, [subjectName, subjectType, startMode, launchUrl, ddAppUrl, gmailTo])

  const debatePrepPlan = useMemo(() => {
    if (!debateResult) return null
    const themes = Array.isArray(debateResult.themes) ? debateResult.themes : []
    const mentions = Array.isArray(debateResult.mentions) ? debateResult.mentions : []
    const topThemes = themes.slice(0, 3)
    const themeLabels = topThemes.map((theme) => theme.name).filter(Boolean)
    const opening = [
      themeLabels[0]
        ? `Frame the core problem around ${themeLabels[0].toLowerCase()}.`
        : `Frame the core problem around ${debateTopic}.`,
      themeLabels[1] ? `Acknowledge shared goals on ${themeLabels[1].toLowerCase()}.` : null,
      themeLabels[2] ? `State your proposed solution on ${themeLabels[2].toLowerCase()}.` : null,
    ].filter(Boolean)
    const crossExam = topThemes.map((theme) => {
      const example = (theme.examples || [])[0]
      return example
        ? `Ask for specifics on ${theme.name.toLowerCase()} (ex: "${example}").`
        : `Ask for specifics on ${theme.name.toLowerCase()} and request timelines.`
    })
    const closing = [
      `Summarize your commitments: ${themeLabels.join(', ') || debateTopic}.`,
      `Reinforce balanced outcomes: public safety, animal welfare, and accountability.`,
      `Close with a clear next-step timeline and measurable targets.`,
    ]
    const counterpoints = topThemes.map((theme) => ({
      theme: theme.name,
      prompt: `Likely pushback on ${theme.name.toLowerCase()}: prepare data on costs, enforcement, and timeline.`,
    }))
    const evidenceCards = mentions.slice(0, 6).map((row, idx) => ({
      id: row.url || row.title || `mention-${idx}`,
      title: row.title || 'Public mention',
      source: row.source || '—',
      date: row.publishedAt || '—',
      snippet: row.snippet || '—',
      url: row.url || '',
      phase: idx < 2 ? 'Opening' : idx < 4 ? 'Cross-exam' : 'Closing',
    }))
    return {
      opening,
      crossExam,
      closing,
      counterpoints,
      evidenceCards,
    }
  }, [debateResult, debateTopic])

  const handleCreate = async (event) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Competitor name is required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await requestJson('/due-diligence/competitors', {
        method: 'POST',
        payload: {
          name: name.trim(),
          competitorType,
          notes: notes.trim(),
        },
      })
      setName('')
      setNotes('')
      loadCompetitors()
    } catch (err) {
      setError(err.message || 'Unable to save competitor.')
    } finally {
      setSaving(false)
    }
  }

  const handleRunDebatePrep = async () => {
    if (!debateOpponent.trim() || !debateTopic.trim()) {
      setDebateError('Set an opponent and topic first.')
      return
    }
    setDebateError('')
    setDebateResult(null)
    setDebateLoading(true)
    try {
      const result = await requestJson('/due-diligence/debate-prep', {
        method: 'POST',
        payload: {
          opponent: debateOpponent.trim(),
          topic: debateTopic.trim(),
          yearsBack: Number(debateYears) || 2,
          maxResults: Number(debateMaxResults) || 25,
          useWikipedia: debateUseWikipedia,
          useGoogle: debateUseGoogle,
          useLocalMedia: debateUseLocalMedia,
          demo: debateUseDemo,
        },
      })
      setDebateResult(result)
    } catch (err) {
      setDebateError(err.message || 'Debate prep failed.')
    } finally {
      setDebateLoading(false)
    }
  }

  const handleDelete = async (competitorId) => {
    setError('')
    try {
      await requestJson(`/due-diligence/competitors/${competitorId}`, {
        method: 'DELETE',
      })
      loadCompetitors()
    } catch (err) {
      setError(err.message || 'Unable to delete competitor.')
    }
  }

  const handleUseWatchlist = (item) => {
    if (!item) return
    if (activeCaseId) {
      handleClearCase()
    }
    const normalizedType =
      item.competitorType === 'Company' ? 'Organization' : item.competitorType || 'Person'
    setActiveSubject(item.name || '', normalizedType, 'Watchlist')
  }

  const companyCandidate = useMemo(
    () => competitors.find((item) => item.competitorType === 'Company'),
    [competitors],
  )
  const personCandidate = useMemo(
    () => competitors.find((item) => item.competitorType === 'Person'),
    [competitors],
  )

  useEffect(() => {
    if (subjectName || autoPrefillRef.current) return
    if (companyCandidate) {
      setActiveSubject(companyCandidate.name, 'Organization', 'Watchlist')
      autoPrefillRef.current = true
      return
    }
    if (personCandidate) {
      setActiveSubject(personCandidate.name, 'Person', 'Watchlist')
      autoPrefillRef.current = true
    }
  }, [companyCandidate, personCandidate, subjectName])

  const handleImportWatchlist = (file) => {
    setImportError('')
    setImportStatus('')
    if (!file) {
      setImportError('Select a CSV file.')
      return
    }
    const reader = new FileReader()
    reader.onload = async () => {
      try {
        setImporting(true)
        const text = String(reader.result || '')
        const { data, fields } = parseCsvText(text)
        const fieldMap = fields.reduce((acc, field) => {
          acc[field.toLowerCase().trim()] = field
          return acc
        }, {})
        const nameField =
          fieldMap.name || fieldMap.competitor_name || fieldMap.competitor || ''
        const typeField =
          fieldMap.competitor_type || fieldMap.type || fieldMap.competitortype || ''
        const notesField = fieldMap.notes || fieldMap.note || fieldMap.description || ''
        if (!nameField) {
          setImportError('CSV must include a name column.')
          setImporting(false)
          return
        }
        const rows = data.filter((row) => String(row[nameField] || '').trim())
        let created = 0
        for (const row of rows) {
          const payload = {
            name: String(row[nameField] || '').trim(),
            competitorType: String(row[typeField] || 'Person').trim() || 'Person',
            notes: String(row[notesField] || '').trim(),
          }
          await requestJson('/due-diligence/competitors', {
            method: 'POST',
            payload,
          })
          created += 1
        }
        setImportStatus(`Imported ${created} competitors.`)
        loadCompetitors()
      } catch (err) {
        setImportError(err.message || 'Import failed.')
      } finally {
        setImporting(false)
      }
    }
    reader.onerror = () => {
      setImportError('Import failed.')
    }
    reader.readAsText(file)
  }

  const formatStepStatus = (status) => {
    switch (status) {
      case 'running':
        return 'Running'
      case 'success':
        return 'Done'
      case 'warning':
        return 'Warning'
      case 'error':
        return 'Failed'
      case 'skipped':
        return 'Skipped'
      default:
        return 'Pending'
    }
  }

  const caseStatusOptions = ['Draft', 'Active', 'Review', 'Decided', 'Closed']
  const taskStatusOptions = ['Open', 'In Progress', 'Blocked', 'Done']

  const duePulseStats = useMemo(
    () => [
      {
        label: 'Competitors',
        value: summary?.competitors ?? '—',
        icon: <IconShieldCheck size={18} />,
        badge: 'Tracked',
      },
      {
        label: 'Network matches',
        value: crmMatches.length,
        icon: <IconUsers size={18} />,
        note: 'Internal signals',
      },
      {
        label: 'Reports run',
        value: reportHistory.length,
        icon: <IconFileSearch size={18} />,
        note: 'DD history',
      },
      {
        label: 'Watchlist hits',
        value: competitorMatches.length,
        icon: <IconAlertTriangle size={18} />,
        badge: 'Review',
      },
    ],
    [competitorMatches.length, crmMatches.length, reportHistory.length, summary?.competitors],
  )

  return (
    <section className="module">
      <details className="dashboard-detail">
        <summary>Risk pipeline stats</summary>
        <div className="dashboard-detail__body">
          <div className="module-header__meta">
            <div className="module-header__metric">
              <span>Competitors</span>
              <strong>{summary?.competitors ?? '—'}</strong>
            </div>
            <div className="module-header__metric">
              <span>Network People</span>
              <strong>{crmSummary?.total_people ?? '—'}</strong>
            </div>
            <div className="module-header__metric">
              <span>Supporters</span>
              <strong>{crmSummary?.supporters ?? '—'}</strong>
            </div>
          </div>
        </div>
      </details>

      <CivicStatGrid
        title="Risk intelligence pulse"
        description="Signals across competitors, watchlists, and internal matches."
        items={duePulseStats}
      />

      <Card className="module-card module-card__wide">
        <Group justify="space-between" align="center" wrap="wrap">
          <div>
            <Text fw={600}>Analysis pipeline</Text>
            <Text size="sm" c="dimmed">
              Progress across internal checks and external sources.
            </Text>
          </div>
          <RingProgress
            size={86}
            thickness={8}
            roundCaps
            sections={[{ value: analysisProgress, color: 'civic' }]}
            label={
              <Text size="sm" fw={600} ta="center">
                {analysisProgress}%
              </Text>
            }
          />
        </Group>
      </Card>

      {error ? <div className="module-alert">{error}</div> : null}

      {showTabs ? (
        <div className="subtabs">
          {[
            { id: 'how-it-works', label: translate('dueDiligence.tabs.how') },
            { id: 'configure', label: translate('dueDiligence.tabs.configure') },
            { id: 'analysis', label: translate('dueDiligence.tabs.analysis') },
            { id: 'debate-prep', label: translate('dueDiligence.tabs.debate') },
            { id: 'launch', label: translate('dueDiligence.tabs.launch') },
            { id: 'watchlist', label: translate('dueDiligence.tabs.watchlist') },
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

      {activeTab === 'how-it-works' && (
        <details className="dashboard-detail">
          <summary>How the workflow runs</summary>
          <div className="dashboard-detail__body">
            <InfoBox
              title="Workflow overview"
              summary="Choose a subject → Check internal sources → Run external analysis → Review report."
              hint="Use the Watchlist tab for repeat subjects, and Launch to open the external DD app."
            />
          </div>
        </details>
      )}

      {activeTab === 'analysis' && (
        <div className="stack">
          <div className="module-card module-card__wide section-intro">
            <div className="card-header">
              <div>
                <h3>Case workspace</h3>
                <p className="muted">
                  Create a case, run checks, and capture a decision.
                </p>
              </div>
              <div className="pill">Case flow</div>
            </div>
            <InfoBox
              title="Workflow"
              summary="Intake → Internal checks → External analysis → Decision"
              hint="Use Watchlist for repeat subjects and Launch for the external DD app."
            />
          </div>

          <div className="module-grid">
            <div className="module-card">
              <h3>Start a new case</h3>
              <p className="muted">Capture the subject and assign ownership.</p>
              <div className="filter-row">
                <input
                  className="input"
                  placeholder="Subject name"
                  value={caseSubject}
                  onChange={(event) => setCaseSubject(event.target.value)}
                />
                <select
                  className="select"
                  value={caseSubjectType}
                  onChange={(event) => setCaseSubjectType(event.target.value)}
                >
                  <option value="Person">Person</option>
                  <option value="Organization">Organization</option>
                </select>
                <input
                  className="input"
                  placeholder="Owner (optional)"
                  value={newCaseOwner}
                  onChange={(event) => setNewCaseOwner(event.target.value)}
                />
                <select
                  className="select"
                  value={newCaseStatus}
                  onChange={(event) => setNewCaseStatus(event.target.value)}
                >
                  {caseStatusOptions.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
                <button
                  className="button"
                  type="button"
                  onClick={handleCreateCase}
                  disabled={caseCreating}
                >
                  {caseCreating ? 'Creating…' : 'Create case'}
                </button>
              </div>
              {caseNotice ? <div className="module-alert">{caseNotice}</div> : null}
            </div>

            <div className="module-card">
              <div className="card-header">
                <div>
                  <h3>Cases</h3>
                  <p className="muted">Select a case to run checks.</p>
                </div>
                <button className="button-secondary" type="button" onClick={loadCases}>
                  Refresh
                </button>
              </div>
              {casesError ? <div className="module-alert">{casesError}</div> : null}
              <div className="table">
                <div className="table-row table-head">
                  <span>Subject</span>
                  <span>Status</span>
                  <span>Risk</span>
                  <span>Updated</span>
                </div>
                {casesLoading ? (
                  <div className="table-row empty">Loading cases…</div>
                ) : cases.length === 0 ? (
                  <div className="table-row empty">No cases yet.</div>
                ) : (
                  cases.map((row) => (
                    <button
                      className={`table-row table-row__button${
                        activeCaseId === row.caseId ? ' is-active' : ''
                      }`}
                      type="button"
                      key={row.caseId}
                      onClick={() => handleSelectCase(row.caseId)}
                    >
                      <span>{row.subject || '—'}</span>
                      <span>{row.status || 'Draft'}</span>
                      <span>{row.lastRiskLevel || '—'}</span>
                      <span>{row.updatedAt || row.createdAt || '—'}</span>
                    </button>
                  ))
                )}
              </div>
              <div className="module-footer">
                <span>
                  {activeCaseId
                    ? `Active case: ${activeCase?.subject || '—'}`
                    : 'No case selected.'}
                </span>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={handleClearCase}
                  disabled={!activeCaseId}
                >
                  Clear selection
                </button>
              </div>
            </div>
          </div>

          <div className="module-card module-card__wide section-intro">
            <div className="card-header">
              <div>
                <h3>Start a due diligence check</h3>
                <p className="muted">
                  Choose a subject, run internal checks, then run external analysis.
                </p>
              </div>
            </div>
            {!activeCaseId ? (
              <div className="module-alert">
                No case selected yet. Create a case above or run analysis to auto-create
                a draft case.
              </div>
            ) : null}
            {activeCaseId ? (
              <div className="module-alert module-alert--success">
                Active case: {activeCase?.subject || '—'} · {caseStatus}
              </div>
            ) : null}
            <InfoBox
              title="Quick steps"
              summary="1) Enter a subject  2) Run internal checks  3) Run external analysis"
              hint="Internal checks scan Network + watchlist. External analysis pulls Wikidata, OpenSanctions, and News/Web."
            />
            {(companyCandidate || personCandidate) && (
              <>
                <div className="card-divider">
                  <h4>Suggested from watchlist</h4>
                </div>
                <div className="module-footer">
                  <span>
                    <strong>Company</strong>{' '}
                    {companyCandidate?.name ? companyCandidate.name : '—'}
                  </span>
                  <span>
                    <strong>Person</strong>{' '}
                    {personCandidate?.name ? personCandidate.name : '—'}
                  </span>
                  {companyCandidate ? (
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => handleUseWatchlist(companyCandidate)}
                    >
                      Use company
                    </button>
                  ) : null}
                  {personCandidate ? (
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => handleUseWatchlist(personCandidate)}
                    >
                      Use person
                    </button>
                  ) : null}
                </div>
              </>
            )}
          <div className="filter-row">
            <input
              className="input"
              placeholder="Enter person or organization"
              value={subjectName}
              onChange={(event) => setSubjectName(event.target.value)}
              disabled={Boolean(activeCaseId)}
            />
            <select
              className="select"
              value={subjectType}
              onChange={(event) => setSubjectType(event.target.value)}
              disabled={Boolean(activeCaseId)}
            >
              <option value="Person">Person</option>
              <option value="Organization">Organization</option>
            </select>
            <button
              className="button"
              type="button"
              onClick={runInternalChecks}
            >
              Check internal records
            </button>
            {activeCaseId ? (
              <button
                className="button-secondary"
                type="button"
                onClick={handleClearCase}
              >
                Change subject
              </button>
            ) : null}
          </div>
          <p className="muted">Internal checks look at Network + watchlist for matches.</p>

          <div className="metric-row">
            <span>Active subject</span>
            <strong>
              {subjectName.trim() ? `${subjectName} (${subjectType})` : '—'}
            </strong>
          </div>
          <div className="metric-row">
            <span>Subject status</span>
            <strong>{subjectStatus}</strong>
          </div>
          {activeCaseId ? (
            <div className="metric-row">
              <span>Case status</span>
              <strong>{caseStatus}</strong>
            </div>
          ) : null}

          <div className="card-divider">
            <h4>Internal checks</h4>
          </div>
          <details className="dashboard-detail" open>
            <summary>Network matches ({crmMatches.length})</summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Name</span>
                  <span>Email</span>
                  <span>Group</span>
                  <span>Time</span>
                </div>
                {!subjectName.trim() ? (
                  <div className="table-row empty">Enter a subject to see matches.</div>
                ) : !internalChecksRan ? (
                  <div className="table-row empty">Run internal checks to see matches.</div>
                ) : crmMatches.length === 0 ? (
                  <div className="table-row empty">No Network matches.</div>
                ) : (
                  crmMatches.slice(0, 12).map((row, idx) => (
                    <div className="table-row" key={`${row.email || 'match'}-${idx}`}>
                      <span>{row.fullName || row.email}</span>
                      <span>{row.email}</span>
                      <span>{row.group || '—'}</span>
                      <span>{row.timeAvailability || 'Unspecified'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail" open>
            <summary>Watchlist matches ({competitorMatches.length})</summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Name</span>
                  <span>Type</span>
                  <span>Notes</span>
                </div>
                {!subjectName.trim() ? (
                  <div className="table-row empty">Enter a subject to see matches.</div>
                ) : !internalChecksRan ? (
                  <div className="table-row empty">Run internal checks to see matches.</div>
                ) : competitorMatches.length === 0 ? (
                  <div className="table-row empty">No watchlist matches.</div>
                ) : (
                  competitorMatches.slice(0, 10).map((row) => (
                    <div className="table-row" key={row.competitorId || row.name}>
                      <span>{row.name}</span>
                      <span>{row.competitorType}</span>
                      <span>{row.notes || '—'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <div className="card-divider">
            <h4>External analysis</h4>
          </div>
          <p className="muted">Select sources and run the external check.</p>
          <div className="filter-row">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={useWikidata}
                onChange={(event) => setUseWikidata(event.target.checked)}
              />
              Wikidata
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={useOpenSanctions}
                onChange={(event) => setUseOpenSanctions(event.target.checked)}
              />
              OpenSanctions
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={useNews}
                onChange={(event) => setUseNews(event.target.checked)}
              />
              News / Web
            </label>
            <button className="button" type="button" onClick={handleRunAnalysis}>
              {analysisLoading ? 'Running…' : 'Run external analysis'}
            </button>
          </div>
          <details className="dashboard-detail">
            <summary>Advanced options</summary>
            <div className="dashboard-detail__body">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={useDemo}
                  onChange={(event) => setUseDemo(event.target.checked)}
                />
                Use demo data if sources are unavailable
              </label>
            </div>
          </details>
          {analysisError ? <div className="module-alert">{analysisError}</div> : null}
          {analysisNotice ? <p className="muted">{analysisNotice}</p> : null}
          {analysisProgress > 0 ? (
            <div className="questionnaire-progress">
              <div className="questionnaire-progress__track">
                <div
                  className="questionnaire-progress__bar"
                  style={{ width: `${Math.min(analysisProgress, 100)}%` }}
                />
              </div>
              <span className="questionnaire-progress__label">{analysisProgress}%</span>
            </div>
          ) : null}
          {analysisSteps.length ? (
            <div className="table">
              <div className="table-row table-head">
                <span>Step</span>
                <span>Status</span>
              </div>
              {analysisSteps.map((step) => (
                <div className="table-row" key={step.id}>
                  <span>{step.label}</span>
                  <span>{formatStepStatus(step.status)}</span>
                </div>
              ))}
            </div>
          ) : null}
          {analysisResult ? (
            <div className="stack">
              <div className="module-alert module-alert--success">
                Risk level: {analysisResult.summary?.risk_level || 'Unknown'} · Total hits:{' '}
                {analysisResult.summary?.total_hits ?? 0}
              </div>
              {analysisResult.summary?.risk_score !== undefined ? (
                <p className="muted">
                  Risk score: {analysisResult.summary?.risk_score}/100
                </p>
              ) : null}
              {analysisResult.summary?.risk_rationale?.length ? (
                <ul className="compact-list">
                  {analysisResult.summary.risk_rationale.map((item, idx) => (
                    <li key={`${item}-${idx}`}>{item}</li>
                  ))}
                </ul>
              ) : null}
              {analysisResult.warnings?.length ? (
                <div className="module-alert">
                  {analysisResult.warnings.map((warning, idx) => (
                    <div key={`${warning}-${idx}`}>{warning}</div>
                  ))}
                </div>
              ) : null}
              {analysisResult.reportId ? (
                <div className="filter-row">
                  <a
                    className="button-secondary"
                    href={`${API_BASE}/due-diligence/reports/${analysisResult.reportId}/pdf`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Download PDF report
                  </a>
                  <span className="muted">
                    Stored: {analysisResult.storedAt || '—'}
                  </span>
                </div>
              ) : null}

              <details className="dashboard-detail" open>
                <summary>
                  Wikidata results ({(analysisResult.wikidata || []).length})
                </summary>
                <div className="dashboard-detail__body">
                  <div className="table">
                    <div className="table-row table-head">
                      <span>Label</span>
                      <span>Description</span>
                      <span>Link</span>
                    </div>
                    {(analysisResult.wikidata || []).length === 0 ? (
                      <div className="table-row empty">No Wikidata matches.</div>
                    ) : (
                      analysisResult.wikidata.map((row) => (
                        <div className="table-row" key={row.id || row.label}>
                          <span>{row.label || '—'}</span>
                          <span>{row.description || '—'}</span>
                          <span>
                            {row.url ? (
                              <a href={row.url} target="_blank" rel="noreferrer">
                                View
                              </a>
                            ) : (
                              '—'
                            )}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </details>

              <details className="dashboard-detail" open>
                <summary>
                  OpenSanctions results ({(analysisResult.opensanctions || []).length})
                </summary>
                <div className="dashboard-detail__body">
                  <div className="table">
                    <div className="table-row table-head">
                      <span>Name</span>
                      <span>Schema</span>
                      <span>Datasets</span>
                      <span>Score</span>
                    </div>
                    {(analysisResult.opensanctions || []).length === 0 ? (
                      <div className="table-row empty">No OpenSanctions matches.</div>
                    ) : (
                      analysisResult.opensanctions.map((row) => (
                        <div className="table-row" key={row.id || row.name}>
                          <span>
                            {row.url ? (
                              <a href={row.url} target="_blank" rel="noreferrer">
                                {row.name || '—'}
                              </a>
                            ) : (
                              row.name || '—'
                            )}
                          </span>
                          <span>{row.schema || '—'}</span>
                          <span>{(row.datasets || []).slice(0, 3).join(', ') || '—'}</span>
                          <span>{row.score?.toFixed?.(2) ?? row.score ?? '—'}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </details>

              <details className="dashboard-detail" open>
                <summary>
                  News / Web results ({(analysisResult.news || []).length})
                </summary>
                <div className="dashboard-detail__body">
                  <div className="table">
                    <div className="table-row table-head">
                      <span>Headline</span>
                      <span>Source</span>
                      <span>Tone</span>
                    </div>
                    {(analysisResult.news || []).length === 0 ? (
                      <div className="table-row empty">No recent news found.</div>
                    ) : (
                      analysisResult.news.map((row) => (
                        <div className="table-row" key={row.url || row.title}>
                          <span>
                            {row.url ? (
                              <a href={row.url} target="_blank" rel="noreferrer">
                                {row.title || '—'}
                              </a>
                            ) : (
                              row.title || '—'
                            )}
                          </span>
                          <span>{row.source || '—'}</span>
                          <span>{row.tone?.toFixed?.(2) ?? row.tone ?? '—'}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </details>
            </div>
          ) : null}
          {subjectName.trim() ? (
            <details className="dashboard-detail">
              <summary>Report history ({reportHistory.length})</summary>
              <div className="dashboard-detail__body">
                <div className="table">
                  <div className="table-row table-head">
                    <span>Created</span>
                    <span>Risk</span>
                    <span>Total hits</span>
                    <span>Sources</span>
                    <span>Download</span>
                  </div>
                  {historyLoading ? (
                    <div className="table-row empty">Loading report history…</div>
                  ) : reportHistory.length === 0 ? (
                    <div className="table-row empty">No prior reports for this subject.</div>
                  ) : (
                    reportHistory.map((row) => (
                      <div className="table-row" key={row.reportId}>
                        <span>{row.createdAt || '—'}</span>
                        <span>{row.riskLevel || '—'}</span>
                        <span>{row.totalHits ?? 0}</span>
                        <span>{(row.sources || []).join(', ') || '—'}</span>
                        <span>
                          <a
                            href={`${API_BASE}/due-diligence/reports/${row.reportId}/pdf`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            PDF
                          </a>
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </details>
          ) : null}
        </div>
        {activeCaseId ? (
          <div className="module-grid">
            <div className="module-card">
              <h3>Case overview</h3>
              <div className="metric-row">
                <span>Case ID</span>
                <strong>{activeCaseId}</strong>
              </div>
              <div className="metric-row">
                <span>Status</span>
                <strong>{caseStatus}</strong>
              </div>
              <div className="metric-row">
                <span>Owner</span>
                <strong>{caseOwner || '—'}</strong>
              </div>
              <div className="metric-row">
                <span>Last risk</span>
                <strong>{activeCase?.lastRiskLevel || '—'}</strong>
              </div>
              <div className="metric-row">
                <span>Last report</span>
                <strong>{activeCase?.lastReportAt || '—'}</strong>
              </div>
              <div className="filter-row">
                <select
                  className="select"
                  value={caseStatus}
                  onChange={(event) => setCaseStatus(event.target.value)}
                >
                  {caseStatusOptions.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
                <input
                  className="input"
                  placeholder="Owner"
                  value={caseOwner}
                  onChange={(event) => setCaseOwner(event.target.value)}
                />
                <button
                  className="button-secondary"
                  type="button"
                  onClick={handleUpdateCase}
                  disabled={caseSaving}
                >
                  {caseSaving ? 'Saving…' : 'Update case'}
                </button>
              </div>
              {caseNotice ? <div className="module-alert">{caseNotice}</div> : null}
            </div>

            <div className="module-card">
              <h3>Tasks</h3>
              <p className="muted">Track actions before final decision.</p>
              <div className="filter-row">
                <input
                  className="input"
                  placeholder="Task title"
                  value={taskLabel}
                  onChange={(event) => setTaskLabel(event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Assignee"
                  value={taskAssignee}
                  onChange={(event) => setTaskAssignee(event.target.value)}
                />
                <input
                  className="input"
                  type="date"
                  value={taskDueDate}
                  onChange={(event) => setTaskDueDate(event.target.value)}
                />
                <button
                  className="button"
                  type="button"
                  onClick={handleCreateTask}
                  disabled={taskSaving}
                >
                  {taskSaving ? 'Adding…' : 'Add task'}
                </button>
              </div>
              {taskError ? <div className="module-alert">{taskError}</div> : null}
              <div className="table">
                <div className="table-row table-head table-row--tasks">
                  <span>Task</span>
                  <span>Status</span>
                  <span>Assignee</span>
                  <span>Due</span>
                  <span>Action</span>
                </div>
                {tasksLoading ? (
                  <div className="table-row table-row--tasks empty">Loading tasks…</div>
                ) : caseTasks.length === 0 ? (
                  <div className="table-row table-row--tasks empty">No tasks yet.</div>
                ) : (
                  caseTasks.map((task) => (
                    <div className="table-row table-row--tasks" key={task.taskId}>
                      <span>{task.label}</span>
                      <select
                        className="select"
                        value={task.status || 'Open'}
                        onChange={(event) =>
                          handleUpdateTaskStatus(task.taskId, event.target.value)
                        }
                      >
                        {taskStatusOptions.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                      <span>{task.assignee || '—'}</span>
                      <span>{task.dueDate || '—'}</span>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => handleUpdateTaskStatus(task.taskId, 'Done')}
                      >
                        Mark done
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="module-card">
              <h3>Decision</h3>
              <p className="muted">Record the final due diligence outcome.</p>
              <div className="filter-row">
                <select
                  className="select"
                  value={decisionOutcome}
                  onChange={(event) => setDecisionOutcome(event.target.value)}
                >
                  <option value="Approve">Approve</option>
                  <option value="Monitor">Monitor</option>
                  <option value="Escalate">Escalate</option>
                  <option value="Reject">Reject</option>
                </select>
                <input
                  className="input"
                  placeholder="Rationale (optional)"
                  value={decisionRationale}
                  onChange={(event) => setDecisionRationale(event.target.value)}
                />
                <button
                  className="button"
                  type="button"
                  onClick={handleCreateDecision}
                  disabled={decisionSaving}
                >
                  {decisionSaving ? 'Saving…' : 'Save decision'}
                </button>
              </div>
              {decisionError ? <div className="module-alert">{decisionError}</div> : null}
              {decisionNotice ? (
                <div className="module-alert module-alert--success">{decisionNotice}</div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="module-alert">
            Select a case to view tasks and record a decision.
          </div>
        )}
      </div>
      )}

      {activeTab === 'debate-prep' && (
        <div className="module-card module-card__wide section-intro">
          <div className="card-header">
            <div>
              <h3>Debate prep</h3>
              <p className="muted">
                Scan public mentions to map likely talking points and positions.
              </p>
            </div>
          </div>
          <div className="stack">
            <div className="filter-row">
              <input
                className="input"
                placeholder="Opponent name"
                value={debateOpponent}
                onChange={(event) => setDebateOpponent(event.target.value)}
              />
              <input
                className="input"
                placeholder="Topic (e.g., education)"
                value={debateTopic}
                onChange={(event) => setDebateTopic(event.target.value)}
              />
              <input
                className="input"
                type="number"
                min="1"
                max="10"
                value={debateYears}
                onChange={(event) => setDebateYears(event.target.value)}
                placeholder="Years back"
              />
              <input
                className="input"
                type="number"
                min="5"
                max="100"
                value={debateMaxResults}
                onChange={(event) => setDebateMaxResults(event.target.value)}
                placeholder="Max results"
              />
              <button
                className="button"
                type="button"
                onClick={handleRunDebatePrep}
              >
                {debateLoading ? 'Running…' : 'Run debate prep'}
              </button>
            </div>
            <div className="filter-row">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={debateUseWikipedia}
                  onChange={(event) => setDebateUseWikipedia(event.target.checked)}
                />
                Wikipedia primer
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={debateUseGoogle}
                  onChange={(event) => setDebateUseGoogle(event.target.checked)}
                />
                Google search results
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={debateUseLocalMedia}
                  onChange={(event) => setDebateUseLocalMedia(event.target.checked)}
                />
                Local media RSS (Publika, Netgazeti)
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={debateUseDemo}
                  onChange={(event) => setDebateUseDemo(event.target.checked)}
                />
                Use demo data if sources are unavailable
              </label>
            </div>
            {debateError ? <div className="module-alert">{debateError}</div> : null}
            {debateResult ? (
              <div className="stack">
                <div className="module-alert module-alert--success">
                  {debateResult.mentions?.length ?? 0} mentions · {debateResult.startDate} →{' '}
                  {debateResult.endDate}
                </div>
                <p className="muted">
                  Query: <strong>{debateResult.query}</strong>
                </p>
                {debateResult.keywords?.length ? (
                  <p className="muted">Keywords: {debateResult.keywords.join(', ')}</p>
                ) : null}
                {debateResult.warnings?.length ? (
                  <div className="module-alert">
                    {debateResult.warnings.map((warning, idx) => (
                      <div key={`${warning}-${idx}`}>{warning}</div>
                    ))}
                  </div>
                ) : null}

                {debatePrepPlan ? (
                  <>
                    <div className="card-divider">
                      <h4>Debate flow</h4>
                    </div>
                    <div className="debate-flow-grid">
                      <div className="module-card debate-flow-card">
                        <div className="debate-card-header">
                          <h5>Opening</h5>
                          <span className="pill">Set the frame</span>
                        </div>
                        <ul className="compact-list">
                          {debatePrepPlan.opening.map((line, idx) => (
                            <li key={`${line}-${idx}`}>{line}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="module-card debate-flow-card">
                        <div className="debate-card-header">
                          <h5>Cross-exam</h5>
                          <span className="pill">Pressure test</span>
                        </div>
                        <ul className="compact-list">
                          {debatePrepPlan.crossExam.map((line, idx) => (
                            <li key={`${line}-${idx}`}>{line}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="module-card debate-flow-card">
                        <div className="debate-card-header">
                          <h5>Closing</h5>
                          <span className="pill">Call to action</span>
                        </div>
                        <ul className="compact-list">
                          {debatePrepPlan.closing.map((line, idx) => (
                            <li key={`${line}-${idx}`}>{line}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    <div className="card-divider">
                      <h4>Likely counterpoints</h4>
                    </div>
                    <div className="table">
                      <div className="table-row table-head">
                        <span>Theme</span>
                        <span>Counter-argument</span>
                      </div>
                      {debatePrepPlan.counterpoints.length === 0 ? (
                        <div className="table-row empty">No counterpoints generated.</div>
                      ) : (
                        debatePrepPlan.counterpoints.map((row, idx) => (
                          <div className="table-row" key={`${row.theme}-${idx}`}>
                            <span>{row.theme}</span>
                            <span>{row.prompt}</span>
                          </div>
                        ))
                      )}
                    </div>

                    <div className="card-divider">
                      <h4>Evidence cards</h4>
                    </div>
                    <div className="debate-evidence-grid">
                      {debatePrepPlan.evidenceCards.length === 0 ? (
                        <div className="table-row empty">No evidence cards yet.</div>
                      ) : (
                        debatePrepPlan.evidenceCards.map((card) => (
                          <div className="debate-evidence-card" key={card.id}>
                            <div className="debate-card-header">
                              <h5>{card.title}</h5>
                              <span className="pill">{card.phase}</span>
                            </div>
                            <p className="muted">
                              {card.source} · {card.date}
                            </p>
                            <p>{card.snippet}</p>
                            {card.url ? (
                              <a href={card.url} target="_blank" rel="noreferrer">
                                Open source
                              </a>
                            ) : null}
                          </div>
                        ))
                      )}
                    </div>
                  </>
                ) : null}

                <div className="card-divider">
                  <h4>Wikipedia primer</h4>
                </div>
                <div className="table">
                  <div className="table-row table-head">
                    <span>Article</span>
                    <span>Summary</span>
                    <span>Link</span>
                  </div>
                  {(debateResult.wikipedia || []).length === 0 ? (
                    <div className="table-row empty">No Wikipedia matches.</div>
                  ) : (
                    debateResult.wikipedia.map((row) => (
                      <div className="table-row" key={row.url || row.title}>
                        <span>{row.title || '—'}</span>
                        <span>{row.summary || '—'}</span>
                        <span>
                          {row.url ? (
                            <a href={row.url} target="_blank" rel="noreferrer">
                              View
                            </a>
                          ) : (
                            '—'
                          )}
                        </span>
                      </div>
                    ))
                  )}
                </div>

                <div className="card-divider">
                  <h4>Strategy map</h4>
                </div>
                <div className="table">
                  <div className="table-row table-head">
                    <span>Theme</span>
                    <span>Mentions</span>
                    <span>Examples</span>
                  </div>
                  {(debateResult.themes || []).length === 0 ? (
                    <div className="table-row empty">No themes detected.</div>
                  ) : (
                    debateResult.themes.map((theme) => (
                      <div className="table-row" key={theme.name}>
                        <span>{theme.name}</span>
                        <span>{theme.count}</span>
                        <span>{(theme.examples || []).slice(0, 2).join(' · ') || '—'}</span>
                      </div>
                    ))
                  )}
                </div>

                <div className="card-divider">
                  <h4>Web mentions</h4>
                </div>
                <div className="table">
                  <div className="table-row table-head">
                    <span>Headline</span>
                    <span>Source</span>
                    <span>Snippet</span>
                    <span>Date</span>
                  </div>
                  {(debateResult.mentions || []).length === 0 ? (
                    <div className="table-row empty">No mentions found.</div>
                  ) : (
                    debateResult.mentions.map((row) => (
                      <div className="table-row" key={row.url || row.title}>
                        <span>
                          {row.url ? (
                            <a href={row.url} target="_blank" rel="noreferrer">
                              {row.title || '—'}
                            </a>
                          ) : (
                            row.title || '—'
                          )}
                        </span>
                        <span>{row.source || '—'}</span>
                        <span>{row.snippet || '—'}</span>
                        <span>{row.publishedAt || '—'}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {activeTab === 'configure' && (
        <div className="stack">
          <div className="module-card module-card__wide section-intro">
            <div className="card-header">
              <div>
                <h3>Set subject context</h3>
                <p className="muted">Pick a watchlist subject to prefill analysis.</p>
              </div>
              <div className="pill">Configure</div>
            </div>
          </div>
          <div className="module-grid">
          <div className="module-card">
            <h3>Network context</h3>
            <div className="metric-row">
              <span>People</span>
              <strong>{crmSummary?.total_people ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Supporters</span>
              <strong>{crmSummary?.supporters ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Members</span>
              <strong>{crmSummary?.members ?? '—'}</strong>
            </div>
          </div>
          <div className="module-card">
            <h3>Competitors</h3>
            <p className="muted">Pick a watchlist subject to use for analysis.</p>
            <select
              className="select"
              value={subjectName}
              onChange={(event) => {
                const selected = competitors.find(
                  (item) => item.name === event.target.value,
                )
                setSubjectName(selected?.name || '')
                setSubjectType(
                  selected?.competitorType === 'Company'
                    ? 'Organization'
                    : selected?.competitorType || 'Person',
                )
              }}
            >
              <option value="">Select competitor</option>
              {competitors.map((item) => (
                <option key={item.competitorId} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
            <button
              className="button"
              type="button"
              onClick={() => {
                if (activeCaseId) {
                  handleClearCase()
                }
                setActiveSubject(subjectName, subjectType, 'Configure')
              }}
            >
              Use for analysis
            </button>
          </div>
          </div>
        </div>
      )}

      {activeTab === 'watchlist' && (
        <div className="module-card module-card__wide section-intro">
          <div className="card-header">
            <div>
              <h3>Watchlist</h3>
              <p className="muted">Add people or companies you monitor regularly.</p>
            </div>
            <div className="pill">Due Diligence</div>
          </div>

          <form className="task-form" onSubmit={handleCreate}>
            <input
              className="input"
              placeholder="Competitor name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <select
              className="select"
              value={competitorType}
              onChange={(event) => setCompetitorType(event.target.value)}
            >
              <option value="Person">Person</option>
              <option value="Company">Company</option>
            </select>
            <input
              className="input"
              placeholder="Notes (optional)"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
            <button className="button" type="submit">
              {saving ? 'Saving…' : 'Add'}
            </button>
          </form>

          <div className="card-divider">
            <h4>CSV import</h4>
          </div>
          {importError ? <div className="module-alert">{importError}</div> : null}
          {importStatus ? (
            <div className="module-alert module-alert--success">{importStatus}</div>
          ) : null}
          <div className="stack">
            <input
              className="input"
              type="file"
              accept=".csv"
              onChange={(event) => handleImportWatchlist(event.target.files?.[0] || null)}
              disabled={importing}
            />
            <p className="muted">
              Required column: <strong>name</strong>. Optional: competitor_type, notes.
            </p>
          </div>

          <div className="table">
            <div className="table-row table-head">
              <span>Name</span>
              <span>Type</span>
              <span>Notes</span>
              <span>Action</span>
            </div>
            {competitors.length === 0 && (
              <div className="table-row empty">No competitors yet.</div>
            )}
            {competitors.map((item) => (
              <div className="table-row" key={item.competitorId}>
                <span>{item.name}</span>
                <span>{item.competitorType}</span>
                <span>{item.notes || '—'}</span>
                <div className="table-actions">
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleUseWatchlist(item)}
                  >
                    Use as subject
                  </button>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleDelete(item.competitorId)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'launch' && (
        <div className="module-card module-card__wide section-intro">
          <div className="card-header">
            <div>
              <h3>Launch</h3>
              <p className="muted">Open or embed the external DD app.</p>
            </div>
          </div>
          <div className="stack">
            {subjectName ? (
              <div className="module-alert module-alert--success">
                Launch subject: {subjectName} ({subjectType})
              </div>
            ) : (
              <div className="module-alert">No subject selected yet.</div>
            )}
            <input
              className="input"
              placeholder="Due diligence app URL"
              value={ddAppUrl}
              onChange={(event) => setDdAppUrl(event.target.value)}
            />
            <input className="input" value={launchUrl} readOnly />
            <div className="filter-row">
              <button
                className="button"
                type="button"
                onClick={() => window.open(launchUrl || ddAppUrl, '_blank')}
                disabled={!ddAppUrl}
              >
                Open DD app
              </button>
              <button
                className="button-secondary"
                type="button"
                onClick={() => window.open(gmailUrl, '_blank')}
                disabled={!subjectName}
              >
                Open in Gmail
              </button>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={embedApp}
                  onChange={(event) => setEmbedApp(event.target.checked)}
                />
                Embed app below
              </label>
            </div>
            <input
              className="input"
              placeholder="Gmail to (optional)"
              value={gmailTo}
              onChange={(event) => setGmailTo(event.target.value)}
            />
            {embedApp && launchUrl ? (
              <iframe
                title="Due Diligence App"
                src={launchUrl}
                className="dd-embed"
              />
            ) : null}
            {!ddAppUrl ? (
              <div className="module-alert">
                External DD app URL is not configured yet. Set `DUE_DILIGENCE_APP_URL` (or
                `DD_APP_URL`) in your environment.
              </div>
            ) : null}
          </div>
        </div>
      )}

      <div className="module-footer">
        <span>Backend scope:</span>
        <strong>Survey API + /due-diligence routes</strong>
      </div>
    </section>
  )
}
