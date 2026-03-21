import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ActionIcon,
  Affix,
  AppShell,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  NavLink,
  Paper,
  Progress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Tooltip,
  Drawer,
  TextInput,
  Textarea,
  useMantineColorScheme,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { Spotlight, spotlight } from '@mantine/spotlight'
import {
  IconArrowRight,
  IconBulb,
  IconChartDots,
  IconLayoutGrid,
  IconMessage2,
  IconMoon,
  IconSearch,
  IconSettings,
  IconShieldCheck,
  IconSpeakerphone,
  IconSun,
  IconTarget,
  IconUsers,
} from '@tabler/icons-react'
import {
  AdminPage,
  AudienceDiscoveryPage,
  CRMPage,
  DataHubPage,
  DeliberationPage,
  DueDiligencePage,
  HowItWorksPage,
  PublicCampaignPage,
} from './modules'
import { API_BASE, getJson, requestJson } from './services/api'
import { LANGUAGES, createTranslator } from './i18n'
import { CivicStatGrid, FormSection, InfoHint, LanguageSelect, PageHeader, StatusMessage } from './ui'
import './App.css'

const normalizeLanguage = (value) => {
  if (!value) return ''
  const normalized = String(value).trim().toLowerCase()
  if (!normalized) return ''
  const exact = LANGUAGES.find((lang) => lang.id.toLowerCase() === normalized)
  if (exact) return exact.id
  const prefix = normalized.split('-')[0]
  const match = LANGUAGES.find((lang) => lang.id.toLowerCase() === prefix)
  return match ? match.id : ''
}

const detectBrowserLanguage = () => {
  if (typeof navigator === 'undefined') return ''
  const candidates = Array.isArray(navigator.languages)
    ? navigator.languages
    : [navigator.language]
  for (const candidate of candidates) {
    const normalized = normalizeLanguage(candidate)
    if (normalized) return normalized
  }
  return ''
}

const getInitialLanguage = () => {
  if (typeof window === 'undefined') return 'en'
  const params = new URLSearchParams(window.location.search)
  const fromUrl = normalizeLanguage(
    params.get('lang') || params.get('language') || params.get('ui_lang'),
  )
  if (fromUrl) return fromUrl
  const stored = normalizeLanguage(localStorage.getItem('fs_lang'))
  if (stored) return stored
  return detectBrowserLanguage() || 'en'
}

const parseStoredList = (value) => {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const parseLocalArray = (value) => {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch (err) {
    return []
  }
}

const shuffleArray = (items) => {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

const buildCommentDeck = (rawComments, votedIds = []) => {
  const votedSet = new Set(votedIds.map((id) => String(id)))
  const seenIds = new Set()
  const normalized = rawComments
    .map((comment, index) => {
      const id =
        comment?.id ||
        comment?.comment_id ||
        comment?.commentId ||
        `comment-${index}`
      const text = String(
        comment?.text || comment?.comment_text || comment?.commentText || '',
      )
        .replace(/\s+/g, ' ')
        .trim()
      if (!text) return null
      const agree = Number(comment?.agree_count || comment?.agreeCount || 0)
      const disagree = Number(comment?.disagree_count || comment?.disagreeCount || 0)
      const pass = Number(comment?.pass_count || comment?.passCount || 0)
      const voteCount = agree + disagree + pass
      const createdAt =
        Date.parse(comment?.created_at || comment?.createdAt || '') || 0
      return {
        id: String(id),
        text,
        voteCount,
        createdAt,
      }
    })
    .filter(Boolean)
    .filter((comment) => {
      if (votedSet.has(comment.id)) return false
      if (seenIds.has(comment.id)) return false
      seenIds.add(comment.id)
      return true
    })

  if (!normalized.length) return []

  const byVoteCount = normalized.reduce((acc, comment) => {
    const key = comment.voteCount
    if (!acc[key]) acc[key] = []
    acc[key].push(comment)
    return acc
  }, {})

  const orderedCounts = Object.keys(byVoteCount)
    .map((value) => Number(value))
    .sort((a, b) => a - b)

  const deck = []
  orderedCounts.forEach((count) => {
    const bucket = byVoteCount[count] || []
    deck.push(...shuffleArray(bucket))
  })

  return deck
}

function App() {
  const params = new URLSearchParams(window.location.search)
  const [language, setLanguage] = useState(getInitialLanguage)
  const t = useMemo(() => createTranslator(language), [language])
  useEffect(() => {
    localStorage.setItem('fs_lang', language)
  }, [language])
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])
  const questionnaire = params.get('questionnaire')
  const conversationId =
    params.get('conversation_id') || params.get('conversation') || ''
  const eventRegistration = params.get('event_registration')
  const eventId = params.get('event_id')
  const campaignPublic = params.get('campaign_public')
  const publicCampaignId = params.get('campaign_id')
  const reportShare = params.get('report_share') || params.get('report')
  const isPublicEvent = eventRegistration === '1' && eventId
  const isPublicCampaign = campaignPublic === '1'
  const isQuestionnaire =
    (questionnaire && questionnaire.startsWith('deliberation')) ||
    (conversationId && params.get('view') === 'mobile')
  const isPublicReport = Boolean(reportShare)
  const isPublicView = isPublicEvent || isQuestionnaire || isPublicCampaign || isPublicReport

  const modules = useMemo(() => {
    const CampaignsModule = (props) => (
      <CRMPage {...props} initialTab="campaigns" hideTabs />
    )
    return [
      {
        id: 'how-it-works',
        label: t('module.howItWorks'),
        description: t('module.howItWorks.desc'),
        Component: HowItWorksPage,
      },
      {
        id: 'crm',
        label: t('module.network'),
        description: t('module.network.desc'),
        Component: CRMPage,
      },
      {
        id: 'campaigns',
        label: t('module.campaigns'),
        description: t('module.campaigns.desc'),
        Component: CampaignsModule,
      },
      {
        id: 'deliberation',
        label: t('module.deliberation'),
        description: t('module.deliberation.desc'),
        Component: DeliberationPage,
      },
      {
        id: 'due-diligence',
        label: t('module.dueDiligence'),
        description: t('module.dueDiligence.desc'),
        Component: DueDiligencePage,
      },
      {
        id: 'audience-discovery',
        label: t('module.audienceDiscovery'),
        description: t('module.audienceDiscovery.desc'),
        Component: AudienceDiscoveryPage,
      },
      {
        id: 'data-hub',
        label: t('module.dataHub'),
        description: t('module.dataHub.desc'),
        Component: DataHubPage,
      },
      {
        id: 'admin',
        label: t('module.settings'),
        description: t('module.settings.desc'),
        Component: AdminPage,
      },
    ]
  }, [t])
  const hubModuleIds = [
    'crm',
    'campaigns',
    'deliberation',
    'due-diligence',
    'audience-discovery',
    'data-hub',
  ]
  const hubModules = useMemo(
    () => modules.filter((module) => hubModuleIds.includes(module.id)),
    [modules],
  )
  const landingQuickModuleIds = ['campaigns', 'deliberation', 'crm']
  const landingQuickModules = useMemo(
    () =>
      landingQuickModuleIds
        .map((moduleId) => modules.find((module) => module.id === moduleId))
        .filter(Boolean),
    [modules],
  )
  const moduleSections = {
    crm: {
      title: 'Network',
      description: 'Manage supporters, outreach, events, and coverage.',
      flowTitle: 'Build the network',
      flowSummary: 'Build, engage, and mobilize in one place.',
      defaultTab: 'overview',
      primaryActions: [
        { label: 'People', type: 'tab', value: 'people', hint: 'Find and update people.' },
        { label: 'Tasks', type: 'tab', value: 'tasks', hint: 'Assign and track work.' },
        { label: 'Events', type: 'tab', value: 'events', hint: 'Plan upcoming events.' },
      ],
      sections: [
        {
          label: 'Overview',
          type: 'tab',
          value: 'overview',
          hint: 'Map, filters, and coverage charts.',
        },
        { label: 'People', type: 'tab', value: 'people', hint: 'Profiles and segments.' },
        { label: 'Tasks', type: 'tab', value: 'tasks', hint: 'Assignments and status.' },
        {
          label: 'Outreach & Events',
          type: 'tab',
          value: 'outreach',
          hint: 'Segments, messaging, and event outreach.',
        },
      ],
    },
    campaigns: {
      title: 'Campaigns',
      description: 'Plan campaigns, launch surveys, and track outcomes.',
      flowTitle: 'Plan',
      flowSummary: 'Plan campaigns, launch surveys, and track outcomes.',
      defaultTab: 'campaigns',
      primaryActions: [
        { label: 'Create campaign', type: 'anchor', value: 'campaigns-create' },
        { label: 'View campaigns', type: 'anchor', value: 'campaigns-list' },
      ],
      sections: [
        { label: 'Overview', type: 'anchor', value: 'campaigns-overview' },
        { label: 'Create', type: 'anchor', value: 'campaigns-create' },
        { label: 'Campaigns', type: 'anchor', value: 'campaigns-list' },
      ],
    },
    deliberation: {
      title: 'Survey & Consensus',
      description: 'Launch surveys, collect votes, and surface consensus.',
      flowTitle: 'Listen to your supporters',
      flowSummary: 'Set up a conversation, share the link, and review insights.',
      defaultTab: 'overview',
      primaryActions: [
        { label: 'Set up', type: 'tab', value: 'setup', hint: 'Create a conversation.' },
        { label: 'Share', type: 'tab', value: 'distribute', hint: 'Share the link.' },
        {
          label: 'Monitoring and Reporting',
          type: 'tab',
          value: 'insights',
          hint: 'Review results.',
        },
      ],
      sections: [
        {
          label: 'Overview',
          type: 'tab',
          value: 'overview',
          hint: 'Quick start and active conversation.',
        },
        { label: 'Set up', type: 'tab', value: 'setup', hint: 'Create and configure.' },
        { label: 'Share', type: 'tab', value: 'distribute', hint: 'Send the link out.' },
        {
          label: 'Monitoring and Reporting',
          type: 'tab',
          value: 'insights',
          hint: 'Consensus analytics.',
        },
        { label: 'Moderate', type: 'tab', value: 'moderation', hint: 'Review comments.' },
      ],
    },
    'due-diligence': {
      title: 'Due Diligence',
      description: 'Investigate subjects and manage watchlists.',
      flowTitle: 'Investigate',
      flowSummary: 'Assess risk, evidence, and watchlists in one flow.',
      defaultTab: 'analysis',
      primaryActions: [
        { label: 'Intake', type: 'tab', value: 'configure', hint: 'Set the subject.' },
        { label: 'Run analysis', type: 'tab', value: 'analysis', hint: 'Generate a report.' },
        { label: 'Watchlist', type: 'tab', value: 'watchlist', hint: 'Track subjects.' },
      ],
      sections: [
        { label: 'Intake', type: 'tab', value: 'configure', hint: 'Set the subject.' },
        { label: 'Enrich', type: 'tab', value: 'analysis', hint: 'Run external sources.' },
        { label: 'Evidence', type: 'tab', value: 'debate-prep', hint: 'Review sources.' },
        { label: 'Report', type: 'tab', value: 'launch', hint: 'Generate outputs.' },
        { label: 'Watchlist', type: 'tab', value: 'watchlist', hint: 'Track subjects.' },
      ],
    },
    'audience-discovery': {
      title: 'Audience Discovery',
      description: 'Turn product pages into segments with evidence.',
      flowTitle: 'Discover',
      flowSummary: 'Turn product pages into segments with evidence.',
      defaultTab: 'overview',
      primaryActions: [
        { label: 'Run discovery', type: 'tab', value: 'overview', hint: 'Add sources and run.' },
        { label: 'Segments', type: 'tab', value: 'segments', hint: 'Review segment drafts.' },
        { label: 'Messaging', type: 'tab', value: 'messaging', hint: 'Messaging ideas.' },
      ],
      sections: [
        { label: 'Discover', type: 'tab', value: 'overview', hint: 'Add sources and run.' },
        { label: 'Claims', type: 'tab', value: 'segments', hint: 'Review segment drafts.' },
        { label: 'Evidence', type: 'tab', value: 'pages', hint: 'Inspect supporting content.' },
        { label: 'Hooks', type: 'tab', value: 'messaging', hint: 'Messaging ideas.' },
        { label: 'Metrics', type: 'tab', value: 'metrics', hint: 'Quality metrics.' },
      ],
    },
    'data-hub': {
      title: 'Data Hub',
      description: 'Explore Neo4j data as a connected graph.',
      flowTitle: 'Explore the graph',
      flowSummary: 'Browse nodes, relationships, and labels from Neo4j.',
      defaultTab: 'explorer',
      primaryActions: [
        { label: 'Explorer', type: 'tab', value: 'explorer', hint: 'Graph and snapshot.' },
        { label: 'Data connectors', type: 'tab', value: 'connectors', hint: 'Stage new data.' },
        { label: 'Nodes', type: 'tab', value: 'nodes', hint: 'Review nodes.' },
        { label: 'Relationships', type: 'tab', value: 'relationships', hint: 'Review edges.' },
      ],
      sections: [
        { label: 'Overview', type: 'tab', value: 'overview', hint: 'Graph summary.' },
        { label: 'Explorer', type: 'tab', value: 'explorer', hint: 'Graph explorer and snapshot.' },
        { label: 'Data connectors', type: 'tab', value: 'connectors', hint: 'Stage data sources.' },
        { label: 'Nodes', type: 'tab', value: 'nodes', hint: 'Browse node details.' },
        {
          label: 'Relationships',
          type: 'tab',
          value: 'relationships',
          hint: 'Browse relationship details.',
        },
      ],
    },
  }
  const getModuleIdFromUrl = () => {
    const search = new URLSearchParams(window.location.search)
    return search.get('module')
  }
  const recentModulesStorageKey = 'fs_recent_modules'
  const [activeModuleId, setActiveModuleId] = useState(() => {
    const fromUrl = getModuleIdFromUrl()
    const match = modules.find((module) => module.id === fromUrl)
    return match?.id || null
  })
  const [recentModuleIds, setRecentModuleIds] = useState(() => {
    if (typeof window === 'undefined') return []
    return parseStoredList(localStorage.getItem(recentModulesStorageKey))
  })
  const activeModule = modules.find((module) => module.id === activeModuleId)
  const ActiveComponent = activeModule?.Component ?? CRMPage
  const recentModules = useMemo(
    () =>
      recentModuleIds
        .map((moduleId) => modules.find((module) => module.id === moduleId))
        .filter(Boolean),
    [modules, recentModuleIds],
  )
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackForm, setFeedbackForm] = useState({
    name: '',
    email: '',
    message: '',
  })
  const [feedbackStatus, setFeedbackStatus] = useState('')
  const [feedbackStatusTone, setFeedbackStatusTone] = useState('info')
  const [feedbackError, setFeedbackError] = useState('')
  const [feedbackSending, setFeedbackSending] = useState(false)
  const initialUrlSync = useRef(true)
  const [moduleTabs, setModuleTabs] = useState({})
  const [navOpened, { toggle: toggleNav, close: closeNav }] = useDisclosure(false)
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()

  const moduleIconMap = {
    'how-it-works': IconBulb,
    crm: IconUsers,
    campaigns: IconSpeakerphone,
    deliberation: IconMessage2,
    'due-diligence': IconShieldCheck,
    'audience-discovery': IconTarget,
    'data-hub': IconChartDots,
    admin: IconSettings,
  }

  const renderModuleIcon = (moduleId, size = 18) => {
    const Icon = moduleIconMap[moduleId] || IconLayoutGrid
    return <Icon size={size} />
  }

  const activeModuleConfig = activeModuleId ? moduleSections[activeModuleId] : null

  const spotlightActions = useMemo(
    () =>
      modules.map((module) => ({
        id: module.id,
        label: module.label,
        description: module.description,
        onClick: () => {
          setActiveModuleId(module.id)
          closeNav()
        },
        leftSection: (
          <ThemeIcon color="civic" variant="light" size="sm">
            {renderModuleIcon(module.id, 14)}
          </ThemeIcon>
        ),
      })),
    [modules, closeNav],
  )

  const hubStats = useMemo(() => {
    const totalSections = Object.values(moduleSections).reduce(
      (sum, entry) => sum + (entry.sections?.length || 0),
      0,
    )
    const hubCoverage = modules.length
      ? Math.round((hubModules.length / modules.length) * 100)
      : 0
    return [
      {
        label: 'Modules ready',
        value: `${hubModules.length}/${modules.length}`,
        icon: renderModuleIcon('crm'),
        badge: 'Live',
        progress: hubCoverage,
      },
      {
        label: 'Navigation sections',
        value: totalSections,
        icon: renderModuleIcon('data-hub'),
        badge: 'Mapped',
      },
      {
        label: 'Workflows',
        value: Object.keys(moduleSections).length,
        icon: renderModuleIcon('how-it-works'),
        note: 'Configured journeys',
      },
      {
        label: 'Public views',
        value: 3,
        icon: renderModuleIcon('campaigns'),
        note: 'Events, campaigns, surveys',
      },
    ]
  }, [hubModules.length, modules.length, moduleSections])

  useEffect(() => {
    if (!activeModuleId) return
    setRecentModuleIds((prev) => {
      const next = [activeModuleId, ...prev.filter((id) => id !== activeModuleId)].slice(
        0,
        3,
      )
      localStorage.setItem(recentModulesStorageKey, JSON.stringify(next))
      return next
    })
  }, [activeModuleId, recentModulesStorageKey])

  useEffect(() => {
    if (isPublicView) return
    const current = getModuleIdFromUrl()
    const nextValue = activeModuleId || ''
    if ((current || '') === nextValue) {
      if (initialUrlSync.current) {
        initialUrlSync.current = false
      }
      return
    }
    const url = new URL(window.location.href)
    if (activeModuleId) {
      url.searchParams.set('module', activeModuleId)
    } else {
      url.searchParams.delete('module')
    }
    if (initialUrlSync.current) {
      window.history.replaceState({}, '', url)
      initialUrlSync.current = false
    } else {
      window.history.pushState({}, '', url)
    }
  }, [activeModuleId, isPublicView])

  useEffect(() => {
    if (isPublicView) return
    const handlePopState = () => {
      const fromUrl = getModuleIdFromUrl()
      const match = modules.find((module) => module.id === fromUrl)
      setActiveModuleId(match?.id || null)
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [modules, isPublicView])

  useEffect(() => {
    if (!activeModuleId) return
    if (moduleTabs[activeModuleId]) return
    const defaults = moduleSections[activeModuleId]?.defaultTab
    if (defaults) {
      setModuleTabs((prev) => ({ ...prev, [activeModuleId]: defaults }))
    }
  }, [activeModuleId, moduleTabs, moduleSections])


  const handleFeedbackSubmit = async (event) => {
    event.preventDefault()
    setFeedbackStatus('')
    setFeedbackStatusTone('info')
    setFeedbackError('')
    if (!feedbackForm.message.trim()) {
      setFeedbackError(t('feedback.errorEmpty'))
      return
    }
    setFeedbackSending(true)
    try {
      const response = await requestJson('/crm/feedback', {
        method: 'POST',
        payload: {
          name: feedbackForm.name.trim(),
          email: feedbackForm.email.trim(),
          message: feedbackForm.message.trim(),
          page: activeModule?.label || 'App',
          channel: 'sidebar_feedback',
        },
      })
      if (response?.email_status === 'sent') {
        setFeedbackStatus(t('feedback.statusSent'))
        setFeedbackStatusTone('success')
      } else if (response?.email_status === 'failed') {
        setFeedbackStatus(t('feedback.statusFailed'))
        setFeedbackStatusTone('error')
      } else if (response?.email_status === 'not_configured') {
        setFeedbackStatus(t('feedback.statusNotConfigured'))
        setFeedbackStatusTone('info')
      } else {
        setFeedbackStatus(t('feedback.statusSaved'))
        setFeedbackStatusTone('success')
      }
      setFeedbackForm({ name: '', email: '', message: '' })
    } catch (err) {
      setFeedbackError(err.message || t('feedback.errorSend'))
    } finally {
      setFeedbackSending(false)
    }
  }

  const handleModuleTabChange = (moduleId, tabValue) => {
    if (!moduleId || !tabValue) return
    setModuleTabs((prev) => ({ ...prev, [moduleId]: tabValue }))
  }

  const scrollToAnchor = (anchorId) => {
    if (!anchorId) return
    const node = document.getElementById(anchorId)
    if (node) {
      node.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const activeSection =
    activeModuleId && moduleTabs[activeModuleId]
      ? (moduleSections[activeModuleId]?.sections || []).find(
          (section) =>
            section.type === 'tab' && section.value === moduleTabs[activeModuleId],
        )
      : null
  const pageTitle = activeSection?.label || activeModule?.label || t('module.network')
  const pageDescription = activeSection?.hint || activeModule?.description
  const pageEyebrow = activeSection ? activeModule?.label : null

  if (isPublicEvent) {
    return (
      <PublicEventRegistration
        eventId={eventId}
        t={t}
        language={language}
        languages={LANGUAGES}
        onLanguageChange={setLanguage}
      />
    )
  }

  if (isPublicCampaign) {
    return (
      <PublicCampaignPage
        campaignId={publicCampaignId}
        t={t}
        language={language}
        languages={LANGUAGES}
        onLanguageChange={setLanguage}
      />
    )
  }

  if (isPublicReport) {
    return (
      <DeliberationPublicReport
        shareId={reportShare}
        t={t}
        language={language}
        languages={LANGUAGES}
        onLanguageChange={setLanguage}
      />
    )
  }

  if (isQuestionnaire) {
    return (
      <DeliberationQuestionnaire
        conversationId={conversationId}
        t={t}
        language={language}
        languages={LANGUAGES}
        onLanguageChange={setLanguage}
      />
    )
  }

  return (
    <AppShell
      padding="md"
      header={{ height: { base: 120, md: 78 } }}
      navbar={{ width: 300, breakpoint: 'md', collapsed: { mobile: !navOpened } }}
      className="app-shell app-shell--sidebar"
    >
      <Spotlight
        actions={spotlightActions}
        searchProps={{ placeholder: 'Search modules and sections...' }}
        nothingFoundMessage="No matches yet"
        highlightQuery
      />
      <AppShell.Header className="app-shell__topbar">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <ActionIcon
              variant="subtle"
              size="lg"
              onClick={toggleNav}
              aria-label="Toggle navigation"
              hiddenFrom="md"
            >
              <IconLayoutGrid size={20} />
            </ActionIcon>
            <Group gap="sm" className="brand" wrap="nowrap">
              <ThemeIcon size="lg" variant="light" color="civic">
                <IconLayoutGrid size={18} />
              </ThemeIcon>
              <div>
                <Text fw={700}>Freedom Square</Text>
                <Text size="xs" c="dimmed">
                  Civic Engagement Suite
                </Text>
              </div>
            </Group>
            <Badge variant="light" color="civic">
              {activeModule ? activeModule.label : 'Module hub'}
            </Badge>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <Tooltip label="Search modules">
              <ActionIcon variant="light" size="lg" onClick={() => spotlight.open()}>
                <IconSearch size={18} />
              </ActionIcon>
            </Tooltip>
            <LanguageSelect
              className="language-select--topbar"
              language={language}
              onLanguageChange={(value) => setLanguage(value)}
              languages={LANGUAGES}
              label={t('language.label')}
              hideLabel
            />
            {activeModule ? (
              <Button variant="light" onClick={() => setActiveModuleId(null)}>
                Back to Modules
              </Button>
            ) : null}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md" className="app-shell__navbar">
        <AppShell.Section grow component={ScrollArea} offsetScrollbars>
          {activeModule ? (
            <Stack gap="md">
              <Paper className="module-view__card">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Flow
                </Text>
                <Text fw={600}>
                  {activeModuleConfig?.flowTitle ||
                    activeModuleConfig?.title ||
                    activeModule?.label}
                </Text>
                <Text size="sm" c="dimmed">
                  {activeModuleConfig?.flowSummary ||
                    activeModuleConfig?.description ||
                    activeModule?.description}
                </Text>
              </Paper>
              <Divider label="Sections" />
              <Stack gap="xs">
                {(activeModuleConfig?.sections || []).map((item) => {
                  const isActive =
                    item.type === 'tab' && moduleTabs[activeModuleId] === item.value
                  return (
                    <NavLink
                      key={`${item.label}-${item.value}`}
                      active={isActive}
                      label={item.label}
                      description={item.hint}
                      onClick={() => {
                        if (item.type === 'tab') {
                          handleModuleTabChange(activeModuleId, item.value)
                        }
                        if (item.type === 'anchor') {
                          scrollToAnchor(item.value)
                        }
                      }}
                      leftSection={
                        <ThemeIcon variant="light" color="civic" size="sm">
                          <IconArrowRight size={14} />
                        </ThemeIcon>
                      }
                      rightSection={item.hint ? <InfoHint text={item.hint} /> : null}
                    />
                  )
                })}
              </Stack>
            </Stack>
          ) : (
            <Stack gap="md">
              {recentModules.length ? (
                <Paper className="module-view__card">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    Recent
                  </Text>
                  <Text fw={600}>Continue where you left off</Text>
                  <Stack gap="xs" mt="sm">
                    {recentModules.map((module) => (
                      <NavLink
                        key={`recent-${module.id}`}
                        label={module.label}
                        description={module.description}
                        onClick={() => {
                          setActiveModuleId(module.id)
                          closeNav()
                        }}
                        leftSection={
                          <ThemeIcon variant="light" color="civic" size="sm">
                            {renderModuleIcon(module.id, 14)}
                          </ThemeIcon>
                        }
                        rightSection={<IconArrowRight size={14} />}
                      />
                    ))}
                  </Stack>
                </Paper>
              ) : null}

              <Paper className="module-view__card">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Find anything
                </Text>
                <Text fw={600}>Search modules and actions</Text>
                <Text size="sm" c="dimmed">
                  Use Spotlight to jump to any workflow.
                </Text>
                <TextInput
                  placeholder="Search (press / or Cmd+K)"
                  leftSection={<IconSearch size={14} />}
                  onFocus={() => spotlight.open()}
                  readOnly
                />
                <Group gap="sm" mt="sm">
                  <Button
                    variant="light"
                    size="xs"
                    onClick={() => {
                      setActiveModuleId('how-it-works')
                      closeNav()
                    }}
                  >
                    Open guide
                  </Button>
                  <Button variant="subtle" size="xs" onClick={() => spotlight.open()}>
                    Open search
                  </Button>
                </Group>
              </Paper>
            </Stack>
          )}
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        {!activeModule ? (
          <Stack gap="lg">
            <div className="module-hub">
              <div className="module-hub__header">
                <h1>Pick a module</h1>
                <p className="muted">Choose where you want to work right now.</p>
              </div>
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
                {hubModules.map((module) => (
                  <Card
                    key={module.id}
                    className="module-tile"
                    onClick={() => setActiveModuleId(module.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setActiveModuleId(module.id)
                      }
                    }}
                  >
                    <Group align="center" gap="sm">
                      <ThemeIcon variant="light" color="civic" size="lg">
                        {renderModuleIcon(module.id, 18)}
                      </ThemeIcon>
                      <div>
                        <Text fw={600}>{module.label}</Text>
                        <Text size="sm" c="dimmed">
                          {module.description}
                        </Text>
                      </div>
                    </Group>
                    <Group justify="flex-end" mt="md">
                      <Button
                        variant="subtle"
                        size="xs"
                        rightSection={<IconArrowRight size={14} />}
                      >
                        Open
                      </Button>
                    </Group>
                  </Card>
                ))}
              </SimpleGrid>
            </div>
          </Stack>
        ) : (
          <div className="module-panel">
            <PageHeader
              className="page-header--hero"
              title={pageTitle}
              description={pageDescription}
              eyebrow={pageEyebrow}
            />
            <ActiveComponent
              t={t}
              language={language}
              activeTabOverride={moduleTabs[activeModuleId]}
              onTabChange={(tabValue) => handleModuleTabChange(activeModuleId, tabValue)}
              activeViewOverride={moduleTabs[activeModuleId]}
              onViewChange={(viewValue) => handleModuleTabChange(activeModuleId, viewValue)}
              showTabs={false}
            />
          </div>
        )}
      </AppShell.Main>
      <Affix position={{ bottom: 24, right: 24 }}>
        <ActionIcon
          size="xl"
          radius="xl"
          variant="filled"
          color="civic"
          onClick={() => setFeedbackOpen((prev) => !prev)}
          aria-label={t('feedback.button')}
        >
          <IconMessage2 size={20} />
        </ActionIcon>
      </Affix>
      <Drawer
        opened={feedbackOpen}
        onClose={() => setFeedbackOpen(false)}
        position="right"
        size="md"
        title={t('feedback.title')}
      >
        <FormSection
          title={t('feedback.title')}
          description="Share what you were trying to do, what happened, and what you expected."
        >
          <form className="stack form-shell" onSubmit={handleFeedbackSubmit} aria-busy={feedbackSending}>
            <Stack>
              <TextInput
                label={t('feedback.name')}
                placeholder="Jane Doe"
                value={feedbackForm.name}
                onChange={(event) =>
                  setFeedbackForm((prev) => ({ ...prev, name: event.target.value }))
                }
              />
              <TextInput
                label={t('feedback.email')}
                placeholder="jane@email.com"
                type="email"
                value={feedbackForm.email}
                onChange={(event) =>
                  setFeedbackForm((prev) => ({ ...prev, email: event.target.value }))
                }
              />
              <Textarea
                label={t('feedback.message')}
                placeholder="Tell us what happened..."
                value={feedbackForm.message}
                onChange={(event) =>
                  setFeedbackForm((prev) => ({ ...prev, message: event.target.value }))
                }
                minRows={5}
                required
              />
              <Group justify="flex-end">
                <Button type="submit" loading={feedbackSending}>
                  {feedbackSending ? t('feedback.sending') : t('feedback.send')}
                </Button>
              </Group>
            </Stack>
            <StatusMessage tone="error" message={feedbackError} />
            <StatusMessage tone={feedbackStatusTone} message={feedbackStatus} />
          </form>
        </FormSection>
      </Drawer>
    </AppShell>
  )
}

function PublicEventRegistration({ eventId, t, language, languages, onLanguageChange }) {
  const translate = t || ((key) => key)
  const [event, setEvent] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    phone: '',
    group: 'Supporter',
    notes: '',
  })
  const [status, setStatus] = useState('')
  const [statusTone, setStatusTone] = useState('info')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    getJson(`/crm/events/detail?event_id=${encodeURIComponent(eventId)}`)
      .then((payload) => setEvent(payload))
      .catch((err) => setError(err.message || translate('event.notFound')))
  }, [eventId])

  const handleSubmit = async (eventAction) => {
    eventAction.preventDefault()
    if (!form.fullName.trim() || !form.email.trim()) {
      setStatus(translate('event.fullNameRequired'))
      setStatusTone('error')
      return
    }
    setStatus('')
    setStatusTone('info')
    setSubmitting(true)
    try {
      const [firstName, ...rest] = form.fullName.trim().split(/\s+/)
      await requestJson(`/crm/events/${eventId}/register`, {
        method: 'POST',
        payload: {
          person: {
            email: form.email.trim(),
            firstName,
            lastName: rest.join(' '),
            phone: form.phone.trim(),
            group: form.group,
          },
          status: 'Registered',
          notes: form.notes.trim(),
        },
      })
      setStatus(translate('event.thanks'))
      setStatusTone('success')
      setForm({
        fullName: '',
        email: '',
        phone: '',
        group: 'Supporter',
        notes: '',
      })
    } catch (err) {
      setStatus(err.message || 'Registration failed.')
      setStatusTone('error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="module">
      <div className="page-language">
        <LanguageSelect
          language={language}
          languages={languages}
          onLanguageChange={onLanguageChange}
          label={translate('language.label')}
        />
      </div>
      <header className="module-header">
        <h2>{event?.name || translate('event.registrationTitle')}</h2>
        {event?.startDate ? <p>{event.startDate}</p> : null}
      </header>
      <StatusMessage tone="error" message={error} />
      {event ? (
        <form
          className="module-card module-card__wide form-shell"
          onSubmit={handleSubmit}
          aria-busy={submitting}
        >
          <FormSection
            title="Attendee details"
            description="Required fields are marked. Confirmation shows here after you submit."
          >
            <div className="form-grid">
              <Field
                id="event-full-name"
                label={translate('event.fullName')}
                helper="Required. Enter first and last name."
                required
              >
                <TextInput
                  placeholder="Aisha Khan"
                  value={form.fullName}
                  onChange={(evt) => setForm((prev) => ({ ...prev, fullName: evt.target.value }))}
                  required
                />
              </Field>
              <Field
                id="event-email"
                label={translate('event.email')}
                helper="Required. We'll email a confirmation."
                required
              >
                <TextInput
                  type="email"
                  placeholder="aisha@email.com"
                  value={form.email}
                  onChange={(evt) => setForm((prev) => ({ ...prev, email: evt.target.value }))}
                  required
                />
              </Field>
              <Field
                id="event-phone"
                label={translate('event.phone')}
                helper="Optional. Include for reminders."
              >
                <TextInput
                  placeholder="+995 555 123 456"
                  value={form.phone}
                  onChange={(evt) => setForm((prev) => ({ ...prev, phone: evt.target.value }))}
                />
              </Field>
            </div>
          </FormSection>
          <FormSection
            title="Registration details"
            description="Optional details to help the organizers prepare."
          >
            <div className="form-grid">
              <Field id="event-group" label="Group" helper="Select the attendee type.">
                <Select
                  value={form.group}
                  onChange={(value) => setForm((prev) => ({ ...prev, group: value || '' }))}
                  data={[
                    { value: 'Supporter', label: translate('event.groupSupporter') },
                    { value: 'Member', label: translate('event.groupMember') },
                  ]}
                />
              </Field>
              <Field id="event-notes" label={translate('event.notes')} helper="Optional notes">
                <Textarea
                  placeholder="Accessibility needs, questions, or context..."
                  value={form.notes}
                  onChange={(evt) => setForm((prev) => ({ ...prev, notes: evt.target.value }))}
                  minRows={4}
                />
              </Field>
            </div>
          </FormSection>
          <div className="form-actions">
            <Button type="submit" loading={submitting}>
              {submitting ? 'Submitting...' : translate('event.register')}
            </Button>
          </div>
          <StatusMessage tone={statusTone} message={status} />
        </form>
      ) : null}
    </section>
  )
}

function DeliberationQuestionnaire({
  conversationId,
  t,
  language,
  languages,
  onLanguageChange,
}) {
  const translate = t || ((key, vars) => key)
  const [error, setError] = useState('')
  const [comments, setComments] = useState([])
  const [commentText, setCommentText] = useState('')
  const [loading, setLoading] = useState(false)
  const [queueLoading, setQueueLoading] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [pendingVote, setPendingVote] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [conversation, setConversation] = useState(null)
  const [votedIds, setVotedIds] = useState([])
  const [seenIds, setSeenIds] = useState([])
  const [importantFlag, setImportantFlag] = useState(false)
  const [completedSent, setCompletedSent] = useState(false)
  const dragStartRef = useRef(null)
  const dragTypeRef = useRef(null)
  const dragPointerIdRef = useRef(null)
  const supportsPointerEvents =
    typeof window !== 'undefined' && typeof window.PointerEvent !== 'undefined'

  const params = new URLSearchParams(window.location.search)
  const sid = params.get('sid') || ''
  const inviteCode = params.get('invite') || ''
  const xid = params.get('xid') || params.get('participant_id') || ''
  const viewMode = params.get('view') || ''
  const isEmbed = viewMode === 'embed'
  const participantStorageKey = `delib_anon_id_${conversationId || 'default'}_${sid || 'default'}`
  const participantRef = useRef(
    xid || localStorage.getItem(participantStorageKey) || `${Date.now()}_${Math.random()}`,
  )
  const participantId = participantRef.current
  const voteStorageKey = useMemo(
    () => `delib_votes_${conversationId || 'default'}_${participantId}`,
    [conversationId, participantId],
  )
  const requestHeaders = useMemo(
    () => ({
      'X-Participant-Id': participantId,
      'X-Invite-Code': inviteCode,
    }),
    [inviteCode, participantId],
  )

  const loadQueue = useCallback(
    async ({ reset = false, extraVotedIds = [] } = {}) => {
      if (!conversationId) return
      setQueueLoading(true)
      setError('')
      try {
        const payload = {
          seen_ids: reset ? [] : seenIds,
          voted_ids: [...votedIds, ...extraVotedIds],
          limit: 50,
        }
        const response = await requestJson(`/conversations/${conversationId}/queue`, {
          method: 'POST',
          payload,
          headers: requestHeaders,
        })
        const items = Array.isArray(response?.items) ? response.items : []
        setComments(items)
        setCurrentIndex(0)
        const nextSeen = items.map((item) => item.id)
        setSeenIds((prev) =>
          Array.from(new Set([...(reset ? [] : prev), ...nextSeen])),
        )
      } catch (err) {
        setError(err.message || translate('questionnaire.loadingBody'))
      } finally {
        setQueueLoading(false)
      }
    },
    [conversationId, requestHeaders, seenIds, translate, votedIds],
  )

  useEffect(() => {
    if (!conversationId) return
    setLoading(true)
    setError('')
    localStorage.setItem(participantStorageKey, participantId)
    const storedVotes = parseLocalArray(localStorage.getItem(voteStorageKey))
    setVotedIds(storedVotes)
    setSeenIds([])
    Promise.all([getJson(`/conversations/${conversationId}`)])
      .then(([convoPayload]) => {
        setConversation(convoPayload)
        setCurrentIndex(0)
        setDragOffset({ x: 0, y: 0 })
        setIsDragging(false)
        setCompletedSent(false)
        loadQueue({ reset: true })
        requestJson(`/conversations/${conversationId}/view`, {
          method: 'POST',
          headers: requestHeaders,
        }).catch(() => null)
      })
      .catch((err) =>
        setError(err.message || 'Unable to load conversation comments.'),
      )
      .finally(() => setLoading(false))
  }, [
    conversationId,
    participantId,
    participantStorageKey,
    voteStorageKey,
    loadQueue,
    requestHeaders,
  ])

  useEffect(() => {
    if (!conversationId) return
    localStorage.setItem(voteStorageKey, JSON.stringify(votedIds))
  }, [conversationId, voteStorageKey, votedIds])

  const currentComment = comments[currentIndex]
  const currentCommentId = currentComment?.id
  const currentText = currentComment?.text || ''
  const identityRequired = conversation?.identity_mode === 'xid_required' && !xid
  const votingDisabled =
    (conversation && conversation.allow_voting === false) || identityRequired
  const totalComments = comments.length + votedIds.length
  const progressCount = votedIds.length
  const progress = totalComments
    ? Math.min(100, Math.round((progressCount / totalComments) * 100))
    : 0
  const swipeHintThreshold = 40
  const swipeIntent =
    dragOffset.x > swipeHintThreshold
      ? 'agree'
      : dragOffset.x < -swipeHintThreshold
        ? 'disagree'
        : dragOffset.y > swipeHintThreshold
          ? 'pass'
          : ''

  const handleVote = useCallback(async (commentId, choice) => {
    if (!commentId || pendingVote || votingDisabled) return
    setPendingVote(true)
    setError('')
    try {
      await requestJson('/vote', {
        method: 'POST',
        payload: {
          conversation_id: conversationId,
          comment_id: commentId,
          choice,
          important: importantFlag,
        },
        headers: requestHeaders,
      })
      setVotedIds((prev) => {
        if (prev.includes(commentId)) return prev
        return [...prev, commentId]
      })
      setComments((prev) => prev.filter((comment) => comment.id !== commentId))
      setCurrentIndex(0)
      setImportantFlag(false)
      setSeenIds((prev) => Array.from(new Set([...prev, commentId])))
      emitEmbedEvent('vote_cast', { comment_id: commentId, choice, important: importantFlag })
      if (comments.length <= 3) {
        loadQueue({ extraVotedIds: [commentId] })
      }
    } catch (err) {
      setError(err.message || translate('questionnaire.voteFailed'))
    } finally {
      setPendingVote(false)
    }
  }, [
    comments.length,
    conversationId,
    emitEmbedEvent,
    importantFlag,
    loadQueue,
    pendingVote,
    requestHeaders,
    translate,
    votingDisabled,
  ])

  const handleSubmit = async () => {
    if (!commentText.trim()) {
      setError(translate('questionnaire.commentEmpty'))
      return
    }
    if (conversation && !conversation.allow_comment_submission) {
      setError(translate('questionnaire.commentDisabled'))
      return
    }
    try {
      const text = commentText.trim()
      await requestJson(`/conversations/${conversationId}/comments`, {
        method: 'POST',
        payload: { text },
        headers: requestHeaders,
      })
      setCommentText('')
      emitEmbedEvent('comment_submitted', { text })
      loadQueue()
    } catch (err) {
      setError(err.message || 'Comment failed.')
    }
  }

  const emitEmbedEvent = useCallback(
    (event, payload = {}) => {
      if (typeof window === 'undefined') return
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(
          {
            type: 'fs_survey_event',
            event,
            conversation_id: conversationId,
            participant_id: participantId,
            ...payload,
          },
          '*',
        )
      }
    },
    [conversationId, participantId],
  )

  useEffect(() => {
    if (!conversationId) return
    emitEmbedEvent('view', { invite: inviteCode || null })
  }, [conversationId, emitEmbedEvent, inviteCode])

  useEffect(() => {
    if (completedSent) return
    if (!currentCommentId && !loading && !queueLoading) {
      emitEmbedEvent('completed_all')
      setCompletedSent(true)
    }
  }, [completedSent, currentCommentId, emitEmbedEvent, loading, queueLoading])

  const resetDrag = () => {
    setDragOffset({ x: 0, y: 0 })
    setIsDragging(false)
    dragStartRef.current = null
    dragTypeRef.current = null
    dragPointerIdRef.current = null
  }

  useEffect(() => {
    resetDrag()
  }, [currentCommentId])

  useEffect(() => {
    if (!currentCommentId) return
    const handleKeyDown = (event) => {
      if (pendingVote) return
      const key = event.key
      if (key === 'ArrowRight' || key === 'd' || key === 'D') {
        event.preventDefault()
        handleVote(currentCommentId, 1)
      } else if (key === 'ArrowLeft' || key === 'a' || key === 'A') {
        event.preventDefault()
        handleVote(currentCommentId, -1)
      } else if (key === 'ArrowDown' || key === 's' || key === 'S') {
        event.preventDefault()
        handleVote(currentCommentId, 0)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentCommentId, handleVote, pendingVote])

  const beginDrag = useCallback(
    (clientX, clientY, type, pointerId = null) => {
      if (pendingVote || !currentCommentId) return
      dragStartRef.current = { x: clientX, y: clientY }
      dragTypeRef.current = type
      dragPointerIdRef.current = pointerId
      setDragOffset({ x: 0, y: 0 })
      setIsDragging(true)
    },
    [currentCommentId, pendingVote],
  )

  const updateDrag = useCallback((clientX, clientY, type, pointerId = null) => {
    if (!dragStartRef.current || dragTypeRef.current !== type) return
    if (type === 'pointer' && dragPointerIdRef.current !== pointerId) return
    setDragOffset({
      x: clientX - dragStartRef.current.x,
      y: clientY - dragStartRef.current.y,
    })
  }, [])

  const endDrag = useCallback(
    (clientX, clientY, type, pointerId = null) => {
      if (!dragStartRef.current || dragTypeRef.current !== type) return
      if (type === 'pointer' && dragPointerIdRef.current !== pointerId) return
      const start = dragStartRef.current
      const endX =
        typeof clientX === 'number' ? clientX : start.x + dragOffset.x
      const endY =
        typeof clientY === 'number' ? clientY : start.y + dragOffset.y
      const x = endX - start.x
      const y = endY - start.y
      const threshold = 70
      const choice =
        x > threshold ? 1 : x < -threshold ? -1 : y > threshold ? 0 : null
      resetDrag()
      if (choice !== null) {
        handleVote(currentCommentId, choice)
      }
    },
    [currentCommentId, dragOffset.x, dragOffset.y, handleVote],
  )

  const handlePointerDown = (event) => {
    if (votingDisabled) return
    if (event.button !== undefined && event.button !== 0) return
    beginDrag(event.clientX, event.clientY, 'pointer', event.pointerId)
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch (err) {
      // Pointer capture isn't supported in all environments.
    }
  }

  const handlePointerMove = (event) => {
    updateDrag(event.clientX, event.clientY, 'pointer', event.pointerId)
  }

  const handlePointerEnd = (event) => {
    endDrag(event?.clientX, event?.clientY, 'pointer', event?.pointerId)
  }

  const handleTouchStart = (event) => {
    if (supportsPointerEvents) return
    if (votingDisabled) return
    const touch = event.touches?.[0]
    if (!touch) return
    beginDrag(touch.clientX, touch.clientY, 'touch')
  }

  const handleTouchMove = (event) => {
    if (supportsPointerEvents) return
    const touch = event.touches?.[0]
    if (!touch) return
    updateDrag(touch.clientX, touch.clientY, 'touch')
  }

  const handleTouchEnd = (event) => {
    if (supportsPointerEvents) return
    const touch = event.changedTouches?.[0]
    endDrag(touch?.clientX, touch?.clientY, 'touch')
  }

  const handleMouseDown = (event) => {
    if (supportsPointerEvents) return
    if (votingDisabled) return
    if (event.button !== 0) return
    beginDrag(event.clientX, event.clientY, 'mouse')
  }

  const handleMouseMove = (event) => {
    if (supportsPointerEvents) return
    updateDrag(event.clientX, event.clientY, 'mouse')
  }

  const handleMouseUp = (event) => {
    if (supportsPointerEvents) return
    endDrag(event.clientX, event.clientY, 'mouse')
  }

  return (
    <section className={`delib-questionnaire ${isEmbed ? 'delib-questionnaire--embed' : ''}`}>
      {!isEmbed ? (
        <div className="page-language page-language--questionnaire">
          <LanguageSelect
            language={language}
            languages={languages}
            onLanguageChange={onLanguageChange}
            label={translate('language.label')}
          />
        </div>
      ) : null}
      {!isEmbed ? (
        <header className="delib-questionnaire__header">
          <span className="pill">{translate('module.deliberation')}</span>
          <h2>{translate('questionnaire.title')}</h2>
          <p>{translate('questionnaire.subtitle')}</p>
        </header>
      ) : null}
      <Progress value={progress} size="lg" radius="xl" color="civic" mb="md" />
      {error ? <div className="module-alert">{error}</div> : null}
      <div className="questionnaire-progress">
        <div className="questionnaire-progress__track">
          <div className="questionnaire-progress__bar" style={{ width: `${progress}%` }} />
        </div>
        <span className="questionnaire-progress__label">
          {progressCount}/{totalComments || 0}
        </span>
      </div>
      <div className="questionnaire-deck">
        <div className="questionnaire-card-stack">
          {currentIndex + 1 < totalComments && (
            <div className="questionnaire-card questionnaire-card--back" aria-hidden="true" />
          )}
          {loading || queueLoading ? (
            <div className="questionnaire-card questionnaire-card--empty">
                    <h3>{translate('questionnaire.loadingTitle')}</h3>
                    <p className="muted">{translate('questionnaire.loadingBody')}</p>
            </div>
          ) : currentComment ? (
            <div
              className={`questionnaire-card ${isDragging ? 'is-dragging' : ''}`}
              style={{
                transform: `translate(${dragOffset.x}px, ${dragOffset.y}px) rotate(${
                  dragOffset.x / 18
                }deg)`,
              }}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerEnd}
              onPointerCancel={handlePointerEnd}
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleTouchEnd}
              onTouchCancel={handleTouchEnd}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
                    <div className="questionnaire-card__title">
                      {translate('questionnaire.questionLabel', {
                        current: progressCount + 1,
                        total: totalComments,
                      })}
                    </div>
              <div className="questionnaire-card__text">{currentText}</div>
              <div className="questionnaire-card__footer">
                      {translate('questionnaire.footer')}
              </div>
              {swipeIntent ? (
                <div className={`questionnaire-swipe-hint questionnaire-swipe-hint--${swipeIntent}`}>
                  {swipeIntent === 'agree'
                          ? `✅ ${translate('questionnaire.agree')}`
                    : swipeIntent === 'disagree'
                            ? `❌ ${translate('questionnaire.disagree')}`
                            : translate('questionnaire.pass')}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="questionnaire-card questionnaire-card--empty">
                    <h3>{translate('questionnaire.doneTitle')}</h3>
                    <p className="muted">{translate('questionnaire.doneBody')}</p>
            </div>
          )}
        </div>
      </div>
      {identityRequired ? (
        <p className="muted">Login is required to vote in this conversation.</p>
      ) : null}
      <div className="questionnaire-importance">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={importantFlag}
            onChange={(event) => setImportantFlag(event.target.checked)}
            disabled={!currentCommentId || pendingVote || votingDisabled}
          />
          This is important to me
        </label>
      </div>
      <div className="questionnaire-controls">
        <button
          className="swipe-button swipe-button--disagree"
          type="button"
          onClick={() => handleVote(currentCommentId, -1)}
          disabled={!currentCommentId || pendingVote || votingDisabled}
        >
                  {translate('questionnaire.disagree')}
        </button>
        <button
          className="swipe-button swipe-button--pass"
          type="button"
          onClick={() => handleVote(currentCommentId, 0)}
          disabled={!currentCommentId || pendingVote || votingDisabled}
        >
                  {translate('questionnaire.pass')}
        </button>
        <button
          className="swipe-button swipe-button--agree"
          type="button"
          onClick={() => handleVote(currentCommentId, 1)}
          disabled={!currentCommentId || pendingVote || votingDisabled}
        >
                  {translate('questionnaire.agree')}
        </button>
      </div>
      {identityRequired ? (
        <p className="muted">Login is required to submit comments.</p>
      ) : conversation?.allow_comment_submission ? (
        <div className="questionnaire-add">
          <div className="card-divider">
                    <h4>{translate('questionnaire.addComment')}</h4>
          </div>
          <textarea
            className="textarea"
            value={commentText}
            onChange={(evt) => setCommentText(evt.target.value)}
          />
          <button className="button" type="button" onClick={handleSubmit}>
                    {translate('questionnaire.submitComment')}
          </button>
        </div>
      ) : (
                <p className="muted">{translate('questionnaire.commentDisabled')}</p>
      )}
    </section>
  )
}


function DeliberationPublicReport({ shareId, t, language, languages, onLanguageChange }) {
  const translate = t || ((key) => key)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!shareId) return
    setLoading(true)
    setError('')
    getJson(`/reports/public/${shareId}`)
      .then((payload) => {
        setReport(payload?.payload || null)
      })
      .catch((err) => setError(err.message || 'Unable to load report.'))
      .finally(() => setLoading(false))
  }, [shareId])

  const consensus = report?.metrics?.consensus || []
  const polarizing = report?.metrics?.polarizing || []

  return (
    <section className="public-report">
      <div className="page-language page-language--questionnaire">
        <LanguageSelect
          language={language}
          languages={languages}
          onLanguageChange={onLanguageChange}
          label={translate('language.label')}
        />
      </div>
      <header className="public-report__header">
        <span className="pill">Public report</span>
        <h2>{report?.name || 'Survey summary'}</h2>
        <p>{report?.generated_at ? `Generated on ${report.generated_at}` : null}</p>
      </header>
      {loading ? (
        <div className="questionnaire-card questionnaire-card--empty">
          <h3>{translate('questionnaire.loadingTitle')}</h3>
          <p className="muted">{translate('questionnaire.loadingBody')}</p>
        </div>
      ) : null}
      {error ? <div className="module-alert">{error}</div> : null}
      {report ? (
        <div className="stack report-stack">
          <div className="report-metrics">
            <div className="report-metric">
              <span>Views</span>
              <strong>{report?.stats?.views ?? 0}</strong>
              <span className="muted">Survey page visits</span>
            </div>
            <div className="report-metric">
              <span>Voters</span>
              <strong>{report?.stats?.voters ?? 0}</strong>
              <span className="muted">Participants who voted</span>
            </div>
            <div className="report-metric">
              <span>Commenters</span>
              <strong>{report?.stats?.commenters ?? 0}</strong>
              <span className="muted">Unique comment authors</span>
            </div>
            <div className="report-metric">
              <span>Votes per voter</span>
              <strong>{report?.stats?.votes_per_participant ?? 0}</strong>
              <span className="muted">Average depth</span>
            </div>
          </div>
          <div className="report-grid">
            <div className="module-card report-card">
              <h4>Consensus statements</h4>
              {consensus.length ? (
                <ul className="report-list">
                  {consensus.slice(0, 5).map((item) => (
                    <li key={item.id}>{item.text}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No consensus statements yet.</p>
              )}
            </div>
            <div className="module-card report-card">
              <h4>Polarizing statements</h4>
              {polarizing.length ? (
                <ul className="report-list">
                  {polarizing.slice(0, 5).map((item) => (
                    <li key={item.id}>{item.text}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No polarizing statements yet.</p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

export default App
