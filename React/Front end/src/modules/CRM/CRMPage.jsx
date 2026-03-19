import { useEffect, useMemo, useState } from 'react'
import {
  getJson,
  requestForm,
  requestJson,
} from '../../services/api'
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
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  Tooltip,
  Legend,
)

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

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

export function CRMPage({
  t,
  initialTab,
  hideTabs = false,
  activeTabOverride,
  onTabChange,
  showTabs = true,
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
  const [activeTab, setActiveTab] = useState(initialTab || 'overview')
  const [selectedEmail, setSelectedEmail] = useState('')

  const normalizeTab = (tabId) => {
    if (!tabId) return ''
    if (tabId === 'events') return 'outreach'
    return tabId
  }

  const applyActiveTab = (nextTab) => {
    const normalized = normalizeTab(nextTab)
    if (!normalized) return
    setActiveTab(normalized)
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
  const [segmentTimeAvailability, setSegmentTimeAvailability] = useState('All')
  const [segmentTags, setSegmentTags] = useState([])
  const [segmentSkills, setSegmentSkills] = useState([])
  const [segmentTagOptions, setSegmentTagOptions] = useState([])
  const [segmentSkillOptions, setSegmentSkillOptions] = useState([])
  const [segmentMinEffort, setSegmentMinEffort] = useState('')
  const [segmentLimit, setSegmentLimit] = useState(200)
  const [segmentSelectedId, setSegmentSelectedId] = useState('')
  const [segmentResults, setSegmentResults] = useState([])
  const [segmentRunLoading, setSegmentRunLoading] = useState(false)
  const [segmentTaskTitle, setSegmentTaskTitle] = useState('')
  const [segmentTaskDescription, setSegmentTaskDescription] = useState('')
  const [segmentTaskDueDate, setSegmentTaskDueDate] = useState('')
  const [segmentTaskStatus, setSegmentTaskStatus] = useState('Open')
  const [segmentTaskSaving, setSegmentTaskSaving] = useState(false)
  const [segmentTaskError, setSegmentTaskError] = useState('')
  const [groups, setGroups] = useState([])
  const [groupsError, setGroupsError] = useState('')
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [groupInvite, setGroupInvite] = useState('')
  const [groupNotes, setGroupNotes] = useState('')
  const [sendGroupId, setSendGroupId] = useState('')
  const [sendMessage, setSendMessage] = useState('')
  const [sendAppendInvite, setSendAppendInvite] = useState(true)
  const [sendingMessage, setSendingMessage] = useState(false)
  const [sendError, setSendError] = useState('')
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
          const stillExists = nextPeople.some((person) => person.email === selectedEmail)
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

  useEffect(() => {
    if (activeTab !== 'people') return
    loadPeople()
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

  const loadProfile = (email) => {
    if (!email) return
    setProfileError('')
    getJson(`/crm/people/${encodeURIComponent(email)}`)
      .then((payload) => {
        setProfile(payload)
        setProfileDraft(payload)
      })
      .catch((err) => {
        setProfileError(err.message || 'Unable to load profile.')
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

  const loadGroups = () => {
    setGroupsLoading(true)
    setGroupsError('')
    getJson('/crm/whatsapp-groups')
      .then((payload) => {
        setGroups(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        setGroupsError(err.message || 'Unable to load WhatsApp groups.')
      })
      .finally(() => {
        setGroupsLoading(false)
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

  useEffect(() => {
    if (activeTab !== 'outreach') return
    loadSegments()
    loadGroups()
    loadSegmentOptions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

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

  const handleCreateGroup = async (event) => {
    event.preventDefault()
    if (!groupName.trim() || !groupInvite.trim()) {
      setGroupsError('Group name and invite link are required.')
      return
    }
    setGroupsError('')
    try {
      await requestJson('/crm/whatsapp-groups', {
        method: 'POST',
        payload: {
          name: groupName.trim(),
          inviteLink: groupInvite.trim(),
          notes: groupNotes.trim(),
        },
      })
      setGroupName('')
      setGroupInvite('')
      setGroupNotes('')
      loadGroups()
    } catch (err) {
      setGroupsError(err.message || 'Unable to save WhatsApp group.')
    }
  }

  const handleDeleteGroup = async (groupId) => {
    setGroupsError('')
    try {
      await requestJson(`/crm/whatsapp-groups/${groupId}`, { method: 'DELETE' })
      if (sendGroupId === groupId) {
        setSendGroupId('')
      }
      loadGroups()
    } catch (err) {
      setGroupsError(err.message || 'Unable to delete WhatsApp group.')
    }
  }

  const handleSendMessage = async () => {
    if (!sendGroupId) {
      setSendError('Select a WhatsApp group.')
      return
    }
    if (!sendMessage.trim()) {
      setSendError('Message is required.')
      return
    }
    setSendError('')
    setSendingMessage(true)
    try {
      await requestJson(`/crm/whatsapp-groups/${sendGroupId}/send`, {
        method: 'POST',
        payload: {
          message: sendMessage.trim(),
          appendInvite: sendAppendInvite,
          source: 'react_outreach',
        },
      })
      setSendMessage('')
    } catch (err) {
      setSendError(err.message || 'Unable to send message.')
    } finally {
      setSendingMessage(false)
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

  const handleCreateSegmentEvent = async () => {
    if (!segmentResults.length) {
      setSegmentEventStatusMessage('Run a segment preview first.')
      return
    }
    if (!segmentEventName.trim()) {
      setSegmentEventStatusMessage('Event name is required.')
      return
    }
    setSegmentEventStatusMessage('')
    try {
      const rows = segmentResults.map((row) => {
        const nameParts = splitFullName(row.fullName)
        return {
          email: row.email,
          firstName: nameParts.firstName,
          lastName: nameParts.lastName,
          group: row.group,
        }
      })
      await requestJson('/crm/events/with-people', {
        method: 'POST',
        payload: {
          event: {
            name: segmentEventName.trim(),
            startDate: segmentEventStartDate || '',
            endDate: segmentEventEndDate || '',
            location: segmentEventLocation.trim(),
            status: segmentEventStatus,
            capacity: segmentEventCapacity ? Number(segmentEventCapacity) : 0,
            notes: segmentEventNotes.trim(),
          },
          rows,
          registrationStatus: 'Registered',
        },
      })
      setSegmentEventStatusMessage('Event created for segment.')
      setSegmentEventName('')
      setSegmentEventStartDate('')
      setSegmentEventEndDate('')
      setSegmentEventLocation('')
      setSegmentEventCapacity('')
      setSegmentEventNotes('')
    } catch (err) {
      setSegmentEventStatusMessage(err.message || 'Unable to create event.')
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

  return (
    <section className="module">
      {error ? <div className="module-alert">{error}</div> : null}

      {!hideTabs && showTabs ? (
        <div className="subtabs">
          {[
            { id: 'overview', label: translate('network.tabs.overview') },
            { id: 'people', label: translate('network.tabs.people') },
            { id: 'furry-friends', label: translate('network.tabs.furryFriends') },
            { id: 'tasks', label: translate('network.tabs.tasks') },
            { id: 'outreach', label: translate('network.tabs.outreach') },
            { id: 'data-entry', label: translate('network.tabs.dataEntry') },
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

      {activeTab === 'data-entry' && <CRMDataEntryTab />}
      {activeTab === 'overview' && <CRMOverviewTab />}
      {activeTab === 'campaigns' && <CRMCampaignsTab />}

      {activeTab === 'people' && (
        <div className="stack">
          <div className="section-block">
            <div className="module-layout">
              <aside className="module-sidebar">
            <div className="sidebar-card sidebar-card--accent">
              <h3>Search filters</h3>
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
                  {peopleLoading ? 'Loading…' : 'Search'}
                </button>
              </form>
            </div>
            <div className="sidebar-card">
              <h3>Directory stats</h3>
              <div className="metric-row">
                <span>Results</span>
                <strong>{people.length}</strong>
              </div>
              <div className="metric-row">
                <span>Total people</span>
                <strong>{summary?.total_people ?? '—'}</strong>
              </div>
            </div>
              </aside>
              <div className="module-main">
                {peopleError ? <div className="module-alert">{peopleError}</div> : null}
              <div className="module-card module-card__wide panel panel--highlight">
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
                      key={person.email}
                      type="button"
                      onClick={() => setSelectedEmail(person.email)}
                    >
                      <span>{person.fullName || person.email}</span>
                      <span>{person.email}</span>
                      <span>{person.group}</span>
                      <span>{person.effortScore ?? '—'}</span>
                      <span>{person.eventAttendCount ?? '—'}</span>
                      <span>{person.referralCount ?? '—'}</span>
                      <span>{person.ratingStars || '—'}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="module-card module-card__wide panel">
                <div className="card-header">
                  <div>
                    <h3>Profile details</h3>
                    <p className="muted">
                      Select a person above to view and edit their profile.
                    </p>
                  </div>
                  {selectedEmail ? <div className="pill">{selectedEmail}</div> : null}
                </div>

                {profileError ? <div className="module-alert">{profileError}</div> : null}

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
                      {profileSaving ? 'Saving…' : 'Save profile'}
                    </button>
                  </div>
                </div>
              )}
              </div>
            </div>
          </div>
        </div>
        <div className="section-block">
          <CRMVolunteersTab />
        </div>
      </div>
      )}
      {activeTab === 'furry-friends' && (
        <div className="module-layout">
          <aside className="module-sidebar">
            <div className="sidebar-card sidebar-card--accent">
              <h3>Search filters</h3>
              <form className="stack" onSubmit={handleFurrySearch}>
                <label className="label">Search</label>
                <input
                  className="input"
                  type="text"
                  value={furryQuery}
                  onChange={(event) => setFurryQuery(event.target.value)}
                  placeholder="Search by name, breed, address, or chip"
                />
                <label className="label">Species</label>
                <select
                  className="select"
                  value={furrySpecies}
                  onChange={(event) => setFurrySpecies(event.target.value)}
                >
                  <option value="All">All species</option>
                  <option value="Dog">Dogs</option>
                  <option value="Cat">Cats</option>
                </select>
                <label className="label">Sort</label>
                <select
                  className="select"
                  value={furrySort}
                  onChange={(event) => setFurrySort(event.target.value)}
                >
                  <option value="Name">Sort: Name</option>
                  <option value="Age">Sort: Age</option>
                  <option value="Municipality">Sort: Municipality</option>
                  <option value="Species">Sort: Species</option>
                </select>
                <button className="button" type="submit">
                  {furryLoading ? 'Loading…' : 'Search'}
                </button>
              </form>
            </div>
            <div className="sidebar-card">
              <h3>Furry friends stats</h3>
              <div className="metric-row">
                <span>Results</span>
                <strong>{furryRows.length}</strong>
              </div>
              <div className="metric-row">
                <span>Total animals</span>
                <strong>{furryTotalCount}</strong>
              </div>
              <div className="metric-row">
                <span>Dogs</span>
                <strong>{furryDogCount}</strong>
              </div>
              <div className="metric-row">
                <span>Cats</span>
                <strong>{furryCatCount}</strong>
              </div>
            </div>
          </aside>
          <div className="module-main">
            {furryError ? <div className="module-alert">{furryError}</div> : null}
            <div className="module-card module-card__wide panel">
              <div className="card-header">
                <div>
                  <h3>Furry friends map</h3>
                  <p className="muted">Map of animals with known locations.</p>
                </div>
                <div className="map-legend">
                  <span>
                    <span className="legend-dot legend-dot--dog" />
                    Dogs
                  </span>
                  <span>
                    <span className="legend-dot legend-dot--cat" />
                    Cats
                  </span>
                </div>
              </div>
              <div className="map-canvas">
                <MapContainer
                  center={furryMapCenter}
                  zoom={12}
                  scrollWheelZoom={false}
                  style={{ height: '100%', width: '100%' }}
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  {furryMapRows.map((row) => (
                    <CircleMarker
                      key={row.furryId}
                      center={[Number(row.lat), Number(row.lon)]}
                      radius={8}
                      pathOptions={{
                        color: row.species === 'Cat' ? '#7c3aed' : '#2563eb',
                        fillColor: row.species === 'Cat' ? '#7c3aed' : '#2563eb',
                        fillOpacity: 0.7,
                      }}
                    >
                      <Popup>
                        <strong>{row.name || 'Unknown'}</strong>
                        <div>{row.species || '—'}</div>
                        <div>{row.breed || '—'}</div>
                        <div>{row.address || row.municipality || '—'}</div>
                        <div>Chip: {row.chipNumber || '—'}</div>
                      </Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
              </div>
            </div>

            <div className="module-card module-card__wide panel panel--highlight">
              <div className="card-header">
                <div>
                  <h3>Furry friends directory</h3>
                  <p className="muted">
                    Stray dogs and cats by address.
                  </p>
                </div>
                <div className="pill">Network</div>
              </div>
              <div className="table">
                <div className="table-row table-row--furry table-head">
                  <span>Name</span>
                  <span>Species</span>
                  <span>Gender</span>
                  <span>Age</span>
                  <span>Neutered</span>
                  <span>Breed</span>
                  <span>Address</span>
                  <span>Chip</span>
                </div>
                {furryRows.length === 0 && !furryLoading && (
                  <div className="table-row empty">No records found.</div>
                )}
                {furryRows.map((row) => (
                  <button
                    className="table-row table-row--furry table-row__button"
                    key={row.furryId}
                    type="button"
                    onClick={() => setSelectedFurryId(row.furryId)}
                  >
                    <span>{row.name || '—'}</span>
                    <span>{row.species || '—'}</span>
                    <span>{row.gender || '—'}</span>
                    <span>{row.age ?? '—'}</span>
                    <span>
                      {typeof row.neutered === 'boolean'
                        ? row.neutered
                          ? 'Yes'
                          : 'No'
                        : '—'}
                    </span>
                    <span>{row.breed || '—'}</span>
                    <span>{row.address || row.municipality || '—'}</span>
                    <span>{row.chipNumber || '—'}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="module-card module-card__wide panel">
              <div className="card-header">
                <div>
                  <h3>Import furry friends CSV</h3>
                  <p className="muted">
                    Upload animal data to populate the directory.
                  </p>
                </div>
              </div>
              <div className="stack">
                <input
                  className="input"
                  type="file"
                  accept=".csv"
                  onChange={(event) => {
                    const file = event.target.files?.[0] || null
                    setFurryImportFile(file)
                  }}
                />
                <button className="button" type="button" onClick={handleFurryImport}>
                  Import CSV
                </button>
                {furryImportStatus ? <p className="muted">{furryImportStatus}</p> : null}
                <p className="muted">
                  Expected columns: pet_type, name, gender, age, neutered, breed, color,
                  chip_number, address, municipality (optional), lat, lon, notes.
                </p>
              </div>
            </div>

            <div className="module-card module-card__wide panel">
              <div className="card-header">
                <div>
                  <h3>Furry friends details</h3>
                  <p className="muted">
                    Select a row above to view and edit the record.
                  </p>
                </div>
                {selectedFurryId ? <div className="pill">{selectedFurryId}</div> : null}
              </div>

              {furryProfileError ? <div className="module-alert">{furryProfileError}</div> : null}

              {!selectedFurryId && <p className="muted">No record selected.</p>}

              {selectedFurryId && furryProfileDraft && (
                <div className="profile-grid">
                  <div>
                    <label className="label">Name</label>
                    <input
                      className="input"
                      value={furryProfileDraft.name || ''}
                      onChange={(event) =>
                        updateFurryProfileField('name', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Municipality</label>
                    <input
                      className="input"
                      value={furryProfileDraft.municipality || ''}
                      onChange={(event) =>
                        updateFurryProfileField('municipality', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Species</label>
                    <select
                      className="select"
                      value={furryProfileDraft.species || 'Dog'}
                      onChange={(event) =>
                        updateFurryProfileField('species', event.target.value)
                      }
                    >
                      <option value="Dog">Dog</option>
                      <option value="Cat">Cat</option>
                    </select>
                  </div>
                  <div>
                    <label className="label">Gender</label>
                    <select
                      className="select"
                      value={furryProfileDraft.gender || ''}
                      onChange={(event) =>
                        updateFurryProfileField('gender', event.target.value)
                      }
                    >
                      <option value="">Unspecified</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                    </select>
                  </div>
                  <div>
                    <label className="label">Age</label>
                    <input
                      className="input"
                      type="number"
                      min="0"
                      value={furryProfileDraft.age ?? ''}
                      onChange={(event) =>
                        updateFurryProfileField('age', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Neutered</label>
                    <select
                      className="select"
                      value={
                        typeof furryProfileDraft.neutered === 'boolean'
                          ? furryProfileDraft.neutered
                            ? 'yes'
                            : 'no'
                          : ''
                      }
                      onChange={(event) => {
                        const value = event.target.value
                        updateFurryProfileField(
                          'neutered',
                          value === '' ? null : value === 'yes',
                        )
                      }}
                    >
                      <option value="">Unspecified</option>
                      <option value="yes">Yes</option>
                      <option value="no">No</option>
                    </select>
                  </div>
                  <div>
                    <label className="label">Breed</label>
                    <input
                      className="input"
                      value={furryProfileDraft.breed || ''}
                      onChange={(event) =>
                        updateFurryProfileField('breed', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Color</label>
                    <input
                      className="input"
                      value={furryProfileDraft.color || ''}
                      onChange={(event) =>
                        updateFurryProfileField('color', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Chip number</label>
                    <input
                      className="input"
                      value={furryProfileDraft.chipNumber || ''}
                      onChange={(event) =>
                        updateFurryProfileField('chipNumber', event.target.value)
                      }
                    />
                  </div>
                  <div className="profile-span">
                    <label className="label">Address</label>
                    <input
                      className="input"
                      value={furryProfileDraft.address || ''}
                      onChange={(event) =>
                        updateFurryProfileField('address', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Latitude</label>
                    <input
                      className="input"
                      type="number"
                      value={furryProfileDraft.lat ?? ''}
                      onChange={(event) =>
                        updateFurryProfileField('lat', event.target.value)
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Longitude</label>
                    <input
                      className="input"
                      type="number"
                      value={furryProfileDraft.lon ?? ''}
                      onChange={(event) =>
                        updateFurryProfileField('lon', event.target.value)
                      }
                    />
                  </div>
                  <div className="profile-span">
                    <label className="label">Notes</label>
                    <textarea
                      className="textarea"
                      value={furryProfileDraft.notes || ''}
                      onChange={(event) =>
                        updateFurryProfileField('notes', event.target.value)
                      }
                    />
                  </div>
                  <div className="profile-actions">
                    <button
                      className="button"
                      type="button"
                      onClick={handleFurrySave}
                      disabled={furryProfileSaving}
                    >
                      {furryProfileSaving ? 'Saving…' : 'Save record'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {activeTab === 'tasks' && (
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
                  {tasksLoading ? 'Loading…' : 'Refresh'}
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
                    <span>{task.dueDate || '—'}</span>
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
      {activeTab === 'outreach' && (
        <div className="stack">
          <div className="module-card module-card__wide section-intro">
            <div className="card-header">
              <div>
                <h3>Outreach & Events</h3>
                <p className="muted">
                  Build segments, preview lists, and coordinate outreach or events in one flow.
                </p>
              </div>
              <div className="pill">Network</div>
            </div>
          </div>

          <details className="dashboard-detail" open>
            <summary>1. Build a segment</summary>
            <div className="dashboard-detail__body">
              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>Segment basics</h3>
                    <p className="muted">Save a list you can reuse for outreach.</p>
                  </div>
                  <div className="pill">Network</div>
                </div>

                {segmentsError ? <div className="module-alert">{segmentsError}</div> : null}

                <form className="stack" onSubmit={handleCreateSegment}>
                  <label className="label">Segment name</label>
                  <input
                    className="input"
                    value={segmentName}
                    onChange={(event) => setSegmentName(event.target.value)}
                    placeholder="Active members in Ward 13"
                  />
                  <label className="label">Description</label>
                  <input
                    className="input"
                    value={segmentDescription}
                    onChange={(event) => setSegmentDescription(event.target.value)}
                    placeholder="High commitment supporters for ward outreach"
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
                  </div>

                  <details className="dashboard-detail">
                    <summary>Advanced filters</summary>
                    <div className="dashboard-detail__body">
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
                    </div>
                  </details>

                  <button className="button" type="submit">
                    Save segment
                  </button>
                </form>

                <div className="table">
                  <div className="table-row table-head">
                    <span>Name</span>
                    <span>Description</span>
                    <span>Updated</span>
                    <span />
                  </div>
                  {segments.length === 0 && !segmentsLoading && (
                    <div className="table-row empty">No segments saved.</div>
                  )}
                  {segments.map((segment) => (
                    <div className="table-row" key={segment.segmentId}>
                      <span>{segment.name}</span>
                      <span>{segment.description || '—'}</span>
                      <span>{segment.updatedAt || '—'}</span>
                      <div className="table-actions">
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => {
                            setSegmentSelectedId(segment.segmentId)
                            handleRunSegment(segment.segmentId)
                          }}
                        >
                          Run
                        </button>
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => handleDeleteSegment(segment.segmentId)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </details>

          <details className="dashboard-detail" open>
            <summary>2. Preview & follow-up</summary>
            <div className="dashboard-detail__body">
              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>Segment preview</h3>
                    <p className="muted">Review results before outreach.</p>
                  </div>
                  <div className="pill">Network</div>
                </div>

                <div className="filter-row">
                  <input
                    className="input"
                    type="number"
                    min="10"
                    max="2000"
                    value={segmentLimit}
                    onChange={(event) => setSegmentLimit(event.target.value)}
                    placeholder="Limit"
                  />
                  <button
                    className="button"
                    type="button"
                    onClick={() => handleRunSegment(segmentSelectedId || null)}
                  >
                    {segmentRunLoading ? 'Running…' : 'Run filter'}
                  </button>
                </div>

                <div className="table">
                  <div className="table-row table-head">
                    <span>Name</span>
                    <span>Email</span>
                    <span>Group</span>
                    <span>Effort</span>
                  </div>
                  {segmentResults.length === 0 && !segmentRunLoading && (
                    <div className="table-row empty">No results yet.</div>
                  )}
                  {segmentResults.map((row) => (
                    <div className="table-row" key={row.email}>
                      <span>{row.fullName}</span>
                      <span>{row.email}</span>
                      <span>{row.group}</span>
                      <span>{row.effortHours ?? 0}</span>
                    </div>
                  ))}
                </div>

                <details className="dashboard-detail">
                  <summary>Create tasks for segment</summary>
                  <div className="dashboard-detail__body">
                    {segmentTaskError ? (
                      <div className="module-alert">{segmentTaskError}</div>
                    ) : null}
                    <div className="stack">
                      <input
                        className="input"
                        value={segmentTaskTitle}
                        onChange={(event) => setSegmentTaskTitle(event.target.value)}
                        placeholder="Task title"
                      />
                      <input
                        className="input"
                        value={segmentTaskDescription}
                        onChange={(event) => setSegmentTaskDescription(event.target.value)}
                        placeholder="Notes"
                      />
                      <div className="filter-row">
                        <input
                          className="input"
                          type="date"
                          value={segmentTaskDueDate}
                          onChange={(event) => setSegmentTaskDueDate(event.target.value)}
                        />
                        <select
                          className="select"
                          value={segmentTaskStatus}
                          onChange={(event) => setSegmentTaskStatus(event.target.value)}
                        >
                          <option value="Open">Open</option>
                          <option value="In Progress">In Progress</option>
                          <option value="Done">Done</option>
                          <option value="Cancelled">Cancelled</option>
                        </select>
                      </div>
                      <button
                        className="button"
                        type="button"
                        onClick={handleBulkTasks}
                        disabled={segmentTaskSaving}
                      >
                        {segmentTaskSaving ? 'Creating…' : 'Create tasks'}
                      </button>
                    </div>
                  </div>
                </details>

                <details className="dashboard-detail">
                  <summary>Create event for segment</summary>
                  <div className="dashboard-detail__body">
                    {segmentEventStatusMessage ? (
                      <div className="module-alert">{segmentEventStatusMessage}</div>
                    ) : null}
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
                      <button className="button" type="button" onClick={handleCreateSegmentEvent}>
                        Create event
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
            <summary>3. Individual outreach</summary>
            <div className="dashboard-detail__body">
              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>Individual outreach</h3>
                    <p className="muted">Pick specific people and create tasks.</p>
                  </div>
                  <div className="pill">Network</div>
                </div>

                {individualError ? (
                  <div className="module-alert">{individualError}</div>
                ) : null}

                <form className="filter-row" onSubmit={handleIndividualSearch}>
                  <input
                    className="input"
                    placeholder="Search by name or email"
                    value={individualQuery}
                    onChange={(event) => setIndividualQuery(event.target.value)}
                  />
                  <button className="button" type="submit">
                    {individualLoading ? 'Searching…' : 'Search'}
                  </button>
                </form>

                <div className="table">
                  <div className="table-row table-head">
                    <span>Name</span>
                    <span>Email</span>
                    <span>Group</span>
                    <span>Select</span>
                  </div>
                  {individualResults.length === 0 && !individualLoading && (
                    <div className="table-row empty">No results yet.</div>
                  )}
                  {individualResults.map((row) => (
                    <div className="table-row" key={row.email}>
                      <span>{row.fullName}</span>
                      <span>{row.email}</span>
                      <span>{row.group}</span>
                      <span>
                        <input
                          type="checkbox"
                          checked={individualSelected.includes(row.email)}
                          onChange={() => handleToggleIndividual(row.email)}
                        />
                      </span>
                    </div>
                  ))}
                </div>

                <details className="dashboard-detail">
                  <summary>Create tasks</summary>
                  <div className="dashboard-detail__body">
                    <p className="muted">
                      Use placeholders like {'{fullName}'} and {'{email}'}.
                    </p>
                    <div className="stack">
                      <input
                        className="input"
                        placeholder="Task title template"
                        value={individualTaskTitle}
                        onChange={(event) => setIndividualTaskTitle(event.target.value)}
                      />
                      <input
                        className="input"
                        placeholder="Task notes template"
                        value={individualTaskDescription}
                        onChange={(event) => setIndividualTaskDescription(event.target.value)}
                      />
                      <div className="filter-row">
                        <input
                          className="input"
                          type="date"
                          value={individualTaskDueDate}
                          onChange={(event) => setIndividualTaskDueDate(event.target.value)}
                        />
                        <select
                          className="select"
                          value={individualTaskStatus}
                          onChange={(event) => setIndividualTaskStatus(event.target.value)}
                        >
                          <option value="Open">Open</option>
                          <option value="In Progress">In Progress</option>
                          <option value="Done">Done</option>
                          <option value="Cancelled">Cancelled</option>
                        </select>
                      </div>
                      <button
                        className="button"
                        type="button"
                        onClick={handleIndividualTasks}
                        disabled={individualTaskSaving}
                      >
                        {individualTaskSaving ? 'Creating…' : 'Create tasks'}
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
            <summary>4. WhatsApp groups & messaging</summary>
            <div className="dashboard-detail__body">
              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>WhatsApp groups</h3>
                    <p className="muted">Manage group links and notes.</p>
                  </div>
                  <div className="pill">Outreach</div>
                </div>

                {groupsError ? <div className="module-alert">{groupsError}</div> : null}

                <form className="stack" onSubmit={handleCreateGroup}>
                  <input
                    className="input"
                    value={groupName}
                    onChange={(event) => setGroupName(event.target.value)}
                    placeholder="Group name"
                  />
                  <input
                    className="input"
                    value={groupInvite}
                    onChange={(event) => setGroupInvite(event.target.value)}
                    placeholder="Invite link"
                  />
                  <input
                    className="input"
                    value={groupNotes}
                    onChange={(event) => setGroupNotes(event.target.value)}
                    placeholder="Notes"
                  />
                  <button className="button" type="submit">
                    Save group
                  </button>
                </form>

                <div className="table">
                  <div className="table-row table-row--three table-head">
                    <span>Name</span>
                    <span>Invite link</span>
                    <span />
                  </div>
                  {groups.length === 0 && !groupsLoading && (
                    <div className="table-row table-row--three empty">No groups saved.</div>
                  )}
                  {groups.map((group) => (
                    <div className="table-row table-row--three" key={group.groupId}>
                      <span>{group.name}</span>
                      <span className="muted">{group.inviteLink}</span>
                      <div className="table-actions">
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => handleDeleteGroup(group.groupId)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="module-card">
                <div className="card-header">
                  <div>
                    <h3>Send WhatsApp message</h3>
                    <p className="muted">Send a message to a saved group.</p>
                  </div>
                  <div className="pill">Outreach</div>
                </div>

                {sendError ? <div className="module-alert">{sendError}</div> : null}

                <div className="stack">
                  <select
                    className="select"
                    value={sendGroupId}
                    onChange={(event) => setSendGroupId(event.target.value)}
                  >
                    <option value="">Select group</option>
                    {groups.map((group) => (
                      <option key={group.groupId} value={group.groupId}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                  <textarea
                    className="textarea"
                    value={sendMessage}
                    onChange={(event) => setSendMessage(event.target.value)}
                    placeholder="Message text"
                  />
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={sendAppendInvite}
                      onChange={(event) => setSendAppendInvite(event.target.checked)}
                    />
                    Append invite link
                  </label>
                  <button
                    className="button"
                    type="button"
                    onClick={handleSendMessage}
                    disabled={sendingMessage}
                  >
                    {sendingMessage ? 'Sending…' : 'Send message'}
                  </button>
                </div>
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
            <summary>5. Events</summary>
            <div className="dashboard-detail__body">
              <CRMEventsTab />
            </div>
          </details>
        </div>
      )}
      <div className="module-footer">
        <span>Backend scope:</span>
        <strong>Survey API + /crm routes</strong>
      </div>
    </section>
  )
}

function CRMDataEntryTab() {
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    supporterType: 'Supporter',
    gender: '',
    age: '',
    phone: '',
    address: '',
    lat: '',
    lon: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [importFile, setImportFile] = useState(null)
  const [importType, setImportType] = useState('Supporter')
  const [importStatus, setImportStatus] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

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
          address: form.address.trim(),
          lat: form.lat ? Number(form.lat) : null,
          lon: form.lon ? Number(form.lon) : null,
        },
      })
      setSuccess('Person saved.')
      setForm((prev) => ({ ...prev, email: '', firstName: '', lastName: '' }))
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
      <details className="dashboard-detail">
        <summary>Data entry</summary>
        <div className="dashboard-detail__body">
          <p className="muted">Add supporters and members manually or import them from CSV.</p>
        </div>
      </details>
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
          <button className="button" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save person'}
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

function CRMDashboardTab() {
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    getJson('/crm/dashboard')
      .then((payload) => {
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

  const groupCounts = dashboard?.charts?.groupCounts || []
  const ratingCounts = dashboard?.charts?.ratingCounts || []
  const timeAvailability = dashboard?.charts?.timeAvailability || []
  const topSkills = dashboard?.charts?.skills || []

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
      <div className="module-card module-card__wide section-intro">
        <div className="card-header">
          <div>
            <h3>Stats</h3>
            <p className="muted">Engagement, skills, and activity at a glance.</p>
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
            <h3>Rating</h3>
            {ratingCounts.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <PolarArea
                  data={radialData(ratingCounts, 'rating', 'count')}
                  options={dashboardPolarOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Time availability</h3>
            {timeAvailability.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <PolarArea
                  data={radialData(timeAvailability, 'availability', 'count')}
                  options={dashboardPolarOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Top skills</h3>
            {topSkills.length > 0 ? (
              <div className="chart-frame chart-frame--tall">
                <Bar
                  data={barData(topSkills.slice(0, 8), 'skill', 'count', 'People')}
                  options={dashboardHorizontalBarOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Manifesto</h3>
            {dashboard?.charts?.manifesto?.length ? (
              <div className="chart-frame">
                <Pie
                  data={radialData(dashboard.charts.manifesto, 'agrees', 'count')}
                  options={dashboardPieOptions}
                />
              </div>
            ) : (
              <p className="muted">No data.</p>
            )}
          </div>
          <div className="module-card dashboard-chart">
            <h3>Membership interest</h3>
            {dashboard?.charts?.membership?.length ? (
              <div className="chart-frame">
                <Doughnut
                  data={radialData(dashboard.charts.membership, 'interested', 'count')}
                  options={dashboardPieOptions}
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

function CRMOverviewTab() {
  return (
    <div className="stack">
      <CRMMapTab />
      <CRMDashboardTab />
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
          <p className="muted">Loading volunteers…</p>
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
                <span>{row.ratingStars || row.rating || '—'}</span>
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
    loadCampaignTasks(selectedCampaignId)
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
      setCampaignVolunteerError('Volunteer name is required.')
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
      setCampaignVolunteerStatus('Volunteer added.')
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

  return (
    <div className="module-grid">
      <div className="campaigns-top-grid">
        <div className="module-card campaigns-overview" id="campaigns-overview">
          <h3>Campaign overview</h3>
          <p className="muted">Create campaigns and guide surveys.</p>
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

        <div className="module-card campaigns-create" id="campaigns-create">
          <h3>Create campaign</h3>
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
                setCampaignForm((prev) => ({ ...prev, objective: event.target.value }))
              }
            />
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
            <textarea
              className="textarea"
              placeholder="Legislation or drafted law"
              value={campaignForm.legislationText}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, legislationText: event.target.value }))
              }
            />
            <textarea
              className="textarea"
              placeholder="Freedom Square manifesto statements"
              value={campaignForm.manifestoText}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, manifestoText: event.target.value }))
              }
            />
            <textarea
              className="textarea"
              placeholder="Expert prompt"
              value={campaignForm.expertPrompt}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, expertPrompt: event.target.value }))
              }
            />
          </div>
          <select
            className="select"
            value={campaignForm.status}
            onChange={(event) =>
              setCampaignForm((prev) => ({ ...prev, status: event.target.value }))
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
                setCampaignForm((prev) => ({ ...prev, startDate: event.target.value }))
              }
            />
            <input
              className="input"
              type="date"
              value={campaignForm.endDate}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, endDate: event.target.value }))
              }
            />
          </div>
          <input
            className="input"
            placeholder="Owner"
            value={campaignForm.owner}
            onChange={(event) =>
              setCampaignForm((prev) => ({ ...prev, owner: event.target.value }))
            }
          />
          <input
            className="input"
            placeholder="Target group"
            value={campaignForm.targetGroup}
            onChange={(event) =>
              setCampaignForm((prev) => ({ ...prev, targetGroup: event.target.value }))
            }
          />
          <input
            className="input"
            type="number"
            min="0"
            placeholder="Goal (people)"
            value={campaignForm.goal}
            onChange={(event) =>
              setCampaignForm((prev) => ({ ...prev, goal: event.target.value }))
            }
          />
          <textarea
            className="textarea"
            placeholder="Notes (optional)"
            value={campaignForm.notes}
            onChange={(event) =>
              setCampaignForm((prev) => ({ ...prev, notes: event.target.value }))
            }
          />
          <button className="button" type="submit">
            Create campaign
          </button>
        </form>
        </div>
      </div>

      <div className="module-card module-card__wide" id="campaigns-list">
        <h3>Campaigns</h3>
        {loading ? <p className="muted">Loading…</p> : null}
        <div className="table">
          <div className="table-row table-row--campaigns table-head">
            <span>Name</span>
            <span>Topic</span>
            <span>Status</span>
            <span>Dates</span>
            <span>Owner</span>
            <span>Goal</span>
            <span>Funding</span>
          </div>
          {campaigns.length === 0 && !loading && (
            <div className="table-row empty">No campaigns yet.</div>
          )}
          {campaigns.map((campaign) => {
            const startDate = campaign.startDate || '—'
            const endDate = campaign.endDate || '—'
            return (
              <button
                type="button"
                className="table-row table-row--campaigns table-row__button"
                key={campaign.campaignId}
                onClick={() => setSelectedCampaignId(campaign.campaignId)}
              >
                <span>{campaign.name}</span>
                <span>{campaign.topic || '—'}</span>
                <span>{campaign.status || 'Planned'}</span>
                <span>
                  {startDate} → {endDate}
                </span>
                <span>{campaign.owner || '—'}</span>
                <span>{campaign.goal ?? 0}</span>
                <span>
                  {Number(campaign.fundsRaisedAmount ?? 0).toLocaleString()} /{' '}
                  {Number(campaign.fundingTargetAmount ?? 0).toLocaleString()}{' '}
                  {campaign.currency || 'GEL'}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Campaign workspace</h3>
            <p className="muted">
              Run analysis, launch survey, and review insights.
            </p>
          </div>
          {selectedCampaignId ? <div className="pill">{selectedCampaignId}</div> : null}
        </div>
        {detailError ? <div className="module-alert">{detailError}</div> : null}
        {!selectedCampaignId && <p className="muted">Select a campaign to continue.</p>}
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
                onChange={(event) => handleDraftChange('objective', event.target.value)}
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
            <div className="table-actions">
              <button className="button" type="button" onClick={handleRunAnalysis}>
                Run analysis
              </button>
              <button className="button-secondary" type="button" onClick={handleLaunchDeliberation}>
                Launch survey
              </button>
              <button className="button-secondary" type="button" onClick={handleRefreshInsights}>
                Refresh insights
              </button>
              {conversationLink ? (
                <a className="button-secondary" href={conversationLink} target="_blank" rel="noreferrer">
                  Open questionnaire
                </a>
              ) : null}
            </div>
            {analysisStatus ? <p className="muted">{analysisStatus}</p> : null}
          </div>
        )}
      </div>

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
                      — {contrib.amount} {contrib.currency}{' '}
                      {contrib.paymentStatus ? `(${contrib.paymentStatus})` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

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
                        {milestone.title} — {milestone.status}
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
                      {expense.category} — {expense.amount} {expense.currency}{' '}
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
                {proofError ? <div className="module-alert">{proofError}</div> : null}
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
                        {artifact.artifactType} — {artifact.caption || artifact.url}
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
                        {partner.name} — {partner.role || 'Partner'}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

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
                        {update.createdBy ? ` — ${update.createdBy}` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="module-card">
                <h4>Execution tasks</h4>
                {campaignTaskError ? (
                  <div className="module-alert">{campaignTaskError}</div>
                ) : null}
                {campaignTaskStatus ? (
                  <div className="module-alert">{campaignTaskStatus}</div>
                ) : null}
                <form className="stack" onSubmit={handleCampaignTaskSubmit}>
                  <input
                    className="input"
                    placeholder="Task title"
                    value={campaignTaskForm.title}
                    onChange={(event) =>
                      setCampaignTaskForm((prev) => ({
                        ...prev,
                        title: event.target.value,
                      }))
                    }
                  />
                  <textarea
                    className="textarea"
                    placeholder="Task description"
                    value={campaignTaskForm.description}
                    onChange={(event) =>
                      setCampaignTaskForm((prev) => ({
                        ...prev,
                        description: event.target.value,
                      }))
                    }
                  />
                  <div className="form-grid">
                    <select
                      className="select"
                      value={campaignTaskForm.status}
                      onChange={(event) =>
                        setCampaignTaskForm((prev) => ({
                          ...prev,
                          status: event.target.value,
                        }))
                      }
                    >
                      <option value="Open">Open</option>
                      <option value="In Progress">In Progress</option>
                      <option value="Done">Done</option>
                      <option value="Cancelled">Cancelled</option>
                    </select>
                    <input
                      className="input"
                      type="date"
                      value={campaignTaskForm.dueDate}
                      onChange={(event) =>
                        setCampaignTaskForm((prev) => ({
                          ...prev,
                          dueDate: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="form-grid">
                    <input
                      className="input"
                      placeholder="Assignee email"
                      value={campaignTaskForm.assigneeEmail}
                      onChange={(event) =>
                        setCampaignTaskForm((prev) => ({
                          ...prev,
                          assigneeEmail: event.target.value,
                        }))
                      }
                    />
                    <select
                      className="select"
                      value={campaignTaskForm.milestoneId}
                      onChange={(event) =>
                        setCampaignTaskForm((prev) => ({
                          ...prev,
                          milestoneId: event.target.value,
                        }))
                      }
                    >
                      <option value="">Link to milestone</option>
                      {milestones.map((milestone) => (
                        <option
                          key={`task-${milestone.milestoneId}`}
                          value={milestone.milestoneId}
                        >
                          {milestone.title}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button className="button" type="submit">
                    Create task
                  </button>
                </form>
                {campaignTasks.length === 0 ? (
                  <p className="muted">No tasks yet.</p>
                ) : (
                  <ul className="compact-list">
                    {campaignTasks.slice(0, 5).map((task) => (
                      <li key={task.taskId}>
                        {task.title} — {task.status}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div className="module-grid">
              <div className="module-card">
                <h4>Volunteer roster</h4>
                {campaignVolunteerError ? (
                  <div className="module-alert">{campaignVolunteerError}</div>
                ) : null}
                {campaignVolunteerStatus ? (
                  <div className="module-alert">{campaignVolunteerStatus}</div>
                ) : null}
                <form className="stack" onSubmit={handleCampaignVolunteerSubmit}>
                  <input
                    className="input"
                    placeholder="Volunteer name"
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
                        {volunteer.name} — {volunteer.role || 'Volunteer'}
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
          </div>
        )}
      </div>

      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Consensus vs polarization</h3>
            <p className="muted">Generated statements for survey.</p>
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
              Final statements, sub statements, and actions linked to tasks.
            </p>
          </div>
        </div>
        <div className="stack">
          <input
            className="input"
            placeholder="Assignee email for tasks"
            value={assigneeEmail}
            onChange={(event) => setAssigneeEmail(event.target.value)}
          />
          {taskStatus ? <p className="muted">{taskStatus}</p> : null}
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
              <button
                className="button-secondary"
                type="button"
                onClick={() => handleCreateTasks(statement)}
              >
                Create tasks
              </button>
            </div>
          ))}
        </div>
      </div>

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
              <strong>{report?.metrics?.total_votes ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Participants</span>
              <strong>{report?.metrics?.total_participants ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Clusters</span>
              <strong>{report?.clusters?.length ?? '—'}</strong>
            </div>
          </div>
        ) : null}
      </div>
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
            <h3>Share registration link</h3>
            <p className="muted">Send a public link to a WhatsApp group.</p>
          </div>
        </div>
        {shareError ? <div className="module-alert">{shareError}</div> : null}
        <div className="stack">
          <input className="input" value={publicLink} readOnly />
          <select
            className="select"
            value={shareGroupId}
            onChange={(event) => setShareGroupId(event.target.value)}
          >
            <option value="">Select WhatsApp group</option>
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
            disabled={sendingLink}
          >
            {sendingLink ? 'Sending…' : 'Send link'}
          </button>
        </div>
      </div>

      <div className="module-card module-card__wide">
        <div className="card-header">
          <div>
            <h3>Share to Slack</h3>
            <p className="muted">Send the registration link to #fs.</p>
          </div>
        </div>
        {slackError ? <div className="module-alert">{slackError}</div> : null}
        {slackStatus ? (
          <div className="module-alert module-alert--success">{slackStatus}</div>
        ) : null}
        <div className="stack">
          <input className="input" value={publicLink} readOnly />
          <textarea
            className="textarea"
            value={slackMessage}
            onChange={(event) => setSlackMessage(event.target.value)}
            placeholder="Slack message"
          />
          <button
            className="button"
            type="button"
            onClick={handleSlackShare}
            disabled={sendingSlack}
          >
            {sendingSlack ? 'Sending…' : 'Send to Slack'}
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
              <span>{row.updatedAt || '—'}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function CRMMapTab() {
  const [mapData, setMapData] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const defaultFilters = {
    showSupporters: true,
    showMembers: true,
    genders: [],
    ageGroups: [],
    timeAvailability: [],
    skills: [],
    minEffort: 0,
    minEvents: 0,
    minReferrals: 0,
    addressQuery: '',
    motivationQuery: '',
  }
  const [filters, setFilters] = useState(defaultFilters)
  const normalizeCoord = (value) => {
    const num = Number(value)
    return Number.isFinite(num) ? num : null
  }
  const hasValidCoords = (lat, lon) => {
    if (lat === null || lon === null) return false
    if (Math.abs(lat) < 0.0001 && Math.abs(lon) < 0.0001) return false
    return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
  }
  const normalizedData = useMemo(() => {
    return mapData
      .map((row) => {
        const lat = normalizeCoord(row.lat)
        const lon = normalizeCoord(row.lon)
        return { ...row, lat, lon }
      })
      .filter((row) => hasValidCoords(row.lat, row.lon))
  }, [mapData])

  useEffect(() => {
    setLoading(true)
    getJson('/crm/map')
      .then((payload) => {
        setMapData(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => setError(err.message || 'Unable to load map data.'))
      .finally(() => setLoading(false))
  }, [])

  const genderOptions = useMemo(() => {
    const set = new Set()
    normalizedData.forEach((row) => {
      if (row.gender) set.add(row.gender)
    })
    return Array.from(set)
  }, [normalizedData])

  const ageOptions = useMemo(() => {
    const set = new Set()
    normalizedData.forEach((row) => {
      if (row.ageGroup) set.add(row.ageGroup)
    })
    return Array.from(set)
  }, [normalizedData])

  const timeOptions = useMemo(() => {
    const set = new Set()
    normalizedData.forEach((row) => {
      if (row.timeAvailability && row.timeAvailability !== 'Unspecified') {
        set.add(row.timeAvailability)
      }
    })
    return Array.from(set)
  }, [normalizedData])

  const skillOptions = useMemo(() => {
    const set = new Set()
    normalizedData.forEach((row) => {
      ;(row.skills || []).forEach((skill) => {
        if (skill) set.add(skill)
      })
    })
    return Array.from(set)
  }, [normalizedData])

  const filtered = useMemo(() => {
    return normalizedData.filter((row) => {
      if (!filters.showSupporters && row.group === 'Supporter') return false
      if (!filters.showMembers && row.group === 'Member') return false
      if (filters.genders.length && !filters.genders.includes(row.gender)) return false
      if (filters.ageGroups.length && !filters.ageGroups.includes(row.ageGroup)) return false
      if (
        filters.timeAvailability.length &&
        !filters.timeAvailability.includes(row.timeAvailability)
      )
        return false
      if (
        filters.skills.length &&
        !(row.skills || []).some((skill) => filters.skills.includes(skill))
      )
        return false
      if (filters.minEffort > 0 && Number(row.effortHours || 0) < filters.minEffort)
        return false
      if (
        filters.minEvents > 0 &&
        Number(row.eventAttendCount || 0) < filters.minEvents
      )
        return false
      if (
        filters.minReferrals > 0 &&
        Number(row.referralCount || 0) < filters.minReferrals
      )
        return false
      if (
        filters.addressQuery &&
        !String(row.addressLabel || '')
          .toLowerCase()
          .includes(filters.addressQuery.toLowerCase())
      )
        return false
      if (
        filters.motivationQuery &&
        !String(row.about || '')
          .toLowerCase()
          .includes(filters.motivationQuery.toLowerCase())
      )
        return false
      return true
    })
  }, [normalizedData, filters])

  const center = useMemo(() => {
    if (!filtered.length) return [0, 0]
    const lat = filtered.reduce((sum, row) => sum + Number(row.lat || 0), 0) / filtered.length
    const lon = filtered.reduce((sum, row) => sum + Number(row.lon || 0), 0) / filtered.length
    return [lat, lon]
  }, [filtered])

  const handleResetFilters = () => {
    setFilters(defaultFilters)
  }

  return (
    <div className="module-layout">
      <aside className="module-sidebar">
        {error ? <div className="module-alert">{error}</div> : null}
        <div className="sidebar-card sidebar-card--accent">
          <div className="card-header">
            <div>
              <h3>Map filters</h3>
              <p className="muted">Filter supporters and members shown on the map.</p>
            </div>
          </div>
          <div className="stack">
            <div className="filter-section">
              <div className="filter-section__title">Audience</div>
              <div className="filter-group">
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={filters.showSupporters}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, showSupporters: event.target.checked }))
                    }
                  />
                  Supporters
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={filters.showMembers}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, showMembers: event.target.checked }))
                    }
                  />
                  Members
                </label>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={handleResetFilters}
                >
                  Reset filters
                </button>
              </div>
            </div>

            <details className="filter-section" open>
              <summary>Demographics</summary>
              <div className="filter-group">
                <label className="label">Gender</label>
                <select
                  className="select select--compact"
                  multiple
                  value={filters.genders}
                  onChange={(event) =>
                    setFilters((prev) => ({
                      ...prev,
                      genders: Array.from(event.target.selectedOptions, (opt) => opt.value),
                    }))
                  }
                >
                  {genderOptions.map((gender) => (
                    <option key={gender} value={gender}>
                      {gender}
                    </option>
                  ))}
                </select>
                <label className="label">Age group</label>
                <select
                  className="select select--compact"
                  multiple
                  value={filters.ageGroups}
                  onChange={(event) =>
                    setFilters((prev) => ({
                      ...prev,
                      ageGroups: Array.from(event.target.selectedOptions, (opt) => opt.value),
                    }))
                  }
                >
                  {ageOptions.map((age) => (
                    <option key={age} value={age}>
                      {age}
                    </option>
                  ))}
                </select>
              </div>
            </details>

            <details className="filter-section">
              <summary>Availability & skills</summary>
              <div className="filter-group">
                <label className="label">Time availability</label>
                <select
                  className="select select--compact"
                  multiple
                  value={filters.timeAvailability}
                  onChange={(event) =>
                    setFilters((prev) => ({
                      ...prev,
                      timeAvailability: Array.from(event.target.selectedOptions, (opt) => opt.value),
                    }))
                  }
                >
                  {timeOptions.map((time) => (
                    <option key={time} value={time}>
                      {time}
                    </option>
                  ))}
                </select>
                <label className="label">Skills</label>
                <select
                  className="select select--compact"
                  multiple
                  value={filters.skills}
                  onChange={(event) =>
                    setFilters((prev) => ({
                      ...prev,
                      skills: Array.from(event.target.selectedOptions, (opt) => opt.value),
                    }))
                  }
                >
                  {skillOptions.map((skill) => (
                    <option key={skill} value={skill}>
                      {skill}
                    </option>
                  ))}
                </select>
              </div>
            </details>

            <details className="filter-section">
              <summary>Engagement</summary>
              <div className="filter-group">
                <input
                  className="input input--compact"
                  type="number"
                  placeholder="Min effort"
                  value={filters.minEffort}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, minEffort: Number(event.target.value) }))
                  }
                />
                <input
                  className="input input--compact"
                  type="number"
                  placeholder="Min events"
                  value={filters.minEvents}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, minEvents: Number(event.target.value) }))
                  }
                />
                <input
                  className="input input--compact"
                  type="number"
                  placeholder="Min referrals"
                  value={filters.minReferrals}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, minReferrals: Number(event.target.value) }))
                  }
                />
              </div>
            </details>

            <details className="filter-section">
              <summary>Text filters</summary>
              <div className="filter-group">
                <input
                  className="input input--compact"
                  placeholder="Address contains"
                  value={filters.addressQuery}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, addressQuery: event.target.value }))
                  }
                />
                <input
                  className="input input--compact"
                  placeholder="Motivation contains"
                  value={filters.motivationQuery}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, motivationQuery: event.target.value }))
                  }
                />
              </div>
            </details>
          </div>
        </div>
      </aside>
      <div className="module-main">
        <div className="module-card module-card__wide panel panel--highlight">
        <div className="card-header">
          <div>
            <h3>Map view</h3>
            <p className="muted">{filtered.length} people shown.</p>
          </div>
          <div className="map-legend">
            <span>
              <span className="legend-dot legend-dot--supporter" />
              Supporter
            </span>
            <span>
              <span className="legend-dot legend-dot--member" />
              Member
            </span>
          </div>
        </div>
        {loading ? (
          <p className="muted">Loading map...</p>
        ) : filtered.length === 0 ? (
          <p className="muted">No map points for the selected filters.</p>
        ) : (
          <MapContainer center={center} zoom={11} className="map-canvas">
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {filtered.map((row) => {
              const color = Array.isArray(row.color)
                ? `rgba(${row.color[0]}, ${row.color[1]}, ${row.color[2]}, ${row.color[3] / 255})`
                : '#1d4ed8'
              const addressLabel =
                row.addressLabel && row.addressLabel !== 'Unspecified'
                  ? row.addressLabel
                  : 'Address not available'
              const coordsLabel =
                Number.isFinite(row.lat) && Number.isFinite(row.lon)
                  ? `${row.lat.toFixed(4)}, ${row.lon.toFixed(4)}`
                  : null
              return (
              <CircleMarker
                key={row.email}
                center={[row.lat, row.lon]}
                pathOptions={{ color }}
                radius={Math.max(4, Number(row.pointSize || 6) / 2)}
              >
                <Popup>
                  <strong>{row.fullName}</strong>
                  <div>{row.email}</div>
                  <div>{addressLabel}</div>
                  {coordsLabel ? <div className="muted">Coords: {coordsLabel}</div> : null}
                  <div>{row.skillsLabel}</div>
                </Popup>
              </CircleMarker>
            )})}
          </MapContainer>
        )}
        </div>
        <div className="module-card module-card__wide panel">
        <div className="card-header">
          <div>
            <h3>Filtered people</h3>
            <p className="muted">Results update as filters change.</p>
          </div>
        </div>
        <div className="table table--scroll">
          <div className="table-row table-row--map table-head">
            <span>Name</span>
            <span>Email</span>
            <span>Group</span>
            <span>Age</span>
            <span>Gender</span>
            <span>Time</span>
            <span>Effort</span>
            <span>Events</span>
          </div>
          {filtered.map((row) => (
            <div className="table-row table-row--map" key={row.email}>
              <span>{row.fullName}</span>
              <span>{row.email}</span>
              <span>{row.group}</span>
              <span>{row.ageGroup}</span>
              <span>{row.gender || '—'}</span>
              <span>{row.timeAvailability}</span>
              <span>{row.effortHours ?? 0}</span>
              <span>{row.eventAttendCount ?? 0}</span>
            </div>
          ))}
        </div>
        </div>
      </div>
    </div>
  )
}
