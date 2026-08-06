import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Accordion,
  ActionIcon,
  Affix,
  AppShell,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  ThemeIcon,
  Tooltip,
  Menu,
} from '@mantine/core'
import { Spotlight, spotlight } from '@mantine/spotlight'
import {
  IconArrowRight,
  IconBulb,
  IconDatabaseSearch,
  IconLanguage,
  IconLayoutGrid,
  IconMessage2,
  IconSearch,
} from '@tabler/icons-react'
import { AppProvider, useApp } from '@/context/AppContext'
import { ThemeToggle } from '@/components/ThemeToggle/ThemeToggle'
import { buildModules, buildModuleSections, HUB_MODULE_IDS, renderModuleIcon } from '@/config/modules'
import { FeedbackDrawer } from '@/components/FeedbackDrawer'
import { DataChatDrawer } from '@/components/DataChatDrawer'
import { PlatformWalkthrough } from '@/components/PlatformWalkthrough'
import { PublicEventRegistration } from '@/views/PublicEventRegistration'
import { PublicSupporterSignup } from '@/views/PublicSupporterSignup'
import { DeliberationQuestionnaire } from '@/views/DeliberationQuestionnaire'
import { DeliberationPublicReport } from '@/views/DeliberationPublicReport'
import { PlatformAccessGate } from '@/views/PlatformAccessGate'
import { clearStoredAccessEmail, getStoredAccessEmail } from '@/services/accessGate'
import { getJson, requestJson } from '@/services/api'
import { PublicCampaignPage } from '@/modules'
import { parseStoredList } from '@/utils/deck'
import { PageHeader } from '@/ui'
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
  const pathName = window.location.pathname || '/'
  const supporterSignup = params.get('supporter_signup')
  const supporterInviteCode = params.get('invite_code') || ''

  const isPublicEvent = eventRegistration === '1' && eventId
  const isPublicCampaign = campaignPublic === '1'
  const isSupporterSignup = supporterSignup === '1' || pathName.replace(/\/$/, '') === '/supporter-signup'
  const isQuestionnaireView = ['mobile', 'participant', 'embed', 'admin'].includes(viewParam)
  const isQuestionnaire =
    (questionnaire && questionnaire.startsWith('deliberation')) ||
    (conversationId && isQuestionnaireView)
  const isPublicReport = Boolean(reportShare)
  const isPublicView =
    isPublicEvent || isQuestionnaire || isPublicCampaign || isPublicReport || isSupporterSignup

  const [accessChecked, setAccessChecked] = useState(false)
  const [accessGranted, setAccessGranted] = useState(false)

  useEffect(() => {
    if (isPublicView) return undefined
    let mounted = true
    const checkAccess = async () => {
      try {
        const status = await getJson('/platform/access/status', { cacheMs: 0 })
        if (!mounted) return
        if (!status?.enabled) {
          setAccessGranted(true)
          setAccessChecked(true)
          return
        }
        const stored = getStoredAccessEmail()
        if (stored) {
          const result = await requestJson('/platform/access/verify', {
            payload: { email: stored },
          })
          if (!mounted) return
          if (result?.allowed) {
            setAccessGranted(true)
            setAccessChecked(true)
            return
          }
          clearStoredAccessEmail()
        }
        setAccessGranted(false)
        setAccessChecked(true)
      } catch {
        // Backend unreachable: let the app render so pages can surface their own errors.
        if (!mounted) return
        setAccessGranted(true)
        setAccessChecked(true)
      }
    }
    checkAccess()
    return () => {
      mounted = false
    }
  }, [isPublicView])

  const modules = useMemo(() => buildModules(t), [t])
  const MODULE_SECTIONS = useMemo(() => buildModuleSections(t), [t])
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
  const [chatOpen, setChatOpen] = useState(false)
  const initialUrlSync = useRef(true)
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


  const handleModuleTabChange = useCallback((moduleId, tabValue) => {
    if (!moduleId || !tabValue) return
    setModuleTabs((prev) => ({ ...prev, [moduleId]: tabValue }))
  }, [])

  const handleWalkthroughModuleChange = useCallback((moduleId) => {
    if (!moduleId) return
    setActiveModuleId(moduleId)
  }, [])

  const handleWalkthroughSectionChange = useCallback(
    (moduleId, sectionValue) => {
      const targetModuleId = moduleId || activeModuleId
      if (targetModuleId && targetModuleId !== activeModuleId) setActiveModuleId(targetModuleId)
      handleModuleTabChange(targetModuleId, sectionValue)
    },
    [activeModuleId, handleModuleTabChange],
  )

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

  if (!accessChecked) {
    return null
  }

  if (!accessGranted) {
    return <PlatformAccessGate onGranted={() => setAccessGranted(true)} />
  }

  return (
    <AppShell
      padding="md"
      header={{ height: { base: 120, md: 78 }, offset: false }}
      className="app-shell app-shell--sidebar"
    >
      <Spotlight
        actions={spotlightActions}
        searchProps={{ placeholder: t('app.searchPlaceholder') }}
        nothingFound={t('app.nothingFound')}
        highlightQuery
      />
      <AppShell.Header className="app-shell__topbar">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" className="topbar__current">
            <Group gap="sm" className="brand" wrap="nowrap" data-tour="brand">
              <ThemeIcon size="lg" variant="light" color="civic">
                <IconLayoutGrid size={18} />
              </ThemeIcon>
              <div>
                <Text fw={700} className="brand__title">Civic Voice Lab</Text>
                <Text size="xs" c="dimmed" className="brand__subtitle">Civic Engagement Suite</Text>
              </div>
            </Group>
            <div className="topbar__center" data-tour="module-context">
              <Badge variant="light" color="civic">
                {activeModule ? activeModule.label : t('app.moduleHub')}
              </Badge>
              {activeModule ? (
                <Button variant="light" size="xs" onClick={() => setActiveModuleId(null)}>
                  {t('app.backToModules')}
                </Button>
              ) : null}
            </div>
          </Group>
          <Group gap="sm" wrap="nowrap" className="topbar__actions topbar__actions--right">
            <Tooltip label={t('app.searchModules')}>
              <ActionIcon variant="light" size="lg" onClick={() => spotlight.open()} data-tour="global-search">
                <IconSearch size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={t('app.howItWorks')}>
              <ActionIcon variant="light" size="lg" onClick={() => setActiveModuleId('how-it-works')}>
                <IconBulb size={18} />
              </ActionIcon>
            </Tooltip>
            <PlatformWalkthrough
              activeModule={activeModule}
              activeModuleConfig={activeModuleConfig}
              modules={modules}
              moduleSections={MODULE_SECTIONS}
              onOpenModuleHub={() => setActiveModuleId(null)}
              onModuleChange={handleWalkthroughModuleChange}
              onModuleSectionChange={handleWalkthroughSectionChange}
            />
            <ThemeToggle />
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <Tooltip label={t('language.label')}>
                  <ActionIcon variant="light" size="md" data-tour="language-menu">
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
            <div className="module-hub" data-tour="module-hub">
              <div className="module-hub__header">
                <h1>{t('app.pickModule')}</h1>
                <p className="muted">{t('app.pickModuleDesc')}</p>
              </div>
              <div className="module-tiles">
                {hubModules.map((module) => {
                  const isModuleReady =
                    !module.status || module.status.toLowerCase() === 'ready'
                  return (
                    <Card
                      key={module.id}
                      className={`module-tile ${!isModuleReady ? 'module-tile--inactive' : ''}`}
                      data-tour={`module-tile-${module.id}`}
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
                            {t('app.open')}
                          </Button>
                        ) : (
                          <Button variant="light" size="xs" disabled>
                            {t('app.inProgress')}
                          </Button>
                        )}
                      </Group>
                    </Card>
                  )
                })}
              </div>
            </div>
            <Accordion variant="separated" radius="md" className="about-accordion" data-tour="about-platform">
              <Accordion.Item value="about">
                <Accordion.Control>
                  <Stack gap={2} align="center">
                    <Text fw={600}>About Civic Voice Lab</Text>
                    <Text size="xs" c="dimmed">Platform overview &amp; capabilities</Text>
                  </Stack>
                </Accordion.Control>
                <Accordion.Panel>
                  <div className="platform-description">
                    <h2>Civic Voice Lab - Civic Engagement Suite</h2>

                    <h3>Executive Summary</h3>
                    <p>Civic Voice Lab is an integrated digital platform designed for political parties, civic movements, NGOs, and advocacy organizations. It combines community management, campaigning, public consultation, collective decision-making, and organizational intelligence in a single environment.</p>
                    <p>The platform helps organizations build stronger relationships with supporters, understand community priorities, coordinate campaigns, and make transparent, evidence-based decisions. By bringing together data, participation, and analytics, Civic Voice Lab reduces reliance on multiple disconnected tools and creates a more efficient and democratic way of organizing communities.</p>

                    <hr />

                    <h3>Network Management (CRM)</h3>
                    <p>The Network module serves as the central database for supporters, members, volunteers, partners, and stakeholders. Organizations can manage contacts, track engagement history, visualize communities geographically, and build targeted outreach strategies.</p>
                    <p>This creates a complete picture of the organization's community and strengthens long-term engagement.</p>

                    <hr />

                    <h3>Campaign Management</h3>
                    <p>The Campaign module enables organizations to plan, coordinate, and monitor political, advocacy, awareness, and community campaigns. Teams can define objectives, track progress, manage activities, and measure campaign performance from a single workspace.</p>
                    <p>The module improves coordination and provides leadership with clear visibility into campaign effectiveness.</p>

                    <hr />

                    <h3>Survey &amp; Consensus</h3>
                    <p>The Survey &amp; Consensus module helps organizations understand what their communities think and where common ground exists. Beyond traditional surveys, the platform identifies patterns in responses, groups participants by shared perspectives, and highlights areas of agreement and disagreement.</p>
                    <p>Results are shown as aggregated, anonymous outputs without identifying individual people. The platform can use generated anonymous participant and result identifiers so organizations can learn from community input while protecting personal identity.</p>
                    <p>This enables organizations to make decisions that are genuinely informed by their members and supporters.</p>

                    <hr />

                    <h3>Deliberation &amp; Collective Decision-Making</h3>
                    <p>Civic Voice Lab provides structured spaces for dialogue where participants can discuss issues, evaluate alternatives, and collaboratively develop solutions.</p>
                    <p>The module supports transparent and participatory governance by ensuring that organizational priorities can be traced back to real community input rather than top-down decision-making.</p>

                    <hr />

                    <h3>Due Diligence &amp; Risk Intelligence</h3>
                    <p>The Due Diligence module helps organizations assess potential partners, stakeholders, and individuals before engagement or collaboration. It supports background research, risk identification, reputation assessment, and watchlist management.</p>
                    <p>This strengthens organizational governance and reduces reputational and operational risks.</p>

                    <hr />

                    <h3>Audience Discovery</h3>
                    <p>The Audience Discovery module uses AI-assisted analysis to identify potential supporter groups, understand their interests, and improve communication strategies. Organizations can better understand who they are trying to reach and which messages are most likely to resonate with different audiences.</p>
                    <p>This improves outreach effectiveness and campaign impact.</p>

                    <hr />

                    <h3>Data Hub &amp; Analytics</h3>
                    <p>The Data Hub acts as the platform's central information layer, connecting data from spreadsheets, external systems, and internal modules into a unified database.</p>
                    <p>Combined with analytics dashboards and reporting tools, it provides leadership teams with real-time insights into supporter engagement, campaign performance, participation trends, and organizational growth.</p>

                    <hr />

                    <h3>Artificial Intelligence Layer</h3>
                    <p>Artificial Intelligence enhances the platform by helping organizations process large volumes of information, identify patterns, and generate actionable insights.</p>
                    <p>AI capabilities include survey analysis, discussion summarization, audience segmentation, trend detection, and decision-support recommendations. The technology is designed to support human decision-making, making participation at scale both practical and manageable.</p>

                    <hr />

                    <h3>Expected Impact</h3>
                    <p>Civic Voice Lab strengthens democratic participation within organizations by enabling communities to actively shape priorities, policies, and campaigns. The platform promotes transparency, accountability, and evidence-based decision-making while helping organizations build stronger, more engaged supporter networks.</p>
                    <p>By combining participation, campaigning, analytics, and AI-powered insights in a single solution, Civic Voice Lab enables civic and political organizations to operate more effectively and democratically in the digital age.</p>

                    <div className="platform-description__principle">
                      <p><strong>Core Principle</strong></p>
                      <p><strong>People should not only receive information; they should actively shape decisions.</strong> Civic Voice Lab transforms supporters from passive audiences into active participants, creating organizations that are more transparent, accountable, and responsive to their communities.</p>
                    </div>
                  </div>
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          </Stack>
        ) : (
          <div className="module-view">
            <aside className="module-view__sidebar" data-tour="module-sidebar">
              <div className="module-view__card">
                <span className="module-view__eyebrow">{t('app.activeModule')}</span>
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
                  <span className="module-nav__title">{t('app.sections')}</span>
                  <div className="module-view__sections" data-tour="module-sections">
                    {activeModuleConfig.sections.map((section) => {
                      const isActive =
                        section.type === 'tab' && moduleTabs[activeModuleId] === section.value
                      return (
                        <button
                          key={`${activeModuleId}-${section.value}`}
                          type="button"
                          className={`module-view__section ${isActive ? 'module-view__section--active' : ''}`}
                          data-tour={`module-section-${section.value}`}
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
            <div className="module-panel" data-tour="module-content">
              <PageHeader
                className="page-header--hero"
                data-tour="module-header"
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
          data-tour="feedback"
        >
          <IconMessage2 size={20} />
        </ActionIcon>
      </Affix>
      <Affix position={{ bottom: 80, right: 24 }}>
        <Button
          className="data-chat-fab"
          radius="xl"
          size="md"
          color="civic"
          leftSection={<IconDatabaseSearch size={18} />}
          onClick={() => setChatOpen((prev) => !prev)}
          aria-label="Ask your data"
          data-tour="data-chat"
        >
          Ask your data
        </Button>
      </Affix>
      <FeedbackDrawer
        opened={feedbackOpen}
        onClose={() => setFeedbackOpen(false)}
        t={t}
        activeModuleLabel={activeModule?.label}
      />
      <DataChatDrawer opened={chatOpen} onClose={() => setChatOpen(false)} />
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
