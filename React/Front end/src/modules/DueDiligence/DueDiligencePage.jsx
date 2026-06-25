import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, Group, RingProgress, Text } from '@mantine/core'
import { IconAlertTriangle, IconFileSearch, IconShieldCheck, IconUsers } from '@tabler/icons-react'
import { getApiBaseUrl, getJson, requestJson } from '../../services/api'
import { CivicStatGrid, InfoBox } from '../../ui'
import { DdAnalysisResultPanels } from './DdAnalysisResultPanels.jsx'
import { normalizeStoredReportToAnalysisResult } from './duediligenceNormalize.js'

export function DueDiligencePage({
  t,
  activeTabOverride,
  onTabChange,
  showTabs = true,
  showIntro = true,
}) {
  const translate = t || ((key, vars) => key)
  const [activeTab, setActiveTab] = useState('overview')
  const applyActiveTab = (nextTab) => {
    if (!nextTab) return
    setActiveTab(nextTab)
    if (onTabChange) onTabChange(nextTab)
  }
  const getCaseDisplayName = (item) =>
    item?.subjectGeorgian || item?.subjectEnglish || item?.subject || ''
  const getCaseSecondaryName = (item) => {
    const primary = getCaseDisplayName(item)
    const secondary = [item?.subjectGeorgian, item?.subjectEnglish]
      .filter(Boolean)
      .find((value) => value !== primary)
    return secondary || ''
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
  const [caseSubjectGeorgian, setCaseSubjectGeorgian] = useState('')
  const [caseSubjectEnglish, setCaseSubjectEnglish] = useState('')
  const [caseSubject, setCaseSubject] = useState('')
  const [caseSubjectType, setCaseSubjectType] = useState('Person')
  const [newCaseOwner, setNewCaseOwner] = useState('')
  const [caseOwner, setCaseOwner] = useState('')
  const [subjectGeorgian, setSubjectGeorgian] = useState('')
  const [subjectEnglish, setSubjectEnglish] = useState('')
  const [caseStatus, setCaseStatus] = useState('Draft')
  const [caseNotice, setCaseNotice] = useState('')
  const [caseCreating, setCaseCreating] = useState(false)
  const [caseSaving, setCaseSaving] = useState(false)
  const [caseDeleting, setCaseDeleting] = useState(false)
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
  const [mediaSources, setMediaSources] = useState([])
  const [mediaSubject, setMediaSubject] = useState('')
  const [mediaTopics, setMediaTopics] = useState('')
  const [mediaMaxResults, setMediaMaxResults] = useState(12)
  const [mediaUsePublika, setMediaUsePublika] = useState(true)
  const [mediaUseInterpressnews, setMediaUseInterpressnews] = useState(true)
  const [mediaUseMeta, setMediaUseMeta] = useState(false)
  const [mediaLoading, setMediaLoading] = useState(false)
  const [mediaError, setMediaError] = useState('')
  const [mediaResult, setMediaResult] = useState(null)
  const [aiReportTopic] = useState('General')
  const [aiReportLoading, setAiReportLoading] = useState(false)
  const [aiReportError, setAiReportError] = useState('')
  const [aiReport, setAiReport] = useState(null)
  const [metaInfo, setMetaInfo] = useState(null)
  const [useWikidata, setUseWikidata] = useState(false)
  const [useWikipedia, setUseWikipedia] = useState(true)
  const [useOpenSanctions, setUseOpenSanctions] = useState(true)
  const [useNews, setUseNews] = useState(true)
  const [useDeclarations, setUseDeclarations] = useState(true)
  const [useDemo, setUseDemo] = useState(true)
  const [ddAppUrl, setDdAppUrl] = useState(
    () => localStorage.getItem('ddAppUrl') || '',
  )
  const [embedApp, setEmbedApp] = useState(false)
  const [gmailTo, setGmailTo] = useState(
    () => localStorage.getItem('ddGmailTo') || '',
  )
  const [selectedHistoryReportId, setSelectedHistoryReportId] = useState('')
  const [archivedReportLoading, setArchivedReportLoading] = useState(false)
  const [reportLoadError, setReportLoadError] = useState('')

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

  useEffect(() => {
    let mounted = true
    Promise.all([
      getJson('/due-diligence/media-sources'),
      getJson('/due-diligence/meta-content-library'),
    ])
      .then(([sourcesPayload, metaPayload]) => {
        if (!mounted) return
        setMediaSources(Array.isArray(sourcesPayload) ? sourcesPayload : [])
        setMetaInfo(metaPayload || null)
      })
      .catch(() => {
        if (!mounted) return
        setMediaSources([])
      })
    return () => {
      mounted = false
    }
  }, [])

  const loadCompetitors = () => {
    setError('')
    getJson('/due-diligence/competitors?limit=50')
      .then((payload) => {
        setCompetitors(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setError(err.message || 'Unable to load watchlist.')
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
      setSubjectGeorgian('')
      setSubjectEnglish('')
      setSubjectType('Person')
      setCaseStatus('Draft')
      setCaseOwner('')
      return
    }
    setActiveCase(found)
    setSubjectName(getCaseDisplayName(found))
    setSubjectGeorgian(found.subjectGeorgian || '')
    setSubjectEnglish(found.subjectEnglish || '')
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
    setSubjectGeorgian('')
    setSubjectEnglish('')
    setCaseStatus('Draft')
    setCaseOwner('')
    setCaseNotice('Case selection cleared. You can start a new case.')
  }

  const handleCreateCase = async () => {
    const subjectGeorgian = caseSubjectGeorgian.trim()
    const subjectEnglish = caseSubjectEnglish.trim()
    const subject = subjectGeorgian || subjectEnglish || caseSubject.trim()
    if (!subject) {
      setCaseNotice('Enter Georgian or English subject name to create a case.')
      return
    }
    setCaseCreating(true)
    setCaseNotice('')
    try {
      const payload = await requestJson('/due-diligence/cases', {
        method: 'POST',
        payload: {
          subject,
          subjectGeorgian,
          subjectEnglish,
          subjectType: caseSubjectType,
          owner: newCaseOwner.trim(),
          status: 'Draft',
        },
      })
      setCases((prev) => [payload, ...prev])
      setActiveCaseId(payload.caseId)
      setActiveCase(payload)
      setSubjectName(getCaseDisplayName(payload))
      setSubjectGeorgian(payload.subjectGeorgian || '')
      setSubjectEnglish(payload.subjectEnglish || '')
      setSubjectType(payload.subjectType || 'Person')
      setStartMode('Analysis')
      setCaseStatus(payload.status || 'Draft')
      setCaseOwner(payload.owner || '')
      setCaseSubjectGeorgian('')
      setCaseSubjectEnglish('')
      setCaseSubject('')
      setCaseSubjectType('Person')
      setNewCaseOwner('')
      setCaseNotice('Case created and selected.')
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
          subject: subjectName.trim() || subjectGeorgian.trim() || subjectEnglish.trim(),
          subjectGeorgian: subjectGeorgian.trim(),
          subjectEnglish: subjectEnglish.trim(),
          subjectType,
        },
      })
      setCases((prev) =>
        prev.map((item) => (item.caseId === activeCaseId ? payload : item)),
      )
      setActiveCase(payload)
      setSubjectName(getCaseDisplayName(payload))
      setSubjectGeorgian(payload.subjectGeorgian || '')
      setSubjectEnglish(payload.subjectEnglish || '')
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
          subjectEnglish: subjectName.trim(),
          subjectType,
          status: 'Draft',
        },
      })
      setCases((prev) => [payload, ...prev])
      setActiveCaseId(payload.caseId)
      setActiveCase(payload)
      setSubjectName(getCaseDisplayName(payload))
      setSubjectGeorgian(payload.subjectGeorgian || '')
      setSubjectEnglish(payload.subjectEnglish || '')
      setSubjectType(payload.subjectType || 'Person')
      setCaseStatus(payload.status || 'Draft')
      setCaseOwner(payload.owner || '')
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
      const watchlistMatches = await getJson(
        `/due-diligence/watchlist-matches?q=${encodeURIComponent(query)}&limit=50`,
      )
      setCrmMatches(Array.isArray(people) ? people : [])
      setCompetitorMatches(Array.isArray(watchlistMatches) ? watchlistMatches : [])
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
    setReportLoadError('')
    setSelectedHistoryReportId('')
    setAnalysisResult(null)
    setAnalysisProgress(5)
    const caseId = await ensureActiveCase()
    const enabled = []
    if (useWikipedia) enabled.push('Wikipedia')
    if (useOpenSanctions) enabled.push('OpenSanctions')
    if (useDeclarations) enabled.push('Asset declarations')
    enabled.push('Netgazeti', 'Publika', 'Interpressnews')
    const steps = [
      { id: 'validate', label: 'Validate subject', status: 'success' },
      {
        id: 'wikipedia',
        label: 'Query Wikipedia',
        status: useWikipedia ? 'running' : 'skipped',
      },
      {
        id: 'opensanctions',
        label: 'Query OpenSanctions',
        status: useOpenSanctions ? 'running' : 'skipped',
      },
      { id: 'media', label: 'Scan Georgian media', status: 'pending' },
      {
        id: 'declarations',
        label: 'Query asset declarations',
        status: useDeclarations ? 'running' : 'skipped',
      },
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
          useWikipedia,
          useOpenSanctions,
          useNews: false,
          useDeclarations,
          maxNews: 8,
          demo: useDemo,
        },
      })
      setAnalysisResult(result)
      let mediaScanWarning = false
      try {
        const mediaPayload = await requestJson('/due-diligence/media-monitor', {
          method: 'POST',
          payload: {
            subject: subjectName.trim(),
            subjectType,
            caseId: caseId || undefined,
            topics: aiReportTopic.trim() ? [aiReportTopic.trim()] : [],
            sourceIds: ['netgazeti', 'publika', 'interpressnews'],
            maxResults: Number(mediaMaxResults) || 12,
            persist: true,
          },
        })
        setMediaResult(mediaPayload)
        setMediaSubject(subjectName.trim())
      } catch (mediaErr) {
        mediaScanWarning = true
        const message = String(mediaErr?.message || '')
        if (message.toLowerCase().includes('not found')) {
          setMediaError('Georgian media scan is not available on this deployment yet. Main DD sources completed; redeploy the backend/main branch to enable media storage.')
        } else {
          setMediaError(message || 'Georgian media scan failed.')
        }
      }
      const warningsText = (result?.warnings || []).join(' ').toLowerCase()
      const hasWikipediaWarning = warningsText.includes('wikipedia request failed')
      const hasWikidataWarning = warningsText.includes('wikidata request failed')
      const hasOpenSanctionsWarning =
        warningsText.includes('opensanctions') &&
        (warningsText.includes('failed') ||
          warningsText.includes('not configured') ||
          warningsText.includes('api key'))
      const hasNewsWarning = warningsText.includes('gdelt news request failed')
      const hasDeclarationWarning =
        warningsText.includes('declaration') &&
        (warningsText.includes('failed') || warningsText.includes('not configured'))
      setAnalysisSteps((prev) =>
        prev.map((step) => {
          if (step.id === 'wikipedia') {
            if (!useWikipedia) return { ...step, status: 'skipped' }
            return { ...step, status: hasWikipediaWarning ? 'warning' : 'success' }
          }
          if (step.id === 'opensanctions') {
            if (!useOpenSanctions) return { ...step, status: 'skipped' }
            return { ...step, status: hasOpenSanctionsWarning ? 'warning' : 'success' }
          }
          if (step.id === 'media') {
            return { ...step, status: mediaScanWarning ? 'warning' : 'success' }
          }
          if (step.id === 'declarations') {
            if (!useDeclarations) return { ...step, status: 'skipped' }
            return { ...step, status: hasDeclarationWarning ? 'warning' : 'success' }
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
        `Due diligence scan complete for ${subjectName} (${subjectType}) using: ${
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

  const handleOpenReportFromHistory = async (reportId) => {
    if (!reportId) return
    setArchivedReportLoading(true)
    setReportLoadError('')
    try {
      const raw = await getJson(`/due-diligence/reports/${reportId}`)
      const normalized = normalizeStoredReportToAnalysisResult(raw)
      setAnalysisResult(normalized)
      setSelectedHistoryReportId(reportId)
      applyActiveTab('reports')
    } catch (err) {
      setReportLoadError(err.message || 'Unable to load report.')
    } finally {
      setArchivedReportLoading(false)
    }
  }

  const handleSaveSubjectToCase = async () => {
    if (!activeCaseId) {
      setCaseNotice('Select a case first.')
      return
    }
    if (!subjectName.trim()) {
      setCaseNotice('Enter a subject name.')
      return
    }
    setCaseSaving(true)
    setCaseNotice('')
    try {
      const payload = await requestJson(`/due-diligence/cases/${activeCaseId}`, {
        method: 'PATCH',
        payload: {
          subject: subjectName.trim(),
          subjectType,
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
      setCaseStatus(payload.status || 'Draft')
      setCaseOwner(payload.owner || '')
      setCaseNotice('Subject saved to case.')
      loadCases()
    } catch (err) {
      setCaseNotice(err.message || 'Unable to update case subject.')
    } finally {
      setCaseSaving(false)
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
    if (!activeCaseId && subjectName.trim()) {
      const match = cases.find((item) => getCaseDisplayName(item) === subjectName.trim() || item.subject === subjectName.trim())
      if (match) {
        setActiveCaseId(match.caseId)
      }
      return
    }
    if (!activeCaseId) return
    const found = cases.find((item) => item.caseId === activeCaseId)
    if (!found) return
    setActiveCase(found)
    setSubjectName(getCaseDisplayName(found))
    setSubjectGeorgian(found.subjectGeorgian || '')
    setSubjectEnglish(found.subjectEnglish || '')
    setSubjectType(found.subjectType || 'Person')
    setCaseStatus(found.status || 'Draft')
    setCaseOwner(found.owner || '')
  }, [cases, activeCaseId, subjectName])

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
    if (!mediaSubject && subjectName) {
      setMediaSubject(subjectName)
    }
  }, [mediaSubject, subjectName])

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
      use_wikipedia: useWikipedia ? '1' : '0',
      use_opensanctions: useOpenSanctions ? '1' : '0',
      use_declarations: useDeclarations ? '1' : '0',
      use_news: useNews ? '1' : '0',
    })
    const base = ddAppUrl.includes('?') ? `${ddAppUrl}&` : `${ddAppUrl}?`
    return `${base}${params.toString()}`
  }, [ddAppUrl, subjectName, subjectType, startMode, useWikidata, useWikipedia, useOpenSanctions, useNews, useDeclarations])

  const subjectStatus = subjectName.trim()
    ? internalChecksRan
      ? crmMatches.length + competitorMatches.length > 0
        ? 'Known'
        : 'New'
      : 'Not checked'
    : 'â€”'

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
      source: row.source || 'â€”',
      date: row.publishedAt || 'â€”',
      snippet: row.snippet || 'â€”',
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
      setError('Name is required.')
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
      setError(err.message || 'Unable to save watchlist entry.')
    } finally {
      setSaving(false)
    }
  }

  const handleRunMediaMonitor = async () => {
    const subject = mediaSubject.trim() || subjectName.trim()
    if (!subject) {
      setMediaError('Enter a person or organization to scan.')
      return
    }
    setMediaError('')
    setMediaResult(null)
    setMediaLoading(true)
    const topics = mediaTopics
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    const sourceIds = ['netgazeti']
    if (mediaUsePublika) sourceIds.push('publika')
    if (mediaUseInterpressnews) sourceIds.push('interpressnews')
    if (mediaUseMeta) sourceIds.push('meta_content_library')
    try {
      const result = await requestJson('/due-diligence/media-monitor', {
        method: 'POST',
        payload: {
          subject,
          subjectType,
          caseId: activeCaseId || undefined,
          topics,
          sourceIds,
          maxResults: Number(mediaMaxResults) || 12,
          persist: true,
        },
      })
      setMediaResult(result)
    } catch (err) {
      setMediaError(err.message || 'Media scan failed.')
    } finally {
      setMediaLoading(false)
    }
  }
  const handleGenerateAiReport = async () => {
    const subject = subjectName.trim() || mediaSubject.trim()
    if (!subject) {
      setAiReportError('Enter or select a subject first.')
      return
    }
    if (!analysisResult && !mediaResult) {
      setAiReportError('Run external analysis or media scan before generating the AI report.')
      return
    }
    setAiReportError('')
    setAiReport(null)
    setAiReportLoading(true)
    try {
      const result = await requestJson('/due-diligence/ai-report', {
        method: 'POST',
        payload: {
          subject,
          subjectType,
          caseId: activeCaseId || undefined,
          topic: aiReportTopic.trim() || 'General',
          analysis: analysisResult || undefined,
          media: mediaResult || undefined,
        },
      })
      setAiReport(result)
    } catch (err) {
      setAiReportError(err.message || 'Unable to generate AI report.')
    } finally {
      setAiReportLoading(false)
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

  const handleArchiveCase = async () => {
    if (!activeCaseId || caseDeleting) return
    setCaseDeleting(true)
    setCaseNotice('')
    try {
      const payload = await requestJson(`/due-diligence/cases/${activeCaseId}/archive`, {
        method: 'POST',
      })
      setCases((prev) => prev.map((item) => (item.caseId === activeCaseId ? payload : item)))
      setActiveCase(payload)
      setCaseStatus(payload.status || 'Archived')
      setCaseNotice('Case archived.')
    } catch (err) {
      setCaseNotice(err.message || 'Unable to archive case.')
    } finally {
      setCaseDeleting(false)
    }
  }

  const handleDeleteCase = async () => {
    if (!activeCaseId || caseDeleting) return
    const ok = window.confirm('Delete this DD case? Reports and media evidence remain, but the case record will be removed.')
    if (!ok) return
    setCaseDeleting(true)
    setCaseNotice('')
    try {
      await requestJson(`/due-diligence/cases/${activeCaseId}`, { method: 'DELETE' })
      setCases((prev) => prev.filter((item) => item.caseId !== activeCaseId))
      handleClearCase()
      setCaseNotice('Case deleted.')
    } catch (err) {
      setCaseNotice(err.message || 'Unable to delete case.')
    } finally {
      setCaseDeleting(false)
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
      setError(err.message || 'Unable to delete watchlist entry.')
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
        setImportStatus(`Imported ${created} watchlist entries.`)
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

  const caseStatusOptions = ['Draft', 'Active', 'Review', 'Decided', 'Closed', 'Archived']
  const taskStatusOptions = ['Open', 'In Progress', 'Blocked', 'Done']

  const duePulseStats = useMemo(
    () => [
      {
        label: 'Watchlist',
        value: summary?.competitors ?? 'â€”',
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
      <div className={showTabs ? 'module-layout' : 'module-layout module-layout--stacked'}>
        <aside className="module-sidebar">
          <div className="sidebar-card">
            <h3>Start a new case</h3>
            <p className="muted">Capture the subject and assign ownership.</p>
            <div className="filter-row">
              <input
                className="input"
                placeholder="Georgian name"
                value={caseSubjectGeorgian}
                onChange={(event) => setCaseSubjectGeorgian(event.target.value)}
              />
              <input
                className="input"
                placeholder="English name"
                value={caseSubjectEnglish}
                onChange={(event) => setCaseSubjectEnglish(event.target.value)}
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
              <button
                className="button"
                type="button"
                onClick={handleCreateCase}
                disabled={caseCreating}
              >
                {caseCreating ? 'Creating...' : 'Create case'}
              </button>
            </div>
            {caseNotice ? <div className="module-alert">{caseNotice}</div> : null}
          </div>

          <div className="sidebar-card">
            <div className="card-header">
              <div>
                <h3>Cases</h3>
                <p className="muted">Select a case to open the workspace.</p>
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
                <div className="table-row empty">Loading casesâ€¦</div>
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
                    <span>
                      {getCaseDisplayName(row) || 'â€”'}
                      {getCaseSecondaryName(row) ? (
                        <small className="muted">{getCaseSecondaryName(row)}</small>
                      ) : null}
                    </span>
                    <span>{row.status || 'Draft'}</span>
                    <span>{row.lastRiskLevel || 'â€”'}</span>
                    <span>{row.updatedAt || row.createdAt || 'â€”'}</span>
                  </button>
                ))
              )}
            </div>
            <div className="module-footer">
              <span>
                {activeCaseId
                  ? `Active case: ${getCaseDisplayName(activeCase) || 'â€”'}`
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
        </aside>

        <div className="module-main">
          {showIntro ? (
            <div className="module-card module-card__wide section-intro">
              <div className="card-header">
                <div>
                  <h3>{translate('dueDiligence.header.title')}</h3>
                  <p className="muted">{translate('dueDiligence.header.subtitle')}</p>
                </div>
                <div className="pill">Due Diligence</div>
              </div>
            </div>
          ) : null}

          {error ? <div className="module-alert">{error}</div> : null}

          <details className="dashboard-detail">
            <summary>Risk pipeline stats</summary>
            <div className="dashboard-detail__body">
              <div className="module-header__meta">
                <div className="module-header__metric">
                  <span>Watchlist</span>
                  <strong>{summary?.competitors ?? 'â€”'}</strong>
                </div>
                <div className="module-header__metric">
                  <span>Network People</span>
                  <strong>{crmSummary?.total_people ?? 'â€”'}</strong>
                </div>
                <div className="module-header__metric">
                  <span>Supporters</span>
                  <strong>{crmSummary?.supporters ?? 'â€”'}</strong>
                </div>
              </div>
            </div>
          </details>

          <CivicStatGrid
            title="Risk intelligence pulse"
            description="Signals across watchlist, network matches, and internal checks."
            items={duePulseStats}
          />

          {showTabs ? (
            <div className="subtabs">
              {[
                { id: 'overview', label: 'Case' },
                { id: 'checks', label: 'Run DD' },
                { id: 'reports', label: 'Report' },
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

          {activeCaseId ? (
            <div className="module-alert module-alert--success">
              Active case: {getCaseDisplayName(activeCase) || 'â€”'} Â· {caseStatus}
            </div>
          ) : (
            <div className="module-alert">
              Select a case to begin. Create a new case in the left panel if needed.
            </div>
          )}

          {activeTab === 'overview' && (
            <div className="stack">
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

              {activeCaseId ? (
                <div className="module-card">
                  <div className="card-header">
                    <div>
                      <h3>Profile</h3>
                      <p className="muted">Profile identity, case status, and latest DD signal.</p>
                    </div>
                  </div>
                  <div className="metric-row">
                    <span>Case ID</span>
                    <strong>{activeCaseId}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Georgian name</span>
                    <strong>{subjectGeorgian || 'â€”'}</strong>
                  </div>
                  <div className="metric-row">
                    <span>English name</span>
                    <strong>{subjectEnglish || 'â€”'}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Search/display name</span>
                    <strong>
                      {subjectName.trim() ? `${subjectName} (${subjectType})` : 'â€”'}
                    </strong>
                  </div>
                  <div className="metric-row">
                    <span>Status</span>
                    <strong>{caseStatus}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Owner</span>
                    <strong>{caseOwner || 'â€”'}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Last risk</span>
                    <strong>{activeCase?.lastRiskLevel || 'â€”'}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Last report</span>
                    <strong>{activeCase?.lastReportAt || 'â€”'}</strong>
                  </div>
                  <div className="filter-row">
                    <input
                      className="input"
                      placeholder="Georgian name"
                      value={subjectGeorgian}
                      onChange={(event) => {
                        setSubjectGeorgian(event.target.value)
                        if (!subjectEnglish.trim()) setSubjectName(event.target.value)
                      }}
                    />
                    <input
                      className="input"
                      placeholder="English name"
                      value={subjectEnglish}
                      onChange={(event) => {
                        setSubjectEnglish(event.target.value)
                        if (!subjectGeorgian.trim()) setSubjectName(event.target.value)
                      }}
                    />
                    <input
                      className="input"
                      placeholder="Display/search name"
                      value={subjectName}
                      onChange={(event) => setSubjectName(event.target.value)}
                    />
                    <select
                      className="select"
                      value={subjectType}
                      onChange={(event) => setSubjectType(event.target.value)}
                    >
                      <option value="Person">Person</option>
                      <option value="Organization">Organization</option>
                    </select>
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
                      {caseSaving ? 'Savingâ€¦' : 'Update case'}
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={handleArchiveCase}
                      disabled={caseDeleting || caseStatus === 'Archived'}
                    >
                      Archive
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={handleDeleteCase}
                      disabled={caseDeleting}
                    >
                      Delete
                    </button>
                  </div>
                  {caseNotice ? <div className="module-alert">{caseNotice}</div> : null}
                </div>
              ) : null}
            </div>
          )}

          {activeTab === 'checks' && (
            <div className="stack">
              <div className="module-card module-card__wide section-intro">
                <div className="card-header">
                  <div>
                    <h3>Checks</h3>
                    <p className="muted">
                      Confirm the subject, scan internal records, then run public-source checks.
                    </p>
                  </div>
                </div>
                {!activeCaseId ? (
                  <div className="module-alert">
                    Select a case to run checks. Running analysis can auto-create a draft case.
                  </div>
                ) : null}
                <InfoBox
                  title="Quick steps"
                  summary="1) Confirm subject  2) Check internal records  3) Run public-source analysis"
                  hint="Internal checks scan Network + watchlist. Public-source analysis pulls Wikidata, OpenSanctions, GDELT, and Netgazeti fallback where available."
                />
                <div className="filter-row">
                  <input
                    className="input"
                    placeholder="Enter person or organization"
                    value={subjectName}
                    onChange={(event) => setSubjectName(event.target.value)}
                  />
                  <select
                    className="select"
                    value={subjectType}
                    onChange={(event) => setSubjectType(event.target.value)}
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
                    <>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={handleSaveSubjectToCase}
                        disabled={caseSaving}
                      >
                        {caseSaving ? 'Savingâ€¦' : 'Save subject to case'}
                      </button>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={handleClearCase}
                      >
                        Clear case
                      </button>
                    </>
                  ) : null}
                </div>
                <p className="muted">Internal checks look at Network + watchlist for matches.</p>

                <p className="muted">
                  Current subject:{' '}
                  <strong>
                    {subjectName.trim() ? `${subjectName} (${subjectType})` : 'â€”'}
                  </strong>
                </p>
              </div>

              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Internal checks</h3>
                    <p className="muted">Network + watchlist match signals.</p>
                  </div>
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
                            <span>{row.group || 'â€”'}</span>
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
                            <span>{row.notes || 'â€”'}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </details>
              </div>

              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Run due diligence</h3>
                    <p className="muted">
                      One scan checks the configured sources and stores evidence on this case.
                    </p>
                  </div>
                  <div className="pill">Configured</div>
                </div>
                <div className="filter-row">
                  {['Wikipedia', 'OpenSanctions', 'Netgazeti', 'Publika', 'Interpressnews', 'Asset declarations'].map((source) => (
                    <span className="pill" key={source}>{source}</span>
                  ))}
                </div>
                <div className="filter-row">
                  <button className="button" type="button" onClick={handleRunAnalysis} disabled={analysisLoading || mediaLoading}>
                    {analysisLoading || mediaLoading ? 'Running...' : 'Run DD scan'}
                  </button>
                </div>
                {analysisError ? <div className="module-alert">{analysisError}</div> : null}
                {mediaError ? <div className="module-alert">{mediaError}</div> : null}
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
                  <DdAnalysisResultPanels
                    analysisResult={analysisResult}
                    onViewFullSources={() => applyActiveTab('reports')}
                    showSourceDetails={false}
                  />
                ) : null}
                {mediaResult ? (
                  <div className="module-alert module-alert--success">
                    Georgian media: {mediaResult.mentions?.length ?? 0} mentions fetched, {mediaResult.storedCount ?? 0} stored.
                  </div>
                ) : null}
              </div>
            </div>
          )}

          {activeTab === 'media' && (
            <div className="stack">
              <div className="module-card module-card__wide section-intro">
                <div className="card-header">
                  <div>
                    <h3>Media database</h3>
                    <p className="muted">
                      Build profile evidence from media mentions, quotes, topics, and source relationships.
                    </p>
                  </div>
                  <div className="pill">Netgazeti first</div>
                </div>
                <InfoBox
                  title="Connector model"
                  summary="Netgazeti, Publika, and Interpressnews run as Georgian media sources. Meta Content Library is tracked as an access-required source."
                  hint="Fetched evidence is stored against the selected due diligence profile and case when a case is active."
                />
              </div>

              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>Sources</h3>
                    <p className="muted">Available connectors for profile media intelligence.</p>
                  </div>
                </div>
                <div className="table">
                  <div className="table-row table-head">
                    <span>Source</span>
                    <span>Status</span>
                    <span>Access</span>
                    <span>Notes</span>
                  </div>
                  {mediaSources.length === 0 ? (
                    <div className="table-row empty">No media sources loaded.</div>
                  ) : (
                    mediaSources.map((source) => (
                      <div className="table-row" key={source.sourceId}>
                        <span>{source.name}</span>
                        <span>{source.status}</span>
                        <span>{source.accessModel}</span>
                        <span>{source.notes}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>Run media scan</h3>
                    <p className="muted">Search Georgian online media and store profile-linked evidence.</p>
                  </div>
                </div>
                <div className="filter-row">
                  <input
                    className="input"
                    placeholder="Person or organization"
                    value={mediaSubject}
                    onChange={(event) => setMediaSubject(event.target.value)}
                  />
                  <input
                    className="input"
                    placeholder="Topics, comma-separated"
                    value={mediaTopics}
                    onChange={(event) => setMediaTopics(event.target.value)}
                  />
                  <input
                    className="input"
                    type="number"
                    min="1"
                    max="50"
                    value={mediaMaxResults}
                    onChange={(event) => setMediaMaxResults(event.target.value)}
                  />
                  <button
                    className="button"
                    type="button"
                    onClick={handleRunMediaMonitor}
                    disabled={mediaLoading}
                  >
                    {mediaLoading ? 'Scanningâ€¦' : 'Scan media'}
                  </button>
                </div>
                <div className="filter-row">
                  <label className="checkbox">
                    <input type="checkbox" checked readOnly />
                    Netgazeti
                  </label>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={mediaUsePublika}
                      onChange={(event) => setMediaUsePublika(event.target.checked)}
                    />
                    Publika
                  </label>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={mediaUseInterpressnews}
                      onChange={(event) => setMediaUseInterpressnews(event.target.checked)}
                    />
                    Interpressnews
                  </label>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={mediaUseMeta}
                      onChange={(event) => setMediaUseMeta(event.target.checked)}
                    />
                    Include Meta access check
                  </label>
                </div>
                {mediaError ? <div className="module-alert">{mediaError}</div> : null}
                {mediaResult?.warnings?.length ? (
                  <div className="module-alert">
                    {mediaResult.warnings.map((warning, idx) => (
                      <div key={`${warning}-${idx}`}>{warning}</div>
                    ))}
                  </div>
                ) : null}
                {mediaResult ? (
                  <div className="module-alert module-alert--success">
                    {mediaResult.mentions?.length ?? 0} mentions fetched Â·{' '}
                    {mediaResult.storedCount ?? 0} stored
                  </div>
                ) : null}
              </div>

              {metaInfo ? (
                <details className="dashboard-detail">
                  <summary>Meta Content Library research path</summary>
                  <div className="dashboard-detail__body">
                    <p className="muted">{metaInfo.fitForDueDiligence}</p>
                    <p className="muted">{metaInfo.eligibleUsers}</p>
                    <div className="table">
                      <div className="table-row table-head">
                        <span>Access step</span>
                      </div>
                      {(metaInfo.accessSteps || []).map((step) => (
                        <div className="table-row" key={step}>
                          <span>{step}</span>
                        </div>
                      ))}
                    </div>
                    <a href={metaInfo.sourceUrl} target="_blank" rel="noreferrer">
                      Meta documentation
                    </a>
                  </div>
                </details>
              ) : null}

              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>Mentions and quotes</h3>
                    <p className="muted">Evidence stays linked to the original article URL.</p>
                  </div>
                </div>
                <div className="table">
                  <div className="table-row table-head">
                    <span>Article</span>
                    <span>Source</span>
                    <span>Topics</span>
                    <span>Quotes</span>
                  </div>
                  {!mediaResult?.mentions?.length ? (
                    <div className="table-row empty">No media mentions loaded yet.</div>
                  ) : (
                    mediaResult.mentions.map((mention) => (
                      <div className="table-row" key={mention.url}>
                        <span>
                          <a href={mention.url} target="_blank" rel="noreferrer">
                            {mention.title}
                          </a>
                          <small className="muted">{mention.publishedAt || ''}</small>
                        </span>
                        <span>{mention.source}</span>
                        <span>{mention.matchedTopics?.join(', ') || 'â€”'}</span>
                        <span>
                          {mention.quotes?.length
                            ? mention.quotes.map((quote) => `â€œ${quote.text}â€`).join(' / ')
                            : 'â€”'}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
          {activeTab === 'reports' && (
            <div className="stack">
              <div className="module-card module-card__wide section-intro">
                <div className="card-header">
                  <div>
                    <h3>Reports</h3>
                    <p className="muted">Open saved reports, inspect source evidence, and download PDFs.</p>
                  </div>
                </div>
                {!activeCaseId && !subjectName.trim() ? (
                  <div className="module-alert">
                    Select a case (or enter a subject in Checks) to view report history.
                  </div>
                ) : null}
              </div>

              {reportLoadError ? <div className="module-alert">{reportLoadError}</div> : null}

              {selectedHistoryReportId ? (
                <div className="module-alert module-alert--success">
                  Viewing saved report <strong>{selectedHistoryReportId}</strong>
                  <span className="filter-row" style={{ display: 'inline-flex', marginLeft: 12 }}>
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => {
                        setSelectedHistoryReportId('')
                        setAnalysisResult(null)
                      }}
                    >
                      Close detail
                    </button>
                  </span>
                </div>
              ) : null}

              <div className="module-card module-card__wide">
                <div className="card-header">
                  <div>
                    <h3>AI synthesized report</h3>
                    <p className="muted">
                      Combine Wikidata, OpenSanctions, news, and media scan evidence into a topic-based analyst brief.
                    </p>
                  </div>
                  <div className="pill">AI layer</div>
                </div>
                <div className="filter-row">
                  <button
                    className="button"
                    type="button"
                    onClick={handleGenerateAiReport}
                    disabled={aiReportLoading || (!analysisResult && !mediaResult)}
                  >
                    {aiReportLoading ? 'Generating...' : 'Generate AI report'}
                  </button>
                </div>
                {!analysisResult && !mediaResult ? (
                  <p className="muted">Run external analysis or scan media first, then generate the synthesized report.</p>
                ) : null}
                {aiReportError ? <div className="module-alert">{aiReportError}</div> : null}
                {aiReport ? (
                  <div className="stack">
                    <div className="module-alert module-alert--success">
                      {aiReport.mode?.startsWith?.('ai:') ? 'AI-generated' : 'Structured'} report for{' '}
                      <strong>{aiReport.subject}</strong> on <strong>{aiReport.topic}</strong>
                    </div>
                    {aiReport.warnings?.length ? (
                      <div className="module-alert">
                        {aiReport.warnings.map((warning, idx) => (
                          <div key={`${warning}-${idx}`}>{warning}</div>
                        ))}
                      </div>
                    ) : null}
                    {aiReport.sections?.length ? (
                      <div className="stack">
                        <div>
                          <h3>{aiReport.reportTitle || `Due Diligence Report: ${aiReport.subject}`}</h3>
                          <p className="muted">
                            {[aiReport.classification, aiReport.topic].filter(Boolean).join(' - ')}
                          </p>
                        </div>
                        {aiReport.sections.map((section, idx) => (
                          <section className="module-card" key={`${section.heading || 'section'}-${idx}`}>
                            <h4>{section.heading || `Section ${idx + 1}`}</h4>
                            {(section.paragraphs || []).map((paragraph, pIdx) => (
                              <p key={`${section.heading || idx}-p-${pIdx}`}>{paragraph}</p>
                            ))}
                            {section.bullets?.length ? (
                              <ul className="compact-list">
                                {section.bullets.map((item, bIdx) => (
                                  <li key={`${section.heading || idx}-b-${bIdx}`}>{item}</li>
                                ))}
                              </ul>
                            ) : null}
                            {section.evidenceRefs?.length ? (
                              <p className="muted">Evidence: {section.evidenceRefs.join(', ')}</p>
                            ) : null}
                          </section>
                        ))}
                      </div>
                    ) : (
                      <>
                        <div>
                          <h4>Executive summary</h4>
                          <p>{aiReport.executiveSummary}</p>
                        </div>
                        <div className="module-grid">
                          <div className="module-card">
                            <h4>Key findings</h4>
                            <ul className="compact-list">
                              {(aiReport.keyFindings || []).map((item, idx) => (
                                <li key={`${item}-${idx}`}>{item}</li>
                              ))}
                            </ul>
                          </div>
                          <div className="module-card">
                            <h4>Risk assessment</h4>
                            <p>{aiReport.riskAssessment}</p>
                          </div>
                        </div>
                        <div>
                          <h4>Topic assessment</h4>
                          <p>{aiReport.topicAssessment}</p>
                        </div>
                      </>
                    )}
                    <div className="table">
                      <div className="table-row table-head">
                        <span>ID / Evidence</span>
                        <span>Source</span>
                        <span>Date</span>
                      </div>
                      {((aiReport.evidenceTable?.length ? aiReport.evidenceTable : aiReport.evidence) || []).length === 0 ? (
                        <div className="table-row empty">No evidence selected for this topic.</div>
                      ) : (
                        (aiReport.evidenceTable?.length ? aiReport.evidenceTable : aiReport.evidence).map((row, idx) => (
                          <div className="table-row" key={`${row.id || row.url || row.title || row.claim}-${idx}`}>
                            <span>
                              {row.url ? (
                                <a href={row.url} target="_blank" rel="noreferrer">
                                  {row.id ? `${row.id}: ` : ''}{row.claim || row.title || 'Source'}
                                </a>
                              ) : (
                                `${row.id ? `${row.id}: ` : ''}${row.claim || row.title || 'Source'}`
                              )}
                              {row.snippet ? <small className="muted">{row.snippet}</small> : null}
                            </span>
                            <span>{row.source || '-'}</span>
                            <span>{row.date || '-'}</span>
                          </div>
                        ))
                      )}
                    </div>
                    <div className="module-grid">
                      <div className="module-card">
                        <h4>Recommended actions</h4>
                        <ul className="compact-list">
                          {(aiReport.recommendedActions || []).map((item, idx) => (
                            <li key={`${item}-${idx}`}>{item}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="module-card">
                        <h4>Limitations</h4>
                        <ul className="compact-list">
                          {((aiReport.limitations?.length ? aiReport.limitations : aiReport.caveats) || []).map((item, idx) => (
                            <li key={`${item}-${idx}`}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>

              {analysisResult ? (
                <div className="module-card module-card__wide">
                  <div className="card-header">
                    <div>
                      <h3>{selectedHistoryReportId ? 'Report detail' : 'Latest analysis detail'}</h3>
                      <p className="muted">
                        {selectedHistoryReportId
                          ? 'Loaded from history (GET /reports/:id).'
                          : 'Sources and evidence from the most recent run.'}
                      </p>
                    </div>
                  </div>
                  <DdAnalysisResultPanels
                    analysisResult={analysisResult}
                    showViewFullSourcesButton={false}
                    showSourceDetails
                  />
                </div>
              ) : null}

              {activeCaseId || subjectName.trim() ? (
                <details className="dashboard-detail" open>
                  <summary>Report history ({reportHistory.length})</summary>
                  <div className="dashboard-detail__body">
                    <div className="table">
                      <div className="table-row table-head">
                        <span>Created</span>
                        <span>Risk</span>
                        <span>Total hits</span>
                        <span>Sources</span>
                        <span>Open</span>
                        <span>PDF</span>
                      </div>
                      {historyLoading ? (
                        <div className="table-row empty">Loading report historyâ€¦</div>
                      ) : reportHistory.length === 0 ? (
                        <div className="table-row empty">No prior reports for this case or subject.</div>
                      ) : (
                        reportHistory.map((row) => (
                          <div className="table-row" key={row.reportId}>
                            <span>{row.createdAt || 'â€”'}</span>
                            <span>{row.riskLevel || 'â€”'}</span>
                            <span>{row.totalHits ?? 0}</span>
                            <span>{(row.sources || []).join(', ') || 'â€”'}</span>
                            <span>
                              <button
                                type="button"
                                className="button-secondary"
                                onClick={() => handleOpenReportFromHistory(row.reportId)}
                                disabled={archivedReportLoading}
                              >
                                {archivedReportLoading ? 'Loadingâ€¦' : 'Open'}
                              </button>
                            </span>
                            <span>
                              <a
                                href={`${getApiBaseUrl()}/due-diligence/reports/${row.reportId}/pdf`}
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
          )}

          {activeTab === 'decision' && (
            <div className="module-card">
              <h3>Decision</h3>
              <p className="muted">Record the case outcome after reviewing profile, media, and report evidence.</p>
              {!activeCaseId ? (
                <div className="module-alert">Select a case to record a decision.</div>
              ) : null}
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
                  {decisionSaving ? 'Savingâ€¦' : 'Save decision'}
                </button>
              </div>
              {decisionError ? <div className="module-alert">{decisionError}</div> : null}
              {decisionNotice ? (
                <div className="module-alert module-alert--success">{decisionNotice}</div>
              ) : null}
            </div>
          )}

          {activeTab === 'advanced' && (
            <div className="stack">
              <details className="dashboard-detail">
                <summary>Configure subject context</summary>
                <div className="dashboard-detail__body">
                  <div className="module-grid">
                    <div className="module-card">
                      <h3>Network context</h3>
                      <div className="metric-row">
                        <span>People</span>
                        <strong>{crmSummary?.total_people ?? 'â€”'}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Supporters</span>
                        <strong>{crmSummary?.supporters ?? 'â€”'}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Members</span>
                        <strong>{crmSummary?.members ?? 'â€”'}</strong>
                      </div>
                    </div>
                    <div className="module-card">
                      <h3>Watchlist</h3>
                      <p className="muted">Pick a watchlist entry to use for analysis.</p>
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
                        <option value="">Select watchlist entry</option>
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
              </details>

              <details className="dashboard-detail">
                <summary>Watchlist</summary>
                <div className="dashboard-detail__body">
                  <form className="task-form" onSubmit={handleCreate}>
                    <input
                      className="input"
                      placeholder="Name"
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
                      {saving ? 'Savingâ€¦' : 'Add'}
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
                      <div className="table-row empty">No watchlist entries yet.</div>
                    )}
                    {competitors.map((item) => (
                      <div className="table-row" key={item.competitorId}>
                        <span>{item.name}</span>
                        <span>{item.competitorType}</span>
                        <span>{item.notes || 'â€”'}</span>
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
              </details>

              <details className="dashboard-detail">
                <summary>Debate prep</summary>
                <div className="dashboard-detail__body">
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
                        {debateLoading ? 'Runningâ€¦' : 'Run debate prep'}
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
                        Use demo data for Wikidata/OpenSanctions/News only
                      </label>
                    </div>
                    {debateError ? <div className="module-alert">{debateError}</div> : null}
                    {debateResult ? (
                      <div className="stack">
                        <div className="module-alert module-alert--success">
                          {debateResult.mentions?.length ?? 0} mentions Â·{' '}
                          {debateResult.startDate} â†’ {debateResult.endDate}
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
                                      {card.source} Â· {card.date}
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
                                <span>{row.title || 'â€”'}</span>
                                <span>{row.summary || 'â€”'}</span>
                                <span>
                                  {row.url ? (
                                    <a href={row.url} target="_blank" rel="noreferrer">
                                      View
                                    </a>
                                  ) : (
                                    'â€”'
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
                                <span>
                                  {(theme.examples || []).slice(0, 2).join(' Â· ') || 'â€”'}
                                </span>
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
                                      {row.title || 'â€”'}
                                    </a>
                                  ) : (
                                    row.title || 'â€”'
                                  )}
                                </span>
                                <span>{row.source || 'â€”'}</span>
                                <span>{row.snippet || 'â€”'}</span>
                                <span>{row.publishedAt || 'â€”'}</span>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </details>

              <details className="dashboard-detail">
                <summary>Launch external DD app</summary>
                <div className="dashboard-detail__body">
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
                        External DD app URL is not configured yet. Set `DUE_DILIGENCE_APP_URL`
                        (or `DD_APP_URL`) in your environment.
                      </div>
                    ) : null}
                  </div>
                </div>
              </details>
            </div>
          )}
        </div>
      </div>

      <div className="module-footer">
        <span>Backend scope:</span>
        <strong>Survey API + /due-diligence routes</strong>
      </div>
    </section>
  )
}






