import { useEffect, useMemo, useRef, useState } from 'react'
import QRCode from 'qrcode'
import {
  getJson,
  requestForm,
  requestJson,
} from '../../services/api'
import {
  getInviteAudienceGroupEmail,
  getInviteAudienceLabel,
  openExternalShareLink,
} from '../../lib/inviteDistribution'
import { CivicStatGrid, PageHeader } from '../../ui'
import {
  IconBrandSlack,
  IconBrandWhatsapp,
  IconCircleCheck,
  IconCircleX,
  IconCopy,
  IconDownload,
  IconExternalLink,
  IconFileText,
  IconMail,
  IconPlus,
  IconQrcode,
  IconRefresh,
  IconSend,
  IconTrash,
  IconUsers,
  IconTarget,
} from '@tabler/icons-react'
import { Bar, Doughnut, Pie, PolarArea } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  Legend,
  LinearScale,
  RadialLinearScale,
  Tooltip,
} from 'chart.js'
import '../../styles/network-report.css'
import CRMNeighborhoodMap from './components/map/CRMNeighborhoodMap'

const NETWORK_CLIENT_CACHE_MS = 10 * 60 * 1000
let cachedNetworkDashboard = null

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  Tooltip,
  Legend,
)

const csvEscape = (value) => {
  if (value === null || value === undefined) return ''
  const text = String(value)
  if (text.includes('"') || text.includes(',') || text.includes('\n')) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

const toCsv = (rows) => {
  if (!Array.isArray(rows) || rows.length === 0) return ''
  const headers = Array.from(
    rows.reduce((acc, row) => {
      Object.keys(row || {}).forEach((key) => acc.add(key))
      return acc
    }, new Set()),
  )
  const lines = [headers.join(',')]
  rows.forEach((row) => {
    const line = headers.map((key) => csvEscape(row?.[key])).join(',')
    lines.push(line)
  })
  return lines.join('\n')
}

const downloadCsv = (filename, rows) => {
  const csv = toCsv(rows)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const splitFullName = (fullName) => {
  const parts = String(fullName || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return { firstName: '', lastName: '' }
  if (parts.length === 1) return { firstName: parts[0], lastName: '' }
  return { firstName: parts[0], lastName: parts.slice(1).join(' ') }
}

const renderTemplate = (template, context) => {
  if (!template) return ''
  return template.replace(/\{(\w+)\}/g, (_, key) => context?.[key] ?? '')
}

/** Human-readable lines for saved segment filterSpec (matches CRM segment form). */
const formatSegmentFilterSummary = (spec) => {
  if (!spec || typeof spec !== 'object') return '-'
  const s = spec
  const lines = []
  if (s.group && s.group !== 'All') lines.push(`Group: ${s.group}`)
  const ta = s.timeAvailability ?? s.time_availability
  if (Array.isArray(ta) && ta.length) lines.push(`Time availability: ${ta.join(', ')}`)
  if (Array.isArray(s.tags) && s.tags.length) lines.push(`Tags: ${s.tags.join(', ')}`)
  if (Array.isArray(s.skills) && s.skills.length) lines.push(`Skills: ${s.skills.join(', ')}`)
  const nameQ = String(s.nameContains ?? s.name_contains ?? '').trim()
  if (nameQ) lines.push(`Name contains: ${nameQ}`)
  const addrQ = String(s.addressContains ?? s.address_contains ?? '').trim()
  if (addrQ) lines.push(`Address contains: ${addrQ}`)
  if (s.gender && s.gender !== 'All') lines.push(`Gender: ${s.gender}`)
  const minAge = s.minAge ?? s.min_age
  const maxAge = s.maxAge ?? s.max_age
  if (minAge != null && minAge !== '') lines.push(`Min age: ${minAge}`)
  if (maxAge != null && maxAge !== '') lines.push(`Max age: ${maxAge}`)
  const cityQ = String(s.cityContains ?? s.city_contains ?? '').trim()
  if (cityQ) lines.push(`City contains: ${cityQ}`)
  const districtQ = String(s.districtContains ?? s.district_contains ?? '').trim()
  if (districtQ) lines.push(`District contains: ${districtQ}`)
  const manifesto = s.agreesWithManifesto ?? s.agrees_with_manifesto
  if (manifesto != null) lines.push(`Manifesto: ${manifesto ? 'Yes' : 'No'}`)
  const membership = s.interestedInMembership ?? s.interested_in_membership
  if (membership != null) lines.push(`Membership interest: ${membership ? 'Yes' : 'No'}`)
  const hasEmail = s.hasEmail ?? s.has_email
  if (hasEmail != null) lines.push(`Has email: ${hasEmail ? 'Yes' : 'No'}`)
  const hasPhone = s.hasPhone ?? s.has_phone
  if (hasPhone != null) lines.push(`Has phone: ${hasPhone ? 'Yes' : 'No'}`)
  const me = s.minEffortHours ?? s.min_effort_hours
  if (me != null && Number(me) > 0) lines.push(`Min effort hours: ${me}`)
  if (!lines.length) return 'All people (no filters)'
  return lines.join('\n')
}

const toYouTubeEmbedUrl = (rawUrl) => {
  const value = String(rawUrl || '').trim()
  if (!value) return ''
  try {
    const url = new URL(value)
    const host = url.hostname.toLowerCase()
    if (host.includes('youtube.com')) {
      if (url.pathname === '/watch') {
        const videoId = url.searchParams.get('v')
        return videoId ? `https://www.youtube.com/embed/${videoId}` : ''
      }
      if (url.pathname.startsWith('/embed/')) {
        return value
      }
      if (url.pathname.startsWith('/shorts/')) {
        const videoId = url.pathname.split('/').filter(Boolean)[1]
        return videoId ? `https://www.youtube.com/embed/${videoId}` : ''
      }
    }
    if (host.includes('youtu.be')) {
      const videoId = url.pathname.replace('/', '').trim()
      return videoId ? `https://www.youtube.com/embed/${videoId}` : ''
    }
  } catch (error) {
    return ''
  }
  return ''
}

const CRM_TAB_STORAGE_KEY = 'fs.crm.activeTab'
const CRM_DEFAULT_TAB = 'overview'
const CRM_TASKS_ENABLED = false
const CRM_PRIMARY_TABS = new Set(
  ['overview', 'intake', 'people', 'segments', CRM_TASKS_ENABLED ? 'tasks' : null].filter(Boolean),
)
const CRM_WORKSPACE_TABS = new Set(['outreach', 'campaigns'])

const normalizeCrmTab = (tabId) => {
  if (!tabId) return CRM_DEFAULT_TAB
  if (tabId === 'events') return 'outreach'
  if (!CRM_TASKS_ENABLED && tabId === 'tasks') return CRM_DEFAULT_TAB
  if (CRM_PRIMARY_TABS.has(tabId) || CRM_WORKSPACE_TABS.has(tabId)) return tabId
  return CRM_DEFAULT_TAB
}

export function CRMPage({
  t,
  initialTab,
  hideTabs = false,
  activeTabOverride,
  onTabChange,
  showTabs = true,
  showIntro = true,
}) {
  const translate = t || ((key, vars) => key)
  const [summary, setSummary] = useState(null)
  const [people, setPeople] = useState([])
  const [error, setError] = useState('')
  const [peopleError, setPeopleError] = useState('')
  const [peopleLoading, setPeopleLoading] = useState(false)
  const [peopleQuery, setPeopleQuery] = useState('')
  const [peopleGroup, setPeopleGroup] = useState('All')
  const [peopleTableSort, setPeopleTableSort] = useState({
    key: 'name',
    direction: 'asc',
  })
  const [activeTab, setActiveTab] = useState(() => {
    if (initialTab) return normalizeCrmTab(initialTab)
    if (typeof window === 'undefined') return CRM_DEFAULT_TAB
    const stored = window.localStorage.getItem(CRM_TAB_STORAGE_KEY)
    return normalizeCrmTab(stored)
  })
  const [selectedEmail, setSelectedEmail] = useState('')
  const [supporterInviteStats, setSupporterInviteStats] = useState(null)
  const [supporterInvites, setSupporterInvites] = useState([])
  const [pendingSupporterSignups, setPendingSupporterSignups] = useState([])
  const [supporterInviteLoading, setSupporterInviteLoading] = useState(false)
  const [supporterInviteError, setSupporterInviteError] = useState('')
  const [supporterInviteStatus, setSupporterInviteStatus] = useState('')
  const [invitePipelineFilter, setInvitePipelineFilter] = useState('all')
  const [supporterReminderSendingCode, setSupporterReminderSendingCode] = useState('')
  const [supporterApprovalProcessingEmail, setSupporterApprovalProcessingEmail] = useState('')
  const [supporterSignupVideoUrl, setSupporterSignupVideoUrl] = useState('')
  const [supporterThankYouVideoUrl, setSupporterThankYouVideoUrl] = useState('')
  const [supporterSignupVideoSaving, setSupporterSignupVideoSaving] = useState(false)
  const [supporterInviteGroupsConfig, setSupporterInviteGroupsConfig] = useState({
    everyoneGroupEmail: '',
    verifiedGroupEmail: '',
    registeredGroupEmail: '',
  })
  const [supporterInviteForm, setSupporterInviteForm] = useState({
    recipientName: '',
    recipientEmail: '',
    recipientPhone: '',
    channel: 'email',
    inviteAudience: 'individual',
    supporterType: 'Supporter',
    notes: '',
  })
  const [latestSupporterInviteLink, setLatestSupporterInviteLink] = useState('')
  const [latestSupporterInviteType, setLatestSupporterInviteType] = useState('Supporter')
  const [supporterQrExpanded, setSupporterQrExpanded] = useState(false)
  const [supporterQrDataUrl, setSupporterQrDataUrl] = useState('')
  const [overviewMapStats, setOverviewMapStats] = useState(null)

  const normalizeTab = (tabId) => {
    return normalizeCrmTab(tabId)
  }

  const applyActiveTab = (nextTab) => {
    const normalized = normalizeTab(nextTab)
    setActiveTab(normalized)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(CRM_TAB_STORAGE_KEY, normalized)
    }
    if (onTabChange) onTabChange(normalized)
  }

  useEffect(() => {
    if (initialTab) {
      applyActiveTab(initialTab)
    }
  }, [initialTab])

  useEffect(() => {
    if (activeTabOverride) {
      const normalized = normalizeTab(activeTabOverride)
      if (normalized && normalized !== activeTab) {
        setActiveTab(normalized)
      }
    }
  }, [activeTabOverride, activeTab])

  const [profile, setProfile] = useState(null)
  const [profileDraft, setProfileDraft] = useState(null)
  const [profileError, setProfileError] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [furryRows, setFurryRows] = useState([])
  const [furryError, setFurryError] = useState('')
  const [furryLoading, setFurryLoading] = useState(false)
  const [furryQuery, setFurryQuery] = useState('')
  const [furrySpecies, setFurrySpecies] = useState('All')
  const [furrySort, setFurrySort] = useState('Name')
  const [selectedFurryId, setSelectedFurryId] = useState('')
  const [furryProfile, setFurryProfile] = useState(null)
  const [furryProfileDraft, setFurryProfileDraft] = useState(null)
  const [furryProfileError, setFurryProfileError] = useState('')
  const [furryProfileSaving, setFurryProfileSaving] = useState(false)
  const [furryImportFile, setFurryImportFile] = useState(null)
  const [furryImportStatus, setFurryImportStatus] = useState('')
  const [tasks, setTasks] = useState([])
  const [tasksError, setTasksError] = useState('')
  const [tasksLoading, setTasksLoading] = useState(false)
  const [taskFilterStatus, setTaskFilterStatus] = useState('All')
  const [taskFilterGroup, setTaskFilterGroup] = useState('All')
  const [taskLimit, setTaskLimit] = useState(200)
  const [newTaskEmail, setNewTaskEmail] = useState('')
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [newTaskDescription, setNewTaskDescription] = useState('')
  const [newTaskDueDate, setNewTaskDueDate] = useState('')
  const [newTaskStatus, setNewTaskStatus] = useState('Open')
  const [taskUpdateId, setTaskUpdateId] = useState('')
  const [taskUpdateStatus, setTaskUpdateStatus] = useState('Open')
  const [segments, setSegments] = useState([])
  const [segmentsError, setSegmentsError] = useState('')
  const [segmentsLoading, setSegmentsLoading] = useState(false)
  const [segmentName, setSegmentName] = useState('')
  const [segmentDescription, setSegmentDescription] = useState('')
  const [segmentGroup, setSegmentGroup] = useState('All')
  const [segmentNameContains, setSegmentNameContains] = useState('')
  const [segmentAddressContains, setSegmentAddressContains] = useState('')
  const [segmentGender, setSegmentGender] = useState('All')
  const [segmentMinAge, setSegmentMinAge] = useState('')
  const [segmentMaxAge, setSegmentMaxAge] = useState('')
  const [segmentCityContains, setSegmentCityContains] = useState('')
  const [segmentDistrictContains, setSegmentDistrictContains] = useState('')
  const [segmentManifesto, setSegmentManifesto] = useState('All')
  const [segmentMembershipInterest, setSegmentMembershipInterest] = useState('All')
  const [segmentHasEmail, setSegmentHasEmail] = useState('All')
  const [segmentHasPhone, setSegmentHasPhone] = useState('All')
  const [segmentTimeAvailability, setSegmentTimeAvailability] = useState('All')
  const [segmentTags, setSegmentTags] = useState([])
  const [segmentSkills, setSegmentSkills] = useState([])
  const [segmentTagOptions, setSegmentTagOptions] = useState([])
  const [segmentSkillOptions, setSegmentSkillOptions] = useState([])
  const [segmentMinEffort, setSegmentMinEffort] = useState('')
  const [segmentLimit, setSegmentLimit] = useState(75)
  const [segmentSelectedId, setSegmentSelectedId] = useState('')
  const [segmentResults, setSegmentResults] = useState([])
  const [segmentRunLoading, setSegmentRunLoading] = useState(false)
  const [segmentMemberCount, setSegmentMemberCount] = useState(null)
  const [segmentCountLoading, setSegmentCountLoading] = useState(false)
  const [showNewSegmentForm, setShowNewSegmentForm] = useState(false)
  const [segmentTaskTitle, setSegmentTaskTitle] = useState('')
  const [segmentTaskDescription, setSegmentTaskDescription] = useState('')
  const [segmentTaskDueDate, setSegmentTaskDueDate] = useState('')
  const [segmentTaskStatus, setSegmentTaskStatus] = useState('Open')
  const [segmentTaskSaving, setSegmentTaskSaving] = useState(false)
  const [segmentTaskError, setSegmentTaskError] = useState('')
  const [outreachDistributionError, setOutreachDistributionError] = useState('')
  const [outreachDistributionStatus, setOutreachDistributionStatus] = useState('')
  const [individualQuery, setIndividualQuery] = useState('')
  const [individualResults, setIndividualResults] = useState([])
  const [individualSelected, setIndividualSelected] = useState([])
  const [individualLoading, setIndividualLoading] = useState(false)
  const [individualError, setIndividualError] = useState('')
  const [individualTaskTitle, setIndividualTaskTitle] = useState('')
  const [individualTaskDescription, setIndividualTaskDescription] = useState('')
  const [individualTaskDueDate, setIndividualTaskDueDate] = useState('')
  const [individualTaskStatus, setIndividualTaskStatus] = useState('Open')
  const [individualTaskSaving, setIndividualTaskSaving] = useState(false)
  const [segmentEventName, setSegmentEventName] = useState('')
  const [segmentEventStatus, setSegmentEventStatus] = useState('Planned')
  const [segmentEventStartDate, setSegmentEventStartDate] = useState('')
  const [segmentEventEndDate, setSegmentEventEndDate] = useState('')
  const [segmentEventLocation, setSegmentEventLocation] = useState('')
  const [segmentEventCapacity, setSegmentEventCapacity] = useState('')
  const [segmentEventNotes, setSegmentEventNotes] = useState('')
  const [segmentEventStatusMessage, setSegmentEventStatusMessage] = useState('')
  const [outreachAttachLoading, setOutreachAttachLoading] = useState(false)
  const [outreachAttachMessage, setOutreachAttachMessage] = useState('')
  const [showNewEventForm, setShowNewEventForm] = useState(false)
  const [outreachEvents, setOutreachEvents] = useState([])
  const [outreachEventsError, setOutreachEventsError] = useState('')
  const [outreachEventId, setOutreachEventId] = useState('')
  const [outreachInviteForm, setOutreachInviteForm] = useState({
    inviteAudience: 'individual',
    recipientName: '',
    recipientEmail: '',
    recipientPhone: '',
    channel: 'email',
    notes: '',
  })

  useEffect(() => {
    let mounted = true
    getJson('/crm/summary')
      .then((summaryPayload) => {
        if (!mounted) return
        setSummary(summaryPayload)
      })
      .catch((err) => {
        if (!mounted) return
        setError(err.message || 'Unable to load NCC data.')
      })
    return () => {
      mounted = false
    }
  }, [])

  const peopleSearchParams = useMemo(() => {
    const params = new URLSearchParams()
    if (peopleGroup !== 'All') {
      params.set('group', peopleGroup)
    }
    if (peopleQuery.trim()) {
      params.set('q', peopleQuery.trim())
    }
    params.set('limit', '200')
    return params.toString()
  }, [peopleGroup, peopleQuery])

  const supporterSignupBaseLink = useMemo(() => {
    if (typeof window === 'undefined') return ''
    const url = new URL(window.location.pathname || '/', window.location.origin)
    url.searchParams.set('supporter_signup', '1')
    return url.toString()
  }, [])
  const supporterSignupVideoEmbedUrl = useMemo(
    () => toYouTubeEmbedUrl(supporterSignupVideoUrl),
    [supporterSignupVideoUrl],
  )
  const supporterThankYouVideoEmbedUrl = useMemo(
    () => toYouTubeEmbedUrl(supporterThankYouVideoUrl),
    [supporterThankYouVideoUrl],
  )

  const furrySearchParams = useMemo(() => {
    const params = new URLSearchParams()
    if (furrySpecies !== 'All') {
      params.set('species', furrySpecies)
    }
    if (furryQuery.trim()) {
      params.set('q', furryQuery.trim())
    }
    const sortMap = {
      Name: 'name',
      Age: 'age',
      Municipality: 'municipality',
      Species: 'species',
    }
    if (sortMap[furrySort]) {
      params.set('sort', sortMap[furrySort])
    }
    params.set('limit', '1000')
    return params.toString()
  }, [furryQuery, furrySpecies, furrySort])

  const furryTotalCount = useMemo(() => furryRows.length, [furryRows])
  const furryDogCount = useMemo(
    () => furryRows.filter((row) => row.species === 'Dog').length,
    [furryRows],
  )
  const furryCatCount = useMemo(
    () => furryRows.filter((row) => row.species === 'Cat').length,
    [furryRows],
  )
  const furryMapRows = useMemo(() => {
    return furryRows.filter((row) => Number.isFinite(Number(row.lat)) && Number.isFinite(Number(row.lon)))
  }, [furryRows])
  const furryMapCenter = useMemo(() => {
    if (!furryMapRows.length) return [41.7151, 44.8271]
    const latSum = furryMapRows.reduce((acc, row) => acc + Number(row.lat), 0)
    const lonSum = furryMapRows.reduce((acc, row) => acc + Number(row.lon), 0)
    return [latSum / furryMapRows.length, lonSum / furryMapRows.length]
  }, [furryMapRows])

  const loadPeople = () => {
    setPeopleLoading(true)
    setPeopleError('')
    const suffix = peopleSearchParams ? `?${peopleSearchParams}` : ''
    getJson(`/crm/people/summary${suffix}`)
      .then((payload) => {
        const nextPeople = Array.isArray(payload) ? payload : []
        setPeople(nextPeople)
        if (selectedEmail) {
          const stillExists = nextPeople.some((person) => (person.email || person.personId) === selectedEmail)
          if (!stillExists) {
            setSelectedEmail('')
            setProfile(null)
            setProfileDraft(null)
            setProfileError('')
          }
        }
      })
      .catch((err) => {
        setPeopleError(err.message || 'Unable to load people.')
      })
      .finally(() => {
        setPeopleLoading(false)
      })
  }

  const normalizeSupporterTypeLabel = (value) =>
    String(value || '')
      .toLowerCase()
      .includes('member')
      ? 'Member'
      : 'Supporter'

  const buildSupporterInviteLink = (inviteCode, supporterType, existingInviteUrl = '') => {
    if (existingInviteUrl) return existingInviteUrl
    if (!supporterSignupBaseLink) return ''
    const url = new URL(supporterSignupBaseLink)
    if (inviteCode) {
      url.searchParams.set('invite_code', inviteCode)
    }
    const normalizedType = normalizeSupporterTypeLabel(supporterType)
    if (normalizedType) {
      url.searchParams.set('supporter_type', normalizedType.toLowerCase())
    }
    return url.toString()
  }

  const buildSupporterReminderMessage = (invite) => {
    const name = invite?.recipientName || 'there'
    const link = buildSupporterInviteLink(
      invite?.inviteCode || '',
      invite?.supporterType || 'Supporter',
      invite?.inviteUrl || '',
    )
    return `Hi ${name}, just a reminder to complete your supporter/member registration:\n${link}`
  }

  const setInviteAudienceGroupEmail = (audience, value) => {
    if (audience === 'everyone') {
      setSupporterInviteGroupsConfig((prev) => ({ ...prev, everyoneGroupEmail: value }))
      return
    }
    if (audience === 'verified') {
      setSupporterInviteGroupsConfig((prev) => ({ ...prev, verifiedGroupEmail: value }))
      return
    }
    if (audience === 'registered') {
      setSupporterInviteGroupsConfig((prev) => ({ ...prev, registeredGroupEmail: value }))
      return
    }
    if (audience === 'segment') {
      return
    }
  }

  const buildSupporterInviteShareMessage = (
    inviteLink,
    inviteType,
    recipientName = '',
    inviteAudience = 'individual',
  ) => {
    const typeLabel = normalizeSupporterTypeLabel(inviteType).toLowerCase()
    if (inviteAudience && inviteAudience !== 'individual') {
      return `Hi team, here is the Freedom Square ${typeLabel} signup form for ${getInviteAudienceLabel(inviteAudience)}:\n${inviteLink}`
    }
    const name = recipientName || 'there'
    return `Hi ${name}, here is your Freedom Square ${typeLabel} signup form:\n${inviteLink}`
  }

  const handleShareSupporterInviteByChannel = async ({
    channel,
    inviteAudience,
    inviteLink,
    inviteType,
    recipientName,
    recipientEmail,
    recipientPhone,
  }) => {
    if (!inviteLink) return
    const normalizedChannel = String(channel || '').toLowerCase()
    const normalizedAudience = String(inviteAudience || 'individual').toLowerCase()
    const message = buildSupporterInviteShareMessage(
      inviteLink,
      inviteType,
      recipientName,
      normalizedAudience,
    )
    if (normalizedChannel === 'email') {
      setSupporterInviteStatus('Invite email was sent directly.')
      return
    }
    if (normalizedChannel === 'whatsapp') {
      const text = encodeURIComponent(message)
      const phone = String(recipientPhone || '').replace(/[^\d]/g, '')
      const whatsappUrl = phone ? `https://wa.me/${phone}?text=${text}` : `https://wa.me/?text=${text}`
      openExternalShareLink(whatsappUrl)
      setSupporterInviteStatus('Invite link created and WhatsApp share opened.')
      return
    }
    if (normalizedChannel === 'slack') {
      if (!navigator?.clipboard) {
        setSupporterInviteError('Clipboard unavailable in this browser.')
        return
      }
      try {
        await navigator.clipboard.writeText(message)
        setSupporterInviteStatus('Invite link created and Slack message copied.')
      } catch (err) {
        setSupporterInviteError('Invite created, but unable to copy Slack message.')
      }
      return
    }
    setSupporterInviteStatus('Invite link created.')
  }

  const loadSupporterInvites = () => {
    setSupporterInviteLoading(true)
    setSupporterInviteError('')
    Promise.allSettled([
      getJson('/crm/supporter-invites/stats'),
      getJson('/crm/supporter-invites?limit=50'),
      getJson('/crm/supporter-signups/pending?limit=100'),
      getJson('/crm/supporter-signup-config'),
      getJson('/crm/supporter-invite-groups-config'),
    ])
      .then(([statsResult, invitesResult, pendingResult, configResult, groupsConfigResult]) => {
        const statsPayload = statsResult.status === 'fulfilled' ? statsResult.value : null
        const invitesPayload = invitesResult.status === 'fulfilled' ? invitesResult.value : []
        const pendingPayload = pendingResult.status === 'fulfilled' ? pendingResult.value : []
        const configPayload = configResult.status === 'fulfilled' ? configResult.value : null
        const groupsConfigPayload =
          groupsConfigResult.status === 'fulfilled' ? groupsConfigResult.value : null
        setSupporterInviteStats(statsPayload || null)
        setSupporterInvites(Array.isArray(invitesPayload) ? invitesPayload : [])
        setPendingSupporterSignups(Array.isArray(pendingPayload) ? pendingPayload : [])
        setSupporterSignupVideoUrl(configPayload?.welcomeVideoUrl || '')
        setSupporterThankYouVideoUrl(configPayload?.thankYouVideoUrl || '')
        setSupporterInviteGroupsConfig({
          everyoneGroupEmail: groupsConfigPayload?.everyoneGroupEmail || '',
          verifiedGroupEmail: groupsConfigPayload?.verifiedGroupEmail || '',
          registeredGroupEmail: groupsConfigPayload?.registeredGroupEmail || '',
        })
        if (statsResult.status === 'rejected' || invitesResult.status === 'rejected') {
          setSupporterInviteError('Unable to load invite metrics right now.')
        }
      })
      .finally(() => {
        setSupporterInviteLoading(false)
      })
  }

  useEffect(() => {
    if (activeTab !== 'people' && activeTab !== 'intake' && activeTab !== 'outreach') return
    if (activeTab === 'people') {
      loadPeople()
    }
    loadSupporterInvites()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, peopleGroup])
  const parseNumber = (value) => {
    if (value === null || value === undefined || value === '') return null
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
    const match = String(value).match(/[\d.]+/)
    return match ? Number(match[0]) : null
  }

  const getPeopleSortValue = (person, key) => {
    switch (key) {
      case 'name':
        return person.fullName || person.email || ''
      case 'email':
        return person.email || ''
      case 'group':
        return person.group || ''
      case 'effort':
        return parseNumber(person.effortScore ?? person.effortHours) ?? null
      case 'events':
        return parseNumber(person.eventAttendCount) ?? null
      case 'referrals':
        return parseNumber(person.referralCount) ?? null
      case 'rating': {
        const ratingValue = parseNumber(person.rating ?? person.ratingStars)
        return ratingValue ?? null
      }
      default:
        return ''
    }
  }

  const sortedPeople = useMemo(() => {
    if (!peopleTableSort?.key) return people
    const { key, direction } = peopleTableSort
    const dir = direction === 'desc' ? -1 : 1
    const copy = [...people]
    copy.sort((a, b) => {
      const aValue = getPeopleSortValue(a, key)
      const bValue = getPeopleSortValue(b, key)
      const aMissing = aValue === null || aValue === undefined || aValue === ''
      const bMissing = bValue === null || bValue === undefined || bValue === ''
      if (aMissing && bMissing) return 0
      if (aMissing) return 1
      if (bMissing) return -1
      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return (aValue - bValue) * dir
      }
      return (
        String(aValue).localeCompare(String(bValue), undefined, {
          numeric: true,
          sensitivity: 'base',
        }) * dir
      )
    })
    return copy
  }, [people, peopleTableSort])

  const handlePeopleSortChange = (key) => {
    setPeopleTableSort((prev) => {
      if (!prev || prev.key !== key) {
        return { key, direction: 'asc' }
      }
      return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
    })
  }

  const renderPeopleSortButton = (label, key) => {
    const isActive = peopleTableSort?.key === key
    const dirLabel = isActive ? (peopleTableSort.direction === 'asc' ? 'asc' : 'desc') : ''
    return (
      <button
        type="button"
        className={`table-sort ${isActive ? 'is-active' : ''}`}
        onClick={() => handlePeopleSortChange(key)}
      >
        <span>{label}</span>
        {dirLabel ? <span className="table-sort__dir">{dirLabel}</span> : null}
      </button>
    )
  }

  const handlePeopleSearch = (event) => {
    event.preventDefault()
    loadPeople()
  }

  const handleCreateSupporterInvite = async (event) => {
    event.preventDefault()
    setSupporterInviteError('')
    setSupporterInviteStatus('')
    const recipientName = supporterInviteForm.recipientName.trim()
    const recipientEmail = supporterInviteForm.recipientEmail.trim()
    const recipientPhone = supporterInviteForm.recipientPhone.trim()
    const selectedChannel = supporterInviteForm.channel
    const selectedAudience = supporterInviteForm.inviteAudience || 'individual'
    try {
      if (selectedChannel === 'email') {
        await requestJson('/crm/supporter-invite-groups-config', {
          method: 'PATCH',
          payload: {
            everyoneGroupEmail: supporterInviteGroupsConfig.everyoneGroupEmail.trim(),
            verifiedGroupEmail: supporterInviteGroupsConfig.verifiedGroupEmail.trim(),
            registeredGroupEmail: supporterInviteGroupsConfig.registeredGroupEmail.trim(),
          },
        })
      }
      const targetEmail =
        selectedChannel === 'email' && selectedAudience !== 'individual'
          ? getInviteAudienceGroupEmail(selectedAudience, supporterInviteGroupsConfig)
          : recipientEmail
      const payload = await requestJson('/crm/supporter-invites', {
        method: 'POST',
        payload: {
          recipientName,
          recipientEmail: targetEmail,
          recipientPhone,
          channel: selectedChannel,
          inviteAudience: selectedAudience,
          supporterType: supporterInviteForm.supporterType,
          notes: '',
        },
      })
      const inviteType = normalizeSupporterTypeLabel(
        payload?.supporterType || supporterInviteForm.supporterType,
      )
      const link = buildSupporterInviteLink(payload?.inviteCode || '', inviteType, payload?.inviteUrl || '')
      setLatestSupporterInviteLink(link)
      setLatestSupporterInviteType(inviteType)
      if (selectedChannel === 'email') {
        if (payload?.emailSent) {
          setSupporterInviteStatus(`Invite email sent to ${payload?.recipientEmail || targetEmail}.`)
        } else {
          setSupporterInviteStatus(
            `Invite created but email failed (${payload?.emailStatus || 'unknown'}).`,
          )
        }
      } else {
        await handleShareSupporterInviteByChannel({
          channel: selectedChannel,
          inviteAudience: selectedAudience,
          inviteLink: link,
          inviteType,
          recipientName: payload?.recipientName || recipientName,
          recipientEmail: payload?.recipientEmail || recipientEmail,
          recipientPhone: payload?.recipientPhone || recipientPhone,
        })
      }
      setSupporterInviteForm((prev) => ({
        ...prev,
        recipientName: '',
        recipientEmail: '',
        recipientPhone: '',
        notes: '',
      }))
      loadSupporterInvites()
    } catch (err) {
      setSupporterInviteError(err.message || 'Unable to create supporter invite.')
    }
  }

  const handleCopySupporterInviteLink = async (value) => {
    if (!value) return
    setSupporterInviteStatus('')
    if (!navigator?.clipboard) {
      setSupporterInviteError('Clipboard unavailable in this browser.')
      return
    }
    try {
      await navigator.clipboard.writeText(value)
      setSupporterInviteStatus('Link copied.')
    } catch (err) {
      setSupporterInviteError('Unable to copy invite link.')
    }
  }

  const handleSaveSupporterSignupVideo = async () => {
    setSupporterInviteError('')
    setSupporterInviteStatus('')
    const trimmedWelcome = supporterSignupVideoUrl.trim()
    const trimmedThankYou = supporterThankYouVideoUrl.trim()
    if (trimmedWelcome && !toYouTubeEmbedUrl(trimmedWelcome)) {
      setSupporterInviteError('Please add a valid YouTube link.')
      return
    }
    if (trimmedThankYou && !toYouTubeEmbedUrl(trimmedThankYou)) {
      setSupporterInviteError('Please add a valid YouTube link.')
      return
    }
    setSupporterSignupVideoSaving(true)
    try {
      await requestJson('/crm/supporter-signup-config', {
        method: 'PATCH',
        payload: { welcomeVideoUrl: trimmedWelcome, thankYouVideoUrl: trimmedThankYou },
      })
      setSupporterInviteStatus('Signup videos updated.')
    } catch (err) {
      setSupporterInviteError(err.message || 'Unable to save signup videos.')
    } finally {
      setSupporterSignupVideoSaving(false)
    }
  }

  const handleSendSupporterReminder = async (invite) => {
    if (!invite?.inviteCode) return
    setSupporterInviteError('')
    setSupporterInviteStatus('')
    setSupporterReminderSendingCode(invite.inviteCode)
    try {
      const response = await requestJson(`/crm/supporter-invites/${encodeURIComponent(invite.inviteCode)}/remind`, {
        method: 'POST',
        payload: {
          channel: invite.channel || 'manual',
          note: 'Manual reminder sent from People directory.',
        },
      })

      let statusMessage = ''
      if (response.emailSent) {
        statusMessage = `Sent: Reminder email sent to ${invite.recipientEmail || invite.inviteCode}.`
      } else {
        statusMessage = `Warning: Reminder tracked but email failed (${response.emailStatus}). Check email configuration.`
      }

      const reminderText = buildSupporterReminderMessage(invite)
      if (navigator?.clipboard) {
        await navigator.clipboard.writeText(reminderText)
        statusMessage += ' Message copied to clipboard.'
      }

      setSupporterInviteStatus(statusMessage)
      loadSupporterInvites()
    } catch (err) {
      setSupporterInviteError(err.message || 'Unable to send reminder.')
    } finally {
      setSupporterReminderSendingCode('')
    }
  }

  const handleApprovePendingSupporterSignup = async (person) => {
    const email = person?.email || ''
    const signupId = person?.signupId || ''
    if (!email && !signupId) return
    setSupporterInviteError('')
    setSupporterInviteStatus('')
    const approveKey = signupId || email
    setSupporterApprovalProcessingEmail(approveKey)
    try {
      if (signupId) {
        await requestJson(`/crm/supporter-signups/by-id/${encodeURIComponent(signupId)}/approve`, {
          method: 'POST',
        })
      } else {
        await requestJson(`/crm/supporter-signups/${encodeURIComponent(email)}/approve`, {
          method: 'POST',
        })
      }
      setSupporterInviteStatus(`Approved ${email || signupId} for Network.`)
      loadSupporterInvites()
    } catch (err) {
      setSupporterInviteError(err.message || 'Unable to approve supporter/member.')
    } finally {
      setSupporterApprovalProcessingEmail('')
    }
  }

  const handleDeclinePendingSupporterSignup = async (person) => {
    const email = person?.email || ''
    const signupId = person?.signupId || ''
    if (!email && !signupId) return
    setSupporterInviteError('')
    setSupporterInviteStatus('')
    const declineKey = signupId || email
    setSupporterApprovalProcessingEmail(declineKey)
    try {
      if (signupId) {
        await requestJson(`/crm/supporter-signups/by-id/${encodeURIComponent(signupId)}/decline`, {
          method: 'POST',
        })
      } else {
        await requestJson(`/crm/supporter-signups/${encodeURIComponent(email)}/decline`, {
          method: 'POST',
        })
      }
      setSupporterInviteStatus(`Declined ${email || signupId}.`)
      loadSupporterInvites()
    } catch (err) {
      setSupporterInviteError(err.message || 'Unable to decline supporter/member.')
    } finally {
      setSupporterApprovalProcessingEmail('')
    }
  }

  const loadProfile = (email) => {
    if (!email) return
    setProfileLoading(true)
    setProfileError('')
    getJson(`/crm/people/${encodeURIComponent(email)}`, { cacheMs: 30000 })
      .then((payload) => {
        setProfile(payload)
        setProfileDraft((current) => ({ ...(current || {}), ...(payload || {}) }))
      })
      .catch((err) => {
        setProfileError(err.message || 'Unable to load profile.')
      })
      .finally(() => {
        setProfileLoading(false)
      })
  }

  useEffect(() => {
    if (!selectedEmail) {
      setProfile(null)
      setProfileDraft(null)
      return
    }
    loadProfile(selectedEmail)
  }, [selectedEmail])

  const handleSelectPerson = (person) => {
    const identifier = person?.email || person?.personId
    if (!identifier) return
    const nameParts = String(person.fullName || '').trim().split(/\s+/).filter(Boolean)
    setSelectedEmail(identifier)
    setProfileError('')
    setProfileDraft({
      personId: person.personId || identifier,
      email: person.email || '',
      firstName: person.firstName || nameParts[0] || '',
      lastName: person.lastName || nameParts.slice(1).join(' '),
      phone: person.phone || '',
      gender: person.gender || '',
      age: person.age || '',
      timeAvailability: person.timeAvailability || 'Unspecified',
      about: person.about || '',
      agreesWithManifesto: !!person.agreesWithManifesto,
      interestedInMembership: !!person.interestedInMembership,
      facebookGroupMember: !!person.facebookGroupMember,
    })
  }

  const updateProfileField = (field, value) => {
    setProfileDraft((prev) => ({ ...(prev || {}), [field]: value }))
  }

  const handleProfileSave = async () => {
    if (!selectedEmail || !profileDraft) return
    setProfileSaving(true)
    setProfileError('')
    try {
      const payload = {
        firstName: profileDraft.firstName || '',
        lastName: profileDraft.lastName || '',
        phone: profileDraft.phone || '',
        gender: profileDraft.gender || '',
        age: profileDraft.age ? Number(profileDraft.age) : null,
        timeAvailability: profileDraft.timeAvailability || 'Unspecified',
        about: profileDraft.about || '',
        agreesWithManifesto: !!profileDraft.agreesWithManifesto,
        interestedInMembership: !!profileDraft.interestedInMembership,
        facebookGroupMember: !!profileDraft.facebookGroupMember,
      }
      const updated = await requestJson(`/crm/people/${encodeURIComponent(selectedEmail)}`, {
        method: 'PATCH',
        payload,
      })
      setProfile(updated)
      setProfileDraft(updated)
    } catch (err) {
      setProfileError(err.message || 'Unable to save profile.')
    } finally {
      setProfileSaving(false)
    }
  }

  const loadFurryFriends = () => {
    setFurryLoading(true)
    setFurryError('')
    const suffix = furrySearchParams ? `?${furrySearchParams}` : ''
    getJson(`/crm/furry/summary${suffix}`)
      .then((payload) => {
        const nextRows = Array.isArray(payload) ? payload : []
        setFurryRows(nextRows)
        if (selectedFurryId) {
          const stillExists = nextRows.some((row) => row.furryId === selectedFurryId)
          if (!stillExists) {
            setSelectedFurryId('')
            setFurryProfile(null)
            setFurryProfileDraft(null)
            setFurryProfileError('')
          }
        }
      })
      .catch((err) => {
        setFurryError(err.message || 'Unable to load furry friends.')
      })
      .finally(() => {
        setFurryLoading(false)
      })
  }

  useEffect(() => {
    if (activeTab !== 'furry-friends') return
    loadFurryFriends()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, furrySpecies, furrySort])

  const handleFurrySearch = (event) => {
    event.preventDefault()
    loadFurryFriends()
  }

  const loadFurryProfile = (furryId) => {
    if (!furryId) return
    setFurryProfileError('')
    getJson(`/crm/furry/${encodeURIComponent(furryId)}`)
      .then((payload) => {
        setFurryProfile(payload)
        setFurryProfileDraft(payload)
      })
      .catch((err) => {
        setFurryProfileError(err.message || 'Unable to load profile.')
      })
  }

  useEffect(() => {
    if (!selectedFurryId) {
      setFurryProfile(null)
      setFurryProfileDraft(null)
      return
    }
    loadFurryProfile(selectedFurryId)
  }, [selectedFurryId])

  const updateFurryProfileField = (field, value) => {
    setFurryProfileDraft((prev) => ({ ...(prev || {}), [field]: value }))
  }

  const handleFurrySave = async () => {
    if (!selectedFurryId || !furryProfileDraft) return
    setFurryProfileSaving(true)
    setFurryProfileError('')
    const latValue = furryProfileDraft.lat
    const lonValue = furryProfileDraft.lon
    try {
      const payload = {
        furryId: selectedFurryId,
        municipality: furryProfileDraft.municipality || '',
        species: furryProfileDraft.species || 'Dog',
        name: furryProfileDraft.name || '',
        gender: furryProfileDraft.gender || '',
        age: furryProfileDraft.age ? Number(furryProfileDraft.age) : null,
        neutered:
          typeof furryProfileDraft.neutered === 'boolean'
            ? furryProfileDraft.neutered
            : null,
        breed: furryProfileDraft.breed || '',
        color: furryProfileDraft.color || '',
        chipNumber: furryProfileDraft.chipNumber || '',
        address: furryProfileDraft.address || '',
        lat:
          latValue === '' || latValue === null || typeof latValue === 'undefined'
            ? null
            : Number(latValue),
        lon:
          lonValue === '' || lonValue === null || typeof lonValue === 'undefined'
            ? null
            : Number(lonValue),
        notes: furryProfileDraft.notes || '',
      }
      const updated = await requestJson('/crm/furry', {
        method: 'POST',
        payload,
      })
      setFurryProfile(updated)
      setFurryProfileDraft(updated)
      loadFurryFriends()
    } catch (err) {
      setFurryProfileError(err.message || 'Unable to save profile.')
    } finally {
      setFurryProfileSaving(false)
    }
  }

  const handleFurryImport = async () => {
    if (!furryImportFile) {
      setFurryImportStatus('Select a CSV file first.')
      return
    }
    setFurryImportStatus('Uploading...')
    const formData = new FormData()
    formData.append('file', furryImportFile)
    try {
      const result = await requestForm('/crm/furry/import', {
        method: 'POST',
        formData,
      })
      setFurryImportStatus(
        `Import complete. ${result?.created ?? 0} rows created/updated.`,
      )
      loadFurryFriends()
    } catch (err) {
      setFurryImportStatus(err.message || 'Import failed.')
    }
  }

  const buildTaskParams = () => {
    const params = new URLSearchParams()
    if (taskFilterStatus !== 'All') {
      params.set('status', taskFilterStatus)
    }
    if (taskFilterGroup !== 'All') {
      params.set('group', taskFilterGroup)
    }
    params.set('limit', String(taskLimit))
    return params.toString()
  }

  const loadTasks = () => {
    setTasksLoading(true)
    setTasksError('')
    const suffix = buildTaskParams()
    getJson(`/crm/tasks?${suffix}`)
      .then((payload) => {
        setTasks(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setTasksError(err.message || 'Unable to load tasks.')
      })
      .finally(() => {
        setTasksLoading(false)
      })
  }

  useEffect(() => {
    if (activeTab !== 'tasks') return
    loadTasks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, taskFilterStatus, taskFilterGroup])

  const buildSegmentFilter = () => {
    const tags = segmentTags.filter(Boolean)
    const skills = segmentSkills.filter(Boolean)
    return {
      group: segmentGroup !== 'All' ? segmentGroup : null,
      timeAvailability:
        segmentTimeAvailability !== 'All' ? [segmentTimeAvailability] : [],
      tags,
      skills,
      nameContains: segmentNameContains.trim() || null,
      addressContains: segmentAddressContains.trim() || null,
      gender: segmentGender !== 'All' ? segmentGender : null,
      minAge: segmentMinAge ? Number(segmentMinAge) : null,
      maxAge: segmentMaxAge ? Number(segmentMaxAge) : null,
      cityContains: segmentCityContains.trim() || null,
      districtContains: segmentDistrictContains.trim() || null,
      agreesWithManifesto: segmentManifesto !== 'All' ? segmentManifesto === 'Yes' : null,
      interestedInMembership:
        segmentMembershipInterest !== 'All' ? segmentMembershipInterest === 'Yes' : null,
      hasEmail: segmentHasEmail !== 'All' ? segmentHasEmail === 'Yes' : null,
      hasPhone: segmentHasPhone !== 'All' ? segmentHasPhone === 'Yes' : null,
      minEffortHours: segmentMinEffort ? Number(segmentMinEffort) : null,
    }
  }

  const loadSegments = () => {
    setSegmentsLoading(true)
    setSegmentsError('')
    getJson('/crm/segments')
      .then((payload) => {
        setSegments(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setSegmentsError(err.message || 'Unable to load segments.')
      })
      .finally(() => {
        setSegmentsLoading(false)
      })
  }

  const loadSegmentOptions = () => {
    Promise.all([
      getJson('/crm/distinct-values?label=Tag'),
      getJson('/crm/distinct-values?label=Skill'),
    ])
      .then(([tags, skills]) => {
        setSegmentTagOptions(Array.isArray(tags) ? tags : [])
        setSegmentSkillOptions(Array.isArray(skills) ? skills : [])
      })
      .catch(() => {
        // Optional enhancement; ignore errors.
      })
  }

  const loadOutreachEvents = () => {
    setOutreachEventsError('')
    return getJson('/crm/events', { forceRefresh: true })
      .then((payload) => {
        const rows = Array.isArray(payload) ? payload : []
        setOutreachEvents(rows)
        setOutreachEventId((current) => {
          if (current && !rows.some((event) => event.eventId === current)) return ''
          return current
        })
      })
      .catch((err) => {
        setOutreachEventsError(err.message || 'Unable to load events.')
      })
  }

  useEffect(() => {
    if (activeTab !== 'outreach') return
    loadSegments()
    loadSegmentOptions()
    loadOutreachEvents()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  useEffect(() => {
    setOutreachInviteForm((prev) =>
      prev.inviteAudience === 'everyone' ? { ...prev, inviteAudience: 'verified' } : prev,
    )
  }, [])

  useEffect(() => {
    if (!segmentSelectedId) {
      setOutreachInviteForm((prev) =>
        prev.inviteAudience === 'segment' ? { ...prev, inviteAudience: 'individual' } : prev,
      )
    }
  }, [segmentSelectedId])

  useEffect(() => {
    if (activeTab !== 'outreach' || !segmentSelectedId) {
      setSegmentMemberCount(null)
      setSegmentCountLoading(false)
      return undefined
    }
    let cancelled = false
    setSegmentCountLoading(true)
    getJson(`/crm/segments/${encodeURIComponent(segmentSelectedId)}/count`)
      .then((payload) => {
        if (cancelled) return
        const n = payload?.count
        setSegmentMemberCount(typeof n === 'number' ? n : null)
      })
      .catch(() => {
        if (!cancelled) setSegmentMemberCount(null)
      })
      .finally(() => {
        if (!cancelled) setSegmentCountLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeTab, segmentSelectedId])

  const handleCreateSegment = async (event) => {
    event.preventDefault()
    if (!segmentName.trim()) {
      setSegmentsError('Segment name is required.')
      return
    }
    setSegmentsError('')
    try {
      await requestJson('/crm/segments', {
        method: 'POST',
        payload: {
          name: segmentName.trim(),
          description: segmentDescription.trim(),
          filterSpec: buildSegmentFilter(),
        },
      })
      setSegmentName('')
      setSegmentDescription('')
      setSegmentTags([])
      setSegmentSkills([])
      setShowNewSegmentForm(false)
      loadSegments()
    } catch (err) {
      setSegmentsError(err.message || 'Unable to save segment.')
    }
  }

  const handleDeleteSegment = async (segmentId) => {
    setSegmentsError('')
    try {
      await requestJson(`/crm/segments/${segmentId}`, { method: 'DELETE' })
      if (segmentSelectedId === segmentId) {
        setSegmentSelectedId('')
        setSegmentResults([])
      }
      loadSegments()
    } catch (err) {
      setSegmentsError(err.message || 'Unable to delete segment.')
    }
  }

  const handleRunSegment = async (segmentId) => {
    setSegmentRunLoading(true)
    setSegmentsError('')
    try {
      const limit = Number(segmentLimit) || 200
      const payload = segmentId
        ? await getJson(`/crm/segments/${segmentId}/run?limit=${limit}`)
        : await requestJson('/crm/segments/run', {
            method: 'POST',
            payload: { filterSpec: buildSegmentFilter(), limit },
          })
      setSegmentResults(Array.isArray(payload) ? payload : [])
    } catch (err) {
      setSegmentsError(err.message || 'Unable to run segment.')
    } finally {
      setSegmentRunLoading(false)
    }
  }

  const handleBulkTasks = async () => {
    if (!segmentResults.length) {
      setSegmentTaskError('Run a segment first.')
      return
    }
    if (!segmentTaskTitle.trim()) {
      setSegmentTaskError('Task title is required.')
      return
    }
    setSegmentTaskError('')
    setSegmentTaskSaving(true)
    try {
      const rows = segmentResults.map((row) => ({
        email: row.email,
        title: segmentTaskTitle.trim(),
        description: segmentTaskDescription.trim(),
        dueDate: segmentTaskDueDate || '',
        status: segmentTaskStatus,
      }))
      await requestJson('/crm/tasks/bulk', { method: 'POST', payload: { rows } })
      setSegmentTaskTitle('')
      setSegmentTaskDescription('')
      setSegmentTaskDueDate('')
    } catch (err) {
      setSegmentTaskError(err.message || 'Unable to create tasks.')
    } finally {
      setSegmentTaskSaving(false)
    }
  }

  const handleIndividualSearch = async (event) => {
    event.preventDefault()
    const query = individualQuery.trim()
    if (query.length < 2) {
      setIndividualError('Enter at least 2 characters to search.')
      return
    }
    setIndividualError('')
    setIndividualLoading(true)
    try {
      const payload = await getJson(
        `/crm/people/summary?q=${encodeURIComponent(query)}&limit=200`,
      )
      setIndividualResults(Array.isArray(payload) ? payload : [])
      setIndividualSelected([])
    } catch (err) {
      setIndividualError(err.message || 'Unable to search people.')
    } finally {
      setIndividualLoading(false)
    }
  }

  const handleToggleIndividual = (email) => {
    setIndividualSelected((prev) =>
      prev.includes(email) ? prev.filter((item) => item !== email) : [...prev, email],
    )
  }

  const handleIndividualTasks = async () => {
    const selectedRows = individualResults.filter((row) =>
      individualSelected.includes(row.email),
    )
    if (!selectedRows.length) {
      setIndividualError('Select at least one person.')
      return
    }
    if (!individualTaskTitle.trim()) {
      setIndividualError('Task title template is required.')
      return
    }
    setIndividualError('')
    setIndividualTaskSaving(true)
    try {
      const rows = selectedRows.map((row) => ({
        email: row.email,
        title: renderTemplate(individualTaskTitle, row),
        description: renderTemplate(individualTaskDescription, row),
        dueDate: individualTaskDueDate || '',
        status: individualTaskStatus,
      }))
      await requestJson('/crm/tasks/bulk', { method: 'POST', payload: { rows } })
      setIndividualTaskTitle('')
      setIndividualTaskDescription('')
      setIndividualTaskDueDate('')
    } catch (err) {
      setIndividualError(err.message || 'Unable to create tasks.')
    } finally {
      setIndividualTaskSaving(false)
    }
  }

  /** Create an event without requiring a segment (POST /crm/events). */
  const handleCreateOutreachEvent = async () => {
    if (!segmentEventName.trim()) {
      setSegmentEventStatusMessage('Event name is required.')
      return
    }
    setSegmentEventStatusMessage('')
    setOutreachAttachMessage('')
    try {
      const created = await requestJson('/crm/events', {
        method: 'POST',
        payload: {
          name: segmentEventName.trim(),
          startDate: segmentEventStartDate || '',
          endDate: segmentEventEndDate || '',
          location: segmentEventLocation.trim(),
          status: segmentEventStatus,
          capacity: segmentEventCapacity ? Number(segmentEventCapacity) : 0,
          notes: segmentEventNotes.trim(),
        },
      })
      if (created?.eventId) {
        setOutreachEventId(created.eventId)
      }
      await loadOutreachEvents()
      setSegmentEventStatusMessage(
        'Event created. Optionally pick a segment below and register its audience, then use distribution.',
      )
      setSegmentEventName('')
      setSegmentEventStartDate('')
      setSegmentEventEndDate('')
      setSegmentEventLocation('')
      setSegmentEventCapacity('')
      setSegmentEventNotes('')
      setShowNewEventForm(false)
    } catch (err) {
      setSegmentEventStatusMessage(err.message || 'Unable to create event.')
    }
  }

  /** Register everyone in the selected segment for the event chosen above (bulk register). */
  const handleAttachSegmentAudienceToEvent = async () => {
    if (!outreachEventId) {
      setOutreachAttachMessage('Select or create an event in the section above first.')
      return
    }
    if (!segmentSelectedId) {
      setOutreachAttachMessage('Select a saved segment first.')
      return
    }
    setOutreachAttachMessage('')
    setSegmentEventStatusMessage('')
    setOutreachAttachLoading(true)
    try {
      const limit = Math.max(1, Number(segmentLimit) || 200)
      const audience = await getJson(`/crm/segments/${encodeURIComponent(segmentSelectedId)}/run?limit=${limit}`)
      if (!Array.isArray(audience) || audience.length === 0) {
        setOutreachAttachMessage('Selected segment has no people to register.')
        return
      }
      const rows = audience.map((row) => {
        const nameParts = splitFullName(row.fullName)
        return {
          email: row.email,
          firstName: nameParts.firstName,
          lastName: nameParts.lastName,
          group: row.group,
        }
      })
      await requestJson(`/crm/events/${encodeURIComponent(outreachEventId)}/register/bulk`, {
        method: 'POST',
        payload: { rows, status: 'Registered' },
      })
      setOutreachAttachMessage(`Registered ${rows.length} people from this segment for the selected event.`)
      loadOutreachEvents()
    } catch (err) {
      setOutreachAttachMessage(err.message || 'Unable to register segment audience for this event.')
    } finally {
      setOutreachAttachLoading(false)
    }
  }

  const outreachSelectedEvent = useMemo(
    () => outreachEvents.find((event) => event.eventId === outreachEventId) || null,
    [outreachEventId, outreachEvents],
  )
  const selectedSegment = useMemo(
    () => segments.find((segment) => segment.segmentId === segmentSelectedId) || null,
    [segmentSelectedId, segments],
  )

  const outreachBaseUrl =
    typeof window !== 'undefined' ? `${window.location.origin}${window.location.pathname}` : ''

  const outreachPublicLink =
    outreachSelectedEvent && outreachBaseUrl
      ? `${outreachBaseUrl}?event_registration=1&event_id=${outreachSelectedEvent.eventId}`
      : ''

  const buildOutreachInviteShareMessage = (
    recipientName,
    event,
    link,
    notes,
    inviteAudience = 'individual',
  ) => {
    const noteBlock = notes ? `\n\nNote: ${notes}` : ''
    const audience = String(inviteAudience || 'individual').toLowerCase()
    if (audience === 'segment') {
      return `Hi, here is the Freedom Square event registration link - ${event?.name || 'our event'}:\n\n${link}${noteBlock}`
    }
    if (audience !== 'individual') {
      return `Hi team, here is the Freedom Square event registration link for ${getInviteAudienceLabel(audience)} - ${event?.name || 'our event'}:\n\n${link}${noteBlock}`
    }
    const name = recipientName || 'there'
    return `Hi ${name}, you're invited to register for ${event?.name || 'our event'}:\n\n${link}${noteBlock}`
  }

  const handleShareOutreachInviteByChannel = async ({
    channel,
    event,
    inviteLink,
    inviteAudience,
    recipientName,
    recipientEmail,
    recipientPhone,
    notes,
  }) => {
    if (!inviteLink || !event) return false
    const normalizedChannel = String(channel || '').toLowerCase()
    const normalizedAudience = String(inviteAudience || 'individual').toLowerCase()
    const trimmedNotes = String(notes || '').trim()

    let segmentMemberEmails = null
    if (normalizedAudience === 'segment') {
      if (!segmentSelectedId) {
        setOutreachDistributionError('Select a saved segment in Audience first.')
        return false
      }
      try {
        const limit = 500
        const rows = await getJson(
          `/crm/segments/${encodeURIComponent(segmentSelectedId)}/run?limit=${limit}`,
        )
        const emails = Array.isArray(rows)
          ? [...new Set(rows.map((r) => String(r?.email || '').trim()).filter(Boolean))]
          : []
        if (!emails.length) {
          setOutreachDistributionError('This segment has no people with email addresses.')
          return false
        }
        segmentMemberEmails = emails
      } catch (err) {
        setOutreachDistributionError(err.message || 'Unable to load segment members.')
        return false
      }
    }

    const message = buildOutreachInviteShareMessage(
      recipientName,
      event,
      inviteLink,
      trimmedNotes,
      normalizedAudience,
    )
    if (normalizedChannel === 'email') {
      const audienceGroupEmail = getInviteAudienceGroupEmail(
        normalizedAudience,
        supporterInviteGroupsConfig,
      )
      const recipientEmails = normalizedAudience === 'segment' && segmentMemberEmails
        ? segmentMemberEmails
        : []
      const targetEmail =
        normalizedAudience === 'individual' ? recipientEmail || '' : audienceGroupEmail
      if (!targetEmail && recipientEmails.length === 0) {
        if (normalizedAudience === 'individual') {
          setOutreachDistributionError('Recipient email is required for email sends.')
        } else if (normalizedAudience === 'segment') {
          setOutreachDistributionError('This segment has no people with email addresses.')
        } else {
          setOutreachDistributionError(
            `Missing Google email list for ${getInviteAudienceLabel(normalizedAudience)}.`,
          )
        }
        return false
      }
      const payload = await requestJson('/crm/event-invites', {
        method: 'POST',
        payload: {
          eventId: event.eventId || '',
          eventName: event.name || 'Registration',
          inviteLink,
          recipientName,
          recipientEmail: targetEmail,
          recipientEmails,
          channel: 'email',
          inviteAudience: normalizedAudience,
          notes: trimmedNotes,
        },
      })
      if (payload?.sentCount === payload?.totalCount && payload?.totalCount > 0) {
        setOutreachDistributionStatus(
          `Registration email sent to ${payload.totalCount} recipient${payload.totalCount === 1 ? '' : 's'}.`,
        )
      } else if (payload?.sentCount > 0) {
        setOutreachDistributionStatus(
          `Registration email sent to ${payload.sentCount} of ${payload.totalCount} recipients.`,
        )
      } else {
        setOutreachDistributionStatus(
          `Registration invite created but email failed (${payload?.emailStatus || 'unknown'}).`,
        )
      }
      return true
    }
    if (normalizedChannel === 'whatsapp') {
      if (normalizedAudience === 'segment' && segmentMemberEmails) {
        if (navigator?.clipboard) {
          try {
            await navigator.clipboard.writeText(
              `${message}\n\n---\nSegment emails (${segmentMemberEmails.length}):\n${segmentMemberEmails.join('\n')}`,
            )
          } catch {
            /* continue with short URL only */
          }
        }
        const text = encodeURIComponent(message)
        openExternalShareLink(`https://wa.me/?text=${text}`)
        setOutreachDistributionStatus(
          'WhatsApp opened with the message; full segment email list copied to clipboard when available.',
        )
        return true
      }
      const text = encodeURIComponent(message)
      const phone = String(recipientPhone || '').replace(/[^\d]/g, '')
      const whatsappUrl = phone ? `https://wa.me/${phone}?text=${text}` : `https://wa.me/?text=${text}`
      openExternalShareLink(whatsappUrl)
      setOutreachDistributionStatus('WhatsApp share opened with the registration link.')
      return true
    }
    if (normalizedChannel === 'slack') {
      if (!navigator?.clipboard) {
        setOutreachDistributionError('Clipboard unavailable in this browser.')
        return false
      }
      try {
        const payload =
          normalizedAudience === 'segment' && segmentMemberEmails
            ? `${message}\n\n---\nSegment emails (${segmentMemberEmails.length}):\n${segmentMemberEmails.join('\n')}`
            : message
        await navigator.clipboard.writeText(payload)
        setOutreachDistributionStatus(
          normalizedAudience === 'segment' && segmentMemberEmails
            ? 'Slack-ready text and segment email list copied.'
            : 'Slack message copied with the registration link.',
        )
        return true
      } catch {
        setOutreachDistributionError('Unable to copy message for Slack.')
        return false
      }
    }
    setOutreachDistributionStatus('Registration link ready to share.')
    return true
  }

  const handleSubmitOutreachInvite = async (submitEvent) => {
    submitEvent.preventDefault()
    setOutreachDistributionError('')
    setOutreachDistributionStatus('')
    const link = outreachPublicLink
    const ev = outreachSelectedEvent
    if (!ev || !link) {
      setOutreachDistributionError('Select an event first.')
      return
    }
    const selectedChannel = outreachInviteForm.channel
    const selectedAudience = outreachInviteForm.inviteAudience || 'individual'
    const recipientName = outreachInviteForm.recipientName.trim()
    const recipientEmail = outreachInviteForm.recipientEmail.trim()
    const recipientPhone = outreachInviteForm.recipientPhone.trim()
    const notes = ''
    try {
      if (
        selectedChannel === 'email' &&
        (selectedAudience === 'verified' || selectedAudience === 'registered')
      ) {
        await requestJson('/crm/supporter-invite-groups-config', {
          method: 'PATCH',
          payload: {
            everyoneGroupEmail: supporterInviteGroupsConfig.everyoneGroupEmail.trim(),
            verifiedGroupEmail: supporterInviteGroupsConfig.verifiedGroupEmail.trim(),
            registeredGroupEmail: supporterInviteGroupsConfig.registeredGroupEmail.trim(),
          },
        })
      }
      const ok = await handleShareOutreachInviteByChannel({
        channel: selectedChannel,
        event: ev,
        inviteLink: link,
        inviteAudience: selectedAudience,
        recipientName,
        recipientEmail,
        recipientPhone,
        notes,
      })
      if (ok) {
        setOutreachInviteForm((prev) => ({
          ...prev,
          recipientName: '',
          recipientEmail: '',
          recipientPhone: '',
          notes: '',
        }))
      }
    } catch (err) {
      setOutreachDistributionError(err.message || 'Unable to send event invite.')
    }
  }

  const handleCopyOutreachEventLink = async () => {
    const value = String(outreachPublicLink || '').trim()
    setOutreachDistributionError('')
    setOutreachDistributionStatus('')
    if (!value) {
      setOutreachDistributionError('Select an event to copy its registration link.')
      return
    }
    if (!navigator?.clipboard) {
      setOutreachDistributionError('Clipboard unavailable in this browser.')
      return
    }
    try {
      await navigator.clipboard.writeText(value)
      setOutreachDistributionStatus('Link copied.')
    } catch {
      setOutreachDistributionError('Unable to copy invite link.')
    }
  }

  const handleCreateTask = async (event) => {
    event.preventDefault()
    if (!newTaskEmail.trim() || !newTaskTitle.trim()) {
      setTasksError('Email and title are required.')
      return
    }
    setTasksError('')
    try {
      await requestJson('/crm/tasks', {
        method: 'POST',
        payload: {
          email: newTaskEmail.trim(),
          title: newTaskTitle.trim(),
          description: newTaskDescription.trim(),
          dueDate: newTaskDueDate || '',
          status: newTaskStatus,
        },
      })
      setNewTaskTitle('')
      setNewTaskDescription('')
      setNewTaskDueDate('')
      loadTasks()
    } catch (err) {
      setTasksError(err.message || 'Unable to create task.')
    }
  }

  const handleTaskStatusUpdate = async () => {
    if (!taskUpdateId) return
    setTasksError('')
    try {
      await requestJson(`/crm/tasks/${taskUpdateId}`, {
        method: 'PATCH',
        payload: { status: taskUpdateStatus },
      })
      loadTasks()
    } catch (err) {
      setTasksError(err.message || 'Unable to update task.')
    }
  }

  const handleDeleteTask = async (taskId) => {
    if (!taskId) return
    setTasksError('')
    try {
      await requestJson(`/crm/tasks/${taskId}`, { method: 'DELETE' })
      loadTasks()
    } catch (err) {
      setTasksError(err.message || 'Unable to delete task.')
    }
  }

  const taskCounts = tasks.reduce(
    (acc, task) => {
      const status = task.status || 'Open'
      acc[status] = (acc[status] || 0) + 1
      return acc
    },
    { Open: 0, 'In Progress': 0, Done: 0, Cancelled: 0 },
  )

  const taskStatusData = {
    labels: ['Open', 'In Progress', 'Done', 'Cancelled'],
    datasets: [
      {
        label: 'Tasks',
        data: [
          taskCounts.Open,
          taskCounts['In Progress'],
          taskCounts.Done,
          taskCounts.Cancelled,
        ],
        backgroundColor: ['#2563eb', '#f59e0b', '#16a34a', '#ef4444'],
      },
    ],
  }

  const taskStatusOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { stepSize: 1 },
      },
    },
  }

  const overviewPulseSummary = activeTab === 'overview' ? overviewMapStats?.summary : null

  const crmPulseStats = useMemo(() => {
    const rate = Number(supporterInviteStats?.conversionRate ?? 0)
    const conversionDisplay =
      supporterInviteStats == null ? '-' : `${Number.isFinite(rate) ? rate.toFixed(1) : '0.0'}%`
    return [
      {
        label: 'Total people',
        value: overviewPulseSummary?.totalPeople ?? summary?.total_people ?? people.length ?? '\u2014',
        icon: <IconUsers size={18} />,
        badge: overviewPulseSummary?.hasActiveFilters ? 'Filtered' : 'Active',
      },
      {
        label: 'Supporters',
        value: overviewPulseSummary?.supporters ?? summary?.supporters ?? '\u2014',
        icon: <IconUsers size={18} />,
        note: 'Community reach',
      },
      {
        label: 'Members',
        value: overviewPulseSummary?.members ?? summary?.members ?? '\u2014',
        icon: <IconUsers size={18} />,
        note: 'Core base',
      },
      {
        label: 'Conversion rate',
        value: conversionDisplay,
        icon: <IconTarget size={18} />,
        note: 'Supporter invite form',
      },
    ]
  }, [overviewPulseSummary, people.length, summary, supporterInviteStats])
  const conversionInvitesSent = Number(supporterInviteStats?.sent || 0)
  const conversionRegisteredCount = Number(supporterInviteStats?.converted || 0)
  const conversionPendingCount = Number(supporterInviteStats?.pending || 0)
  const conversionRateValue = Number(supporterInviteStats?.conversionRate || 0)
  const memberConversionCount = supporterInvites.reduce((acc, invite) => {
    const isConverted = String(invite?.status || '').toLowerCase() === 'converted'
    const type = normalizeSupporterTypeLabel(invite?.supporterType || '')
    return isConverted && type === 'Member' ? acc + 1 : acc
  }, 0)
  const conversionSentBaseline = Math.max(conversionInvitesSent, 1)
  const supporterStageRatio = Math.min(
    100,
    Math.max(14, Math.round((conversionRegisteredCount / conversionSentBaseline) * 100)),
  )
  const memberStageRatio = Math.min(
    supporterStageRatio,
    Math.max(8, Math.round((memberConversionCount / conversionSentBaseline) * 100)),
  )
  const pendingByInviteCode = useMemo(() => {
    const map = new Map()
    pendingSupporterSignups.forEach((person) => {
      const inviteCode = String(person?.inviteCode || '').trim()
      if (inviteCode) {
        map.set(inviteCode, person)
      }
    })
    return map
  }, [pendingSupporterSignups])
  const invitePipelineAllRows = useMemo(() => {
    const toMillis = (value) => {
      const ms = Date.parse(value || '')
      return Number.isFinite(ms) ? ms : 0
    }
    const inviteRows = supporterInvites.map((invite) => {
      const email = String(
        invite?.recipientEmail || invite?.convertedEmail || invite?.submittedEmail || '',
      )
        .trim()
        .toLowerCase()
      const inviteCode = String(invite?.inviteCode || '').trim()
      const pendingPerson = inviteCode ? pendingByInviteCode.get(inviteCode) : null
      const rawStatus = String(invite?.status || 'sent').toLowerCase()
      const isConverted = rawStatus === 'converted'
      const isPendingApproval = !!pendingPerson
      let pipelineStatus = 'sent'
      if (isConverted) pipelineStatus = 'converted'
      else if (isPendingApproval) pipelineStatus = 'pending'
      return {
        key: `invite-${invite?.inviteId || invite?.inviteCode || email || Math.random()}`,
        source: 'invite',
        recipient:
          invite?.recipientName || pendingPerson?.firstName || pendingPerson?.email || 'Recipient',
        email: invite?.recipientEmail || pendingPerson?.email || invite?.convertedEmail || '-',
        audience: getInviteAudienceLabel(invite?.inviteAudience || 'individual'),
        channel: invite?.channel || 'manual',
        supporterType: invite?.supporterType || pendingPerson?.supporterType || 'Supporter',
        status: pipelineStatus,
        statusLabel:
          pipelineStatus === 'converted'
            ? 'Converted'
            : pipelineStatus === 'pending'
              ? 'Pending approval'
              : 'Sent',
        reminderCount: invite?.reminderCount ?? 0,
        createdAt: invite?.createdAt || pendingPerson?.createdAt || '-',
        convertedAt: invite?.convertedAt || '-',
        sortAt: Math.max(toMillis(invite?.createdAt), toMillis(pendingPerson?.createdAt)),
        invite,
        pendingPerson,
      }
    })
    const seenPendingSignupIds = new Set(
      inviteRows.map((row) => String(row?.pendingPerson?.signupId || '')).filter(Boolean),
    )
    const orphanPendingRows = pendingSupporterSignups
      .filter((person) => !seenPendingSignupIds.has(String(person?.signupId || '')))
      .map((person) => ({
        key: `pending-${person?.signupId || person?.email}`,
        source: 'pending',
        recipient: `${person?.firstName || ''} ${person?.lastName || ''}`.trim() || person?.email || 'Pending form',
        email: person?.email || '-',
        audience: 'Single recipient',
        channel: '-',
        supporterType: person?.supporterType || 'Supporter',
        status: 'pending',
        statusLabel: 'Pending approval',
        reminderCount: 0,
        createdAt: person?.createdAt || '-',
        convertedAt: '-',
        sortAt: toMillis(person?.createdAt),
        invite: null,
        pendingPerson: person,
      }))
    return [...inviteRows, ...orphanPendingRows].sort((a, b) => b.sortAt - a.sortAt)
  }, [supporterInvites, pendingSupporterSignups, pendingByInviteCode])
  const invitePipelineRows = useMemo(() => {
    const merged = [...invitePipelineAllRows]
    if (invitePipelineFilter === 'pending') {
      return merged.filter((row) => row.status === 'pending')
    }
    if (invitePipelineFilter === 'sent') {
      return merged.filter((row) => row.status === 'sent')
    }
    if (invitePipelineFilter === 'converted') {
      return merged.filter((row) => row.status === 'converted')
    }
    return merged
  }, [invitePipelineAllRows, invitePipelineFilter])
  const invitePipelinePendingCount = pendingSupporterSignups.length
  const fallbackInviteType = normalizeSupporterTypeLabel(
    latestSupporterInviteType || supporterInviteForm.supporterType || 'Supporter',
  )
  const fallbackOpenFormLink = buildSupporterInviteLink('', fallbackInviteType)
  const supporterQrLink = latestSupporterInviteLink || fallbackOpenFormLink

  useEffect(() => {
    let cancelled = false
    if (!supporterQrLink || !supporterQrExpanded) {
      setSupporterQrDataUrl('')
      return undefined
    }
    QRCode.toDataURL(supporterQrLink, {
      errorCorrectionLevel: 'M',
      margin: 2,
      width: 280,
      color: {
        dark: '#0f172a',
        light: '#ffffff',
      },
    })
      .then((url) => {
        if (!cancelled) setSupporterQrDataUrl(url)
      })
      .catch(() => {
        if (!cancelled) setSupporterQrDataUrl('')
      })
    return () => {
      cancelled = true
    }
  }, [supporterQrLink, supporterQrExpanded])

  return (
    <section className="module module--crm-radical">
      {showIntro ? (
        <div className="module-card module-card__wide section-intro">
          <div className="card-header">
            <div>
              <h3>{translate('network.header.title')}</h3>
              <p className="muted">{translate('network.header.subtitle')}</p>
            </div>
            <div className="pill">Network</div>
          </div>
        </div>
      ) : null}

      {error ? <div className="module-alert">{error}</div> : null}
      <CivicStatGrid
        title="Network pulse"
        description={overviewPulseSummary?.hasActiveFilters
          ? 'Filtered by the current Map & Coverage filters.'
          : 'Live health checks for supporters, conversion, and outreach readiness.'}
        items={crmPulseStats}
      />

      {!hideTabs && showTabs ? (
        <div className="subtabs">
          {[
            { id: 'overview', label: 'Map & Coverage' },
            { id: 'intake', label: 'New supporters/members' },
            { id: 'people', label: 'People & Segments' },
            CRM_TASKS_ENABLED ? { id: 'tasks', label: 'Task board' } : null,
          ].filter(Boolean).map((tab) => (
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
        <CRMOverviewTab mapStats={overviewMapStats} onMapStatsChange={setOverviewMapStats} />
      )}

      {activeTab === 'people' && (
        <div className="stack">
          <div className="section-block">
            <div className="module-layout">
              <aside className="module-sidebar">
            <div className="sidebar-card sidebar-card--accent" data-tour="network-people-search">
              <h3>Find people</h3>
              <form className="stack" onSubmit={handlePeopleSearch}>
                <label className="label">Search</label>
                <input
                  className="input"
                  type="text"
                  value={peopleQuery}
                  onChange={(event) => setPeopleQuery(event.target.value)}
                  placeholder="Search by name or email"
                />
                <label className="label">Group</label>
                <select
                  className="select"
                  value={peopleGroup}
                  onChange={(event) => setPeopleGroup(event.target.value)}
                >
                  <option value="All">All groups</option>
                  <option value="Supporter">Supporters</option>
                  <option value="Member">Members</option>
                </select>
                <button className="button" type="submit">
                  {peopleLoading ? 'Loading...' : 'Search'}
                </button>
              </form>
            </div>
            <div className="sidebar-card">
              <h3>Stats</h3>
              <div className="metric-row">
                <span>Results</span>
                <strong>{people.length}</strong>
              </div>
              <div className="metric-row">
                <span>Total people</span>
                <strong>{summary?.total_people ?? '-'}</strong>
              </div>
            </div>
              </aside>
              <div className="module-main">
                {peopleError ? <div className="module-alert">{peopleError}</div> : null}
              <div className="module-card module-card__wide panel panel--highlight" data-tour="network-people-directory">
                <div className="card-header">
                  <div>
                    <h3>People directory</h3>
                    <p className="muted">
                      Search supporters and members from the Network.
                    </p>
                  </div>
                  <div className="pill">Network</div>
                </div>
                <div className="table">
                <div className="table-row table-row--people table-head">
                  {renderPeopleSortButton('Name', 'name')}
                  {renderPeopleSortButton('Email', 'email')}
                  {renderPeopleSortButton('Group', 'group')}
                  {renderPeopleSortButton('Effort', 'effort')}
                  {renderPeopleSortButton('Events', 'events')}
                  {renderPeopleSortButton('Referrals', 'referrals')}
                  {renderPeopleSortButton('Rating', 'rating')}
                </div>
                {sortedPeople.length === 0 && !peopleLoading && (
                    <div className="table-row empty">No people found.</div>
                  )}
                {sortedPeople.map((person) => (
                    <button
                      className="table-row table-row--people table-row__button"
                      key={person.email || person.personId}
                      type="button"
                      onClick={() => handleSelectPerson(person)}
                    >
                      <span>{person.fullName || person.email}</span>
                      <span>{person.email || person.personId || '?'}</span>
                      <span>{person.group}</span>
                      <span>{person.effortScore ?? '-'}</span>
                      <span>{person.eventAttendCount ?? '-'}</span>
                      <span>{person.referralCount ?? '-'}</span>
                      <span>{person.ratingStars || '-'}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="module-card module-card__wide panel" data-tour="network-profile-editor">
                <div className="card-header">
                  <div>
                    <h3>Profile details</h3>
                    <p className="muted">
                      Select a person above to view and edit their profile.
                    </p>
                  </div>
                  {selectedEmail ? <div className="pill">{profileDraft?.email || selectedEmail}</div> : null}
                </div>

                {profileError ? <div className="module-alert">{profileError}</div> : null}
                {profileLoading ? <p className="muted">Loading full profile...</p> : null}

                {!selectedEmail && <p className="muted">No person selected.</p>}

                {selectedEmail && profileDraft && (
                  <div className="profile-grid">
                    <div>
                      <label className="label">First name</label>
                      <input
                        className="input"
                        value={profileDraft.firstName || ''}
                        onChange={(event) => updateProfileField('firstName', event.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label">Last name</label>
                      <input
                        className="input"
                        value={profileDraft.lastName || ''}
                        onChange={(event) => updateProfileField('lastName', event.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label">Phone</label>
                      <input
                        className="input"
                        value={profileDraft.phone || ''}
                        onChange={(event) => updateProfileField('phone', event.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label">Gender</label>
                      <select
                        className="select"
                        value={profileDraft.gender || ''}
                        onChange={(event) => updateProfileField('gender', event.target.value)}
                      >
                        <option value="">Unspecified</option>
                        <option value="Male">Male</option>
                        <option value="Female">Female</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                    <div>
                      <label className="label">Age</label>
                      <input
                        className="input"
                        type="number"
                        value={profileDraft.age || ''}
                        onChange={(event) => updateProfileField('age', event.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label">Time availability</label>
                      <select
                      className="select"
                      value={profileDraft.timeAvailability || 'Unspecified'}
                      onChange={(event) =>
                        updateProfileField('timeAvailability', event.target.value)
                      }
                    >
                      <option value="Unspecified">Unspecified</option>
                      <option value="Weekends">Weekends</option>
                      <option value="Evenings">Evenings</option>
                      <option value="Full-time">Full-time</option>
                      <option value="Ad-hoc">Ad-hoc</option>
                    </select>
                  </div>
                  <div className="profile-span">
                    <label className="label">Notes</label>
                    <textarea
                      className="textarea"
                      value={profileDraft.about || ''}
                      onChange={(event) => updateProfileField('about', event.target.value)}
                    />
                  </div>
                  <div className="profile-span profile-checks">
                    <label>
                      <input
                        type="checkbox"
                        checked={!!profileDraft.agreesWithManifesto}
                        onChange={(event) =>
                          updateProfileField('agreesWithManifesto', event.target.checked)
                        }
                      />
                      Agrees with manifesto
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={!!profileDraft.interestedInMembership}
                        onChange={(event) =>
                          updateProfileField('interestedInMembership', event.target.checked)
                        }
                      />
                      Interested in membership
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={!!profileDraft.facebookGroupMember}
                        onChange={(event) =>
                          updateProfileField('facebookGroupMember', event.target.checked)
                        }
                      />
                      Facebook group member
                    </label>
                  </div>
                  <div className="profile-actions">
                    <button
                      className="button"
                      type="button"
                      onClick={handleProfileSave}
                      disabled={profileSaving}
                    >
                      {profileSaving ? 'Saving...' : <IconCircleCheck size={17} />}
                    </button>
                  </div>
                </div>
              )}
              </div>

            </div>
          </div>
        </div>
      </div>
      )}

      {activeTab === 'intake' && (
        <div className="stack">
          <div className="module-card module-card__wide panel intake-flow">
            <div className="module-card intake-tile intake-order-links" data-tour="network-signup-link">
              <div className="intake-invite-compact">
                <div className="intake-invite-compact__form">
                  <div className="intake-section-heading">
                    <div>
                      <h4 className="intake-section-title">Send signup link</h4>
                      <p className="muted">
                        Send signup invitations by email, WhatsApp, or Slack.
                      </p>
                    </div>
                    <div className="share-channel-icons" aria-label="Signup channel">
                      <button
                        className={
                          supporterInviteForm.channel === 'email'
                            ? 'icon-button icon-button--primary active'
                            : 'icon-button'
                        }
                        type="button"
                        title="Email"
                        aria-label="Email"
                        onClick={() =>
                          setSupporterInviteForm((prev) => ({
                            ...prev,
                            channel: 'email',
                          }))
                        }
                      >
                        <IconMail size={17} />
                      </button>
                      <button
                        className={
                          supporterInviteForm.channel === 'whatsapp'
                            ? 'icon-button icon-button--primary active'
                            : 'icon-button'
                        }
                        type="button"
                        title="WhatsApp"
                        aria-label="WhatsApp"
                        onClick={() =>
                          setSupporterInviteForm((prev) => ({
                            ...prev,
                            channel: 'whatsapp',
                          }))
                        }
                      >
                        <IconBrandWhatsapp size={17} />
                      </button>
                      <button
                        className={
                          supporterInviteForm.channel === 'slack'
                            ? 'icon-button icon-button--primary active'
                            : 'icon-button'
                        }
                        type="button"
                        title="Slack"
                        aria-label="Slack"
                        onClick={() =>
                          setSupporterInviteForm((prev) => ({
                            ...prev,
                            channel: 'slack',
                          }))
                        }
                      >
                        <IconBrandSlack size={17} />
                      </button>
                      <button
                        className={supporterQrExpanded ? 'icon-button icon-button--primary active' : 'icon-button'}
                        type="button"
                        title="QR code"
                        aria-label="Show QR code"
                        onClick={() => setSupporterQrExpanded((prev) => !prev)}
                        disabled={!supporterQrLink}
                      >
                        <IconQrcode size={17} />
                      </button>
                    </div>
                  </div>
                  {supporterQrExpanded ? (
                    <div className="share-qr-panel">
                      <div className="share-qr-panel__code" aria-label="Signup QR code">
                        {supporterQrDataUrl ? (
                          <img src={supporterQrDataUrl} alt="QR code for the signup form link" />
                        ) : (
                          <span className="muted">Generating QR code...</span>
                        )}
                      </div>
                      <div className="share-qr-panel__meta">
                        <strong>Scan to open the signup form</strong>
                        <p className="muted">Supporters can scan this code with their phone camera.</p>
                      </div>
                    </div>
                  ) : null}
                  <form
                    id="crm-supporter-invite-form"
                    className="form-grid intake-invite-form-compact"
                    onSubmit={handleCreateSupporterInvite}
                  >
                <select
                  className="select"
                  value={supporterInviteForm.inviteAudience}
                  onChange={(event) =>
                    setSupporterInviteForm((prev) => ({
                      ...prev,
                      inviteAudience: event.target.value,
                    }))
                  }
                >
                  <option value="individual">Single recipient</option>
                  <option value="everyone">Everyone</option>
                  <option value="verified">Verified users</option>
                  <option value="registered">Registered users</option>
                </select>
                {supporterInviteForm.inviteAudience === 'individual' ? (
                  <>
                    <input
                      className="input"
                      placeholder="Recipient name"
                      value={supporterInviteForm.recipientName}
                      onChange={(event) =>
                        setSupporterInviteForm((prev) => ({
                          ...prev,
                          recipientName: event.target.value,
                        }))
                      }
                    />
                    {supporterInviteForm.channel === 'email' ? (
                      <input
                        className="input"
                        type="email"
                        placeholder="Recipient email"
                        value={supporterInviteForm.recipientEmail}
                        onChange={(event) =>
                          setSupporterInviteForm((prev) => ({
                            ...prev,
                            recipientEmail: event.target.value,
                          }))
                        }
                      />
                    ) : null}
                    {supporterInviteForm.channel === 'whatsapp' ? (
                      <input
                        className="input"
                        placeholder="Recipient phone"
                        value={supporterInviteForm.recipientPhone}
                        onChange={(event) =>
                          setSupporterInviteForm((prev) => ({
                            ...prev,
                            recipientPhone: event.target.value,
                          }))
                        }
                      />
                    ) : null}
                  </>
                ) : supporterInviteForm.channel === 'email' ? (
                  <div className="form-grid__full">
                    <label className="label">Group email list</label>
                    <input
                      className="input"
                      type="email"
                      list="supporter-invite-group-options"
                      placeholder="group@googlegroups.com"
                      value={getInviteAudienceGroupEmail(
                        supporterInviteForm.inviteAudience,
                        supporterInviteGroupsConfig,
                      )}
                      onChange={(event) =>
                        setInviteAudienceGroupEmail(
                          supporterInviteForm.inviteAudience,
                          event.target.value,
                        )
                      }
                    />
                    <datalist id="supporter-invite-group-options">
                      {[...new Set(Object.values(supporterInviteGroupsConfig).filter(Boolean))].map(
                        (groupEmail) => (
                          <option key={groupEmail} value={groupEmail} />
                        ),
                      )}
                    </datalist>
                    <p className="muted">
                      Backend Gmail sends to this group email for{' '}
                      {getInviteAudienceLabel(supporterInviteForm.inviteAudience)}.
                    </p>
                  </div>
                ) : (
                  <div className="form-grid__full muted">
                    Audience group lists are used when channel is Email.
                  </div>
                )}
                <select
                  className="select"
                  value={supporterInviteForm.supporterType}
                  onChange={(event) =>
                    setSupporterInviteForm((prev) => ({
                      ...prev,
                      supporterType: event.target.value,
                    }))
                  }
                >
                  <option value="Supporter">Supporter form</option>
                  <option value="Member">Member form</option>
                </select>
              </form>
                </div>
                <div className="intake-invite-combined__cta-row intake-invite-compact__actions">
                  <button
                    className="icon-button icon-button--primary intake-invite-combined__cta-send"
                    type="submit"
                    form="crm-supporter-invite-form"
                    disabled={supporterInviteLoading}
                    title="Send invite"
                    aria-label="Send invite"
                  >
                    {supporterInviteLoading ? '...' : <IconSend size={17} />}
                  </button>
                  <a
                    className="icon-button intake-invite-combined__cta-open"
                    href={latestSupporterInviteLink || fallbackOpenFormLink || '#'}
                    target="_blank"
                    rel="noreferrer"
                    title="Open latest form"
                    aria-label="Open latest form"
                  >
                    <IconExternalLink size={17} />
                  </a>

                </div>
              </div>
            </div>
            <div className="module-card intake-tile stack intake-order-pending" data-tour="network-application-pipeline">
              <div className="card-header">
                <h4 className="intake-section-title">Pipeline</h4>
              </div>
              {supporterInviteError ? <div className="module-alert">{supporterInviteError}</div> : null}
              {supporterInviteStatus ? (
                <div className="module-alert module-alert--success">{supporterInviteStatus}</div>
              ) : null}
              <div className="form-grid" style={{ marginTop: 0 }}>
                <div className="filter-row">
                  <button
                    className="button-secondary button-secondary--small"
                    type="button"
                    onClick={loadSupporterInvites}
                    disabled={supporterInviteLoading}
                  >
                    {supporterInviteLoading
                      ? 'Refreshing...'
                      : `Refresh (${invitePipelinePendingCount})`}
                  </button>
                </div>
                <div className="filter-row" style={{ justifyContent: 'flex-end' }}>
                  <select
                    className="select input--compact"
                    value={invitePipelineFilter}
                    onChange={(event) => setInvitePipelineFilter(event.target.value)}
                  >
                    <option value="all">All statuses</option>
                    <option value="pending">Pending approval</option>
                    <option value="sent">Sent</option>
                    <option value="converted">Converted</option>
                  </select>
                </div>
              </div>
              <div className="table">
                <div className="table-row table-head">
                  <span>Recipient</span>
                  <span>Email</span>
                  <span>Audience</span>
                  <span>Channel</span>
                  <span>Type</span>
                  <span>Status</span>
                  <span>Sent / submitted</span>
                  <span>Reminders</span>
                  <span>Action</span>
                </div>
                {supporterInviteLoading ? (
                  <div className="table-row empty">Loading invite pipeline...</div>
                ) : null}
                {invitePipelineRows.length === 0 && !supporterInviteLoading ? (
                  <div className="table-row empty">No invite pipeline rows.</div>
                ) : null}
                {invitePipelineRows.map((row) => (
                  <div className="table-row" key={row.key}>
                    <span>{row.recipient || '-'}</span>
                    <span>{row.email || '-'}</span>
                    <span>{row.audience || '-'}</span>
                    <span>{row.channel || '-'}</span>
                    <span>{row.supporterType || 'Supporter'}</span>
                    <span>{row.statusLabel}</span>
                    <span>{row.createdAt || '-'}</span>
                    <span>{row.reminderCount ?? 0}</span>
                    <span className="filter-row">
                      {row.status === 'pending' ? (
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            className="button-secondary button-secondary--small"
                            type="button"
                            onClick={() =>
                              handleApprovePendingSupporterSignup(
                                row.pendingPerson || {
                                  email: row.email,
                                },
                              )
                            }
                            disabled={
                              (!row.pendingPerson?.signupId && (!row.email || row.email === '-')) ||
                              supporterApprovalProcessingEmail ===
                                (row.pendingPerson?.signupId || row.email)
                            }
                          >
                            {supporterApprovalProcessingEmail ===
                            (row.pendingPerson?.signupId || row.email)
                              ? 'Approving...'
                              : 'Approve'}
                          </button>
                          <button
                            className="button-secondary button-secondary--small"
                            type="button"
                            onClick={() =>
                              handleDeclinePendingSupporterSignup(
                                row.pendingPerson || {
                                  email: row.email,
                                },
                              )
                            }
                            disabled={
                              (!row.pendingPerson?.signupId && (!row.email || row.email === '-')) ||
                              supporterApprovalProcessingEmail ===
                                (row.pendingPerson?.signupId || row.email)
                            }
                            style={{ backgroundColor: '#dc3545', borderColor: '#dc3545', color: 'white' }}
                          >
                            {supporterApprovalProcessingEmail ===
                            (row.pendingPerson?.signupId || row.email)
                              ? 'Declining...'
                              : 'Decline'}
                          </button>
                        </div>
                      ) : null}
                      {row.invite && row.status === 'sent' ? (
                        <button
                          className="button-secondary button-secondary--small"
                          type="button"
                          onClick={() => handleSendSupporterReminder(row.invite)}
                          disabled={
                            supporterReminderSendingCode === row.invite.inviteCode
                          }
                        >
                          {supporterReminderSendingCode === row.invite.inviteCode
                            ? 'Sending...'
                            : 'Send reminder'}
                        </button>
                      ) : null}
                      {row.status === 'converted' ? <span className="pill">Converted</span> : null}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="module-card module-card__wide conversion-visual intake-order-conversion" data-tour="network-conversion-rate">
              <div className="card-header">
                <div>
                  <h3 className="intake-section-title">Conversion funnel</h3>
                  <p className="muted">
                    Visual flow from invitations to approved supporter/member records.
                  </p>
                </div>
                <div className="filter-row">
                  <button
                    className="button-secondary button-secondary--small"
                    type="button"
                    onClick={loadSupporterInvites}
                    disabled={supporterInviteLoading}
                  >
                    {supporterInviteLoading ? '...' : <IconRefresh size={16} />}
                  </button>
                  <div className="pill">Live</div>
                </div>
              </div>
              <div className="conversion-visual__layout">
                <div className="conversion-funnel">
                  <div className="conversion-funnel__segment conversion-funnel__segment--sent" style={{ width: '100%' }}>
                    <span className="conversion-funnel__value">{conversionInvitesSent}</span>
                  </div>
                  <div
                    className="conversion-funnel__segment conversion-funnel__segment--supporter"
                    style={{ width: `${supporterStageRatio}%` }}
                  >
                    <span className="conversion-funnel__value">{conversionRegisteredCount}</span>
                  </div>
                  <div
                    className="conversion-funnel__segment conversion-funnel__segment--member"
                    style={{ width: `${memberStageRatio}%` }}
                  >
                    <span className="conversion-funnel__value">{memberConversionCount}</span>
                  </div>
                </div>
                <div className="conversion-visual__legend">
                  <div className="conversion-legend-row">
                    <span>Invites sent</span>
                    <strong>{conversionInvitesSent}</strong>
                  </div>
                  <div className="conversion-legend-row">
                    <span>Become supporter</span>
                    <strong>{conversionRegisteredCount}</strong>
                  </div>
                  <div className="conversion-legend-row">
                    <span>Members</span>
                    <strong>{memberConversionCount}</strong>
                  </div>
                  <div className="conversion-legend-row conversion-legend-row--rate">
                    <span>Conversion rate</span>
                    <strong>{conversionRateValue.toFixed(1)}%</strong>
                  </div>
                  <p className="muted">Share = stage count / invites sent</p>
                </div>
              </div>
            </div>
            <details className="dashboard-detail intake-tile intake-order-videos intake-video-expander">
              <summary>
                <span className="intake-section-title">Signup videos</span>
              </summary>
              <div className="dashboard-detail__body">
                <div className="stack">
                  <label className="label">Welcome video (YouTube)</label>
                  <input
                    className="input"
                    placeholder="https://www.youtube.com/watch?v=..."
                    value={supporterSignupVideoUrl}
                    onChange={(event) => setSupporterSignupVideoUrl(event.target.value)}
                  />
                  <label className="label">Thank you video (YouTube)</label>
                  <input
                    className="input"
                    placeholder="https://www.youtube.com/watch?v=..."
                    value={supporterThankYouVideoUrl}
                    onChange={(event) => setSupporterThankYouVideoUrl(event.target.value)}
                  />
                  <div className="filter-row">
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={handleSaveSupporterSignupVideo}
                      disabled={supporterSignupVideoSaving}
                    >
                      {supporterSignupVideoSaving ? 'Saving...' : <IconCircleCheck size={16} />}
                    </button>
                  </div>
                  {supporterSignupVideoEmbedUrl ? (
                    <div className="card-divider">
                      <iframe
                        src={supporterSignupVideoEmbedUrl}
                        title="Supporter welcome video"
                        style={{ width: '100%', minHeight: 260, border: 0, borderRadius: 12 }}
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                      />
                    </div>
                  ) : (
                    <p className="muted">Add a YouTube link to show a welcome message on the signup form.</p>
                  )}
                  {supporterThankYouVideoEmbedUrl ? (
                    <div className="card-divider">
                      <iframe
                        src={supporterThankYouVideoEmbedUrl}
                        title="Supporter thank you video"
                        style={{ width: '100%', minHeight: 260, border: 0, borderRadius: 12 }}
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                      />
                    </div>
                  ) : (
                    <p className="muted">Add a second YouTube link for the post-signup thank you section.</p>
                  )}
                </div>
              </div>
            </details>
          </div>
        </div>
      )}
      {CRM_TASKS_ENABLED && activeTab === 'tasks' && (
        <div className="module-layout">
          <aside className="module-sidebar">
            <div className="sidebar-card sidebar-card--accent">
              <h3>Filters</h3>
              <div className="stack">
                <select
                  className="select"
                  value={taskFilterStatus}
                  onChange={(event) => setTaskFilterStatus(event.target.value)}
                >
                  <option value="All">All statuses</option>
                  <option value="Open">Open</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Done">Done</option>
                  <option value="Cancelled">Cancelled</option>
                </select>
                <select
                  className="select"
                  value={taskFilterGroup}
                  onChange={(event) => setTaskFilterGroup(event.target.value)}
                >
                  <option value="All">All groups</option>
                  <option value="Supporter">Supporters</option>
                  <option value="Member">Members</option>
                </select>
                <input
                  className="input"
                  type="number"
                  value={taskLimit}
                  min="10"
                  max="1000"
                  onChange={(event) => setTaskLimit(event.target.value)}
                />
                <button className="button" type="button" onClick={loadTasks}>
                  {tasksLoading ? 'Loading...' : 'Refresh'}
                </button>
              </div>
            </div>
            <div className="sidebar-card">
              <h3>Create task</h3>
              <form className="stack" onSubmit={handleCreateTask}>
                <input
                  className="input"
                  placeholder="Person email"
                  value={newTaskEmail}
                  onChange={(event) => setNewTaskEmail(event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Task title"
                  value={newTaskTitle}
                  onChange={(event) => setNewTaskTitle(event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Notes (optional)"
                  value={newTaskDescription}
                  onChange={(event) => setNewTaskDescription(event.target.value)}
                />
                <input
                  className="input"
                  type="date"
                  value={newTaskDueDate}
                  onChange={(event) => setNewTaskDueDate(event.target.value)}
                />
                <select
                  className="select"
                  value={newTaskStatus}
                  onChange={(event) => setNewTaskStatus(event.target.value)}
                >
                  <option value="Open">Open</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Done">Done</option>
                  <option value="Cancelled">Cancelled</option>
                </select>
                <button className="button" type="submit">
                  Add task
                </button>
              </form>
            </div>
            <div className="sidebar-card">
              <h3>Update status</h3>
              <div className="stack">
                <select
                  className="select"
                  value={taskUpdateId}
                  onChange={(event) => setTaskUpdateId(event.target.value)}
                >
                  <option value="">Select task</option>
                  {tasks.map((task) => (
                    <option key={task.taskId} value={task.taskId}>
                      {task.title}
                    </option>
                  ))}
                </select>
                <select
                  className="select"
                  value={taskUpdateStatus}
                  onChange={(event) => setTaskUpdateStatus(event.target.value)}
                >
                  <option value="Open">Open</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Done">Done</option>
                  <option value="Cancelled">Cancelled</option>
                </select>
                <button className="button" type="button" onClick={handleTaskStatusUpdate}>
                  Update status
                </button>
              </div>
            </div>
          </aside>
          <div className="module-main">
            {tasksError ? <div className="module-alert">{tasksError}</div> : null}
            <div className="module-card module-card__wide panel panel--highlight">
              <div className="card-header">
                <div>
                  <h3>Tasks</h3>
                  <p className="muted">Create and track follow-ups.</p>
                </div>
                <div className="pill">NCC</div>
              </div>
              <div className="module-footer">
                <span>
                  <strong>Open</strong> {taskCounts.Open}
                </span>
                <span>
                  <strong>In Progress</strong> {taskCounts['In Progress']}
                </span>
                <span>
                  <strong>Done</strong> {taskCounts.Done}
                </span>
                <span>
                  <strong>Cancelled</strong> {taskCounts.Cancelled}
                </span>
              </div>
              <div className="card-divider">
                <h4>Task status overview</h4>
              </div>
              <div className="chart-frame chart-frame--short">
                <Bar data={taskStatusData} options={taskStatusOptions} />
              </div>
            </div>
            <div className="module-card module-card__wide panel">
              <div className="table">
                <div className="table-row table-row--tasks table-head">
                  <span>Title</span>
                  <span>Status</span>
                  <span>Due</span>
                  <span>Email</span>
                  <span>Actions</span>
                </div>
                {tasks.length === 0 && !tasksLoading && (
                  <div className="table-row empty">No tasks found.</div>
                )}
                {tasks.map((task) => (
                  <div className="table-row table-row--tasks" key={task.taskId}>
                    <span>{task.title}</span>
                    <span>{task.status}</span>
                    <span>{task.dueDate || '-'}</span>
                    <span>{task.email}</span>
                    <div className="table-actions">
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => handleDeleteTask(task.taskId)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
      {(activeTab === 'people' || activeTab === 'segments' || activeTab === 'outreach') && (
        <div className="stack crm-outreach-flow">
          <div className="module-card module-card__wide module-card--outreach-flow-segment" data-tour="network-segment-builder">
            <div className="card-header">
              <div>
                <h3>{activeTab === 'outreach' ? 'Audience' : 'Segments'}</h3>
                <p className="muted">
                  {activeTab === 'outreach'
                    ? 'Pick a saved Network segment, then register that audience for the selected event.'
                    : 'Create reusable audience groups from your people directory. Campaigns and surveys can use these same saved segments.'}
                </p>
              </div>
              <div className="pill">Audience</div>
            </div>
            {segmentsError ? <div className="module-alert">{segmentsError}</div> : null}
            <div className="filter-row">
              <select
                className="select"
                value={segmentSelectedId}
                onChange={(event) => setSegmentSelectedId(event.target.value)}
              >
                <option value="">Select saved segment</option>
                {segments.map((segment) => (
                  <option key={segment.segmentId} value={segment.segmentId}>
                    {segment.name}
                  </option>
                ))}
              </select>
              <button
                className="button-secondary"
                type="button"
                disabled={!segmentSelectedId}
                onClick={() => handleDeleteSegment(segmentSelectedId)}
              ><IconTrash size={17} /></button>
              {activeTab !== 'outreach' ? (
                <button
                  className="button"
                  type="button"
                  onClick={() => setShowNewSegmentForm((prev) => !prev)}
                >
                  {showNewSegmentForm ? <IconCircleX size={17} /> : <IconPlus size={17} />}
                </button>
              ) : null}
          </div>
            {segmentSelectedId ? (
              <details
                className="dashboard-detail intake-tile outreach-detail-expander"
                key={segmentSelectedId}
                defaultOpen
              >
                <summary>
                  <span className="intake-section-title">Segment details</span>
                </summary>
                <div className="dashboard-detail__body">
                  {selectedSegment ? (
                    <div className="stack" style={{ marginTop: 0, gap: 12 }}>
                      <div className="module-footer outreach-detail-footer">
                        <span>
                          <strong>Name:</strong> {selectedSegment.name || '-'}
                        </span>
                        <span>
                          <strong>Description:</strong> {selectedSegment.description || '-'}
                        </span>
                        <span>
                          <strong>Size:</strong>{' '}
                          {segmentCountLoading ? '...' : segmentMemberCount != null ? segmentMemberCount : '-'}
                        </span>
                        <span>
                          <strong>Updated:</strong> {selectedSegment.updatedAt || '-'}
                        </span>
                        <span>
                          <strong>ID:</strong> {selectedSegment.segmentId || '-'}
                        </span>
                      </div>
                      <div>
                        <strong>Filters</strong>
                        <p
                          className="muted"
                          style={{ whiteSpace: 'pre-line', margin: '6px 0 0', lineHeight: 1.45 }}
                        >
                          {formatSegmentFilterSummary(selectedSegment.filterSpec || {})}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="muted" style={{ margin: 0 }}>
                      Segment data is unavailable. Try refreshing the list.
                    </p>
                  )}
                </div>
              </details>
            ) : (
              <p className="muted" style={{ margin: 0 }}>
                Select a saved segment to view its details.
              </p>
            )}
            {activeTab === 'outreach' ? (
            <div className="outreach-segment-to-event" style={{ marginTop: 14 }}>
              <h4 className="intake-section-title" style={{ margin: '0 0 8px', fontSize: '1rem' }}>
                Register segment for selected event
              </h4>
              <p className="muted" style={{ margin: '0 0 10px', lineHeight: 1.45 }}>
                Uses the event from the Events section (above). Choose a segment, then bulk-register those
                people for that event.
              </p>
              {!outreachEventId ? (
                <p className="muted" style={{ margin: 0 }}>
                  Select or create an event in Events first.
                </p>
              ) : (
                <>
                  <p className="muted" style={{ margin: '0 0 8px' }}>
                    Event:{' '}
                    <strong>{outreachSelectedEvent?.name || outreachEventId}</strong>
                  </p>
                  <button
                    type="button"
                    className="button"
                    disabled={!segmentSelectedId || outreachAttachLoading}
                    onClick={handleAttachSegmentAudienceToEvent}
                  >
                    {outreachAttachLoading ? '...' : <IconCircleCheck size={17} />}
                  </button>
                </>
              )}
              {outreachAttachMessage ? (
                <div className="module-alert" style={{ marginTop: 10 }}>
                  {outreachAttachMessage}
                </div>
              ) : null}
            </div>
            ) : null}
            {activeTab !== 'outreach' && showNewSegmentForm ? (
                <form className="stack" onSubmit={handleCreateSegment} data-tour="network-segment-form">
                  <input
                    className="input"
                    value={segmentName}
                    onChange={(event) => setSegmentName(event.target.value)}
                  placeholder="Segment name"
                  />
                  <input
                    className="input"
                    value={segmentDescription}
                    onChange={(event) => setSegmentDescription(event.target.value)}
                  placeholder="Description"
                  />
                  <div className="filter-row">
                    <select
                      className="select"
                      value={segmentGroup}
                      onChange={(event) => setSegmentGroup(event.target.value)}
                    >
                      <option value="All">All groups</option>
                      <option value="Supporter">Supporters</option>
                      <option value="Member">Members</option>
                    </select>
                    <select
                      className="select"
                      value={segmentTimeAvailability}
                      onChange={(event) => setSegmentTimeAvailability(event.target.value)}
                    >
                      <option value="All">Any availability</option>
                      <option value="Weekends">Weekends</option>
                      <option value="Evenings">Evenings</option>
                      <option value="Full-time">Full-time</option>
                      <option value="Ad-hoc">Ad-hoc</option>
                    </select>
                    <select
                      className="select"
                      value={segmentGender}
                      onChange={(event) => setSegmentGender(event.target.value)}
                    >
                      <option value="All">Any gender</option>
                      <option value="F">Female</option>
                      <option value="M">Male</option>
                      <option value="O">Other</option>
                      <option value="U">Unspecified</option>
                    </select>
                  </div>
                      <div className="filter-row">
                        <input
                          className="input"
                          type="number"
                          min="0"
                          value={segmentMinAge}
                          onChange={(event) => setSegmentMinAge(event.target.value)}
                          placeholder="Min age"
                        />
                        <input
                          className="input"
                          type="number"
                          min="0"
                          value={segmentMaxAge}
                          onChange={(event) => setSegmentMaxAge(event.target.value)}
                          placeholder="Max age"
                        />
                        <input
                          className="input"
                          value={segmentCityContains}
                          onChange={(event) => setSegmentCityContains(event.target.value)}
                          placeholder="City contains"
                        />
                        <input
                          className="input"
                          value={segmentDistrictContains}
                          onChange={(event) => setSegmentDistrictContains(event.target.value)}
                          placeholder="District contains"
                        />
                      </div>
                      <div className="filter-row">
                        <select
                          className="select"
                          value={segmentManifesto}
                          onChange={(event) => setSegmentManifesto(event.target.value)}
                        >
                          <option value="All">Any manifesto status</option>
                          <option value="Yes">Agrees with manifesto</option>
                          <option value="No">Does not agree</option>
                        </select>
                        <select
                          className="select"
                          value={segmentMembershipInterest}
                          onChange={(event) => setSegmentMembershipInterest(event.target.value)}
                        >
                          <option value="All">Any membership interest</option>
                          <option value="Yes">Interested in membership</option>
                          <option value="No">Not interested</option>
                        </select>
                        <select
                          className="select"
                          value={segmentHasEmail}
                          onChange={(event) => setSegmentHasEmail(event.target.value)}
                        >
                          <option value="All">Any email status</option>
                          <option value="Yes">Has email</option>
                          <option value="No">No email</option>
                        </select>
                        <select
                          className="select"
                          value={segmentHasPhone}
                          onChange={(event) => setSegmentHasPhone(event.target.value)}
                        >
                          <option value="All">Any phone status</option>
                          <option value="Yes">Has phone</option>
                          <option value="No">No phone</option>
                        </select>
                      </div>
                      <div className="filter-row">
                        <input
                          className="input"
                          type="number"
                          min="0"
                          step="0.5"
                          value={segmentMinEffort}
                          onChange={(event) => setSegmentMinEffort(event.target.value)}
                          placeholder="Min effort hours"
                        />
                        <input
                          className="input"
                          value={segmentNameContains}
                          onChange={(event) => setSegmentNameContains(event.target.value)}
                          placeholder="Name contains"
                        />
                        <input
                          className="input"
                          value={segmentAddressContains}
                          onChange={(event) => setSegmentAddressContains(event.target.value)}
                          placeholder="Address contains"
                        />
                      </div>
                      <div className="filter-row">
                        <select
                          className="select"
                          multiple
                          value={segmentTags}
                          onChange={(event) =>
                            setSegmentTags(
                              Array.from(event.target.selectedOptions, (opt) => opt.value),
                            )
                          }
                        >
                          {segmentTagOptions.map((tag) => (
                            <option key={tag} value={tag}>
                              {tag}
                            </option>
                          ))}
                        </select>
                        <select
                          className="select"
                          multiple
                          value={segmentSkills}
                          onChange={(event) =>
                            setSegmentSkills(
                              Array.from(event.target.selectedOptions, (opt) => opt.value),
                            )
                          }
                        >
                          {segmentSkillOptions.map((skill) => (
                            <option key={skill} value={skill}>
                              {skill}
                            </option>
                          ))}
                        </select>
                      </div>
                  <button className="button" type="submit">
                    Save segment
                  </button>
                </form>
            ) : null}
                  </div>

          {activeTab === 'outreach' ? (
          <div id="campaign-events" className="module-card module-card__wide module-card--outreach-flow-events">
                <div className="card-header">
                  <div>
                <h3>Events</h3>
                <p className="muted">
                  Create a new event or pick one from the list (no segment required). Then attach a segment
                  below if you want bulk registrations, and use distribution for links and invites.
                </p>
                  </div>
              <div className="pill">Events</div>
                </div>
            {outreachEventsError ? <div className="module-alert">{outreachEventsError}</div> : null}
            {segmentEventStatusMessage ? <div className="module-alert">{segmentEventStatusMessage}</div> : null}
                <div className="filter-row">
              <select
                className="select"
                value={outreachEventId}
                onChange={(event) => setOutreachEventId(event.target.value)}
              >
                <option value="">Select created event</option>
                {outreachEvents.map((event) => (
                  <option key={event.eventId} value={event.eventId}>
                    {event.name}
                  </option>
                ))}
              </select>
              <button className="button-secondary" type="button" onClick={loadOutreachEvents}><IconRefresh size={17} /></button>
                  <button
                    className="button"
                    type="button"
                onClick={() => setShowNewEventForm((prev) => !prev)}
                  >
                {showNewEventForm ? <IconCircleX size={17} /> : <IconPlus size={17} />}
                  </button>
                </div>
            {outreachEventId ? (
              <details
                className="dashboard-detail intake-tile outreach-detail-expander"
                key={outreachEventId}
                defaultOpen
              >
                <summary>
                  <span className="intake-section-title">Event details</span>
                </summary>
                <div className="dashboard-detail__body">
                  {outreachSelectedEvent ? (
                    <div className="module-footer outreach-detail-footer">
                      <span>
                        <strong>Name:</strong> {outreachSelectedEvent.name || '-'}
                      </span>
                      <span>
                        <strong>Start:</strong> {outreachSelectedEvent.startDate || '-'}
                      </span>
                      <span>
                        <strong>End:</strong> {outreachSelectedEvent.endDate || '-'}
                      </span>
                      <span>
                        <strong>Status:</strong> {outreachSelectedEvent.status || 'Planned'}
                      </span>
                      <span>
                        <strong>Registrations:</strong> {outreachSelectedEvent.registrations ?? 0}
                      </span>
                      <span>
                        <strong>Location:</strong> {outreachSelectedEvent.location || '-'}
                      </span>
                    </div>
                  ) : (
                    <p className="muted" style={{ margin: 0 }}>
                      Event data is unavailable. Try refreshing the list.
                    </p>
                  )}
                </div>
              </details>
            ) : (
              <p className="muted" style={{ margin: 0 }}>
                Select an event to view its details.
              </p>
            )}
            {showNewEventForm ? (
                    <div className="stack">
                      <input
                        className="input"
                        placeholder="Event name"
                        value={segmentEventName}
                        onChange={(event) => setSegmentEventName(event.target.value)}
                      />
                      <div className="filter-row">
                        <input
                          className="input"
                          type="date"
                          value={segmentEventStartDate}
                          onChange={(event) => setSegmentEventStartDate(event.target.value)}
                        />
                        <input
                          className="input"
                          type="date"
                          value={segmentEventEndDate}
                          onChange={(event) => setSegmentEventEndDate(event.target.value)}
                        />
                      </div>
                      <div className="filter-row">
                        <input
                          className="input"
                          placeholder="Location"
                          value={segmentEventLocation}
                          onChange={(event) => setSegmentEventLocation(event.target.value)}
                        />
                        <select
                          className="select"
                          value={segmentEventStatus}
                          onChange={(event) => setSegmentEventStatus(event.target.value)}
                        >
                          <option value="Planned">Planned</option>
                          <option value="Scheduled">Scheduled</option>
                          <option value="Completed">Completed</option>
                          <option value="Cancelled">Cancelled</option>
                        </select>
                        <input
                          className="input"
                          type="number"
                          placeholder="Capacity"
                          value={segmentEventCapacity}
                          onChange={(event) => setSegmentEventCapacity(event.target.value)}
                        />
                      </div>
                      <input
                        className="input"
                        placeholder="Notes"
                        value={segmentEventNotes}
                        onChange={(event) => setSegmentEventNotes(event.target.value)}
                      />
                      <button className="button" type="button" onClick={handleCreateOutreachEvent}>
                        Create event
                      </button>
                    </div>
                ) : null}
                </div>

          ) : null}

          {activeTab === 'outreach' ? (
          <div id="campaign-share" className="module-card module-card__wide module-card--outreach-flow-distribute" data-tour="campaign-send-link">
            <div className="card-header">
              <div>
                <h3>Send registration link</h3>
                <p className="muted">
                  Choose a single recipient, the saved segment, or verified / registered Google groups.
                  Then pick a channel and send or copy the event link.
                </p>
              </div>
              <div className="share-channel-icons" aria-label="Registration channel">
                <button
                  className={
                    outreachInviteForm.channel === 'email'
                      ? 'icon-button icon-button--primary active'
                      : 'icon-button'
                  }
                  type="button"
                  title="Email"
                  aria-label="Email"
                  onClick={() =>
                    setOutreachInviteForm((prev) => ({
                      ...prev,
                      channel: 'email',
                    }))
                  }
                >
                  <IconMail size={17} />
                </button>
                <button
                  className={
                    outreachInviteForm.channel === 'whatsapp'
                      ? 'icon-button icon-button--primary active'
                      : 'icon-button'
                  }
                  type="button"
                  title="WhatsApp"
                  aria-label="WhatsApp"
                  onClick={() =>
                    setOutreachInviteForm((prev) => ({
                      ...prev,
                      channel: 'whatsapp',
                    }))
                  }
                >
                  <IconBrandWhatsapp size={17} />
                </button>
                <button
                  className={
                    outreachInviteForm.channel === 'slack'
                      ? 'icon-button icon-button--primary active'
                      : 'icon-button'
                  }
                  type="button"
                  title="Slack"
                  aria-label="Slack"
                  onClick={() =>
                    setOutreachInviteForm((prev) => ({
                      ...prev,
                      channel: 'slack',
                    }))
                  }
                >
                  <IconBrandSlack size={17} />
                </button>
              </div>
            </div>
            {outreachDistributionError ? (
              <div className="module-alert">{outreachDistributionError}</div>
            ) : null}
            {outreachDistributionStatus ? (
              <div className="module-alert module-alert--success">{outreachDistributionStatus}</div>
            ) : null}
            <div className="module-card intake-tile intake-order-links">
              <div className="intake-invite-compact">
                <div className="intake-invite-compact__form">
                  <div className="intake-section-heading">
                    <h4 className="intake-section-title">Invite</h4>
                  </div>
                  <form
                    id="crm-outreach-invite-form"
                    className="form-grid intake-invite-form-compact"
                    onSubmit={handleSubmitOutreachInvite}
                  >
                    <select
                      className="select"
                      value={outreachInviteForm.inviteAudience}
                      onChange={(event) =>
                        setOutreachInviteForm((prev) => ({
                          ...prev,
                          inviteAudience: event.target.value,
                        }))
                      }
                    >
                      <option value="individual">Single recipient</option>
                      {segmentSelectedId ? (
                        <option value="segment">Selected segment (member emails)</option>
                      ) : null}
                      <option value="verified">Verified users (group list)</option>
                      <option value="registered">Registered users (group list)</option>
                    </select>
                    {outreachInviteForm.inviteAudience === 'individual' ? (
                      <>
                        <input
                          className="input"
                          placeholder="Recipient name"
                          value={outreachInviteForm.recipientName}
                          onChange={(event) =>
                            setOutreachInviteForm((prev) => ({
                              ...prev,
                              recipientName: event.target.value,
                            }))
                          }
                        />
                        {outreachInviteForm.channel === 'email' ? (
                          <input
                            className="input"
                            type="email"
                            placeholder="Recipient email"
                            value={outreachInviteForm.recipientEmail}
                            onChange={(event) =>
                              setOutreachInviteForm((prev) => ({
                                ...prev,
                                recipientEmail: event.target.value,
                              }))
                            }
                          />
                        ) : null}
                        {outreachInviteForm.channel === 'whatsapp' ? (
                          <input
                            className="input"
                            placeholder="Recipient phone"
                            value={outreachInviteForm.recipientPhone}
                            onChange={(event) =>
                              setOutreachInviteForm((prev) => ({
                                ...prev,
                                recipientPhone: event.target.value,
                              }))
                            }
                          />
                        ) : null}
                      </>
                    ) : outreachInviteForm.inviteAudience === 'segment' &&
                      outreachInviteForm.channel === 'email' ? (
                      <div className="form-grid__full">
                        <p className="muted" style={{ margin: 0 }}>
                          Sends the registration link directly to people in the selected segment who have
                          email addresses.
                        </p>
                      </div>
                    ) : outreachInviteForm.channel === 'email' ? (
                      <div className="form-grid__full">
                        <label className="label">Group email list</label>
                        <input
                          className="input"
                          type="email"
                          list="outreach-event-invite-group-options"
                          placeholder="group@googlegroups.com"
                          value={getInviteAudienceGroupEmail(
                            outreachInviteForm.inviteAudience,
                            supporterInviteGroupsConfig,
                          )}
                          onChange={(event) =>
                            setInviteAudienceGroupEmail(
                              outreachInviteForm.inviteAudience,
                              event.target.value,
                            )
                          }
                        />
                        <datalist id="outreach-event-invite-group-options">
                          {[...new Set(Object.values(supporterInviteGroupsConfig).filter(Boolean))].map(
                            (groupEmail) => (
                              <option key={groupEmail} value={groupEmail} />
                            ),
                          )}
                        </datalist>
                        <p className="muted">
                          Outlook opens with this group email in To: field for{' '}
                          {getInviteAudienceLabel(outreachInviteForm.inviteAudience)}.
                        </p>
                      </div>
                    ) : outreachInviteForm.inviteAudience === 'segment' ? (
                      <div className="form-grid__full muted">
                        Segment audience: Slack copies the message plus all member emails. WhatsApp opens a
                        short message and copies the full email list when possible.
                      </div>
                    ) : (
                      <div className="form-grid__full muted">
                        Audience group lists are used when channel is Email.
                      </div>
                    )}
                  </form>
                </div>
                <div className="intake-invite-combined__cta-row intake-invite-compact__actions">
                  <button
                    className="icon-button icon-button--primary intake-invite-combined__cta-send"
                    type="submit"
                    form="crm-outreach-invite-form"
                    disabled={!outreachEventId}
                    title="Send invite"
                    aria-label="Send invite"
                  ><IconSend size={17} /></button>
                  <button
                    className="icon-button intake-invite-combined__cta-copy"
                    type="button"
                    title="Copy link"
                    aria-label="Copy link"
                    onClick={handleCopyOutreachEventLink}
                  ><IconCopy size={17} /></button>
                  <a
                    className="icon-button intake-invite-combined__cta-open"
                    href={outreachPublicLink || '#'}
                    target="_blank"
                    rel="noreferrer"
                    title="Open form"
                    aria-label="Open form"
                  ><IconExternalLink size={17} /></a>
                </div>
              </div>
            </div>
          </div>
          ) : null}

          {activeTab === 'outreach' ? (
          <div id="campaign-results" className="module-card module-card__wide module-card--outreach-flow-results">
            <div className="card-header">
              <div>
                <h3>Results</h3>
                <p className="muted">Registration and audience status for the selected event.</p>
              </div>
              <div className="pill">Results</div>
            </div>
            <div className="module-footer outreach-detail-footer">
              <span>
                <strong>Event:</strong> {outreachSelectedEvent?.name || 'Select an event'}
              </span>
              <span>
                <strong>Registrations:</strong> {outreachSelectedEvent?.registrations ?? 0}
              </span>
              <span>
                <strong>Audience:</strong> {selectedSegment?.name || 'No segment selected'}
              </span>
            </div>
          </div>
          ) : null}
        </div>
      )}
    </section>
  )
}

function CRMDataEntryTab() {
  const defaultEducationOptions = [
    'High School',
    'Vocational',
    'Bachelor',
    'Master',
    'Doctorate',
  ]
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    supporterType: 'Supporter',
    gender: '',
    age: '',
    phone: '',
    timeAvailability: 'Unspecified',
    address: '',
    lat: '',
    lon: '',
    effortHours: '',
    eventsAttendedCount: '',
    referralCount: '',
    tasksCompleted: '',
    educationLevels: [],
    about: '',
    tags: '',
    skills: [],
    involvementAreas: '',
    agreesWithManifesto: false,
    interestedInMembership: false,
    facebookGroupMember: false,
  })
  const [educationOptions, setEducationOptions] = useState(defaultEducationOptions)
  const [skillOptions, setSkillOptions] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [importFile, setImportFile] = useState(null)
  const [importType, setImportType] = useState('Supporter')
  const [importStatus, setImportStatus] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  useEffect(() => {
    let mounted = true
    Promise.all([
      getJson('/crm/distinct-values?label=EducationLevel'),
      getJson('/crm/distinct-values?label=Skill'),
    ])
      .then(([education, skills]) => {
        if (!mounted) return
        if (Array.isArray(education) && education.length) {
          setEducationOptions(education)
        }
        setSkillOptions(Array.isArray(skills) ? skills : [])
      })
      .catch(() => null)
    return () => {
      mounted = false
    }
  }, [])

  const handleSave = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')
    if (!form.email.trim()) {
      setError('Email is required.')
      return
    }
    setSaving(true)
    try {
      await requestJson('/crm/people', {
        method: 'POST',
        payload: {
          email: form.email.trim(),
          firstName: form.firstName.trim(),
          lastName: form.lastName.trim(),
          supporterType: form.supporterType,
          gender: form.gender,
          age: form.age ? Number(form.age) : null,
          phone: form.phone.trim(),
          timeAvailability: form.timeAvailability,
          address: form.address.trim(),
          lat: form.lat ? Number(form.lat) : null,
          lon: form.lon ? Number(form.lon) : null,
          effortHours: form.effortHours ? Number(form.effortHours) : null,
          eventsAttendedCount: form.eventsAttendedCount ? Number(form.eventsAttendedCount) : null,
          referralCount: form.referralCount ? Number(form.referralCount) : null,
          tasksCompleted: form.tasksCompleted ? Number(form.tasksCompleted) : null,
          educationLevels: form.educationLevels,
          about: form.about.trim(),
          tags: form.tags
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          skills: form.skills,
          involvementAreas: form.involvementAreas
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          agreesWithManifesto: !!form.agreesWithManifesto,
          interestedInMembership: !!form.interestedInMembership,
          facebookGroupMember: !!form.facebookGroupMember,
        },
      })
      setSuccess('Person saved.')
      setForm((prev) => ({
        ...prev,
        firstName: '',
        lastName: '',
        email: '',
        phone: '',
        address: '',
            educationLevels: [],
            skills: [],
      }))
    } catch (err) {
      setError(err.message || 'Unable to save person.')
    } finally {
      setSaving(false)
    }
  }

  const handleImport = async () => {
    if (!importFile) {
      setImportStatus('Select a CSV file first.')
      return
    }
    setImportStatus('Uploading...')
    const formData = new FormData()
    formData.append('file', importFile)
    try {
      const result = await requestForm(
        `/crm/people/import?default_type=${encodeURIComponent(importType)}`,
        {
          method: 'POST',
          formData,
        },
      )
      setImportStatus(
        `Import complete. ${result?.created ?? 0} rows created/updated.`,
      )
    } catch (err) {
      setImportStatus(err.message || 'Import failed.')
    }
  }

  const handleExport = async (group) => {
    setExportError('')
    setExporting(true)
    try {
      const rows = await getJson(
        `/crm/people/summary?group=${encodeURIComponent(group)}&limit=5000`,
      )
      downloadCsv(`${group.toLowerCase()}_people.csv`, rows)
    } catch (err) {
      setExportError(err.message || 'Export failed.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="stack">
      <div className="module-grid">
      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>New person</h3>
            <p className="muted">Capture supporters and members quickly.</p>
          </div>
              <div className="pill">Network</div>
        </div>

        {error ? <div className="module-alert">{error}</div> : null}
        {success ? <div className="module-alert module-alert--success">{success}</div> : null}

        <form className="form-grid" onSubmit={handleSave}>
          <input
            className="input"
            placeholder="First name"
            value={form.firstName}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, firstName: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Last name"
            value={form.lastName}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, lastName: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Email *"
            value={form.email}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, email: event.target.value }))
            }
          />
          <select
            className="select"
            value={form.supporterType}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, supporterType: event.target.value }))
            }
          >
            <option value="Supporter">Supporter</option>
            <option value="Member">Member</option>
          </select>
          <select
            className="select"
            value={form.gender}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, gender: event.target.value }))
            }
          >
            <option value="">Gender</option>
            <option value="Male">Male</option>
            <option value="Female">Female</option>
            <option value="Other">Other</option>
          </select>
          <input
            className="input"
            type="number"
            placeholder="Age"
            value={form.age}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, age: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Phone"
            value={form.phone}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, phone: event.target.value }))
            }
          />
          <select
            className="select"
            value={form.timeAvailability}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, timeAvailability: event.target.value }))
            }
          >
            <option value="Unspecified">Unspecified availability</option>
            <option value="Weekends">Weekends</option>
            <option value="Evenings">Evenings</option>
            <option value="Full-time">Full-time</option>
            <option value="Ad-hoc">Ad-hoc</option>
          </select>
          <input
            className="input"
            placeholder="Address"
            value={form.address}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, address: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Latitude"
            value={form.lat}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, lat: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Longitude"
            value={form.lon}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, lon: event.target.value }))
            }
          />
          <input
            className="input"
            type="number"
            step="0.5"
            placeholder="Effort hours"
            value={form.effortHours}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, effortHours: event.target.value }))
            }
          />
          <input
            className="input"
            type="number"
            placeholder="Events attended count"
            value={form.eventsAttendedCount}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, eventsAttendedCount: event.target.value }))
            }
          />
          <input
            className="input"
            type="number"
            placeholder="Referral count"
            value={form.referralCount}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, referralCount: event.target.value }))
            }
          />
          <input
            className="input"
            type="number"
            placeholder="Tasks completed"
            value={form.tasksCompleted}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, tasksCompleted: event.target.value }))
            }
          />
          <select
            className="select"
            multiple
            value={form.educationLevels}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                educationLevels: Array.from(event.target.selectedOptions, (opt) => opt.value),
              }))
            }
          >
            {educationOptions.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
          <input
            className="input"
            placeholder="Tags (comma separated)"
            value={form.tags}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, tags: event.target.value }))
            }
          />
          <select
            className="select"
            multiple
            value={form.skills}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                skills: Array.from(event.target.selectedOptions, (opt) => opt.value),
              }))
            }
          >
            {skillOptions.length === 0 ? (
              <option value="" disabled>
                No skills yet (add via imports/profile updates)
              </option>
            ) : null}
            {skillOptions.map((skill) => (
              <option key={skill} value={skill}>
                {skill}
              </option>
            ))}
          </select>
          <input
            className="input"
            placeholder="Involvement areas (comma separated)"
            value={form.involvementAreas}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, involvementAreas: event.target.value }))
            }
          />
          <textarea
            className="textarea form-grid__full"
            placeholder="About / notes"
            value={form.about}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, about: event.target.value }))
            }
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.agreesWithManifesto}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, agreesWithManifesto: event.target.checked }))
              }
            />
            Agrees with manifesto
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.interestedInMembership}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, interestedInMembership: event.target.checked }))
              }
            />
            Interested in membership
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.facebookGroupMember}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, facebookGroupMember: event.target.checked }))
              }
            />
            Facebook group member
          </label>
          <button className="button" type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Save person'}
          </button>
        </form>
      </div>

        <div className="module-card">
        <div className="card-header">
          <div>
            <h3>People CSV import</h3>
            <p className="muted">Upload supporters or members in bulk.</p>
          </div>
        </div>
        <div className="stack">
          <select
            className="select"
            value={importType}
            onChange={(event) => setImportType(event.target.value)}
          >
            <option value="Supporter">Supporters</option>
            <option value="Member">Members</option>
          </select>
          <input
            className="input"
            type="file"
            accept=".csv"
            onChange={(event) => setImportFile(event.target.files?.[0] || null)}
          />
          <div className="stack">
            <p className="muted">
              Required columns: <strong>email</strong>, <strong>first_name</strong>,{' '}
              <strong>last_name</strong>.
            </p>
            <p className="muted">
              Optional columns: gender, age, phone, address, lat, lon, supporter_type,
              effort_hours, events_attended, tasks_completed, referral_count, education,
              skills, time_availability.
            </p>
          </div>
          <button className="button" type="button" onClick={handleImport}>
            Import CSV
          </button>
          {importStatus ? <p className="muted">{importStatus}</p> : null}
        </div>
      </div>

      <div className="module-card">
        <div className="card-header">
          <div>
            <h3>Export data</h3>
            <p className="muted">Download a CSV snapshot.</p>
          </div>
        </div>
        {exportError ? <div className="module-alert">{exportError}</div> : null}
        <div className="stack">
          <button
            className="button-secondary"
            type="button"
            onClick={() => handleExport('Supporter')}
            disabled={exporting}
          >
            Export supporters
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => handleExport('Member')}
            disabled={exporting}
          >
            Export members
          </button>
        </div>
      </div>
    </div>
    </div>
  )
}

function CRMDashboardTab({ mapStats } = {}) {
  const [dashboard, setDashboard] = useState(() => cachedNetworkDashboard)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    getJson('/crm/dashboard', { cacheMs: NETWORK_CLIENT_CACHE_MS })
      .then((payload) => {
        cachedNetworkDashboard = payload
        if (!mounted) return
        setDashboard(payload)
      })
      .catch((err) => {
        if (!mounted) return
        setError(err.message || 'Unable to load dashboard.')
      })
    return () => {
      mounted = false
    }
  }, [])

  const filteredCharts = useMemo(() => {
    if (!Array.isArray(mapStats?.people)) return null
    const rows = mapStats.people
    const countValues = (values, keyName) => {
      const counts = new Map()
      values.forEach((value) => {
        const label = String(value || '').trim() || 'Unspecified'
        counts.set(label, (counts.get(label) || 0) + 1)
      })
      return Array.from(counts.entries())
        .map(([label, count]) => ({ [keyName]: label, count }))
        .sort((a, b) => b.count - a.count || String(a[keyName]).localeCompare(String(b[keyName])))
    }
    const byGroup = countValues(rows.map((person) => person.type || 'Unspecified'), 'group')
    const byGender = countValues(rows.map((person) => person.gender || 'U'), 'gender')
    const ageOrder = ['18-24', '25-34', '35-44', '45-54', '55-64', '65+', 'Unknown', 'Unspecified']
    const byAge = countValues(rows.map((person) => person.ageGroup || 'Unknown'), 'group').sort((a, b) => {
      const aIndex = ageOrder.indexOf(a.group)
      const bIndex = ageOrder.indexOf(b.group)
      if (aIndex !== -1 || bIndex !== -1) return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex)
      return String(a.group).localeCompare(String(b.group))
    })
    const groupTimeAvailability = (value) => {
      const text = String(value || '').trim().toLowerCase()
      if (!text || text === 'unspecified' || text === 'unknown') return 'Flexible/unspecified'
      const hasAfterHours =
        text.includes('\u10d0\u10e0\u10d0\u10e1\u10d0\u10db\u10e3\u10e8\u10d0\u10dd') ||
        text.includes('\u10d0\u10e0\u10d0\u10e1\u10d0\u10db\u10e3\u10e8\u10dd') ||
        text.includes('after') ||
        text.includes('evening') ||
        text.includes('off hours') ||
        text.includes('non-working')
      const hasWorkingHours =
        text.includes('\u10e1\u10d0\u10db\u10e3\u10e8\u10d0\u10dd') ||
        text.includes('working hour') ||
        text.includes('business hour') ||
        text.includes('daytime')
      const hasWeekend =
        text.includes('\u10e8\u10d0\u10d1\u10d0\u10d7') ||
        text.includes('\u10d9\u10d5\u10d8\u10e0\u10d0\u10e1') ||
        text.includes('weekend') ||
        text.includes('saturday') ||
        text.includes('sunday')
      const hasFlexible =
        text.includes('\u10d7\u10d0\u10d5\u10d8\u10e1\u10e3\u10e4\u10d0\u10da') ||
        text.includes('\u10e8\u10d4\u10d7\u10d0\u10dc\u10ee\u10db') ||
        text.includes('\u10e8\u10d4\u10e1\u10d0\u10eb\u10da\u10d4\u10d1') ||
        text.includes('\u10e1\u10d0\u10ed\u10d8\u10e0\u10dd\u10d4\u10d1') ||
        text.includes('\u10db\u10dd\u10d5\u10d0\u10ee\u10d4\u10e0\u10ee') ||
        text.includes('flex') ||
        text.includes('depends') ||
        text.includes('as needed') ||
        text.includes('by agreement')
      if (hasAfterHours) return 'After hours'
      if (hasWorkingHours) return 'Working hours'
      if (hasWeekend) return 'Weekends'
      if (hasFlexible) return 'Flexible/unspecified'
      return 'Flexible/unspecified'
    }
    const timeOrder = ['Working hours', 'After hours', 'Weekends', 'Flexible/unspecified']
    const byTime = countValues(rows.map((person) => groupTimeAvailability(person.timeAvailability)), 'group').sort(
      (a, b) => timeOrder.indexOf(a.group) - timeOrder.indexOf(b.group),
    )
    const byRegion = countValues(rows.map((person) => person.city || 'Unknown'), 'group').slice(0, 12)
    const normalizeManifesto = (value) => {
      if (value === true) return 'Yes'
      if (value === false) return 'No'
      const text = String(value ?? '').trim().toLowerCase()
      if (!text) return 'Unspecified'
      if (['true', 'yes', '1', 'agree', 'agreed'].includes(text)) return 'Yes'
      if (['false', 'no', '0', 'disagree'].includes(text)) return 'No'
      return 'Unspecified'
    }
    const byManifesto = countValues(rows.map((person) => normalizeManifesto(person.agreesWithManifesto)), 'agrees')
    const skillValues = rows.flatMap((person) => {
      if (Array.isArray(person.skills)) return person.skills
      return String(person.skills || '')
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean)
    })
    const bySkill = countValues(skillValues, 'expertise').slice(0, 15)
    const regionalSkillCounts = new Map()
    rows.forEach((person) => {
      const region = String(person.city || person.neighborhood || 'Unknown').trim() || 'Unknown'
      const skills = Array.isArray(person.skills)
        ? person.skills
        : String(person.skills || '')
            .split(',')
            .map((skill) => skill.trim())
            .filter(Boolean)
      skills.forEach((skill) => {
        const label = String(skill || '').trim()
        if (!label) return
        const key = `${region}|||${label}`
        regionalSkillCounts.set(key, (regionalSkillCounts.get(key) || 0) + 1)
      })
    })
    const regionalSkillsRows = Array.from(regionalSkillCounts.entries())
      .map(([key, count]) => {
        const [region, skill] = key.split('|||')
        return { region, skill, count }
      })
      .sort((a, b) => b.count - a.count)

    return {
      groupCounts: byGroup,
      genderCounts: byGender,
      ageGroups: byAge,
      timeAvailabilityGrouped: byTime,
      regionGrouped: byRegion,
      combinedExpertise: bySkill,
      regionalSkills: regionalSkillsRows,
      manifesto: byManifesto,
    }
  }, [mapStats])

  const activeCharts = filteredCharts || dashboard?.charts || {}
  const groupCounts = activeCharts.groupCounts || []
  const genderCounts = activeCharts.genderCounts || []
  const ageGroups = activeCharts.ageGroups || []
  const professionCounts = activeCharts.professionCounts || []
  const regionCounts = activeCharts.regionCounts || []
  const regionDetail = activeCharts.regionDetail || []
  const partyMembership = activeCharts.partyMembership || []
  const involvementAreas = activeCharts.involvementAreas || []
  const membershipGrowth = activeCharts.membershipGrowth || []
  const engagementReady = activeCharts.engagementReady || []
  const manifesto = activeCharts.manifesto || []
  const membershipInterest = activeCharts.membership || []
  const timeAvailability = activeCharts.timeAvailability || []
  const timeAvailabilityGrouped = activeCharts.timeAvailabilityGrouped || []
  const regionGrouped = activeCharts.regionGrouped || []
  const combinedExpertise = activeCharts.combinedExpertise || []
  const regionalSkills = activeCharts.regionalSkills || []

  const chartPalette = [
    '#2563eb',
    '#0ea5e9',
    '#14b8a6',
    '#22c55e',
    '#f59e0b',
    '#f97316',
    '#ef4444',
    '#8b5cf6',
    '#64748b',
    '#ec4899',
  ]

  // Georgian to English translations for Involvement Areas
  const involvementAreaTranslations = {
    'ექსპერტული მხარდაჭერა თქვენს სფეროში': 'Expert Support',
    'საინფორმაციო და საგანმანათლებლო შეხვედრებში მონაწილეობა': 'Educational Events',
    'ონლაინ კამპანიაში მონაწილეობა/ ინფორმაციის გავრცელებაში დახმარება': 'Online Campaign',
    'ევენტების ორგანიზება': 'Event Organization',
    'ადგილზე მხარდაჭერა მიტინგებსა და სხვა ღონისძიებებზე': 'On-site Support',
    'სხვა': 'Other',
  }

  // Translate involvement areas for display
  const translateInvolvementAreas = (areas) => {
    return areas.map(area => ({
      ...area,
      area: involvementAreaTranslations[area.area] || area.area
    }))
  }

  const pickColors = (count) =>
    Array.from({ length: count }, (_, idx) => chartPalette[idx % chartPalette.length])

  const barData = (rows, labelKey, valueKey, label) => ({
    labels: rows.map((row) => row[labelKey]),
    datasets: [
      {
        label,
        data: rows.map((row) => row[valueKey]),
        backgroundColor: pickColors(rows.length),
        borderRadius: 8,
      },
    ],
  })

  const radialData = (rows, labelKey, valueKey) => ({
    labels: rows.map((row) => row[labelKey]),
    datasets: [
      {
        data: rows.map((row) => row[valueKey]),
        backgroundColor: pickColors(rows.length),
        borderWidth: 1,
      },
    ],
  })

  const dashboardBarOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { stepSize: 1 },
      },
    },
  }

  const dashboardPieOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 10 } },
    },
  }

  const dashboardPolarOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 10 } },
    },
    scales: {
      r: {
        ticks: { display: false },
        grid: { color: 'rgba(148, 163, 184, 0.3)' },
      },
    },
  }

  const dashboardHorizontalBarOptions = {
    ...dashboardBarOptions,
    indexAxis: 'y',
  }

  return (
    <div className="stack">
      <div className="module-card module-card__wide section-intro" data-tour="network-statistics">
        <div className="card-header">
          <div>
            <h3>Stats</h3>
            <p className="muted">
              {filteredCharts
                ? 'Filtered by the current Map & Coverage filters.'
                : 'Engagement, skills, and activity at a glance.'}
            </p>
          </div>
        </div>
      </div>
      {error ? <div className="module-alert">{error}</div> : null}
      <div className="module-grid dashboard-grid">
          <div className="module-card dashboard-chart">
            <h3>People distribution</h3>
            {groupCounts.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <Doughnut
                  data={radialData(groupCounts, 'group', 'count')}
                  options={dashboardPieOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Gender distribution</h3>
            {genderCounts.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                {/* DEBUG: {JSON.stringify(genderCounts)} */}
                <Bar
                  data={{
                    labels: genderCounts.map(d =>
                      d.gender === 'F' ? 'Female' :
                      d.gender === 'M' ? 'Male' :
                      d.gender === 'O' ? 'Other' :
                      d.gender === 'U' ? 'Unspecified' : d.gender
                    ),
                    datasets: [{
                      label: 'People',
                      data: genderCounts.map(d => d.count),
                      backgroundColor: pickColors(genderCounts.length),
                      borderRadius: 8,
                    }]
                  }}
                  options={dashboardBarOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Age groups</h3>
            {ageGroups.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <Bar
                  data={{
                    labels: ageGroups.map(d => d.group),
                    datasets: [{
                      data: ageGroups.map(d => d.count),
                      backgroundColor: ['#3182ce', '#38a169', '#d69e2e', '#e53e3e']
                    }]
                  }}
                  options={dashboardBarOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Time availability (Grouped)</h3>
            {timeAvailabilityGrouped.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <Pie
                  data={radialData(timeAvailabilityGrouped, 'group', 'count')}
                  options={dashboardPieOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Region distribution</h3>
            {regionGrouped.length > 0 ? (
              <div className="chart-frame">
                <Pie
                  data={radialData(regionGrouped, 'group', 'count')}
                  options={dashboardPieOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Combined Expertise</h3>
            {combinedExpertise.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <Bar
                  data={{
                    labels: combinedExpertise.map(d => d.expertise.length > 30 ? d.expertise.substring(0, 30) + '...' : d.expertise),
                    datasets: [{
                      label: 'People',
                      data: combinedExpertise.map(d => d.count),
                      backgroundColor: pickColors(combinedExpertise.length),
                    }]
                  }}
                  options={{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                      x: { beginAtZero: true, ticks: { stepSize: 1 } },
                      y: { ticks: { font: { size: 10 } } }
                    }
                  }}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Manifesto</h3>
            {manifesto.length ? (
              <div className="chart-frame">
                <Pie
                  data={radialData(manifesto, 'agrees', 'count')}
                  options={dashboardPieOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Regional Skills Distribution</h3>
            {regionalSkills.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <Bar
                  data={{
                    labels: [...new Set(regionalSkills.map(d => d.region))],
                    datasets: [
                      {
                        label: 'Top Skills by Region',
                        data: Object.entries(
                          regionalSkills.reduce((acc, item) => {
                            acc[item.region] = (acc[item.region] || 0) + item.count;
                            return acc;
                          }, {})
                        ).map(([_, count]) => count),
                        backgroundColor: '#3182ce',
                      }
                    ]
                  }}
                  options={{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: { display: false },
                      tooltip: {
                        callbacks: {
                          afterLabel: (context) => {
                            const region = context.label;
                            const skills = regionalSkills
                              .filter(d => d.region === region)
                              .sort((a, b) => b.count - a.count)
                              .slice(0, 3)
                              .map(d => `${d.skill}: ${d.count}`)
                              .join(', ');
                            return `Top skills: ${skills}`;
                          }
                        }
                      }
                    },
                    scales: {
                      x: { beginAtZero: true, ticks: { stepSize: 1 } },
                      y: { ticks: { font: { size: 11 } } }
                    }
                  }}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
      </div>
    </div>
  )
}

function CRMOverviewTab({ mapStats, onMapStatsChange } = {}) {
  const reportRef = useRef(null)
  const [cacheStatus, setCacheStatus] = useState(null)
  const [cacheError, setCacheError] = useState('')
  const [cacheRefreshing, setCacheRefreshing] = useState(false)
  const [cacheProgress, setCacheProgress] = useState(0)
  const [mapRefreshToken, setMapRefreshToken] = useState(0)
  const reportTimestamp = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        dateStyle: 'full',
        timeStyle: 'short',
      }).format(new Date()),
    [],
  )

  const formatCacheDate = (value) => {
    if (!value) return 'Not fetched yet'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return 'Not available'
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date)
  }

  const loadCacheStatus = (forceRefresh = false) => {
    setCacheError('')
    return getJson('/crm/cache/crm/status', { cacheMs: 0, forceRefresh })
      .then((payload) => {
        setCacheStatus(payload || null)
        return payload
      })
      .catch((err) => {
        setCacheError(err.message || 'Unable to load cache status.')
        return null
      })
  }

  useEffect(() => {
    loadCacheStatus(true)
  }, [])

  const handleRefreshCache = async () => {
    setCacheRefreshing(true)
    setCacheError('')
    setCacheProgress(12)
    const timers = [
      window.setTimeout(() => setCacheProgress(35), 500),
      window.setTimeout(() => setCacheProgress(62), 1500),
      window.setTimeout(() => setCacheProgress(84), 3000),
    ]
    try {
      const payload = await requestJson('/crm/cache/crm/refresh', { method: 'POST' })
      setCacheStatus(payload || null)
      setCacheProgress(100)
      setMapRefreshToken(Date.now())
    } catch (err) {
      setCacheError(err.message || 'Unable to fetch latest CRM data.')
    } finally {
      timers.forEach((timer) => window.clearTimeout(timer))
      window.setTimeout(() => {
        setCacheRefreshing(false)
        setCacheProgress(0)
      }, 700)
    }
  }

  const handlePrintReport = () => {
    window.print()
  }

  const handleDownloadReportJpg = async () => {
    const element = reportRef.current
    if (!element) return
    const width = Math.ceil(element.scrollWidth)
    const height = Math.ceil(element.scrollHeight)
    const clone = element.cloneNode(true)
    clone.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml')
    const serialized = new XMLSerializer().serializeToString(clone)
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
        <foreignObject width="100%" height="100%">${serialized}</foreignObject>
      </svg>
    `
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' })
    const imageUrl = URL.createObjectURL(blob)
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d')
      context.fillStyle = '#f8fafc'
      context.fillRect(0, 0, width, height)
      context.drawImage(image, 0, 0)
      URL.revokeObjectURL(imageUrl)
      try {
        const link = document.createElement('a')
        link.download = `network-report-${new Date().toISOString().slice(0, 10)}.jpg`
        link.href = canvas.toDataURL('image/jpeg', 0.92)
        link.click()
      } catch (error) {
        handlePrintReport()
      }
    }
    image.onerror = () => {
      URL.revokeObjectURL(imageUrl)
      handlePrintReport()
    }
    image.src = imageUrl
  }

  return (
    <div className="stack network-report" ref={reportRef}>
      <div className="module-card module-card__wide network-report__header">
        <div>
          <div className="pill">Today&apos;s Report</div>
          <h3>Network</h3>
        </div>
        <div>
          <div className="network-report__actions">
            <button className="button-secondary button-secondary--small" type="button" onClick={handlePrintReport}>
              Print / save PDF
            </button>
            <button className="button-secondary button-secondary--small" type="button" onClick={handleDownloadReportJpg}>
              Download JPG snapshot
            </button>
          </div>
          <p className="muted network-report__timestamp">Snapshot generated {reportTimestamp}</p>
        </div>
      </div>
      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>CRM data snapshot</h3>
            <p className="muted">
              The map and coverage views use the latest local snapshot when available, which keeps the platform faster and reduces Aura reads.
            </p>
          </div>
          <div className="pill">{cacheStatus?.status || 'missing'}</div>
        </div>
        {cacheError ? <div className="module-alert">{cacheError}</div> : null}
        <div className="module-grid">
          <div className="metric-row">
            <span>Last fetched</span>
            <strong>{formatCacheDate(cacheStatus?.lastFetchedAt)}</strong>
          </div>
          <div className="metric-row">
            <span>People in snapshot</span>
            <strong>{cacheStatus?.peopleCount ?? 0}</strong>
          </div>
          <div className="metric-row">
            <span>Changes since fetch</span>
            <strong>{cacheStatus?.changesSinceFetch ?? '?'}</strong>
          </div>
          <div className="metric-row">
            <span>Expires</span>
            <strong>{formatCacheDate(cacheStatus?.expiresAt)}</strong>
          </div>
        </div>
        <p className="muted">
          {cacheStatus?.exists
            ? `Snapshot is deleted after ${cacheStatus.deleteHours || 72} hours. Refresh is recommended when the change count is high.`
            : 'No snapshot yet. Until the first fetch, the app can still query Aura directly.'}
        </p>
        {cacheRefreshing ? (
          <div className="stack">
            <p className="muted">Fetching latest data from Aura. This might take some time.</p>
            <div className="progress-bar" aria-label="CRM snapshot refresh progress">
              <span style={{ width: `${cacheProgress}%` }} />
            </div>
          </div>
        ) : null}
        <div className="button-row">
          <button className="button" type="button" onClick={handleRefreshCache} disabled={cacheRefreshing}>
            <IconRefresh size={16} /> {cacheRefreshing ? 'Fetching...' : 'Fetch latest data'}
          </button>
          <button className="button-secondary" type="button" onClick={() => loadCacheStatus(true)} disabled={cacheRefreshing}>
            Check status
          </button>
        </div>
      </div>
      <CRMMapTab onStatsChange={onMapStatsChange} refreshToken={mapRefreshToken} />
      <CRMDashboardTab mapStats={mapStats} />
    </div>
  )
}

function CRMVolunteersTab() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    setLoading(true)
    getJson('/crm/people/summary?limit=2000&sort=effortScore')
      .then((payload) => {
        if (!mounted) return
        setRows(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        if (!mounted) return
        setError(err.message || 'Unable to load volunteer data.')
      })
      .finally(() => {
        if (!mounted) return
        setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const volunteers = useMemo(() => {
    return rows.filter((row) => {
      const ratingValue = Number(row.rating ?? 0)
      return row.group === 'Supporter' && ratingValue >= 4
    })
  }, [rows])
  const avgEffort =
    volunteers.length > 0
      ? volunteers.reduce((sum, row) => sum + Number(row.effortScore || 0), 0) /
        volunteers.length
      : 0

  const topVolunteers = useMemo(() => {
    const copy = [...volunteers]
    copy.sort((a, b) => {
      const ratingDiff = Number(b.rating ?? 0) - Number(a.rating ?? 0)
      if (ratingDiff !== 0) return ratingDiff
      return (
        Number(b.effortScore || b.effortHours || 0) -
        Number(a.effortScore || a.effortHours || 0)
      )
    })
    return copy.slice(0, 20)
  }, [volunteers])

  const skillCounts = useMemo(() => {
    const counts = {}
    volunteers.forEach((row) => {
      const skills = Array.isArray(row.skills)
        ? row.skills
        : String(row.skills || '')
            .split(',')
            .map((skill) => skill.trim())
            .filter(Boolean)
      skills.forEach((skill) => {
        counts[skill] = (counts[skill] || 0) + 1
      })
    })
    return counts
  }, [volunteers])

  const topSkills = useMemo(() => {
    return Object.entries(skillCounts)
      .map(([skill, count]) => ({ skill, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12)
  }, [skillCounts])

  const skillData = {
    labels: topSkills.map((row) => row.skill),
    datasets: [
      {
        label: 'Volunteers',
        data: topSkills.map((row) => row.count),
        backgroundColor: '#2563eb',
      },
    ],
  }

  return (
    <div className="stack">
      <div className="module-card module-card__wide section-intro">
        <div className="card-header">
          <div>
            <h3>Volunteer engagement</h3>
            <p className="muted">Volunteer metrics, top supporters, and skills.</p>
          </div>
          <div className="pill">Network</div>
        </div>
      </div>
      <div className="module-grid">
        {error ? <div className="module-alert">{error}</div> : null}
        <div className="module-card">
        <h3>Volunteer metrics</h3>
        {loading ? (
          <p className="muted">Loading volunteers...</p>
        ) : (
          <>
            <div className="metric-row">
              <span>4-5 star supporters</span>
              <strong>{volunteers.length}</strong>
      </div>
            <div className="metric-row">
              <span>Avg effort score</span>
              <strong>{avgEffort.toFixed(1)}</strong>
            </div>
            <div className="metric-row">
              <span>Total people</span>
              <strong>{rows.length}</strong>
            </div>
          </>
        )}
      </div>
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Top supporters</h3>
              <p className="muted">Highest-rated supporters based on activity.</p>
            </div>
          </div>
          <div className="table">
            <div className="table-row table-head">
              <span>Name</span>
              <span>Email</span>
              <span>Rating</span>
              <span>Effort</span>
            </div>
            {topVolunteers.length === 0 && !loading && (
              <div className="table-row empty">No volunteer activity yet.</div>
            )}
            {topVolunteers.map((row) => (
              <div className="table-row" key={row.email}>
                <span>{row.fullName || row.email}</span>
                <span>{row.email}</span>
                <span>{row.ratingStars || row.rating || '-'}</span>
                <span>{row.effortScore ?? row.effortHours ?? 0}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Skill distribution</h3>
              <p className="muted">Top skills among active volunteers.</p>
            </div>
          </div>
          {topSkills.length ? (
            <Bar data={skillData} />
          ) : (
            <p className="muted">No skills recorded yet.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function CRMCampaignsTab() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [selectedCampaignId, setSelectedCampaignId] = useState('')
  const [campaignDetail, setCampaignDetail] = useState(null)
  const [campaignDraft, setCampaignDraft] = useState(null)
  const [detailError, setDetailError] = useState('')
  const [analysisStatus, setAnalysisStatus] = useState('')
  const [report, setReport] = useState(null)
  const [reportError, setReportError] = useState('')
  const [assigneeEmail, setAssigneeEmail] = useState('')
  const [taskStatus, setTaskStatus] = useState('')
  const [campaignSaveStatus, setCampaignSaveStatus] = useState('')
  const [campaignSaveError, setCampaignSaveError] = useState('')
  const [fundingSummary, setFundingSummary] = useState(null)
  const [contributions, setContributions] = useState([])
  const [contributionStatus, setContributionStatus] = useState('')
  const [contributionError, setContributionError] = useState('')
  const [contributionForm, setContributionForm] = useState({
    amount: '',
    currency: 'GEL',
    contributorName: '',
    contributorEmail: '',
    isAnonymous: false,
    note: '',
  })
  const [milestones, setMilestones] = useState([])
  const [milestoneStatus, setMilestoneStatus] = useState('')
  const [milestoneError, setMilestoneError] = useState('')
  const [milestoneForm, setMilestoneForm] = useState({
    title: '',
    amountTarget: '',
    dueDate: '',
    status: 'Planned',
    completionPercent: '',
  })
  const [expenses, setExpenses] = useState([])
  const [expenseStatus, setExpenseStatus] = useState('')
  const [expenseError, setExpenseError] = useState('')
  const [expenseForm, setExpenseForm] = useState({
    category: '',
    vendor: '',
    amount: '',
    currency: 'GEL',
    receiptLink: '',
    approvedBy: '',
    milestoneId: '',
  })
  const [proofArtifacts, setProofArtifacts] = useState([])
  const [proofStatus, setProofStatus] = useState('')
  const [proofError, setProofError] = useState('')
  const [proofForm, setProofForm] = useState({
    artifactType: 'image',
    caption: '',
    url: '',
    uploadedBy: '',
    verificationStatus: 'Pending',
    milestoneId: '',
  })
  const [partners, setPartners] = useState([])
  const [partnerStatus, setPartnerStatus] = useState('')
  const [partnerError, setPartnerError] = useState('')
  const [partnerForm, setPartnerForm] = useState({
    name: '',
    role: '',
    contact: '',
    verificationNotes: '',
  })
  const [campaignUpdates, setCampaignUpdates] = useState([])
  const [campaignUpdateStatus, setCampaignUpdateStatus] = useState('')
  const [campaignUpdateError, setCampaignUpdateError] = useState('')
  const [campaignUpdateForm, setCampaignUpdateForm] = useState({
    message: '',
    createdBy: '',
    status: '',
  })
  const [campaignMessages, setCampaignMessages] = useState([])
  const [campaignMessageStatus, setCampaignMessageStatus] = useState('')
  const [campaignMessageError, setCampaignMessageError] = useState('')
  const [generatedCampaignMessages, setGeneratedCampaignMessages] = useState([])
  const [campaignMessageForm, setCampaignMessageForm] = useState({
    channel: 'whatsapp',
    language: 'ka',
    tone: 'clear',
    title: '',
    body: '',
    callToAction: '',
    status: 'Draft',
  })
  const [campaignMessageGenerateForm, setCampaignMessageGenerateForm] = useState({
    channel: 'whatsapp',
    language: 'ka',
    tone: 'clear',
    instructions: '',
  })
  const [campaignTasks, setCampaignTasks] = useState([])
  const [campaignTaskStatus, setCampaignTaskStatus] = useState('')
  const [campaignTaskError, setCampaignTaskError] = useState('')
  const [campaignTaskForm, setCampaignTaskForm] = useState({
    title: '',
    description: '',
    status: 'Open',
    dueDate: '',
    assigneeEmail: '',
    milestoneId: '',
  })
  const [campaignVolunteers, setCampaignVolunteers] = useState([])
  const [campaignVolunteerStatus, setCampaignVolunteerStatus] = useState('')
  const [campaignVolunteerError, setCampaignVolunteerError] = useState('')
  const [campaignVolunteerForm, setCampaignVolunteerForm] = useState({
    name: '',
    email: '',
    phone: '',
    role: '',
    notes: '',
  })
  const [campaignForm, setCampaignForm] = useState({
    name: '',
    topic: '',
    objective: '',
    problemTitle: '',
    problemDescription: '',
    locationCity: '',
    locationDistrict: '',
    beneficiaryType: '',
    fundingTargetAmount: '',
    currency: 'GEL',
    operationalFeePercent: '10',
    legislationText: '',
    manifestoText: '',
    expertPrompt: '',
    status: 'Planned',
    startDate: '',
    endDate: '',
    owner: '',
    targetGroup: '',
    goal: '',
    notes: '',
  })
  const [campaignSearch, setCampaignSearch] = useState('')
  const [campaignStatusFilter, setCampaignStatusFilter] = useState('All')
  const [campaignOwnerFilter, setCampaignOwnerFilter] = useState('All')
  const [campaignSort, setCampaignSort] = useState('recent')
  const [campaignSection, setCampaignSection] = useState('strategy')

  const loadCampaigns = () => {
    setError('')
    setLoading(true)
    getJson('/crm/campaigns')
      .then((payload) => setCampaigns(Array.isArray(payload) ? payload : []))
      .catch((err) => setError(err.message || 'Unable to load campaigns.'))
      .finally(() => setLoading(false))
  }

  const loadCampaignDetail = (campaignId) => {
    if (!campaignId) return
    setDetailError('')
    getJson(`/crm/campaigns/${campaignId}`)
      .then((payload) => {
        setCampaignDetail(payload)
        setCampaignDraft(payload)
      })
      .catch((err) =>
        setDetailError(err.message || 'Unable to load campaign details.'),
      )
  }

  const loadFundingSummary = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/funding-summary`)
      .then((payload) => setFundingSummary(payload))
      .catch(() => setFundingSummary(null))
  }

  const loadContributions = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/contributions`)
      .then((payload) => setContributions(Array.isArray(payload) ? payload : []))
      .catch(() => setContributions([]))
  }

  const loadMilestones = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/milestones`)
      .then((payload) => setMilestones(Array.isArray(payload) ? payload : []))
      .catch(() => setMilestones([]))
  }

  const loadExpenses = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/expenses`)
      .then((payload) => setExpenses(Array.isArray(payload) ? payload : []))
      .catch(() => setExpenses([]))
  }

  const loadProof = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/proof`)
      .then((payload) =>
        setProofArtifacts(Array.isArray(payload) ? payload : []),
      )
      .catch(() => setProofArtifacts([]))
  }

  const loadPartners = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/partners`)
      .then((payload) => setPartners(Array.isArray(payload) ? payload : []))
      .catch(() => setPartners([]))
  }

  const loadCampaignUpdates = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/updates`)
      .then((payload) =>
        setCampaignUpdates(Array.isArray(payload) ? payload : []),
      )
      .catch(() => setCampaignUpdates([]))
  }

  const loadCampaignMessages = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/messages`)
      .then((payload) =>
        setCampaignMessages(Array.isArray(payload) ? payload : []),
      )
      .catch(() => setCampaignMessages([]))
  }

  const loadCampaignTasks = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/tasks`)
      .then((payload) =>
        setCampaignTasks(Array.isArray(payload) ? payload : []),
      )
      .catch(() => setCampaignTasks([]))
  }

  const loadCampaignVolunteers = (campaignId) => {
    if (!campaignId) return
    getJson(`/crm/campaigns/${campaignId}/volunteers`)
      .then((payload) =>
        setCampaignVolunteers(Array.isArray(payload) ? payload : []),
      )
      .catch(() => setCampaignVolunteers([]))
  }

  useEffect(() => {
    loadCampaigns()
  }, [])

  useEffect(() => {
    if (!selectedCampaignId) {
      setCampaignDetail(null)
      setCampaignDraft(null)
      setFundingSummary(null)
      setContributions([])
      setMilestones([])
      setExpenses([])
      setProofArtifacts([])
      setPartners([])
      setCampaignUpdates([])
      setCampaignMessages([])
      setGeneratedCampaignMessages([])
      setCampaignTasks([])
      setCampaignVolunteers([])
      return
    }
    loadCampaignDetail(selectedCampaignId)
    loadFundingSummary(selectedCampaignId)
    loadContributions(selectedCampaignId)
    loadMilestones(selectedCampaignId)
    loadExpenses(selectedCampaignId)
    loadProof(selectedCampaignId)
    loadPartners(selectedCampaignId)
    loadCampaignUpdates(selectedCampaignId)
    loadCampaignMessages(selectedCampaignId)
    loadCampaignVolunteers(selectedCampaignId)
  }, [selectedCampaignId])

  const handleCreateCampaign = async (event) => {
    event.preventDefault()
    if (!campaignForm.name.trim()) {
      setError('Campaign name is required.')
      return
    }
    setError('')
    setStatusMessage('')
    try {
      const created = await requestJson('/crm/campaigns', {
        method: 'POST',
        payload: {
          name: campaignForm.name.trim(),
          topic: campaignForm.topic.trim(),
          objective: campaignForm.objective.trim(),
          problemTitle: campaignForm.problemTitle.trim(),
          problemDescription: campaignForm.problemDescription.trim(),
          locationCity: campaignForm.locationCity.trim(),
          locationDistrict: campaignForm.locationDistrict.trim(),
          beneficiaryType: campaignForm.beneficiaryType.trim(),
          fundingTargetAmount: campaignForm.fundingTargetAmount
            ? Number(campaignForm.fundingTargetAmount)
            : 0,
          currency: campaignForm.currency || 'GEL',
          operationalFeePercent: campaignForm.operationalFeePercent
            ? Number(campaignForm.operationalFeePercent)
            : 0,
          operationalFeeAmount:
            campaignForm.fundingTargetAmount && campaignForm.operationalFeePercent
              ? (Number(campaignForm.fundingTargetAmount) *
                  Number(campaignForm.operationalFeePercent)) /
                100
              : 0,
          executionBudgetAmount: campaignForm.fundingTargetAmount
            ? Number(campaignForm.fundingTargetAmount) -
              (campaignForm.operationalFeePercent
                ? (Number(campaignForm.fundingTargetAmount) *
                    Number(campaignForm.operationalFeePercent)) /
                  100
                : 0)
            : 0,
          legislationText: campaignForm.legislationText.trim(),
          manifestoText: campaignForm.manifestoText.trim(),
          expertPrompt: campaignForm.expertPrompt.trim(),
          status: campaignForm.status,
          startDate: campaignForm.startDate,
          endDate: campaignForm.endDate,
          owner: campaignForm.owner.trim(),
          targetGroup: campaignForm.targetGroup.trim(),
          goal: campaignForm.goal ? Number(campaignForm.goal) : 0,
          notes: campaignForm.notes.trim(),
        },
      })
      setCampaignForm({
        name: '',
        topic: '',
        objective: '',
        problemTitle: '',
        problemDescription: '',
        locationCity: '',
        locationDistrict: '',
        beneficiaryType: '',
        fundingTargetAmount: '',
        currency: 'GEL',
        operationalFeePercent: '10',
        legislationText: '',
        manifestoText: '',
        expertPrompt: '',
        status: 'Planned',
        startDate: '',
        endDate: '',
        owner: '',
        targetGroup: '',
        goal: '',
        notes: '',
      })
      setStatusMessage('Campaign created.')
      loadCampaigns()
      if (created?.campaignId) {
        setSelectedCampaignId(created.campaignId)
        setCampaignSection('strategy')
      }
    } catch (err) {
      setError(err.message || 'Unable to create campaign.')
    }
  }

  const handleContributionSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    const amountValue = Number(contributionForm.amount)
    if (!amountValue || amountValue <= 0) {
      setContributionError('Enter a positive contribution amount.')
      return
    }
    setContributionError('')
    setContributionStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/contributions`, {
        method: 'POST',
        payload: {
          amount: amountValue,
          currency: contributionForm.currency,
          contributorName: contributionForm.contributorName.trim(),
          contributorEmail: contributionForm.contributorEmail.trim(),
          isAnonymous: contributionForm.isAnonymous,
          note: contributionForm.note.trim(),
        },
      })
      setContributionForm({
        amount: '',
        currency: contributionForm.currency,
        contributorName: '',
        contributorEmail: '',
        isAnonymous: false,
        note: '',
      })
      setContributionStatus('Contribution recorded.')
      loadFundingSummary(selectedCampaignId)
      loadContributions(selectedCampaignId)
    } catch (err) {
      setContributionError(err.message || 'Unable to record contribution.')
    }
  }

  const handleSaveExecutionPlan = async () => {
    if (!selectedCampaignId || !campaignDraft) return
    setCampaignSaveError('')
    setCampaignSaveStatus('')
    try {
      const updated = await requestJson(`/crm/campaigns/${selectedCampaignId}`, {
        method: 'PATCH',
        payload: {
          status: campaignDraft.status,
          implementationSteps: campaignDraft.implementationSteps || '',
          responsibleOwner: campaignDraft.responsibleOwner || '',
          communityPartner: campaignDraft.communityPartner || '',
          executionStartDate: campaignDraft.executionStartDate || '',
          expectedCompletionDate: campaignDraft.expectedCompletionDate || '',
        },
      })
      setCampaignDetail(updated)
      setCampaignDraft(updated)
      setCampaignSaveStatus('Execution plan saved.')
    } catch (err) {
      setCampaignSaveError(err.message || 'Unable to update campaign.')
    }
  }

  const handleMilestoneSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!milestoneForm.title.trim()) {
      setMilestoneError('Milestone title is required.')
      return
    }
    setMilestoneError('')
    setMilestoneStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/milestones`, {
        method: 'POST',
        payload: {
          title: milestoneForm.title.trim(),
          amountTarget: milestoneForm.amountTarget
            ? Number(milestoneForm.amountTarget)
            : 0,
          dueDate: milestoneForm.dueDate,
          status: milestoneForm.status,
          completionPercent: milestoneForm.completionPercent
            ? Number(milestoneForm.completionPercent)
            : 0,
        },
      })
      setMilestoneForm({
        title: '',
        amountTarget: '',
        dueDate: '',
        status: 'Planned',
        completionPercent: '',
      })
      setMilestoneStatus('Milestone added.')
      loadMilestones(selectedCampaignId)
    } catch (err) {
      setMilestoneError(err.message || 'Unable to add milestone.')
    }
  }

  const handleExpenseSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!expenseForm.category.trim()) {
      setExpenseError('Expense category is required.')
      return
    }
    const amountValue = Number(expenseForm.amount)
    if (!amountValue || amountValue <= 0) {
      setExpenseError('Enter a positive expense amount.')
      return
    }
    setExpenseError('')
    setExpenseStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/expenses`, {
        method: 'POST',
        payload: {
          category: expenseForm.category.trim(),
          vendor: expenseForm.vendor.trim(),
          amount: amountValue,
          currency: expenseForm.currency,
          receiptLink: expenseForm.receiptLink.trim(),
          approvedBy: expenseForm.approvedBy.trim(),
          milestoneId: expenseForm.milestoneId,
        },
      })
      setExpenseForm({
        category: '',
        vendor: '',
        amount: '',
        currency: expenseForm.currency,
        receiptLink: '',
        approvedBy: '',
        milestoneId: '',
      })
      setExpenseStatus('Expense recorded.')
      loadExpenses(selectedCampaignId)
    } catch (err) {
      setExpenseError(err.message || 'Unable to record expense.')
    }
  }

  const handleProofSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!proofForm.url.trim()) {
      setProofError('Proof URL is required.')
      return
    }
    setProofError('')
    setProofStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/proof`, {
        method: 'POST',
        payload: {
          artifactType: proofForm.artifactType,
          caption: proofForm.caption.trim(),
          url: proofForm.url.trim(),
          uploadedBy: proofForm.uploadedBy.trim(),
          verificationStatus: proofForm.verificationStatus,
          milestoneId: proofForm.milestoneId,
        },
      })
      setProofForm({
        artifactType: proofForm.artifactType,
        caption: '',
        url: '',
        uploadedBy: '',
        verificationStatus: proofForm.verificationStatus,
        milestoneId: '',
      })
      setProofStatus('Proof artifact added.')
      loadProof(selectedCampaignId)
    } catch (err) {
      setProofError(err.message || 'Unable to add proof.')
    }
  }

  const handlePartnerSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!partnerForm.name.trim()) {
      setPartnerError('Partner name is required.')
      return
    }
    setPartnerError('')
    setPartnerStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/partners`, {
        method: 'POST',
        payload: {
          name: partnerForm.name.trim(),
          role: partnerForm.role.trim(),
          contact: partnerForm.contact.trim(),
          verificationNotes: partnerForm.verificationNotes.trim(),
        },
      })
      setPartnerForm({
        name: '',
        role: '',
        contact: '',
        verificationNotes: '',
      })
      setPartnerStatus('Partner added.')
      loadPartners(selectedCampaignId)
    } catch (err) {
      setPartnerError(err.message || 'Unable to add partner.')
    }
  }

  const handleCampaignUpdateSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!campaignUpdateForm.message.trim()) {
      setCampaignUpdateError('Update message is required.')
      return
    }
    setCampaignUpdateError('')
    setCampaignUpdateStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/updates`, {
        method: 'POST',
        payload: {
          message: campaignUpdateForm.message.trim(),
          createdBy: campaignUpdateForm.createdBy.trim(),
          status: campaignUpdateForm.status,
        },
      })
      setCampaignUpdateForm({ message: '', createdBy: '', status: '' })
      setCampaignUpdateStatus('Update posted.')
      loadCampaignUpdates(selectedCampaignId)
    } catch (err) {
      setCampaignUpdateError(err.message || 'Unable to post update.')
    }
  }

  const campaignMessagePayload = () => ({
    channel: campaignMessageForm.channel,
    language: campaignMessageForm.language,
    tone: campaignMessageForm.tone.trim(),
    title: campaignMessageForm.title.trim(),
    body: campaignMessageForm.body.trim(),
    callToAction: campaignMessageForm.callToAction.trim(),
    status: campaignMessageForm.status,
  })

  const handleGenerateCampaignMessage = async () => {
    if (!selectedCampaignId) return
    setCampaignMessageError('')
    setCampaignMessageStatus('Generating message...')
    try {
      const payload = await requestJson(
        `/crm/campaigns/${selectedCampaignId}/messages/generate`,
        {
          method: 'POST',
          payload: {
            channel: campaignMessageGenerateForm.channel,
            language: campaignMessageGenerateForm.language,
            tone: campaignMessageGenerateForm.tone.trim(),
            instructions: campaignMessageGenerateForm.instructions.trim(),
          },
        },
      )
      const messages = Array.isArray(payload?.messages) ? payload.messages : []
      setGeneratedCampaignMessages(messages)
      if (messages[0]) {
        setCampaignMessageForm((prev) => ({
          ...prev,
          channel: messages[0].channel || prev.channel,
          language: messages[0].language || prev.language,
          tone: messages[0].tone || prev.tone,
          title: messages[0].title || '',
          body: messages[0].body || '',
          callToAction: messages[0].callToAction || '',
          status: messages[0].status || 'Draft',
        }))
      }
      setCampaignMessageStatus('Message drafted.')
    } catch (err) {
      setCampaignMessageStatus('')
      setCampaignMessageError(err.message || 'Unable to generate message.')
    }
  }

  const handleCampaignMessageSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!campaignMessageForm.body.trim()) {
      setCampaignMessageError('Message body is required.')
      return
    }
    setCampaignMessageError('')
    setCampaignMessageStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/messages`, {
        method: 'POST',
        payload: campaignMessagePayload(),
      })
      setCampaignMessageForm((prev) => ({
        ...prev,
        title: '',
        body: '',
        callToAction: '',
        status: 'Draft',
      }))
      setGeneratedCampaignMessages([])
      setCampaignMessageStatus('Message saved.')
      loadCampaignMessages(selectedCampaignId)
    } catch (err) {
      setCampaignMessageError(err.message || 'Unable to save message.')
    }
  }

  const handleCopyCampaignMessage = async (message) => {
    const text = [message?.title, message?.body, message?.callToAction]
      .filter(Boolean)
      .join('\n\n')
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCampaignMessageStatus('Message copied.')
    } catch (err) {
      setCampaignMessageError('Unable to copy message.')
    }
  }

  const handleCampaignTaskSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!campaignTaskForm.title.trim()) {
      setCampaignTaskError('Task title is required.')
      return
    }
    setCampaignTaskError('')
    setCampaignTaskStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/tasks`, {
        method: 'POST',
        payload: {
          title: campaignTaskForm.title.trim(),
          description: campaignTaskForm.description.trim(),
          status: campaignTaskForm.status,
          dueDate: campaignTaskForm.dueDate,
          assigneeEmail: campaignTaskForm.assigneeEmail.trim(),
          milestoneId: campaignTaskForm.milestoneId,
        },
      })
      setCampaignTaskForm({
        title: '',
        description: '',
        status: 'Open',
        dueDate: '',
        assigneeEmail: '',
        milestoneId: '',
      })
      setCampaignTaskStatus('Task created.')
      loadCampaignTasks(selectedCampaignId)
    } catch (err) {
      setCampaignTaskError(err.message || 'Unable to create task.')
    }
  }

  const handleCampaignVolunteerSubmit = async (event) => {
    event.preventDefault()
    if (!selectedCampaignId) return
    if (!campaignVolunteerForm.name.trim()) {
      setCampaignVolunteerError('Name is required.')
      return
    }
    setCampaignVolunteerError('')
    setCampaignVolunteerStatus('')
    try {
      await requestJson(`/crm/campaigns/${selectedCampaignId}/volunteers`, {
        method: 'POST',
        payload: {
          name: campaignVolunteerForm.name.trim(),
          email: campaignVolunteerForm.email.trim(),
          phone: campaignVolunteerForm.phone.trim(),
          role: campaignVolunteerForm.role.trim(),
          notes: campaignVolunteerForm.notes.trim(),
        },
      })
      setCampaignVolunteerForm({
        name: '',
        email: '',
        phone: '',
        role: '',
        notes: '',
      })
      setCampaignVolunteerStatus('Person added.')
      loadCampaignVolunteers(selectedCampaignId)
    } catch (err) {
      setCampaignVolunteerError(err.message || 'Unable to add volunteer.')
    }
  }

  const handleDraftChange = (field, value) => {
    setCampaignDraft((prev) => ({ ...(prev || {}), [field]: value }))
  }

  const handleRunAnalysis = async () => {
    if (!selectedCampaignId || !campaignDraft) return
    setAnalysisStatus('Running analysis...')
    setDetailError('')
    try {
      const updated = await requestJson(
        `/crm/campaigns/${selectedCampaignId}/analysis`,
        {
          method: 'POST',
          payload: {
            topic: campaignDraft.topic || campaignDraft.name,
            legislationText: campaignDraft.legislationText || '',
            manifestoText: campaignDraft.manifestoText || '',
            expertPrompt: campaignDraft.expertPrompt || '',
          },
        },
      )
      setCampaignDetail(updated)
      setCampaignDraft(updated)
      setAnalysisStatus('Analysis updated.')
    } catch (err) {
      setDetailError(err.message || 'Unable to run analysis.')
      setAnalysisStatus('')
    }
  }

  const handleLaunchDeliberation = async () => {
    if (!selectedCampaignId) return
    setAnalysisStatus('Launching survey...')
    setDetailError('')
    try {
      const updated = await requestJson(
        `/crm/campaigns/${selectedCampaignId}/deliberation`,
        { method: 'POST' },
      )
      setCampaignDetail(updated)
      setCampaignDraft(updated)
      setAnalysisStatus('Survey launched.')
    } catch (err) {
      setDetailError(err.message || 'Unable to launch survey.')
      setAnalysisStatus('')
    }
  }

  const handleRefreshInsights = async () => {
    const conversationId = campaignDetail?.deliberationConversationId
    if (!conversationId) return
    setReportError('')
    setReport(null)
    try {
      const payload = await getJson(`/conversations/${conversationId}/report`)
      setReport(payload)
    } catch (err) {
      setReportError(err.message || 'Unable to load survey report.')
    }
  }

  const finalStatements = useMemo(() => {
    const topic = campaignDraft?.topic || campaignDetail?.topic || 'Campaign'
    const consensus =
      campaignDraft?.consensusStatements || campaignDetail?.consensusStatements || []
    const base = consensus.length
      ? consensus
      : campaignDraft?.polarizationStatements || campaignDetail?.polarizationStatements || []
    const templates = [
      `Advance ${topic} with transparent implementation and accountability.`,
      `${topic} must protect democratic values and national interests.`,
      `${topic} should deliver measurable public benefits.`,
      `${topic} should align with European standards and rule of law.`,
      `${topic} must remain peaceful and constitutional.`,
    ]
    return new Array(5).fill(null).map((_, index) => {
      const statement = base[index] || templates[index]
      return {
        statement,
        subStatements: [
          `Clarify scope and intent for: ${statement}`,
          `Define measurable targets for ${topic}.`,
          `Coordinate partners to deliver this commitment.`,
        ],
        actions: [
          `Draft outreach brief: ${statement}`,
          `Schedule stakeholder session on ${topic}.`,
        ],
      }
    })
  }, [campaignDetail, campaignDraft])

  const handleCreateTasks = async (statement) => {
    if (!assigneeEmail.trim()) {
      setTaskStatus('Add an assignee email to create tasks.')
      return
    }
    setTaskStatus('Creating tasks...')
    try {
      await Promise.all(
        statement.actions.map((action) =>
          requestJson('/crm/tasks', {
            method: 'POST',
            payload: {
              email: assigneeEmail.trim(),
              title: action,
              description: `Campaign: ${campaignDraft?.name || campaignDetail?.name}\nStatement: ${statement.statement}`,
              status: 'Open',
            },
          }),
        ),
      )
      setTaskStatus('Tasks created.')
    } catch (err) {
      setTaskStatus(err.message || 'Unable to create tasks.')
    }
  }

  const scrollToSection = (sectionId) => {
    if (typeof document === 'undefined') return
    const element = document.getElementById(sectionId)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const clearCampaignSelection = () => {
    setSelectedCampaignId('')
    setCampaignSection('strategy')
  }

  const clearCampaignFilters = () => {
    setCampaignSearch('')
    setCampaignStatusFilter('All')
    setCampaignOwnerFilter('All')
    setCampaignSort('recent')
  }

  const totalCampaigns = campaigns.length
  const activeCampaigns = campaigns.filter((row) => row.status === 'Active').length
  const plannedCampaigns = campaigns.filter((row) => row.status === 'Planned').length
  const draftCampaigns = campaigns.filter((row) => row.status === 'Draft').length
  const fundingCampaigns = campaigns.filter((row) => row.status === 'Funding').length
  const inProgressCampaigns = campaigns.filter(
    (row) => row.status === 'In Progress',
  ).length
  const completedCampaigns = campaigns.filter((row) => row.status === 'Completed').length
  const conversationLink = campaignDetail?.deliberationConversationId
    ? `/?conversation_id=${campaignDetail.deliberationConversationId}&view=mobile`
    : ''
  const fundingTargetAmount = Number(campaignForm.fundingTargetAmount) || 0
  const operationalFeePercent = Number(campaignForm.operationalFeePercent) || 0
  const operationalFeeAmount = fundingTargetAmount
    ? (fundingTargetAmount * operationalFeePercent) / 100
    : 0
  const executionBudgetAmount = Math.max(
    fundingTargetAmount - operationalFeeAmount,
    0,
  )
  const displayCurrency = fundingSummary?.currency || campaignDetail?.currency || 'GEL'
  const raisedAmount = Number(
    fundingSummary?.fundsRaisedAmount ?? campaignDetail?.fundsRaisedAmount ?? 0,
  )
  const targetAmount = Number(
    fundingSummary?.fundingTargetAmount ?? campaignDetail?.fundingTargetAmount ?? 0,
  )
  const allocatedOperations = Number(fundingSummary?.allocatedOperations ?? 0)
  const allocatedExecution = Number(fundingSummary?.allocatedExecution ?? 0)
  const fundingProgress = targetAmount
    ? Math.min((raisedAmount / targetAmount) * 100, 100)
    : 0
  const contributorCount =
    fundingSummary?.contributorCount ?? contributions.length ?? 0

  const ownerOptions = useMemo(() => {
    const owners = campaigns.map((row) => row.owner).filter(Boolean)
    return ['All', ...Array.from(new Set(owners)).sort()]
  }, [campaigns])

  const filteredCampaigns = useMemo(() => {
    const searchTerm = campaignSearch.trim().toLowerCase()
    let rows = [...campaigns]
    if (campaignStatusFilter !== 'All') {
      rows = rows.filter(
        (row) => (row.status || 'Planned') === campaignStatusFilter,
      )
    }
    if (campaignOwnerFilter !== 'All') {
      rows = rows.filter((row) => (row.owner || '-') === campaignOwnerFilter)
    }
    if (searchTerm) {
      rows = rows.filter((row) =>
        [row.name, row.topic, row.owner, row.status].some((value) =>
          String(value || '')
            .toLowerCase()
            .includes(searchTerm),
        ),
      )
    }
    const toDateValue = (value) => {
      const time = Date.parse(value || '')
      return Number.isNaN(time) ? 0 : time
    }
    const fundingRatio = (row) => {
      const raised = Number(row.fundsRaisedAmount ?? 0)
      const target = Number(row.fundingTargetAmount ?? 0)
      return target ? raised / target : 0
    }
    const sorters = {
      recent: (a, b) =>
        toDateValue(b.startDate) - toDateValue(a.startDate) ||
        (a.name || '').localeCompare(b.name || ''),
      name: (a, b) => (a.name || '').localeCompare(b.name || ''),
      status: (a, b) => (a.status || '').localeCompare(b.status || ''),
      funding: (a, b) =>
        fundingRatio(b) - fundingRatio(a) ||
        (a.name || '').localeCompare(b.name || ''),
    }
    rows.sort(sorters[campaignSort] || sorters.recent)
    return rows
  }, [
    campaigns,
    campaignOwnerFilter,
    campaignSearch,
    campaignSort,
    campaignStatusFilter,
  ])

  const selectedCampaign = campaignDraft || campaignDetail
  const campaignNextSteps = useMemo(() => {
    if (!selectedCampaignId || !selectedCampaign) return []
    const steps = []
    if (!selectedCampaign.objective) {
      steps.push('Add a clear objective for the campaign.')
    }
    if (!selectedCampaign.owner && !selectedCampaign.responsibleOwner) {
      steps.push('Assign a campaign owner to keep delivery on track.')
    }
    if (!Number(selectedCampaign.fundingTargetAmount)) {
      steps.push('Set a funding target to unlock transparency goals.')
    }
    if (!selectedCampaign.implementationSteps) {
      steps.push('Draft the execution plan so the team knows the next steps.')
    }
    if (!selectedCampaign.deliberationConversationId) {
      steps.push('Launch the survey to capture supporter feedback.')
    }
    const statements =
      selectedCampaign.consensusStatements ||
      selectedCampaign.polarizationStatements ||
      []
    if (!statements.length) {
      steps.push('Run analysis to generate consensus statements.')
    }
    return steps.slice(0, 4)
  }, [selectedCampaign, selectedCampaignId])

  const campaignStatusOptions = [
    'All',
    'Draft',
    'Planned',
    'Active',
    'Funding',
    'Funded',
    'In Progress',
    'Awaiting Verification',
    'Completed',
    'Cancelled',
    'Paused',
  ]
  const campaignDetailTabs = [
    { id: 'strategy', label: 'Brief' },
    { id: 'messages', label: 'Messages' },
    { id: 'people', label: 'Audience' },
    { id: 'execution', label: 'Events & Links' },
    { id: 'updates', label: 'Updates' },
    { id: 'funding', label: 'Funding' },
    { id: 'operations', label: 'Results' },
    { id: 'statements', label: 'Statements' },
    { id: 'insights', label: 'Insights' },
  ]

  return (
    <div className="module-grid">
      <PageHeader
        eyebrow="Campaigns hub"
        title="Campaigns"
        description="Plan, fund, execute, and communicate campaigns with clear next steps."
        className="page-header--hero module-card__wide campaigns-header"
        meta={
          <div className="module-header__meta">
            <div className="module-header__metric">
              <span>Total</span>
              <strong>{totalCampaigns}</strong>
            </div>
            <div className="module-header__metric">
              <span>Active</span>
              <strong>{activeCampaigns}</strong>
            </div>
            <div className="module-header__metric">
              <span>Funding</span>
              <strong>{fundingCampaigns}</strong>
            </div>
            <div className="module-header__metric">
              <span>In progress</span>
              <strong>{inProgressCampaigns}</strong>
            </div>
          </div>
        }
        actions={
          <>
            <button
              className="button"
              type="button"
              onClick={() => scrollToSection('campaigns-create')}
            >
              New campaign
            </button>
            <button className="button-secondary" type="button" onClick={loadCampaigns}>
              Refresh list
            </button>
            <button
              className="button-ghost"
              type="button"
              onClick={clearCampaignSelection}
              disabled={!selectedCampaignId}
            >
              Clear selection
            </button>
          </>
        }
      />

      <div className="campaigns-top-grid">
        <div className="module-card campaigns-overview" id="campaigns-overview">
          <div className="card-header">
            <div>
              <h3>Campaign overview</h3>
              <p className="muted">Status snapshot and quick filters.</p>
            </div>
            <div className="pill">Live</div>
          </div>
          <div className="campaigns-overview__stats">
            <div className="metric-row">
              <span>Total</span>
              <strong>{totalCampaigns}</strong>
            </div>
            <div className="metric-row">
              <span>Active</span>
              <strong>{activeCampaigns}</strong>
            </div>
            <div className="metric-row">
              <span>Draft</span>
              <strong>{draftCampaigns}</strong>
            </div>
            <div className="metric-row">
              <span>Planned</span>
              <strong>{plannedCampaigns}</strong>
            </div>
            <div className="metric-row">
              <span>Funding</span>
              <strong>{fundingCampaigns}</strong>
            </div>
            <div className="metric-row">
              <span>In progress</span>
              <strong>{inProgressCampaigns}</strong>
            </div>
            <div className="metric-row">
              <span>Completed</span>
              <strong>{completedCampaigns}</strong>
            </div>
          </div>
          <div className="campaigns-quick-filters">
            {[
              { label: 'All', value: 'All', count: totalCampaigns },
              { label: 'Active', value: 'Active', count: activeCampaigns },
              { label: 'Draft', value: 'Draft', count: draftCampaigns },
              { label: 'Funding', value: 'Funding', count: fundingCampaigns },
              { label: 'In progress', value: 'In Progress', count: inProgressCampaigns },
              { label: 'Completed', value: 'Completed', count: completedCampaigns },
            ].map((filter) => (
              <button
                key={filter.value}
                className={`button-secondary button-secondary--small ${campaignStatusFilter === filter.value ? 'is-active' : ''}`}
                type="button"
                onClick={() => setCampaignStatusFilter(filter.value)}
                aria-pressed={campaignStatusFilter === filter.value}
              >
                {filter.label} ({filter.count})
              </button>
            ))}
          </div>
          <p className="muted">
            Showing {filteredCampaigns.length} of {totalCampaigns} campaigns.
          </p>
        </div>

        <div className="module-card campaigns-create" id="campaigns-create">
          <div className="card-header">
            <div>
              <h3>New campaign</h3>
              <p className="muted">
                Start with the essentials. Add details as you go.
              </p>
            </div>
          </div>
          {error ? <div className="module-alert">{error}</div> : null}
          {statusMessage ? <div className="module-alert">{statusMessage}</div> : null}
          <form className="stack" onSubmit={handleCreateCampaign}>
            <div className="campaign-create-grid">
              <input
                className="input"
                placeholder="Campaign name"
                value={campaignForm.name}
                onChange={(event) =>
                  setCampaignForm((prev) => ({ ...prev, name: event.target.value }))
                }
              />
              <input
                className="input"
                placeholder="Topic (e.g., Holly's Law)"
                value={campaignForm.topic}
                onChange={(event) =>
                  setCampaignForm((prev) => ({ ...prev, topic: event.target.value }))
                }
              />
              <textarea
                className="textarea"
                placeholder="Objective"
                value={campaignForm.objective}
                onChange={(event) =>
                  setCampaignForm((prev) => ({
                    ...prev,
                    objective: event.target.value,
                  }))
                }
              />
            </div>
            <details className="dashboard-detail">
              <summary>Problem & funding</summary>
              <div className="stack">
                <input
                  className="input"
                  placeholder="Problem title"
                  value={campaignForm.problemTitle}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      problemTitle: event.target.value,
                    }))
                  }
                />
                <textarea
                  className="textarea"
                  placeholder="Problem description"
                  value={campaignForm.problemDescription}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      problemDescription: event.target.value,
                    }))
                  }
                />
                <div className="form-grid">
                  <input
                    className="input"
                    placeholder="City"
                    value={campaignForm.locationCity}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        locationCity: event.target.value,
                      }))
                    }
                  />
                  <input
                    className="input"
                    placeholder="District"
                    value={campaignForm.locationDistrict}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        locationDistrict: event.target.value,
                      }))
                    }
                  />
                </div>
                <input
                  className="input"
                  placeholder="Beneficiary type"
                  value={campaignForm.beneficiaryType}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      beneficiaryType: event.target.value,
                    }))
                  }
                />
                <div className="form-grid">
                  <input
                    className="input"
                    type="number"
                    min="0"
                    placeholder="Funding target"
                    value={campaignForm.fundingTargetAmount}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        fundingTargetAmount: event.target.value,
                      }))
                    }
                  />
                  <select
                    className="select"
                    value={campaignForm.currency}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        currency: event.target.value,
                      }))
                    }
                  >
                    <option value="GEL">GEL</option>
                    <option value="USD">USD</option>
                    <option value="EUR">EUR</option>
                  </select>
                </div>
                <div className="form-grid">
                  <input
                    className="input"
                    type="number"
                    min="0"
                    placeholder="Operational fee %"
                    value={campaignForm.operationalFeePercent}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        operationalFeePercent: event.target.value,
                      }))
                    }
                  />
                  <div className="metric-row">
                    <span>Execution budget</span>
                    <strong>
                      {executionBudgetAmount.toLocaleString()} {campaignForm.currency}
                    </strong>
                  </div>
                </div>
              </div>
            </details>
            <details className="dashboard-detail">
              <summary>Policy & research</summary>
              <div className="stack">
                <textarea
                  className="textarea"
                  placeholder="Legislation or drafted law"
                  value={campaignForm.legislationText}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      legislationText: event.target.value,
                    }))
                  }
                />
                <textarea
                  className="textarea"
                  placeholder="Freedom Square manifesto statements"
                  value={campaignForm.manifestoText}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      manifestoText: event.target.value,
                    }))
                  }
                />
                <textarea
                  className="textarea"
                  placeholder="Expert prompt"
                  value={campaignForm.expertPrompt}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      expertPrompt: event.target.value,
                    }))
                  }
                />
              </div>
            </details>
            <details className="dashboard-detail">
              <summary>Operations & ownership</summary>
              <div className="stack">
                <select
                  className="select"
                  value={campaignForm.status}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      status: event.target.value,
                    }))
                  }
                >
                  <option value="Draft">Draft</option>
                  <option value="Funding">Funding</option>
                  <option value="Funded">Funded</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Awaiting Verification">Awaiting Verification</option>
                  <option value="Completed">Completed</option>
                  <option value="Cancelled">Cancelled</option>
                  <option value="Planned">Planned</option>
                  <option value="Active">Active</option>
                  <option value="Paused">Paused</option>
                </select>
                <div className="form-grid">
                  <input
                    className="input"
                    type="date"
                    value={campaignForm.startDate}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        startDate: event.target.value,
                      }))
                    }
                  />
                  <input
                    className="input"
                    type="date"
                    value={campaignForm.endDate}
                    onChange={(event) =>
                      setCampaignForm((prev) => ({
                        ...prev,
                        endDate: event.target.value,
                      }))
                    }
                  />
                </div>
                <input
                  className="input"
                  placeholder="Owner"
                  value={campaignForm.owner}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      owner: event.target.value,
                    }))
                  }
                />
                <input
                  className="input"
                  placeholder="Target group"
                  value={campaignForm.targetGroup}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      targetGroup: event.target.value,
                    }))
                  }
                />
                <input
                  className="input"
                  type="number"
                  min="0"
                  placeholder="Goal (people)"
                  value={campaignForm.goal}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      goal: event.target.value,
                    }))
                  }
                />
                <textarea
                  className="textarea"
                  placeholder="Notes (optional)"
                  value={campaignForm.notes}
                  onChange={(event) =>
                    setCampaignForm((prev) => ({
                      ...prev,
                      notes: event.target.value,
                    }))
                  }
                />
              </div>
            </details>
            <button className="button" type="submit">
              Create campaign
            </button>
          </form>
        </div>
      </div>

      <div className="module-card module-card__wide" id="campaigns-list">
        <div className="card-header">
          <div>
            <h3>Campaigns</h3>
            <p className="muted">Select a campaign to open its workspace.</p>
          </div>
          {selectedCampaignId ? <div className="pill">Selected</div> : null}
        </div>
        {loading ? <p className="muted">Loading...</p> : null}
        <div className="campaigns-list-toolbar">
          <div className="filter-row">
            <input
              className="input"
              placeholder="Search by name, topic, owner, or status"
              value={campaignSearch}
              onChange={(event) => setCampaignSearch(event.target.value)}
            />
            <select
              className="select"
              value={campaignStatusFilter}
              onChange={(event) => setCampaignStatusFilter(event.target.value)}
            >
              {campaignStatusOptions.map((status) => (
                <option key={status} value={status}>
                  {status === 'All' ? 'All statuses' : status}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={campaignOwnerFilter}
              onChange={(event) => setCampaignOwnerFilter(event.target.value)}
            >
              {ownerOptions.map((owner) => (
                <option key={owner} value={owner}>
                  {owner === 'All' ? 'All owners' : owner}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={campaignSort}
              onChange={(event) => setCampaignSort(event.target.value)}
            >
              <option value="recent">Most recent</option>
              <option value="name">Name A-Z</option>
              <option value="status">Status</option>
              <option value="funding">Funding progress</option>
            </select>
          </div>
          <div className="campaigns-list-actions">
            <button
              className="button-secondary"
              type="button"
              onClick={() => downloadCsv('campaigns.csv', filteredCampaigns)}
            >
              Export CSV
            </button>
            <button className="button-ghost" type="button" onClick={clearCampaignFilters}>
              Clear filters
            </button>
          </div>
        </div>
        <div className="table table--stacked">
          <div className="table-row table-row--campaigns table-head">
            <span>Name</span>
            <span>Topic</span>
            <span>Status</span>
            <span>Dates</span>
            <span>Owner</span>
            <span>Goal</span>
            <span>Funding</span>
          </div>
          {filteredCampaigns.length === 0 && !loading && (
            <div className="table-row empty">
              {campaigns.length === 0
                ? 'No campaigns yet.'
                : 'No campaigns match these filters.'}
            </div>
          )}
          {filteredCampaigns.map((campaign) => {
            const startDate = campaign.startDate || '-'
            const endDate = campaign.endDate || '-'
            const isSelected = selectedCampaignId === campaign.campaignId
            return (
              <button
                type="button"
                className={`table-row table-row--campaigns table-row__button ${isSelected ? 'is-active' : ''}`}
                key={campaign.campaignId}
                onClick={() => {
                  setSelectedCampaignId(campaign.campaignId)
                  setCampaignSection('strategy')
                }}
                aria-pressed={isSelected}
              >
                <span data-label="Name">{campaign.name}</span>
                <span data-label="Topic">{campaign.topic || '-'}</span>
                <span data-label="Status">{campaign.status || 'Planned'}</span>
                <span data-label="Dates">
                  {startDate} to {endDate}
                </span>
                <span data-label="Owner">{campaign.owner || '-'}</span>
                <span data-label="Goal">{campaign.goal ?? 0}</span>
                <span data-label="Funding">
                  {Number(campaign.fundsRaisedAmount ?? 0).toLocaleString()} /{' '}
                  {Number(campaign.fundingTargetAmount ?? 0).toLocaleString()}{' '}
                  {campaign.currency || 'GEL'}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="module-card module-card__wide campaigns-detail-header">
        <div className="card-header">
          <div>
            <h3>{selectedCampaign?.name || 'Campaign details'}</h3>
            <p className="muted">
              Strategy, execution, funding, and updates in one workspace.
            </p>
          </div>
          {selectedCampaignId ? (
            <div className="pill">{selectedCampaign?.status || 'Planned'}</div>
          ) : null}
        </div>
        {detailError ? <div className="module-alert">{detailError}</div> : null}
        {!selectedCampaignId || !selectedCampaign ? (
          <p className="muted">Select a campaign to view its workspace.</p>
        ) : (
          <>
            <div className="campaigns-detail-grid">
              <div className="campaigns-detail-metrics">
                <div className="metric-row">
                  <span>Owner</span>
                  <strong>
                    {selectedCampaign.responsibleOwner ||
                      selectedCampaign.owner ||
                      '-'}
                  </strong>
                </div>
                <div className="metric-row">
                  <span>Status</span>
                  <strong>{selectedCampaign.status || 'Planned'}</strong>
                </div>
                <div className="metric-row">
                  <span>Dates</span>
                  <strong>
                    {selectedCampaign.startDate ||
                      selectedCampaign.executionStartDate ||
                      '-'}{' '} to {' '}
                    {selectedCampaign.endDate ||
                      selectedCampaign.expectedCompletionDate ||
                      '-'}
                  </strong>
                </div>
                <div className="metric-row">
                  <span>Funding</span>
                  <strong>
                    {raisedAmount.toLocaleString()} / {targetAmount.toLocaleString()}{' '}
                    {displayCurrency}
                  </strong>
                </div>
                <div className="metric-row">
                  <span>Goal</span>
                  <strong>{Number(selectedCampaign.goal ?? 0).toLocaleString()}</strong>
                </div>
              </div>
              <div className="campaigns-detail-actions">
                <div className="table-actions">
                  <button
                    className="button"
                    type="button"
                    onClick={handleRunAnalysis}
                    disabled={!campaignDraft}
                  >
                    Run analysis
                  </button>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={handleLaunchDeliberation}
                    disabled={!selectedCampaignId}
                  >
                    Launch survey
                  </button>
                  <button
                    className="button-ghost"
                    type="button"
                    onClick={handleRefreshInsights}
                    disabled={!campaignDetail?.deliberationConversationId}
                  >
                    Refresh insights
                  </button>
                  {conversationLink ? (
                    <a
                      className="button-ghost"
                      href={conversationLink}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open questionnaire
                    </a>
                  ) : null}
                </div>
                {analysisStatus ? <p className="muted">{analysisStatus}</p> : null}
              </div>
              {campaignNextSteps.length ? (
                <div className="campaigns-next-steps">
                  <h4>Smart next steps</h4>
                  <ul className="compact-list">
                    {campaignNextSteps.map((step, index) => (
                      <li key={`step-${index}`}>{step}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
            <div className="subtabs campaigns-detail-tabs">
              {campaignDetailTabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`subtab ${campaignSection === tab.id ? 'active' : ''}`}
                  onClick={() => setCampaignSection(tab.id)}
                  aria-pressed={campaignSection === tab.id}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {campaignSection === 'strategy' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Strategy and analysis</h3>
              <p className="muted">
                Refine your topic, objective, and research inputs.
              </p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to edit strategy.</p>
          )}
          {selectedCampaignId && campaignDraft && (
            <div className="stack">
              <div className="form-grid">
                <input
                  className="input"
                  placeholder="Topic"
                  value={campaignDraft.topic || ''}
                  onChange={(event) => handleDraftChange('topic', event.target.value)}
                />
                <input
                  className="input"
                  placeholder="Objective"
                  value={campaignDraft.objective || ''}
                  onChange={(event) =>
                    handleDraftChange('objective', event.target.value)
                  }
                />
              </div>
              <textarea
                className="textarea"
                placeholder="Legislation or drafted law"
                value={campaignDraft.legislationText || ''}
                onChange={(event) =>
                  handleDraftChange('legislationText', event.target.value)
                }
              />
              <textarea
                className="textarea"
                placeholder="Freedom Square manifesto statements"
                value={campaignDraft.manifestoText || ''}
                onChange={(event) =>
                  handleDraftChange('manifestoText', event.target.value)
                }
              />
              <textarea
                className="textarea"
                placeholder="Expert prompt"
                value={campaignDraft.expertPrompt || ''}
                onChange={(event) =>
                  handleDraftChange('expertPrompt', event.target.value)
                }
              />
            </div>
          )}
        </div>
      )}

      {campaignSection === 'execution' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Execution plan</h3>
              <p className="muted">
                Move funded campaigns into delivery and verification.
              </p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to manage execution.</p>
          )}
          {selectedCampaignId && campaignDraft && (
            <div className="stack">
              {campaignSaveError ? (
                <div className="module-alert">{campaignSaveError}</div>
              ) : null}
              {campaignSaveStatus ? (
                <div className="module-alert">{campaignSaveStatus}</div>
              ) : null}
              <div className="form-grid">
                <select
                  className="select"
                  value={campaignDraft.status || 'Planned'}
                  onChange={(event) => handleDraftChange('status', event.target.value)}
                >
                  <option value="Draft">Draft</option>
                  <option value="Funding">Funding</option>
                  <option value="Funded">Funded</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Awaiting Verification">Awaiting Verification</option>
                  <option value="Completed">Completed</option>
                  <option value="Cancelled">Cancelled</option>
                  <option value="Planned">Planned</option>
                  <option value="Active">Active</option>
                  <option value="Paused">Paused</option>
                </select>
                <input
                  className="input"
                  placeholder="Responsible owner"
                  value={campaignDraft.responsibleOwner || ''}
                  onChange={(event) =>
                    handleDraftChange('responsibleOwner', event.target.value)
                  }
                />
              </div>
              <div className="form-grid">
                <input
                  className="input"
                  placeholder="Community partner"
                  value={campaignDraft.communityPartner || ''}
                  onChange={(event) =>
                    handleDraftChange('communityPartner', event.target.value)
                  }
                />
                <input
                  className="input"
                  type="date"
                  value={campaignDraft.executionStartDate || ''}
                  onChange={(event) =>
                    handleDraftChange('executionStartDate', event.target.value)
                  }
                />
                <input
                  className="input"
                  type="date"
                  value={campaignDraft.expectedCompletionDate || ''}
                  onChange={(event) =>
                    handleDraftChange('expectedCompletionDate', event.target.value)
                  }
                />
              </div>
              <textarea
                className="textarea"
                placeholder="Implementation steps"
                value={campaignDraft.implementationSteps || ''}
                onChange={(event) =>
                  handleDraftChange('implementationSteps', event.target.value)
                }
              />
              <button
                className="button"
                type="button"
                onClick={handleSaveExecutionPlan}
              >
                Save execution plan
              </button>
            </div>
          )}
        </div>
      )}

      {campaignSection === 'funding' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Funding and transparency</h3>
              <p className="muted">
                Track progress toward the target and record contributions.
              </p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to see funding activity.</p>
          )}
          {selectedCampaignId && (
            <div className="stack">
              <div className="module-grid">
                <div className="module-card">
                  <h4>Funding summary</h4>
                  <div className="questionnaire-progress">
                    <div className="questionnaire-progress__track">
                      <div
                        className="questionnaire-progress__bar"
                        style={{ width: `${fundingProgress}%` }}
                      />
                    </div>
                    <span className="questionnaire-progress__label">
                      {fundingProgress.toFixed(0)}%
                    </span>
                  </div>
                  <div className="metric-row">
                    <span>Raised</span>
                    <strong>
                      {raisedAmount.toLocaleString()} {displayCurrency}
                    </strong>
                  </div>
                  <div className="metric-row">
                    <span>Target</span>
                    <strong>
                      {targetAmount.toLocaleString()} {displayCurrency}
                    </strong>
                  </div>
                  <div className="metric-row">
                    <span>Contributors</span>
                    <strong>{contributorCount}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Allocated to operations</span>
                    <strong>
                      {allocatedOperations.toLocaleString()} {displayCurrency}
                    </strong>
                  </div>
                  <div className="metric-row">
                    <span>Allocated to execution</span>
                    <strong>
                      {allocatedExecution.toLocaleString()} {displayCurrency}
                    </strong>
                  </div>
                </div>

                <div className="module-card">
                  <h4>Record contribution</h4>
                  {contributionError ? (
                    <div className="module-alert">{contributionError}</div>
                  ) : null}
                  {contributionStatus ? (
                    <div className="module-alert">{contributionStatus}</div>
                  ) : null}
                  <form className="stack" onSubmit={handleContributionSubmit}>
                    <div className="form-grid">
                      <input
                        className="input"
                        type="number"
                        min="0"
                        placeholder="Amount"
                        value={contributionForm.amount}
                        onChange={(event) =>
                          setContributionForm((prev) => ({
                            ...prev,
                            amount: event.target.value,
                          }))
                        }
                      />
                      <select
                        className="select"
                        value={contributionForm.currency}
                        onChange={(event) =>
                          setContributionForm((prev) => ({
                            ...prev,
                            currency: event.target.value,
                          }))
                        }
                      >
                        <option value="GEL">GEL</option>
                        <option value="USD">USD</option>
                        <option value="EUR">EUR</option>
                      </select>
                    </div>
                    <input
                      className="input"
                      placeholder="Contributor name"
                      value={contributionForm.contributorName}
                      onChange={(event) =>
                        setContributionForm((prev) => ({
                          ...prev,
                          contributorName: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      type="email"
                      placeholder="Contributor email"
                      value={contributionForm.contributorEmail}
                      onChange={(event) =>
                        setContributionForm((prev) => ({
                          ...prev,
                          contributorEmail: event.target.value,
                        }))
                      }
                    />
                    <textarea
                      className="textarea"
                      placeholder="Note (optional)"
                      value={contributionForm.note}
                      onChange={(event) =>
                        setContributionForm((prev) => ({
                          ...prev,
                          note: event.target.value,
                        }))
                      }
                    />
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={contributionForm.isAnonymous}
                        onChange={(event) =>
                          setContributionForm((prev) => ({
                            ...prev,
                            isAnonymous: event.target.checked,
                          }))
                        }
                      />
                      Contribute anonymously
                    </label>
                    <button className="button" type="submit">
                      Record contribution
                    </button>
                  </form>
                </div>
              </div>

              <div className="module-card">
                <h4>Recent contributions</h4>
                {contributions.length === 0 ? (
                  <p className="muted">No contributions recorded yet.</p>
                ) : (
                  <ul className="compact-list">
                    {contributions.slice(0, 5).map((contrib) => (
                      <li key={contrib.contributionId}>
                        {contrib.isAnonymous
                          ? 'Anonymous'
                          : contrib.contributorName || 'Supporter'}{' '}
                        - {contrib.amount} {contrib.currency}{' '}
                        {contrib.paymentStatus ? `(${contrib.paymentStatus})` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {campaignSection === 'operations' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Execution, proof, and partners</h3>
              <p className="muted">
                Track milestones, spending, proof of work, and local partners.
              </p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to manage execution.</p>
          )}
          {selectedCampaignId && (
            <div className="stack">
              <div className="module-grid">
                <div className="module-card">
                  <h4>Milestones</h4>
                  {milestoneError ? (
                    <div className="module-alert">{milestoneError}</div>
                  ) : null}
                  {milestoneStatus ? (
                    <div className="module-alert">{milestoneStatus}</div>
                  ) : null}
                  <form className="stack" onSubmit={handleMilestoneSubmit}>
                    <input
                      className="input"
                      placeholder="Milestone title"
                      value={milestoneForm.title}
                      onChange={(event) =>
                        setMilestoneForm((prev) => ({
                          ...prev,
                          title: event.target.value,
                        }))
                      }
                    />
                    <div className="form-grid">
                      <input
                        className="input"
                        type="number"
                        min="0"
                        placeholder="Amount target"
                        value={milestoneForm.amountTarget}
                        onChange={(event) =>
                          setMilestoneForm((prev) => ({
                            ...prev,
                            amountTarget: event.target.value,
                          }))
                        }
                      />
                      <input
                        className="input"
                        type="date"
                        value={milestoneForm.dueDate}
                        onChange={(event) =>
                          setMilestoneForm((prev) => ({
                            ...prev,
                            dueDate: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="form-grid">
                      <select
                        className="select"
                        value={milestoneForm.status}
                        onChange={(event) =>
                          setMilestoneForm((prev) => ({
                            ...prev,
                            status: event.target.value,
                          }))
                        }
                      >
                        <option value="Planned">Planned</option>
                        <option value="Funding">Funding</option>
                        <option value="In Progress">In Progress</option>
                        <option value="Completed">Completed</option>
                      </select>
                      <input
                        className="input"
                        type="number"
                        min="0"
                        max="100"
                        placeholder="Completion %"
                        value={milestoneForm.completionPercent}
                        onChange={(event) =>
                          setMilestoneForm((prev) => ({
                            ...prev,
                            completionPercent: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <button className="button" type="submit">
                      Add milestone
                    </button>
                  </form>
                  {milestones.length === 0 ? (
                    <p className="muted">No milestones yet.</p>
                  ) : (
                    <ul className="compact-list">
                      {milestones.slice(0, 5).map((milestone) => (
                        <li key={milestone.milestoneId}>
                          {milestone.title} - {milestone.status}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="module-card">
                  <h4>Expenses</h4>
                  {expenseError ? (
                    <div className="module-alert">{expenseError}</div>
                  ) : null}
                  {expenseStatus ? (
                    <div className="module-alert">{expenseStatus}</div>
                  ) : null}
                  <form className="stack" onSubmit={handleExpenseSubmit}>
                    <input
                      className="input"
                      placeholder="Category"
                      value={expenseForm.category}
                      onChange={(event) =>
                        setExpenseForm((prev) => ({
                          ...prev,
                          category: event.target.value,
                        }))
                      }
                    />
                    <div className="form-grid">
                      <input
                        className="input"
                        placeholder="Vendor"
                        value={expenseForm.vendor}
                        onChange={(event) =>
                          setExpenseForm((prev) => ({
                            ...prev,
                            vendor: event.target.value,
                          }))
                        }
                      />
                      <input
                        className="input"
                        type="number"
                        min="0"
                        placeholder="Amount"
                        value={expenseForm.amount}
                        onChange={(event) =>
                          setExpenseForm((prev) => ({
                            ...prev,
                            amount: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="form-grid">
                      <select
                        className="select"
                        value={expenseForm.currency}
                        onChange={(event) =>
                          setExpenseForm((prev) => ({
                            ...prev,
                            currency: event.target.value,
                          }))
                        }
                      >
                        <option value="GEL">GEL</option>
                        <option value="USD">USD</option>
                        <option value="EUR">EUR</option>
                      </select>
                      <select
                        className="select"
                        value={expenseForm.milestoneId}
                        onChange={(event) =>
                          setExpenseForm((prev) => ({
                            ...prev,
                            milestoneId: event.target.value,
                          }))
                        }
                      >
                        <option value="">Link to milestone</option>
                        {milestones.map((milestone) => (
                          <option
                            key={`expense-${milestone.milestoneId}`}
                            value={milestone.milestoneId}
                          >
                            {milestone.title}
                          </option>
                        ))}
                      </select>
                    </div>
                    <input
                      className="input"
                      placeholder="Receipt link"
                      value={expenseForm.receiptLink}
                      onChange={(event) =>
                        setExpenseForm((prev) => ({
                          ...prev,
                          receiptLink: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      placeholder="Approved by"
                      value={expenseForm.approvedBy}
                      onChange={(event) =>
                        setExpenseForm((prev) => ({
                          ...prev,
                          approvedBy: event.target.value,
                        }))
                      }
                    />
                    <button className="button" type="submit">
                      Record expense
                    </button>
                  </form>
                  {expenses.length === 0 ? (
                    <p className="muted">No expenses yet.</p>
                  ) : (
                    <ul className="compact-list">
                      {expenses.slice(0, 5).map((expense) => (
                        <li key={expense.expenseId}>
                          {expense.category} - {expense.amount} {expense.currency}{' '}
                          {expense.approvalStatus
                            ? `(${expense.approvalStatus})`
                            : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <div className="module-grid">
                <div className="module-card">
                  <h4>Proof of work</h4>
                  {proofError ? (
                    <div className="module-alert">{proofError}</div>
                  ) : null}
                  {proofStatus ? (
                    <div className="module-alert">{proofStatus}</div>
                  ) : null}
                  <form className="stack" onSubmit={handleProofSubmit}>
                    <div className="form-grid">
                      <select
                        className="select"
                        value={proofForm.artifactType}
                        onChange={(event) =>
                          setProofForm((prev) => ({
                            ...prev,
                            artifactType: event.target.value,
                          }))
                        }
                      >
                        <option value="image">Image</option>
                        <option value="pdf">PDF</option>
                        <option value="video">Video</option>
                        <option value="link">Link</option>
                        <option value="text">Text update</option>
                      </select>
                      <select
                        className="select"
                        value={proofForm.milestoneId}
                        onChange={(event) =>
                          setProofForm((prev) => ({
                            ...prev,
                            milestoneId: event.target.value,
                          }))
                        }
                      >
                        <option value="">Link to milestone</option>
                        {milestones.map((milestone) => (
                          <option
                            key={`proof-${milestone.milestoneId}`}
                            value={milestone.milestoneId}
                          >
                            {milestone.title}
                          </option>
                        ))}
                      </select>
                    </div>
                    <input
                      className="input"
                      placeholder="Proof URL"
                      value={proofForm.url}
                      onChange={(event) =>
                        setProofForm((prev) => ({
                          ...prev,
                          url: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      placeholder="Uploaded by"
                      value={proofForm.uploadedBy}
                      onChange={(event) =>
                        setProofForm((prev) => ({
                          ...prev,
                          uploadedBy: event.target.value,
                        }))
                      }
                    />
                    <textarea
                      className="textarea"
                      placeholder="Caption"
                      value={proofForm.caption}
                      onChange={(event) =>
                        setProofForm((prev) => ({
                          ...prev,
                          caption: event.target.value,
                        }))
                      }
                    />
                    <select
                      className="select"
                      value={proofForm.verificationStatus}
                      onChange={(event) =>
                        setProofForm((prev) => ({
                          ...prev,
                          verificationStatus: event.target.value,
                        }))
                      }
                    >
                      <option value="Pending">Pending</option>
                      <option value="Verified">Verified</option>
                      <option value="Rejected">Rejected</option>
                    </select>
                    <button className="button" type="submit">
                      Add proof
                    </button>
                  </form>
                  {proofArtifacts.length === 0 ? (
                    <p className="muted">No proof artifacts yet.</p>
                  ) : (
                    <ul className="compact-list">
                      {proofArtifacts.slice(0, 5).map((artifact) => (
                        <li key={artifact.proofId}>
                          {artifact.artifactType} - {artifact.caption || artifact.url}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="module-card">
                  <h4>Partners</h4>
                  {partnerError ? (
                    <div className="module-alert">{partnerError}</div>
                  ) : null}
                  {partnerStatus ? (
                    <div className="module-alert">{partnerStatus}</div>
                  ) : null}
                  <form className="stack" onSubmit={handlePartnerSubmit}>
                    <input
                      className="input"
                      placeholder="Partner name"
                      value={partnerForm.name}
                      onChange={(event) =>
                        setPartnerForm((prev) => ({
                          ...prev,
                          name: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      placeholder="Role"
                      value={partnerForm.role}
                      onChange={(event) =>
                        setPartnerForm((prev) => ({
                          ...prev,
                          role: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      placeholder="Contact"
                      value={partnerForm.contact}
                      onChange={(event) =>
                        setPartnerForm((prev) => ({
                          ...prev,
                          contact: event.target.value,
                        }))
                      }
                    />
                    <textarea
                      className="textarea"
                      placeholder="Verification notes"
                      value={partnerForm.verificationNotes}
                      onChange={(event) =>
                        setPartnerForm((prev) => ({
                          ...prev,
                          verificationNotes: event.target.value,
                        }))
                      }
                    />
                    <button className="button" type="submit">
                      Add partner
                    </button>
                  </form>
                  {partners.length === 0 ? (
                    <p className="muted">No partners yet.</p>
                  ) : (
                    <ul className="compact-list">
                      {partners.slice(0, 5).map((partner) => (
                        <li key={partner.partnerId}>
                          {partner.name} - {partner.role || 'Partner'}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {campaignSection === 'messages' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Campaign messages</h3>
              <p className="muted">
                Draft communication messages for email, WhatsApp, Slack, and field outreach.
              </p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to create messages.</p>
          )}
          {selectedCampaignId && (
            <div className="module-grid">
              <div className="module-card">
                <h4>Message builder</h4>
                {campaignMessageError ? (
                  <div className="module-alert">{campaignMessageError}</div>
                ) : null}
                {campaignMessageStatus ? (
                  <div className="module-alert">{campaignMessageStatus}</div>
                ) : null}
                <div className="form-grid">
                  <select
                    className="select"
                    value={campaignMessageGenerateForm.channel}
                    onChange={(event) =>
                      setCampaignMessageGenerateForm((prev) => ({
                        ...prev,
                        channel: event.target.value,
                      }))
                    }
                  >
                    <option value="whatsapp">WhatsApp</option>
                    <option value="email">Email</option>
                    <option value="slack">Slack</option>
                    <option value="social">Social post</option>
                    <option value="field">Field script</option>
                  </select>
                  <select
                    className="select"
                    value={campaignMessageGenerateForm.language}
                    onChange={(event) =>
                      setCampaignMessageGenerateForm((prev) => ({
                        ...prev,
                        language: event.target.value,
                      }))
                    }
                  >
                    <option value="ka">Georgian</option>
                    <option value="en">English</option>
                    <option value="bilingual">Georgian + English</option>
                  </select>
                  <input
                    className="input"
                    placeholder="Tone"
                    value={campaignMessageGenerateForm.tone}
                    onChange={(event) =>
                      setCampaignMessageGenerateForm((prev) => ({
                        ...prev,
                        tone: event.target.value,
                      }))
                    }
                  />
                </div>
                <textarea
                  className="textarea"
                  placeholder="Extra instructions for this message"
                  value={campaignMessageGenerateForm.instructions}
                  onChange={(event) =>
                    setCampaignMessageGenerateForm((prev) => ({
                      ...prev,
                      instructions: event.target.value,
                    }))
                  }
                />
                <div className="button-row">
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={handleGenerateCampaignMessage}
                  >
                    <IconSend size={16} /> Draft message
                  </button>
                </div>
                <form className="stack" onSubmit={handleCampaignMessageSubmit}>
                  <div className="form-grid">
                    <select
                      className="select"
                      value={campaignMessageForm.channel}
                      onChange={(event) =>
                        setCampaignMessageForm((prev) => ({
                          ...prev,
                          channel: event.target.value,
                        }))
                      }
                    >
                      <option value="whatsapp">WhatsApp</option>
                      <option value="email">Email</option>
                      <option value="slack">Slack</option>
                      <option value="social">Social post</option>
                      <option value="field">Field script</option>
                    </select>
                    <select
                      className="select"
                      value={campaignMessageForm.status}
                      onChange={(event) =>
                        setCampaignMessageForm((prev) => ({
                          ...prev,
                          status: event.target.value,
                        }))
                      }
                    >
                      <option value="Draft">Draft</option>
                      <option value="Ready">Ready</option>
                      <option value="Sent">Sent</option>
                      <option value="Archived">Archived</option>
                    </select>
                  </div>
                  <input
                    className="input"
                    placeholder="Message title"
                    value={campaignMessageForm.title}
                    onChange={(event) =>
                      setCampaignMessageForm((prev) => ({
                        ...prev,
                        title: event.target.value,
                      }))
                    }
                  />
                  <textarea
                    className="textarea"
                    placeholder="Message body"
                    value={campaignMessageForm.body}
                    onChange={(event) =>
                      setCampaignMessageForm((prev) => ({
                        ...prev,
                        body: event.target.value,
                      }))
                    }
                  />
                  <input
                    className="input"
                    placeholder="Call to action"
                    value={campaignMessageForm.callToAction}
                    onChange={(event) =>
                      setCampaignMessageForm((prev) => ({
                        ...prev,
                        callToAction: event.target.value,
                      }))
                    }
                  />
                  <div className="button-row">
                    <button className="button" type="submit">
                      Save message
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => handleCopyCampaignMessage(campaignMessageForm)}
                    >
                      <IconCopy size={16} /> Copy
                    </button>
                  </div>
                </form>
                {generatedCampaignMessages.length ? (
                  <p className="muted">Generated draft loaded into the editor.</p>
                ) : null}
              </div>

              <div className="module-card">
                <h4>Saved messages</h4>
                {campaignMessages.length === 0 ? (
                  <p className="muted">No saved messages yet.</p>
                ) : (
                  <div className="stack">
                    {campaignMessages.slice(0, 8).map((message) => (
                      <div className="metric-row" key={message.messageId}>
                        <span>
                          <strong>{message.title || message.channel}</strong>
                          <br />
                          <span className="muted">{message.channel} / {message.status}</span>
                        </span>
                        <button
                          className="icon-button"
                          type="button"
                          title="Copy message"
                          onClick={() => handleCopyCampaignMessage(message)}
                        >
                          <IconCopy size={16} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {campaignSection === 'updates' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Campaign updates</h3>
              <p className="muted">
                Keep stakeholders informed and share delivery progress.
              </p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to add updates.</p>
          )}
          {selectedCampaignId && (
            <div className="module-grid">
              <div className="module-card">
                <h4>Campaign updates</h4>
                {campaignUpdateError ? (
                  <div className="module-alert">{campaignUpdateError}</div>
                ) : null}
                {campaignUpdateStatus ? (
                  <div className="module-alert">{campaignUpdateStatus}</div>
                ) : null}
                <form className="stack" onSubmit={handleCampaignUpdateSubmit}>
                  <textarea
                    className="textarea"
                    placeholder="Update message"
                    value={campaignUpdateForm.message}
                    onChange={(event) =>
                      setCampaignUpdateForm((prev) => ({
                        ...prev,
                        message: event.target.value,
                      }))
                    }
                  />
                  <div className="form-grid">
                    <input
                      className="input"
                      placeholder="Posted by"
                      value={campaignUpdateForm.createdBy}
                      onChange={(event) =>
                        setCampaignUpdateForm((prev) => ({
                          ...prev,
                          createdBy: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      placeholder="Status note (optional)"
                      value={campaignUpdateForm.status}
                      onChange={(event) =>
                        setCampaignUpdateForm((prev) => ({
                          ...prev,
                          status: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <button className="button" type="submit">
                    Post update
                  </button>
                </form>
                {campaignUpdates.length === 0 ? (
                  <p className="muted">No updates yet.</p>
                ) : (
                  <ul className="compact-list">
                    {campaignUpdates.slice(0, 5).map((update) => (
                      <li key={update.updateId}>
                        {update.message}
                        {update.createdBy ? ` - ${update.createdBy}` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

            </div>
          )}
        </div>
      )}

      {campaignSection === 'people' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Audience</h3>
              <p className="muted">Track campaign participants and field roles.</p>
            </div>
          </div>
          {!selectedCampaignId && (
            <p className="muted">Select a campaign to manage people.</p>
          )}
          {selectedCampaignId && (
            <div className="module-grid">
              <div className="module-card">
                <h4>Campaign people</h4>
                {campaignVolunteerError ? (
                  <div className="module-alert">{campaignVolunteerError}</div>
                ) : null}
                {campaignVolunteerStatus ? (
                  <div className="module-alert">{campaignVolunteerStatus}</div>
                ) : null}
                <form className="stack" onSubmit={handleCampaignVolunteerSubmit}>
                  <input
                    className="input"
                    placeholder="Name"
                    value={campaignVolunteerForm.name}
                    onChange={(event) =>
                      setCampaignVolunteerForm((prev) => ({
                        ...prev,
                        name: event.target.value,
                      }))
                    }
                  />
                  <div className="form-grid">
                    <input
                      className="input"
                      placeholder="Email"
                      value={campaignVolunteerForm.email}
                      onChange={(event) =>
                        setCampaignVolunteerForm((prev) => ({
                          ...prev,
                          email: event.target.value,
                        }))
                      }
                    />
                    <input
                      className="input"
                      placeholder="Phone"
                      value={campaignVolunteerForm.phone}
                      onChange={(event) =>
                        setCampaignVolunteerForm((prev) => ({
                          ...prev,
                          phone: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <input
                    className="input"
                    placeholder="Role"
                    value={campaignVolunteerForm.role}
                    onChange={(event) =>
                      setCampaignVolunteerForm((prev) => ({
                        ...prev,
                        role: event.target.value,
                      }))
                    }
                  />
                  <textarea
                    className="textarea"
                    placeholder="Notes"
                    value={campaignVolunteerForm.notes}
                    onChange={(event) =>
                      setCampaignVolunteerForm((prev) => ({
                        ...prev,
                        notes: event.target.value,
                      }))
                    }
                  />
                  <button className="button" type="submit">
                    Add volunteer
                  </button>
                </form>
                {campaignVolunteers.length === 0 ? (
                  <p className="muted">No volunteers yet.</p>
                ) : (
                  <ul className="compact-list">
                    {campaignVolunteers.slice(0, 5).map((volunteer) => (
                      <li key={volunteer.volunteerId}>
                        {volunteer.name} - {volunteer.role || 'Volunteer'}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="module-card">
                <h4>Workday planning</h4>
                <p className="muted">
                  Use the Events tab to schedule community action days.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {campaignSection === 'statements' && (
        <>
          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Consensus vs polarization</h3>
                <p className="muted">Generated statements for the survey.</p>
              </div>
            </div>
            <div className="module-grid">
              <div className="module-card">
                <h4>Consensus</h4>
                <ul className="compact-list">
                  {(campaignDetail?.consensusStatements || []).map((statement, idx) => (
                    <li key={`consensus-${idx}`}>{statement}</li>
                  ))}
                </ul>
              </div>
              <div className="module-card">
                <h4>Polarization</h4>
                <ul className="compact-list">
                  {(campaignDetail?.polarizationStatements || []).map((statement, idx) => (
                    <li key={`polar-${idx}`}>{statement}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="module-card module-card__wide">
            <div className="card-header">
              <div>
                <h3>Campaign final statements</h3>
                <p className="muted">
                  Final statements, sub statements, and communication actions for campaign follow-up.
                </p>
              </div>
            </div>
            <div className="module-grid">
              {finalStatements.map((statement, idx) => (
                <div className="module-card" key={`final-${idx}`}>
                  <h4>{statement.statement}</h4>
                  <div className="card-divider">
                    <h5>Sub statements</h5>
                  </div>
                  <ul className="compact-list">
                    {statement.subStatements.map((item, subIdx) => (
                      <li key={`sub-${idx}-${subIdx}`}>{item}</li>
                    ))}
                  </ul>
                  <div className="card-divider">
                    <h5>Actions</h5>
                  </div>
                  <ul className="compact-list">
                    {statement.actions.map((action, actionIdx) => (
                      <li key={`action-${idx}-${actionIdx}`}>{action}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {campaignSection === 'insights' && (
        <div className="module-card module-card__wide">
          <div className="card-header">
            <div>
              <h3>Survey insights</h3>
              <p className="muted">Latest report from the survey module.</p>
            </div>
          </div>
          {reportError ? <div className="module-alert">{reportError}</div> : null}
          {!report && <p className="muted">Run survey and refresh insights.</p>}
          {report ? (
            <div className="stack">
              <div className="metric-row">
                <span>Total votes</span>
                <strong>{report?.metrics?.total_votes ?? '-'}</strong>
              </div>
              <div className="metric-row">
                <span>Participants</span>
                <strong>{report?.metrics?.total_participants ?? '-'}</strong>
              </div>
              <div className="metric-row">
                <span>Clusters</span>
                <strong>{report?.clusters?.length ?? '-'}</strong>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function CRMEventsTab() {
  const [events, setEvents] = useState([])
  const [statusCounts, setStatusCounts] = useState([])
  const [groups, setGroups] = useState([])
  const [error, setError] = useState('')
  const [selectedEventId, setSelectedEventId] = useState('')
  const [registrations, setRegistrations] = useState([])
  const [registrationError, setRegistrationError] = useState('')
  const [eventForm, setEventForm] = useState({
    name: '',
    startDate: '',
    endDate: '',
    location: '',
    status: 'Planned',
    capacity: '',
    notes: '',
  })
  const [registrationForm, setRegistrationForm] = useState({
    fullName: '',
    email: '',
    phone: '',
    group: 'Supporter',
    status: 'Registered',
    notes: '',
  })
  const [sendingLink, setSendingLink] = useState(false)
  const [shareError, setShareError] = useState('')
  const [shareGroupId, setShareGroupId] = useState('')
  const [slackMessage, setSlackMessage] = useState('')
  const [slackError, setSlackError] = useState('')
  const [slackStatus, setSlackStatus] = useState('')
  const [sendingSlack, setSendingSlack] = useState(false)
  const [exportStatus, setExportStatus] = useState('')

  const loadEvents = () => {
    setError('')
    Promise.all([
      getJson('/crm/events'),
      getJson('/crm/events/registrations/status-counts'),
      getJson('/crm/whatsapp-groups'),
    ])
      .then(([eventsPayload, statusPayload, groupsPayload]) => {
        setEvents(Array.isArray(eventsPayload) ? eventsPayload : [])
        setStatusCounts(Array.isArray(statusPayload) ? statusPayload : [])
        setGroups(Array.isArray(groupsPayload) ? groupsPayload : [])
      })
      .catch((err) => {
        setError(err.message || 'Unable to load events.')
      })
  }

  useEffect(() => {
    loadEvents()
  }, [])

  useEffect(() => {
    if (!selectedEventId) {
      setRegistrations([])
      return
    }
    setRegistrationError('')
    getJson(`/crm/events/${selectedEventId}/registrations?limit=2000`)
      .then((payload) => setRegistrations(Array.isArray(payload) ? payload : []))
      .catch((err) =>
        setRegistrationError(err.message || 'Unable to load registrations.'),
      )
  }, [selectedEventId])

  const totalEvents = events.length
  const totalRegs = events.reduce(
    (acc, event) => acc + Number(event.registrations || 0),
    0,
  )
  const attendedCount = statusCounts
    .filter((row) => row.registrationStatus === 'Attended')
    .reduce((acc, row) => acc + Number(row.count || 0), 0)
  const attendanceRate = totalRegs ? (attendedCount / totalRegs) * 100 : 0

  const statusTotals = statusCounts.reduce((acc, row) => {
    const status = row.registrationStatus || 'Registered'
    acc[status] = (acc[status] || 0) + Number(row.count || 0)
    return acc
  }, {})
  const statusLabels = Object.keys(statusTotals)
  const statusValues = statusLabels.map((label) => statusTotals[label])
  const statusChartData = {
    labels: statusLabels,
    datasets: [
      {
        data: statusValues,
        backgroundColor: ['#2563eb', '#16a34a', '#f59e0b', '#ef4444', '#64748b'],
      },
    ],
  }

  const handleCreateEvent = async (event) => {
    event.preventDefault()
    if (!eventForm.name.trim()) {
      setError('Event name is required.')
      return
    }
    setError('')
    try {
      await requestJson('/crm/events', {
        method: 'POST',
        payload: {
          name: eventForm.name.trim(),
          startDate: eventForm.startDate,
          endDate: eventForm.endDate,
          location: eventForm.location,
          status: eventForm.status,
          capacity: eventForm.capacity ? Number(eventForm.capacity) : 0,
          notes: eventForm.notes,
        },
      })
      setEventForm({
        name: '',
        startDate: '',
        endDate: '',
        location: '',
        status: 'Planned',
        capacity: '',
        notes: '',
      })
      loadEvents()
    } catch (err) {
      setError(err.message || 'Unable to create event.')
    }
  }

  const handleRegister = async (event) => {
    event.preventDefault()
    if (!selectedEventId) {
      setRegistrationError('Select an event.')
      return
    }
    if (!registrationForm.email.trim() || !registrationForm.fullName.trim()) {
      setRegistrationError('Full name and email are required.')
      return
    }
    setRegistrationError('')
    const nameParts = splitFullName(registrationForm.fullName)
    try {
      await requestJson(`/crm/events/${selectedEventId}/register`, {
        method: 'POST',
        payload: {
          person: {
            email: registrationForm.email.trim(),
            firstName: nameParts.firstName,
            lastName: nameParts.lastName,
            phone: registrationForm.phone.trim(),
            group: registrationForm.group,
          },
          status: registrationForm.status,
          notes: registrationForm.notes.trim(),
        },
      })
      setRegistrationForm({
        fullName: '',
        email: '',
        phone: '',
        group: 'Supporter',
        status: 'Registered',
        notes: '',
      })
      const payload = await getJson(
        `/crm/events/${selectedEventId}/registrations?limit=2000`,
      )
      setRegistrations(Array.isArray(payload) ? payload : [])
    } catch (err) {
      setRegistrationError(err.message || 'Unable to register person.')
    }
  }

  const selectedEvent = events.find((event) => event.eventId === selectedEventId)
  const appBase = `${window.location.origin}${window.location.pathname}`
  const publicLink = selectedEvent
    ? `${appBase}?event_registration=1&event_id=${selectedEvent.eventId}`
    : ''

  useEffect(() => {
    if (!selectedEvent || !publicLink) {
      setSlackMessage('')
      return
    }
    setSlackMessage(`Event registration: ${selectedEvent.name}\n\nRegister here:\n${publicLink}`)
    setSlackStatus('')
    setSlackError('')
  }, [selectedEventId, publicLink, selectedEvent?.name])

  const handleShareLink = async () => {
    if (!shareGroupId || !publicLink) {
      setShareError('Select a WhatsApp group and event first.')
      return
    }
    setShareError('')
    setSendingLink(true)
    try {
      await requestJson(`/crm/whatsapp-groups/${shareGroupId}/send`, {
        method: 'POST',
        payload: {
          message: `Event registration: ${selectedEvent?.name}\n\nRegister here:\n${publicLink}`,
          appendInvite: false,
          source: 'events_share',
        },
      })
    } catch (err) {
      setShareError(err.message || 'Unable to send link.')
    } finally {
      setSendingLink(false)
    }
  }

  const handleSlackShare = async () => {
    if (!publicLink) {
      setSlackError('Select an event first.')
      return
    }
    const message =
      slackMessage ||
      `Event registration: ${selectedEvent?.name}\n\nRegister here:\n${publicLink}`
    setSlackError('')
    setSlackStatus('')
    setSendingSlack(true)
    try {
      await requestJson('/crm/slack/send', {
        method: 'POST',
        payload: {
          message,
          source: 'events_share',
        },
      })
      setSlackStatus('Sent to Slack.')
    } catch (err) {
      setSlackError(err.message || 'Unable to send to Slack.')
    } finally {
      setSendingSlack(false)
    }
  }

  const handleExportEvents = () => {
    setExportStatus('')
    if (!events.length) {
      setExportStatus('No events to export.')
      return
    }
    downloadCsv('crm_events.csv', events)
    setExportStatus('Events CSV downloaded.')
  }

  const handleExportRegistrations = () => {
    setExportStatus('')
    if (!selectedEventId) {
      setExportStatus('Select an event first.')
      return
    }
    if (!registrations.length) {
      setExportStatus('No registrations to export.')
      return
    }
    downloadCsv(`event_${selectedEventId}_registrations.csv`, registrations)
    setExportStatus('Registrations CSV downloaded.')
  }

  return (
    <div className="module-grid">
      {error ? <div className="module-alert">{error}</div> : null}
      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Create event</h3>
            <p className="muted">Plan and register your audience.</p>
          </div>
          <div className="pill">Network</div>
        </div>
        <form className="form-grid" onSubmit={handleCreateEvent}>
          <input
            className="input"
            placeholder="Event name *"
            value={eventForm.name}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, name: event.target.value }))
            }
          />
          <input
            className="input"
            type="date"
            value={eventForm.startDate}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, startDate: event.target.value }))
            }
          />
          <input
            className="input"
            type="date"
            value={eventForm.endDate}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, endDate: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Location"
            value={eventForm.location}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, location: event.target.value }))
            }
          />
          <select
            className="select"
            value={eventForm.status}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, status: event.target.value }))
            }
          >
            <option value="Planned">Planned</option>
            <option value="Scheduled">Scheduled</option>
            <option value="Completed">Completed</option>
            <option value="Cancelled">Cancelled</option>
          </select>
          <input
            className="input"
            type="number"
            placeholder="Capacity"
            value={eventForm.capacity}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, capacity: event.target.value }))
            }
          />
          <textarea
            className="textarea"
            placeholder="Notes"
            value={eventForm.notes}
            onChange={(event) =>
              setEventForm((prev) => ({ ...prev, notes: event.target.value }))
            }
          />
          <button className="button" type="submit">
            Create event
          </button>
        </form>
      </div>
      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Event registration</h3>
            <p className="muted">Register a person to an event.</p>
          </div>
        </div>
        {registrationError ? (
          <div className="module-alert">{registrationError}</div>
        ) : null}
        <form className="form-grid" onSubmit={handleRegister}>
          <select
            className="select"
            value={selectedEventId}
            onChange={(event) => setSelectedEventId(event.target.value)}
          >
            <option value="">Select event</option>
            {events.map((event) => (
              <option key={event.eventId} value={event.eventId}>
                {event.name}
              </option>
            ))}
          </select>
          <input
            className="input"
            placeholder="Full name *"
            value={registrationForm.fullName}
            onChange={(event) =>
              setRegistrationForm((prev) => ({
                ...prev,
                fullName: event.target.value,
              }))
            }
          />
          <input
            className="input"
            placeholder="Email *"
            value={registrationForm.email}
            onChange={(event) =>
              setRegistrationForm((prev) => ({
                ...prev,
                email: event.target.value,
              }))
            }
          />
          <input
            className="input"
            placeholder="Phone"
            value={registrationForm.phone}
            onChange={(event) =>
              setRegistrationForm((prev) => ({
                ...prev,
                phone: event.target.value,
              }))
            }
          />
          <select
            className="select"
            value={registrationForm.group}
            onChange={(event) =>
              setRegistrationForm((prev) => ({
                ...prev,
                group: event.target.value,
              }))
            }
          >
            <option value="Supporter">Supporter</option>
            <option value="Member">Member</option>
          </select>
          <select
            className="select"
            value={registrationForm.status}
            onChange={(event) =>
              setRegistrationForm((prev) => ({
                ...prev,
                status: event.target.value,
              }))
            }
          >
            <option value="Registered">Registered</option>
            <option value="Attended">Attended</option>
            <option value="Cancelled">Cancelled</option>
            <option value="No Show">No Show</option>
          </select>
          <input
            className="input"
            placeholder="Notes"
            value={registrationForm.notes}
            onChange={(event) =>
              setRegistrationForm((prev) => ({
                ...prev,
                notes: event.target.value,
              }))
            }
          />
          <button className="button" type="submit">
            Register
          </button>
        </form>
      </div>
      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Channels</h3>
            <p className="muted">Share registration links through WhatsApp and Slack.</p>
          </div>
        </div>
        {shareError ? <div className="module-alert">{shareError}</div> : null}
        {slackError ? <div className="module-alert">{slackError}</div> : null}
        {slackStatus ? (
          <div className="module-alert module-alert--success">{slackStatus}</div>
        ) : null}
        <div className="stack">
          {groups.length === 0 ? (
            <p className="muted">
              No groups available. Ask admin to configure WhatsApp groups first.
            </p>
          ) : null}
          <div className="card-divider">
            <h4>WhatsApp</h4>
          </div>
          <input className="input" value={publicLink} readOnly />
          <select
            className="select"
            value={shareGroupId}
            onChange={(event) => setShareGroupId(event.target.value)}
          >
            <option value="">Select existing WhatsApp group</option>
            {groups.map((group) => (
              <option key={group.groupId} value={group.groupId}>
                {group.name}
              </option>
            ))}
          </select>
          <button
            className="button"
            type="button"
            onClick={handleShareLink}
            disabled={sendingLink || groups.length === 0}
          >
            {sendingLink ? 'Sending...' : 'Send link'}
          </button>
          <div className="card-divider">
            <h4>Slack</h4>
            <p className="muted">Send to the default Slack channel.</p>
        </div>
          <input className="input" value={publicLink} readOnly />
          <button
            className="button"
            type="button"
            onClick={handleSlackShare}
            disabled={sendingSlack}
          >
            {sendingSlack ? 'Sending...' : 'Send to default Slack'}
          </button>
        </div>
      </div>
      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Registrations</h3>
            <p className="muted">View registrations for the selected event.</p>
          </div>
        </div>
        <div className="table">
          <div className="table-row table-head">
            <span>Name</span>
            <span>Email</span>
            <span>Status</span>
            <span>Updated</span>
          </div>
          {registrations.length === 0 && !selectedEventId && (
            <div className="table-row empty">Select an event to view registrations.</div>
          )}
          {registrations.map((row) => (
            <div className="table-row" key={`${row.email}-${row.updatedAt}`}>
              <span>{`${row.firstName || ''} ${row.lastName || ''}`.trim()}</span>
              <span>{row.email}</span>
              <span>{row.registrationStatus}</span>
              <span>{row.updatedAt || '-'}</span>
            </div>
          ))}
        </div>
      </div>
      <details className="dashboard-detail module-card module-card__wide">
        <summary>Reporting & exports (optional)</summary>
        <div className="dashboard-detail__body">
          <div className="module-grid">
            <div className="module-card">
              <h3>Event statistics</h3>
              <div className="metric-row">
                <span>Events</span>
                <strong>{totalEvents}</strong>
              </div>
              <div className="metric-row">
                <span>Registrations</span>
                <strong>{totalRegs}</strong>
              </div>
              <div className="metric-row">
                <span>Attended</span>
                <strong>{attendedCount}</strong>
              </div>
              <div className="metric-row">
                <span>Attendance rate</span>
                <strong>{attendanceRate.toFixed(1)}%</strong>
              </div>
            </div>
            <div className="module-card">
              <h3>Registration status</h3>
              {statusLabels.length ? (
                <Pie data={statusChartData} />
              ) : (
                <p className="muted">No registration data yet.</p>
              )}
            </div>
            <div className="module-card">
              <h3>Exports</h3>
              <p className="muted">Download events or registration data.</p>
              <div className="stack">
                <button className="button-secondary" type="button" onClick={handleExportEvents}>
                  Export events CSV
                </button>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={handleExportRegistrations}
                >
                  Export registrations CSV
                </button>
                {exportStatus ? <p className="muted">{exportStatus}</p> : null}
              </div>
            </div>
          </div>
        </div>
      </details>
    </div>
  )
}

function CRMMapTab({ onStatsChange, refreshToken } = {}) {
  return <CRMNeighborhoodMap onStatsChange={onStatsChange} refreshToken={refreshToken} />
}
