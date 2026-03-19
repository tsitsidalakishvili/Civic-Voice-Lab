import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AdminPage,
  AudienceDiscoveryPage,
  CRMPage,
  DeliberationPage,
  DueDiligencePage,
  HowItWorksPage,
  PublicCampaignPage,
} from './modules'
import { API_BASE, getJson, requestJson } from './services/api'
import { LANGUAGES, createTranslator } from './i18n'
import {
  Field,
  FormSection,
  InfoHint,
  MobileNavDrawer,
  PageHeader,
  StatusMessage,
} from './ui'
import './App.css'

function App() {
  const params = new URLSearchParams(window.location.search)
  const [language, setLanguage] = useState(
    () => localStorage.getItem('fs_lang') || 'en',
  )
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
  const isPublicEvent = eventRegistration === '1' && eventId
  const isPublicCampaign = campaignPublic === '1'
  const isQuestionnaire =
    (questionnaire && questionnaire.startsWith('deliberation')) ||
    (conversationId && params.get('view') === 'mobile')
  const isPublicView = isPublicEvent || isQuestionnaire || isPublicCampaign

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
  ]
  const hubModules = useMemo(
    () => modules.filter((module) => hubModuleIds.includes(module.id)),
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
      description: 'Collect comments, votes, and consensus insights.',
      flowTitle: 'Listen to your supporters',
      flowSummary: 'Run public surveys, collect comments, and review insights.',
      defaultTab: 'overview',
      primaryActions: [
        { label: 'Setup', type: 'tab', value: 'setup', hint: 'Create a conversation.' },
        { label: 'Distribute', type: 'tab', value: 'distribute', hint: 'Share links.' },
        { label: 'Insights', type: 'tab', value: 'insights', hint: 'Review results.' },
      ],
      sections: [
        {
          label: 'Listen to your supporters',
          type: 'tab',
          value: 'overview',
          hint: 'High-level view.',
        },
        { label: 'Setup', type: 'tab', value: 'setup', hint: 'Create a conversation.' },
        { label: 'Collect', type: 'tab', value: 'distribute', hint: 'Distribute links.' },
        { label: 'Moderate', type: 'tab', value: 'moderation', hint: 'Review comments.' },
        { label: 'Insights', type: 'tab', value: 'insights', hint: 'Consensus analytics.' },
        { label: 'Data', type: 'tab', value: 'data', hint: 'Import/export.' },
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
  }
  const getModuleIdFromUrl = () => {
    const search = new URLSearchParams(window.location.search)
    return search.get('module')
  }
  const [activeModuleId, setActiveModuleId] = useState(() => {
    const fromUrl = getModuleIdFromUrl()
    const match = modules.find((module) => module.id === fromUrl)
    return match?.id || null
  })
  const activeModule = modules.find((module) => module.id === activeModuleId)
  const ActiveComponent = activeModule?.Component ?? CRMPage
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
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

  useEffect(() => {
    if (mobileNavOpen) {
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = ''
      }
    }
    document.body.style.overflow = ''
  }, [mobileNavOpen])

  useEffect(() => {
    if (!mobileNavOpen) return
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setMobileNavOpen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [mobileNavOpen])

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
    return <PublicEventRegistration eventId={eventId} t={t} />
  }

  if (isPublicCampaign) {
    return <PublicCampaignPage campaignId={publicCampaignId} t={t} />
  }

  if (isQuestionnaire) {
    return <DeliberationQuestionnaire conversationId={conversationId} t={t} />
  }

  return (
    <div className="app-shell app-shell--sidebar">
      <header className="app-shell__topbar">
        <div className="brand">
          <div className="brand__mark">FS</div>
          <div>
            <div className="brand__title">Freedom Square</div>
            <div className="brand__subtitle">Civic Engagement Suite</div>
          </div>
        </div>
        {activeModule ? (
          <div className="topbar__current">
            <span className="pill">{activeModule?.label}</span>
            <span className="topbar__meta">Module view</span>
          </div>
        ) : (
          <div className="topbar__current">
            <span className="pill">Module hub</span>
            <span className="topbar__meta">Pick a module to start</span>
          </div>
        )}
        <div className="topbar__actions">
          {activeModule ? (
            <button className="pill pill--button" type="button" onClick={() => setActiveModuleId(null)}>
              Back to Modules
            </button>
          ) : null}
        </div>
      </header>
      {!activeModule ? (
        <section className="module-hub">
          <div className="module-hub__header">
            <h1>Pick a module</h1>
            <p className="muted">Choose where you want to work right now.</p>
          </div>
          <div className="module-tiles">
            {hubModules.map((module) => (
              <button
                key={module.id}
                className="module-tile"
                type="button"
                onClick={() => setActiveModuleId(module.id)}
              >
                <h3>{module.label}</h3>
                <p className="muted">{module.description}</p>
                <span className="module-tile__cta">Open</span>
              </button>
            ))}
          </div>
        </section>
      ) : (
        <div className="module-view">
          <aside className="module-view__sidebar">
            <div className="module-view__card">
              <span className="module-view__eyebrow">How it works</span>
              <h3>
                {moduleSections[activeModuleId]?.flowTitle ||
                  moduleSections[activeModuleId]?.title ||
                  activeModule?.label}
              </h3>
              <p className="muted">
                {moduleSections[activeModuleId]?.flowSummary ||
                  moduleSections[activeModuleId]?.description ||
                  activeModule?.description}
              </p>
            </div>
            <div className="module-view__card">
              <span className="module-view__eyebrow">Sections</span>
              <div className="module-view__sections">
                {(moduleSections[activeModuleId]?.sections || []).map((item) => {
                  const isActive =
                    item.type === 'tab' && moduleTabs[activeModuleId] === item.value
                  return (
                    <button
                      key={`${item.label}-${item.value}`}
                      type="button"
                      className={
                        isActive
                          ? 'module-view__section module-view__section--active'
                          : 'module-view__section'
                      }
                      onClick={() => {
                        if (item.type === 'tab') {
                          handleModuleTabChange(activeModuleId, item.value)
                        }
                        if (item.type === 'anchor') {
                          scrollToAnchor(item.value)
                        }
                      }}
                    >
                      <span>{item.label}</span>
                      {item.hint ? <InfoHint text={item.hint} /> : null}
                    </button>
                  )
                })}
              </div>
            </div>
          </aside>
          <main className="module-panel">
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
          </main>
        </div>
      )}
      <MobileNavDrawer
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        modules={hubModules}
        activeModuleId={activeModuleId}
        onSelect={(moduleId) => {
          setActiveModuleId(moduleId)
          setMobileNavOpen(false)
        }}
        language={language}
        onLanguageChange={(value) => setLanguage(value)}
        t={t}
        languages={LANGUAGES}
        currentModuleLabel={activeModule?.label || 'Module hub'}
      />
      <button
        className="feedback-fab"
        type="button"
        onClick={() => setFeedbackOpen((prev) => !prev)}
      >
        {t('feedback.button')}
      </button>
      {feedbackOpen && (
        <aside className="feedback-panel" role="dialog" aria-label={t('feedback.title')}>
          <FormSection
            title={t('feedback.title')}
            description="Share what you were trying to do, what happened, and what you expected."
          >
            <form
              className="stack form-shell"
              onSubmit={handleFeedbackSubmit}
              aria-busy={feedbackSending}
            >
              <Field
                id="feedback-name"
                label={t('feedback.name')}
                helper="Optional, helps us follow up with the right context."
              >
                <input
                  className="input"
                  placeholder="Jane Doe"
                  value={feedbackForm.name}
                  onChange={(event) =>
                    setFeedbackForm((prev) => ({ ...prev, name: event.target.value }))
                  }
                />
              </Field>
              <Field
                id="feedback-email"
                label={t('feedback.email')}
                helper="Optional, include if you want a reply."
              >
                <input
                  className="input"
                  type="email"
                  placeholder="jane@email.com"
                  value={feedbackForm.email}
                  onChange={(event) =>
                    setFeedbackForm((prev) => ({ ...prev, email: event.target.value }))
                  }
                />
              </Field>
              <Field
                id="feedback-message"
                label={t('feedback.message')}
                helper="Required. The more detail you share, the faster we can act."
                required
              >
                <textarea
                  className="textarea"
                  placeholder="Tell us what happened..."
                  value={feedbackForm.message}
                  onChange={(event) =>
                    setFeedbackForm((prev) => ({ ...prev, message: event.target.value }))
                  }
                  required
                />
              </Field>
              <div className="form-actions">
                <button className="button" type="submit" disabled={feedbackSending}>
                  {feedbackSending ? t('feedback.sending') : t('feedback.send')}
                </button>
              </div>
              <StatusMessage tone="error" message={feedbackError} />
              <StatusMessage tone={feedbackStatusTone} message={feedbackStatus} />
            </form>
          </FormSection>
        </aside>
      )}
    </div>
  )
}

function PublicEventRegistration({ eventId, t }) {
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
                <input
                  className="input"
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
                <input
                  className="input"
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
                <input
                  className="input"
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
                <select
                  className="select"
                  value={form.group}
                  onChange={(evt) => setForm((prev) => ({ ...prev, group: evt.target.value }))}
                >
                  <option value="Supporter">{translate('event.groupSupporter')}</option>
                  <option value="Member">{translate('event.groupMember')}</option>
                </select>
              </Field>
              <Field id="event-notes" label={translate('event.notes')} helper="Optional notes">
                <textarea
                  className="textarea"
                  placeholder="Accessibility needs, questions, or context..."
                  value={form.notes}
                  onChange={(evt) => setForm((prev) => ({ ...prev, notes: evt.target.value }))}
                />
              </Field>
            </div>
          </FormSection>
          <div className="form-actions">
            <button className="button" type="submit" disabled={submitting}>
              {submitting ? 'Submitting...' : translate('event.register')}
            </button>
          </div>
          <StatusMessage tone={statusTone} message={status} />
        </form>
      ) : null}
    </section>
  )
}

function DeliberationQuestionnaire({ conversationId, t }) {
  const translate = t || ((key, vars) => key)
  const [error, setError] = useState('')
  const [comments, setComments] = useState([])
  const [commentText, setCommentText] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [pendingVote, setPendingVote] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [conversation, setConversation] = useState(null)
  const dragStartRef = useRef(null)

  const params = new URLSearchParams(window.location.search)
  const sid = params.get('sid') || ''
  const participantStorageKey = `delib_anon_id_${conversationId || 'default'}_${sid || 'default'}`
  const participantRef = useRef(
    localStorage.getItem(participantStorageKey) || `${Date.now()}_${Math.random()}`,
  )
  const participantId = participantRef.current

  useEffect(() => {
    if (!conversationId) return
    setLoading(true)
    setError('')
    localStorage.setItem(participantStorageKey, participantId)
    Promise.all([
      getJson(`/conversations/${conversationId}`),
      getJson(`/conversations/${conversationId}/comments?status=approved`),
    ])
      .then(([convoPayload, commentsPayload]) => {
        setConversation(convoPayload)
        const approved = Array.isArray(commentsPayload) ? commentsPayload : []
        setComments(approved.slice(0, 5))
        setCurrentIndex(0)
      })
      .catch((err) =>
        setError(err.message || 'Unable to load conversation comments.'),
      )
      .finally(() => setLoading(false))
  }, [conversationId])

  const currentComment = comments[currentIndex]
  const currentCommentId =
    currentComment?.id || currentComment?.comment_id || currentComment?.commentId
  const currentText =
    currentComment?.text || currentComment?.comment_text || currentComment?.commentText || ''
  const totalComments = comments.length
  const progress = totalComments
    ? Math.min(100, Math.round((Math.min(currentIndex, totalComments) / totalComments) * 100))
    : 0
  const swipeIntent =
    dragOffset.x > 50
      ? 'agree'
      : dragOffset.x < -50
        ? 'disagree'
        : dragOffset.y > 50
          ? 'pass'
          : ''

  const handleVote = async (commentId, choice) => {
    if (!commentId || pendingVote) return
    setPendingVote(true)
    setError('')
    try {
      await requestJson('/vote', {
        method: 'POST',
        payload: { conversation_id: conversationId, comment_id: commentId, choice },
        headers: { 'X-Participant-Id': participantId },
      })
      setCurrentIndex((prev) => Math.min(prev + 1, comments.length))
    } catch (err) {
      setError(err.message || translate('questionnaire.voteFailed'))
    } finally {
      setPendingVote(false)
    }
  }

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
      await requestJson(`/conversations/${conversationId}/comments`, {
        method: 'POST',
        payload: { text: commentText.trim() },
        headers: { 'X-Participant-Id': participantId },
      })
      setCommentText('')
    } catch (err) {
      setError(err.message || 'Comment failed.')
    }
  }

  const resetDrag = () => {
    setDragOffset({ x: 0, y: 0 })
    setIsDragging(false)
    dragStartRef.current = null
  }

  const handlePointerDown = (event) => {
    if (pendingVote || !currentCommentId) return
    if (event.button !== undefined && event.button !== 0) return
    dragStartRef.current = { x: event.clientX, y: event.clientY }
    setDragOffset({ x: 0, y: 0 })
    setIsDragging(true)
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch (err) {
      // Pointer capture isn't supported in all environments.
    }
  }

  const handlePointerMove = (event) => {
    if (!dragStartRef.current || !isDragging) return
    setDragOffset({
      x: event.clientX - dragStartRef.current.x,
      y: event.clientY - dragStartRef.current.y,
    })
  }

  const handlePointerEnd = (event) => {
    if (!dragStartRef.current) return
    const start = dragStartRef.current
    const endX =
      event && typeof event.clientX === 'number' ? event.clientX : start.x + dragOffset.x
    const endY =
      event && typeof event.clientY === 'number' ? event.clientY : start.y + dragOffset.y
    const x = endX - start.x
    const y = endY - start.y
    const threshold = 90
    const choice =
      x > threshold ? 1 : x < -threshold ? -1 : y > threshold ? 0 : null
    resetDrag()
    if (choice !== null) {
      handleVote(currentCommentId, choice)
    }
  }

  return (
    <section className="delib-questionnaire">
            <header className="delib-questionnaire__header">
              <span className="pill">{translate('module.deliberation')}</span>
              <h2>{translate('questionnaire.title')}</h2>
              <p>{translate('questionnaire.subtitle')}</p>
      </header>
      {error ? <div className="module-alert">{error}</div> : null}
      <div className="questionnaire-progress">
        <div className="questionnaire-progress__track">
          <div className="questionnaire-progress__bar" style={{ width: `${progress}%` }} />
        </div>
        <span className="questionnaire-progress__label">
          {Math.min(currentIndex + 1, totalComments)}/{totalComments || 0}
        </span>
      </div>
      <div className="questionnaire-deck">
        <div className="questionnaire-card-stack">
          {currentIndex + 1 < totalComments && (
            <div className="questionnaire-card questionnaire-card--back" aria-hidden="true" />
          )}
          {loading ? (
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
            >
                    <div className="questionnaire-card__title">
                      {translate('questionnaire.questionLabel', {
                        current: currentIndex + 1,
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
      <div className="questionnaire-controls">
        <button
          className="swipe-button swipe-button--disagree"
          type="button"
          onClick={() => handleVote(currentCommentId, -1)}
          disabled={!currentCommentId || pendingVote}
        >
                  {translate('questionnaire.disagree')}
        </button>
        <button
          className="swipe-button swipe-button--pass"
          type="button"
          onClick={() => handleVote(currentCommentId, 0)}
          disabled={!currentCommentId || pendingVote}
        >
                  {translate('questionnaire.pass')}
        </button>
        <button
          className="swipe-button swipe-button--agree"
          type="button"
          onClick={() => handleVote(currentCommentId, 1)}
          disabled={!currentCommentId || pendingVote}
        >
                  {translate('questionnaire.agree')}
        </button>
      </div>
      {conversation?.allow_comment_submission ? (
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

export default App
