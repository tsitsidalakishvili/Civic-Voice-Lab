import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ActionIcon,
  Affix,
  AppShell,
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Tooltip,
  Menu,
  useMantineColorScheme,
} from '@mantine/core'
import { Spotlight, spotlight } from '@mantine/spotlight'
import {
  IconArrowRight,
  IconBulb,
  IconLanguage,
  IconLayoutGrid,
  IconMessage2,
  IconSearch,
} from '@tabler/icons-react'
import { AppProvider, useApp } from './context/AppContext'
import { buildModules, HUB_MODULE_IDS, MODULE_SECTIONS, renderModuleIcon } from './config/modules'
import { FeedbackDrawer } from './components/FeedbackDrawer'
import { PublicEventRegistration } from './views/PublicEventRegistration'
import { PublicSupporterSignup } from './views/PublicSupporterSignup'
import { DeliberationQuestionnaire } from './views/DeliberationQuestionnaire'
import { DeliberationPublicReport } from './views/DeliberationPublicReport'
import { PublicCampaignPage } from './modules'
import { parseStoredList } from './utils/deck'
import { PageHeader } from './ui'
import './App.css'

function AppShell_() {
  const { language, setLanguage, t, languages } = useApp()
  const params = new URLSearchParams(window.location.search)

  const questionnaire = params.get('questionnaire')
  const conversationId = params.get('conversation_id') || params.get('conversation') || ''
  const viewParam = params.get('view') || ''
  const eventRegistration = params.get('event_registration')
  const eventId = params.get('event_id')
  const campaignPublic = params.get('campaign_public')
  const publicCampaignId = params.get('campaign_id')
  const reportShare = params.get('report_share') || params.get('report')
  const supporterSignup = params.get('supporter_signup')
  const supporterInviteCode = params.get('invite_code') || ''

  const isPublicEvent = eventRegistration === '1' && eventId
  const isPublicCampaign = campaignPublic === '1'
  const isSupporterSignup = supporterSignup === '1'
  const isQuestionnaireView = ['mobile', 'participant', 'embed', 'admin'].includes(viewParam)
  const isQuestionnaire =
    (questionnaire && questionnaire.startsWith('deliberation')) ||
    (conversationId && isQuestionnaireView)
  const isPublicReport = Boolean(reportShare)
  const isPublicView =
    isPublicEvent || isQuestionnaire || isPublicCampaign || isPublicReport || isSupporterSignup

  const modules = useMemo(() => buildModules(t), [t])
  const hubModules = useMemo(
    () => modules.filter((m) => HUB_MODULE_IDS.includes(m.id)),
    [modules],
  )

  const recentModulesStorageKey = 'fs_recent_modules'
  const [activeModuleId, setActiveModuleId] = useState(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('module')
    return modules.find((m) => m.id === fromUrl)?.id || null
  })
  const [recentModuleIds, setRecentModuleIds] = useState(() =>
    parseStoredList(localStorage.getItem(recentModulesStorageKey)),
  )
  const [moduleTabs, setModuleTabs] = useState({})
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const initialUrlSync = useRef(true)
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()

  const activeModule = modules.find((m) => m.id === activeModuleId)
  const ActiveComponent = activeModule?.Component

  const spotlightActions = useMemo(
    () =>
      modules.map((m) => ({
        id: m.id,
        label: m.label,
        description: m.description,
        onClick: () => setActiveModuleId(m.id),
        leftSection: (
          <ThemeIcon color="civic" variant="light" size="sm">
            {renderModuleIcon(m.id, 14)}
          </ThemeIcon>
        ),
      })),
    [modules],
  )

  useEffect(() => {
    if (!activeModuleId) return
    setRecentModuleIds((prev) => {
      const next = [activeModuleId, ...prev.filter((id) => id !== activeModuleId)].slice(0, 3)
      localStorage.setItem(recentModulesStorageKey, JSON.stringify(next))
      return next
    })
  }, [activeModuleId])

  useEffect(() => {
    if (isPublicView) return
    const current = new URLSearchParams(window.location.search).get('module') || ''
    const next = activeModuleId || ''
    if (current === next) {
      initialUrlSync.current = false
      return
    }
    const url = new URL(window.location.href)
    if (activeModuleId) url.searchParams.set('module', activeModuleId)
    else url.searchParams.delete('module')
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
      const fromUrl = new URLSearchParams(window.location.search).get('module')
      setActiveModuleId(modules.find((m) => m.id === fromUrl)?.id || null)
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [modules, isPublicView])

  useEffect(() => {
    if (!activeModuleId || moduleTabs[activeModuleId]) return
    const defaultTab = MODULE_SECTIONS[activeModuleId]?.defaultTab
    if (defaultTab) setModuleTabs((prev) => ({ ...prev, [activeModuleId]: defaultTab }))
  }, [activeModuleId, moduleTabs])

  const handleModuleTabChange = (moduleId, tabValue) => {
    if (!moduleId || !tabValue) return
    setModuleTabs((prev) => ({ ...prev, [moduleId]: tabValue }))
  }

  const scrollToAnchor = (anchorId) => {
    if (!anchorId) return
    document.getElementById(anchorId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleModuleNavigation = (moduleId, entry) => {
    if (!entry) return
    if (entry.type === 'tab') handleModuleTabChange(moduleId, entry.value)
    else if (entry.type === 'anchor') scrollToAnchor(entry.value)
  }

  const activeModuleConfig = activeModuleId ? MODULE_SECTIONS[activeModuleId] : null
  const activeSection =
    activeModuleId && moduleTabs[activeModuleId]
      ? (MODULE_SECTIONS[activeModuleId]?.sections || []).find(
          (s) => s.type === 'tab' && s.value === moduleTabs[activeModuleId],
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
        languages={languages}
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
        languages={languages}
        onLanguageChange={setLanguage}
      />
    )
  }
  if (isSupporterSignup) {
    return (
      <PublicSupporterSignup
        inviteCode={supporterInviteCode}
        t={t}
        language={language}
        languages={languages}
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
        languages={languages}
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
        languages={languages}
        onLanguageChange={setLanguage}
      />
    )
  }

  return (
    <AppShell
      padding="md"
      header={{ height: { base: 120, md: 78 }, offset: false }}
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
          <Group gap="sm" wrap="nowrap" className="topbar__current">
            <Group gap="sm" className="brand" wrap="nowrap">
              <ThemeIcon size="lg" variant="light" color="civic">
                <IconLayoutGrid size={18} />
              </ThemeIcon>
              <div>
                <Text fw={700} className="brand__title">Freedom Square</Text>
                <Text size="xs" c="dimmed" className="brand__subtitle">Civic Engagement Suite</Text>
              </div>
            </Group>
            <div className="topbar__center">
              <Badge variant="light" color="civic">
                {activeModule ? activeModule.label : 'Module hub'}
              </Badge>
              {activeModule ? (
                <Button variant="light" size="xs" onClick={() => setActiveModuleId(null)}>
                  Back to Modules
                </Button>
              ) : null}
            </div>
          </Group>
          <Group gap="sm" wrap="nowrap" className="topbar__actions topbar__actions--right">
            <Tooltip label="Search modules">
              <ActionIcon variant="light" size="lg" onClick={() => spotlight.open()}>
                <IconSearch size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="How it works">
              <ActionIcon variant="light" size="lg" onClick={() => setActiveModuleId('how-it-works')}>
                <IconBulb size={18} />
              </ActionIcon>
            </Tooltip>
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <Tooltip label={t('language.label')}>
                  <ActionIcon variant="light" size="md">
                    <IconLanguage size={16} />
                  </ActionIcon>
                </Tooltip>
              </Menu.Target>
              <Menu.Dropdown>
                {languages.map((lang) => (
                  <Menu.Item key={lang.id} onClick={() => setLanguage(lang.id)}>
                    {lang.label}
                  </Menu.Item>
                ))}
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        {!activeModule ? (
          <Stack gap="lg">
            <div className="module-hub">
              <div className="module-hub__header">
                <h1>Pick a module</h1>
                <p className="muted">Choose where you want to work right now.</p>
              </div>
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" className="module-tiles">
                {hubModules.map((module) => {
                  const isModuleReady =
                    !module.status || module.status.toLowerCase() === 'ready'
                  return (
                    <Card
                      key={module.id}
                      className={`module-tile ${!isModuleReady ? 'module-tile--inactive' : ''}`}
                      onClick={isModuleReady ? () => setActiveModuleId(module.id) : undefined}
                      role="button"
                      aria-disabled={!isModuleReady}
                      tabIndex={isModuleReady ? 0 : -1}
                      onKeyDown={(e) => {
                        if (!isModuleReady) return
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setActiveModuleId(module.id)
                        }
                      }}
                    >
                      <Group align="center" gap="sm">
                        <ThemeIcon variant="light" color="civic" size="lg">
                          {renderModuleIcon(module.id, 18)}
                        </ThemeIcon>
                        <div>
                          <div className="module-tile__header">
                            <Text fw={600}>{module.label}</Text>
                            {module.status ? (
                              <span className="pill pill--status">{module.status}</span>
                            ) : null}
                          </div>
                          <Text size="sm" c="dimmed">{module.description}</Text>
                        </div>
                      </Group>
                      <Group justify="flex-end" mt="md">
                        {isModuleReady ? (
                          <Button
                            variant="subtle"
                            size="xs"
                            rightSection={<IconArrowRight size={14} />}
                          >
                            Open
                          </Button>
                        ) : (
                          <Button variant="light" size="xs" disabled>
                            In progress
                          </Button>
                        )}
                      </Group>
                    </Card>
                  )
                })}
              </SimpleGrid>
            </div>
          </Stack>
        ) : (
          <div className="module-view">
            <aside className="module-view__sidebar">
              <div className="module-view__card">
                <span className="module-view__eyebrow">Active module</span>
                <h3>{activeModuleConfig?.title || activeModule?.label}</h3>
                <p className="muted">{activeModuleConfig?.description || activeModule?.description}</p>
                {activeModuleConfig?.flowTitle ? (
                  <div className="module-view__flow">
                    <span className="module-view__flow-title">{activeModuleConfig.flowTitle}</span>
                    {activeModuleConfig.flowSummary ? (
                      <span className="muted">{activeModuleConfig.flowSummary}</span>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {activeModuleConfig?.sections?.length ? (
                <div className="module-view__card">
                  <span className="module-nav__title">Sections</span>
                  <div className="module-view__sections">
                    {activeModuleConfig.sections.map((section) => {
                      const isActive =
                        section.type === 'tab' && moduleTabs[activeModuleId] === section.value
                      return (
                        <button
                          key={`${activeModuleId}-${section.value}`}
                          type="button"
                          className={`module-view__section ${isActive ? 'module-view__section--active' : ''}`}
                          onClick={() => handleModuleNavigation(activeModuleId, section)}
                          aria-current={isActive ? 'page' : undefined}
                        >
                          <span>{section.label}</span>
                          {section.hint ? <span className="muted">{section.hint}</span> : null}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ) : null}
            </aside>
            <div className="module-panel">
              <PageHeader
                className="page-header--hero"
                title={pageTitle}
                description={pageDescription}
                eyebrow={pageEyebrow}
              />
              {ActiveComponent ? (
                <ActiveComponent
                  t={t}
                  language={language}
                  activeTabOverride={moduleTabs[activeModuleId]}
                  onTabChange={(tabValue) => handleModuleTabChange(activeModuleId, tabValue)}
                  activeViewOverride={moduleTabs[activeModuleId]}
                  onViewChange={(viewValue) => handleModuleTabChange(activeModuleId, viewValue)}
                  showTabs={false}
                  showIntro={false}
                />
              ) : null}
            </div>
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
      <FeedbackDrawer
        opened={feedbackOpen}
        onClose={() => setFeedbackOpen(false)}
        t={t}
        activeModuleLabel={activeModule?.label}
      />
    </AppShell>
  )
}

export default function App() {
  return (
    <AppProvider>
      <AppShell_ />
    </AppProvider>
  )
}
