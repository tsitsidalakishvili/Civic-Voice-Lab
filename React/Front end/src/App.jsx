import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AdminPage,
  AudienceDiscoveryPage,
  CRMPage,
  DeliberationPage,
  DueDiligencePage,
  HowItWorksPage,
} from './modules'
import { API_BASE, getJson, requestJson } from './services/api'
import { LANGUAGES, createTranslator } from './i18n'
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

  if (eventRegistration === '1' && eventId) {
    return <PublicEventRegistration eventId={eventId} t={t} />
  }

  if (
    (questionnaire && questionnaire.startsWith('deliberation')) ||
    (conversationId && params.get('view') === 'mobile')
  ) {
    return <DeliberationQuestionnaire conversationId={conversationId} t={t} />
  }

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

  const [activeModuleId, setActiveModuleId] = useState(modules[0].id)
  const activeModule = modules.find((module) => module.id === activeModuleId)
  const ActiveComponent = activeModule?.Component ?? CRMPage
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackForm, setFeedbackForm] = useState({
    name: '',
    email: '',
    message: '',
  })
  const [feedbackStatus, setFeedbackStatus] = useState('')
  const [feedbackError, setFeedbackError] = useState('')
  const [feedbackSending, setFeedbackSending] = useState(false)

  const handleFeedbackSubmit = async (event) => {
    event.preventDefault()
    setFeedbackStatus('')
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
      } else if (response?.email_status === 'failed') {
        setFeedbackStatus(t('feedback.statusFailed'))
      } else if (response?.email_status === 'not_configured') {
        setFeedbackStatus(t('feedback.statusNotConfigured'))
      } else {
        setFeedbackStatus(t('feedback.statusSaved'))
      }
      setFeedbackForm({ name: '', email: '', message: '' })
    } catch (err) {
      setFeedbackError(err.message || t('feedback.errorSend'))
    } finally {
      setFeedbackSending(false)
    }
  }

  return (
    <div className="app-shell app-shell--sidebar">
      <aside className="module-nav" aria-label="Module navigation">
        <div className="module-nav__title">{t('modules.title')}</div>
        <div className="module-nav__switch">
          <label className="label">{t('language.label')}</label>
          <select
            className="select"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
          >
            {LANGUAGES.map((lang) => (
              <option key={lang.id} value={lang.id}>
                {lang.label}
              </option>
            ))}
          </select>
        </div>
        {modules.map((module) => (
          <button
            key={module.id}
            type="button"
            className={
              module.id === activeModuleId
                ? 'module-nav__item module-nav__item--active'
                : 'module-nav__item'
            }
            onClick={() => setActiveModuleId(module.id)}
          >
            <span className="module-nav__label">{module.label}</span>
            <span className="module-nav__desc">{module.description}</span>
          </button>
        ))}
      </aside>

      <main className="module-panel">
        <ActiveComponent t={t} language={language} />
      </main>
      <button
        className="feedback-fab"
        type="button"
        onClick={() => setFeedbackOpen((prev) => !prev)}
      >
        {t('feedback.button')}
      </button>
      {feedbackOpen && (
        <aside className="feedback-panel">
          <div className="card-header">
            <div>
              <h3>{t('feedback.title')}</h3>
              <p className="muted">{t('feedback.subtitle')}</p>
            </div>
          </div>
          {feedbackError ? <div className="module-alert">{feedbackError}</div> : null}
          {feedbackStatus ? (
            <div className="module-alert module-alert--success">{feedbackStatus}</div>
          ) : null}
          <form className="stack" onSubmit={handleFeedbackSubmit}>
            <input
              className="input"
              placeholder={t('feedback.name')}
              value={feedbackForm.name}
              onChange={(event) =>
                setFeedbackForm((prev) => ({ ...prev, name: event.target.value }))
              }
            />
            <input
              className="input"
              placeholder={t('feedback.email')}
              value={feedbackForm.email}
              onChange={(event) =>
                setFeedbackForm((prev) => ({ ...prev, email: event.target.value }))
              }
            />
            <textarea
              className="textarea"
              placeholder={t('feedback.message')}
              value={feedbackForm.message}
              onChange={(event) =>
                setFeedbackForm((prev) => ({ ...prev, message: event.target.value }))
              }
            />
            <button className="button" type="submit" disabled={feedbackSending}>
              {feedbackSending ? t('feedback.sending') : t('feedback.send')}
            </button>
          </form>
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

  useEffect(() => {
    getJson(`/crm/events/detail?event_id=${encodeURIComponent(eventId)}`)
      .then((payload) => setEvent(payload))
      .catch((err) => setError(err.message || translate('event.notFound')))
  }, [eventId])

  const handleSubmit = async (eventAction) => {
    eventAction.preventDefault()
    if (!form.fullName.trim() || !form.email.trim()) {
      setStatus(translate('event.fullNameRequired'))
      return
    }
    setStatus('')
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
      setForm({
        fullName: '',
        email: '',
        phone: '',
        group: 'Supporter',
        notes: '',
      })
    } catch (err) {
      setStatus(err.message || 'Registration failed.')
    }
  }

  return (
    <section className="module">
      <header className="module-header">
        <h2>{event?.name || translate('event.registrationTitle')}</h2>
        {event?.startDate ? <p>{event.startDate}</p> : null}
      </header>
      {error ? <div className="module-alert">{error}</div> : null}
      {event ? (
        <form className="module-card module-card__wide form-grid" onSubmit={handleSubmit}>
          <input
            className="input"
            placeholder={translate('event.fullName')}
            value={form.fullName}
            onChange={(evt) => setForm((prev) => ({ ...prev, fullName: evt.target.value }))}
          />
          <input
            className="input"
            placeholder={translate('event.email')}
            value={form.email}
            onChange={(evt) => setForm((prev) => ({ ...prev, email: evt.target.value }))}
          />
          <input
            className="input"
            placeholder={translate('event.phone')}
            value={form.phone}
            onChange={(evt) => setForm((prev) => ({ ...prev, phone: evt.target.value }))}
          />
          <select
            className="select"
            value={form.group}
            onChange={(evt) => setForm((prev) => ({ ...prev, group: evt.target.value }))}
          >
            <option value="Supporter">{translate('event.groupSupporter')}</option>
            <option value="Member">{translate('event.groupMember')}</option>
          </select>
          <textarea
            className="textarea"
            placeholder={translate('event.notes')}
            value={form.notes}
            onChange={(evt) => setForm((prev) => ({ ...prev, notes: evt.target.value }))}
          />
          <button className="button" type="submit">
            {translate('event.register')}
          </button>
        </form>
      ) : null}
      {status ? <p className="muted">{status}</p> : null}
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
