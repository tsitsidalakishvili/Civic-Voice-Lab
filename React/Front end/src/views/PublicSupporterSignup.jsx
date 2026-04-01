import { useEffect, useMemo, useState } from 'react'
import { Button, Checkbox, MultiSelect, Select, TextInput } from '@mantine/core'
import { getJson, requestJson } from '../services/api'
import { Field, FormSection, LanguageSelect, StatusMessage } from '../ui'

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
      if (url.pathname.startsWith('/embed/')) return value
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

const INTEREST_VALUES = [
  'Urbanism & city development',
  'Mobility & transport',
  'Housing & neighborhoods',
  'Environment & climate',
  'Education',
  'Healthcare',
  'Local economy & jobs',
  'Digital governance',
  'Culture & youth',
]

const INTEREST_KEYWORDS = {
  'Urbanism & city development': ['city', 'urban', 'development', 'public space', 'planning'],
  'Mobility & transport': ['transport', 'mobility', 'traffic', 'bus', 'metro', 'road'],
  'Housing & neighborhoods': ['housing', 'home', 'neighborhood', 'rent', 'zoning'],
  'Environment & climate': ['environment', 'climate', 'green', 'waste', 'air', 'water'],
  Education: ['education', 'school', 'student', 'teacher'],
  Healthcare: ['health', 'healthcare', 'hospital', 'clinic'],
  'Local economy & jobs': ['economy', 'jobs', 'employment', 'business', 'market'],
  'Digital governance': ['digital', 'technology', 'online', 'service', 'data'],
  'Culture & youth': ['culture', 'youth', 'arts', 'sports', 'community'],
}

const DEFAULT_SUGGESTED_CONVERSATIONS = [
  { id: '', topicKey: 'supporter.signup.success.defaultTopic.strayDogs' },
  { id: '', topicKey: 'supporter.signup.success.defaultTopic.mobility' },
]

const rankConversationsByInterests = (conversations, interests) => {
  const filteredConversations = (Array.isArray(conversations) ? conversations : []).filter(
    (conversation) => String(conversation?.topic || '').trim().toLowerCase() !== 'survey flow smoke test',
  )
  const selected = (interests || []).filter(Boolean)
  if (!selected.length) return filteredConversations.slice(0, 6)
  const keywords = selected.flatMap((interest) => INTEREST_KEYWORDS[interest] || [])
  if (!keywords.length) return filteredConversations.slice(0, 6)
  return [...filteredConversations]
    .map((conversation) => {
      const blob = `${conversation?.topic || ''} ${conversation?.description || ''}`.toLowerCase()
      const score = keywords.reduce((acc, keyword) => (blob.includes(keyword) ? acc + 1 : acc), 0)
      return { ...conversation, _matchScore: score }
    })
    .sort((a, b) => (b._matchScore || 0) - (a._matchScore || 0))
    .filter((conversation, index) => (conversation._matchScore || 0) > 0 || index < 3)
    .slice(0, 6)
}

export function PublicSupporterSignup({
  inviteCode,
  t,
  language,
  languages,
  onLanguageChange,
}) {
  const translate = t || ((key) => key)
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    supporterType: 'Supporter',
    gender: '',
    age: '',
    timeAvailability: 'Unspecified',
    address: '',
    lat: '',
    lon: '',
    educationLevels: [],
    skills: [],
    involvementAreas: [],
    about: '',
    agreesWithManifesto: false,
    facebookGroupMember: false,
    interestedInMembership: false,
    interests: [],
  })
  const [status, setStatus] = useState('')
  const [statusTone, setStatusTone] = useState('info')
  const [submitting, setSubmitting] = useState(false)
  const [welcomeVideoUrl, setWelcomeVideoUrl] = useState('')
  const [thankYouVideoUrl, setThankYouVideoUrl] = useState('')
  const [welcomeVideoError, setWelcomeVideoError] = useState('')
  const [educationOptions, setEducationOptions] = useState([
    'High School',
    'Vocational',
    'Bachelor',
    'Master',
    'Doctorate',
  ])
  const [skillOptions, setSkillOptions] = useState([])
  const [involvementAreaOptions, setInvolvementAreaOptions] = useState([])
  const [recommendedConversations, setRecommendedConversations] = useState([])
  const [recommendationsLoading, setRecommendationsLoading] = useState(false)
  const heading = useMemo(
    () =>
      form.supporterType === 'Member'
        ? translate('supporter.signup.heading.member')
        : translate('supporter.signup.heading.supporter'),
    [form.supporterType, translate],
  )
  const welcomeVideoEmbedUrl = useMemo(() => toYouTubeEmbedUrl(welcomeVideoUrl), [welcomeVideoUrl])
  const thankYouVideoEmbedUrl = useMemo(
    () => toYouTubeEmbedUrl(thankYouVideoUrl) || welcomeVideoEmbedUrl,
    [thankYouVideoUrl, welcomeVideoEmbedUrl],
  )
  const supporterTypeOptions = useMemo(
    () => [
      { value: 'Supporter', label: translate('supporter.signup.type.supporter') },
      { value: 'Member', label: translate('supporter.signup.type.member') },
    ],
    [translate],
  )
  const genderOptions = useMemo(
    () => [
      { value: '', label: translate('supporter.signup.gender.unspecified') },
      { value: 'Male', label: translate('supporter.signup.gender.male') },
      { value: 'Female', label: translate('supporter.signup.gender.female') },
      { value: 'Other', label: translate('supporter.signup.gender.other') },
    ],
    [translate],
  )
  const availabilityOptions = useMemo(
    () => [
      { value: 'Unspecified', label: translate('supporter.signup.availability.unspecified') },
      { value: 'Weekends', label: translate('supporter.signup.availability.weekends') },
      { value: 'Evenings', label: translate('supporter.signup.availability.evenings') },
      { value: 'Full-time', label: translate('supporter.signup.availability.fullTime') },
      { value: 'Ad-hoc', label: translate('supporter.signup.availability.adHoc') },
    ],
    [translate],
  )
  const interestOptions = useMemo(
    () =>
      INTEREST_VALUES.map((value) => ({
        value,
        label: translate(`supporter.signup.interests.option.${value}`),
      })),
    [translate],
  )
  const fallbackSuggestedConversations = useMemo(
    () =>
      DEFAULT_SUGGESTED_CONVERSATIONS.map((item, index) => ({
        id: item.id || `fallback-topic-${index}`,
        topic: translate(item.topicKey),
        isFallback: true,
      })),
    [translate],
  )
  const buildConversationLink = (conversationId) => {
    if (!conversationId || typeof window === 'undefined') return ''
    const url = new URL(window.location.pathname || '/', window.location.origin)
    url.searchParams.set('questionnaire', 'deliberation')
    url.searchParams.set('conversation_id', conversationId)
    url.searchParams.set('view', 'participant')
    if (language) {
      url.searchParams.set('lang', language)
    }
    return url.toString()
  }

  useEffect(() => {
    getJson('/crm/supporter-signup-config')
      .then((payload) => {
        setWelcomeVideoUrl(payload?.welcomeVideoUrl || '')
        setThankYouVideoUrl(payload?.thankYouVideoUrl || '')
      })
      .catch((err) => {
        setWelcomeVideoError(err.message || translate('supporter.signup.video.loadError'))
      })
  }, [])

  useEffect(() => {
    let mounted = true
    Promise.all([
      getJson('/crm/distinct-values?label=EducationLevel'),
      getJson('/crm/distinct-values?label=Skill'),
      getJson('/crm/distinct-values?label=InvolvementArea'),
    ])
      .then(([education, skills, involvementAreas]) => {
        if (!mounted) return
        if (Array.isArray(education) && education.length) {
          setEducationOptions(education)
        }
        setSkillOptions(Array.isArray(skills) ? skills : [])
        setInvolvementAreaOptions(Array.isArray(involvementAreas) ? involvementAreas : [])
      })
      .catch(() => null)
    return () => {
      mounted = false
    }
  }, [])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!form.firstName.trim() || !form.email.trim()) {
      setStatus(translate('supporter.signup.validation.requiredNameEmail'))
      setStatusTone('error')
      return
    }
    setSubmitting(true)
    setStatus('')
    setStatusTone('info')
    try {
      await requestJson('/crm/supporter-signup', {
        method: 'POST',
        payload: {
          firstName: form.firstName.trim(),
          lastName: form.lastName.trim(),
          email: form.email.trim(),
          phone: form.phone.trim(),
          supporterType: form.supporterType,
          gender: form.gender || null,
          age: form.age ? Number(form.age) : null,
          timeAvailability: form.timeAvailability,
          address: form.address.trim(),
          lat: form.lat ? Number(form.lat) : null,
          lon: form.lon ? Number(form.lon) : null,
          educationLevels: form.educationLevels,
          skills: form.skills,
          involvementAreas: form.involvementAreas,
          about: form.about.trim(),
          agreesWithManifesto: !!form.agreesWithManifesto,
          facebookGroupMember: !!form.facebookGroupMember,
          interestedInMembership: !!form.interestedInMembership,
          interests: form.interests,
          inviteCode: inviteCode || '',
        },
      })
      setStatus(translate('supporter.signup.status.submitted'))
      setStatusTone('success')
      setRecommendationsLoading(true)
      try {
        const payload = await getJson('/conversations')
        const openConversations = (Array.isArray(payload) ? payload : []).filter((item) => item?.is_open)
        setRecommendedConversations(rankConversationsByInterests(openConversations, form.interests))
      } catch (error) {
        setRecommendedConversations([])
      } finally {
        setRecommendationsLoading(false)
      }
      setForm((prev) => ({
        ...prev,
        firstName: '',
        lastName: '',
        email: '',
        phone: '',
        age: '',
        address: '',
        lat: '',
        lon: '',
        educationLevels: [],
        skills: [],
        involvementAreas: [],
        about: '',
        agreesWithManifesto: false,
        facebookGroupMember: false,
        interestedInMembership: false,
        interests: [],
      }))
    } catch (err) {
      setStatus(err.message || translate('supporter.signup.status.submitError'))
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
        <h2>{heading}</h2>
      </header>
      {welcomeVideoError ? <StatusMessage tone="error" message={welcomeVideoError} /> : null}
      <div className="supporter-signup-layout">
        <div className="supporter-signup-section">
          <div className="module-card supporter-video-card supporter-video-card--hero">
            <div className="supporter-video-card__eyebrow">{translate('supporter.signup.video.eyebrow')}</div>
            <h3>{translate('supporter.signup.video.title')}</h3>
            <p className="muted">{translate('supporter.signup.video.description')}</p>
            {welcomeVideoEmbedUrl ? (
              <div className="supporter-video-card__frame">
                <iframe
                  src={welcomeVideoEmbedUrl}
                  title="Organization welcome message"
                  className="supporter-video-card__embed"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            ) : (
              <div className="supporter-video-card__placeholder">
                {translate('supporter.signup.video.placeholder')}
              </div>
            )}
          </div>

          <details className="dashboard-detail supporter-signup-expander" open>
            <summary>
              <span>{translate('supporter.signup.form.expanderTitle')}</span>
            </summary>
            <div className="dashboard-detail__body">
              <form className="module-card module-card__wide form-shell supporter-signup-form" onSubmit={handleSubmit}>
                <FormSection
                  title={translate('supporter.signup.form.title')}
                  description={translate('supporter.signup.form.description')}
                >
                  <div className="form-grid">
            <Field id="supporter-first-name" label={translate('supporter.signup.firstName')} required>
              <TextInput
                value={form.firstName}
                onChange={(event) => setForm((prev) => ({ ...prev, firstName: event.target.value }))}
                required
              />
            </Field>
            <Field id="supporter-last-name" label={translate('supporter.signup.lastName')}>
              <TextInput
                value={form.lastName}
                onChange={(event) => setForm((prev) => ({ ...prev, lastName: event.target.value }))}
              />
            </Field>
            <Field id="supporter-email" label={translate('supporter.signup.email')} required>
              <TextInput
                type="email"
                value={form.email}
                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                required
              />
            </Field>
            <Field id="supporter-phone" label={translate('supporter.signup.phone')}>
              <TextInput
                value={form.phone}
                onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
              />
            </Field>
            <Field id="supporter-type" label={translate('supporter.signup.registrationType')}>
              <Select
                value={form.supporterType}
                onChange={(value) => setForm((prev) => ({ ...prev, supporterType: value || 'Supporter' }))}
                data={supporterTypeOptions}
              />
            </Field>
            <Field id="supporter-gender" label={translate('supporter.signup.gender')}>
              <Select
                value={form.gender}
                onChange={(value) => setForm((prev) => ({ ...prev, gender: value || '' }))}
                data={genderOptions}
              />
            </Field>
            <Field id="supporter-age" label={translate('supporter.signup.age')}>
              <TextInput
                type="number"
                min="0"
                value={form.age}
                onChange={(event) => setForm((prev) => ({ ...prev, age: event.target.value }))}
              />
            </Field>
            <Field id="supporter-time" label={translate('supporter.signup.timeAvailability')}>
              <Select
                value={form.timeAvailability}
                onChange={(value) =>
                  setForm((prev) => ({ ...prev, timeAvailability: value || 'Unspecified' }))
                }
                data={availabilityOptions}
              />
            </Field>
            <Field id="supporter-address" label={translate('supporter.signup.address')}>
              <TextInput
                value={form.address}
                onChange={(event) => setForm((prev) => ({ ...prev, address: event.target.value }))}
              />
            </Field>
            <Field id="supporter-lat" label={translate('supporter.signup.latitude')}>
              <TextInput
                value={form.lat}
                onChange={(event) => setForm((prev) => ({ ...prev, lat: event.target.value }))}
              />
            </Field>
            <Field id="supporter-lon" label={translate('supporter.signup.longitude')}>
              <TextInput
                value={form.lon}
                onChange={(event) => setForm((prev) => ({ ...prev, lon: event.target.value }))}
              />
            </Field>
            <Field id="supporter-education-levels" label={translate('supporter.signup.educationLevels')}>
              <MultiSelect
                value={form.educationLevels}
                onChange={(value) => setForm((prev) => ({ ...prev, educationLevels: value }))}
                data={educationOptions}
                searchable
                placeholder={translate('supporter.signup.educationPlaceholder')}
              />
            </Field>
            <Field id="supporter-skills" label={translate('supporter.signup.skills')}>
              <MultiSelect
                value={form.skills}
                onChange={(value) => setForm((prev) => ({ ...prev, skills: value }))}
                data={skillOptions}
                searchable
                placeholder={translate('supporter.signup.skillsPlaceholder')}
              />
            </Field>
            <Field id="supporter-involvement" label={translate('supporter.signup.involvementAreas')}>
              <MultiSelect
                value={form.involvementAreas}
                onChange={(value) => setForm((prev) => ({ ...prev, involvementAreas: value }))}
                data={involvementAreaOptions}
                searchable
                placeholder={translate('supporter.signup.involvementPlaceholder')}
              />
            </Field>
            <Field id="supporter-about" label={translate('supporter.signup.about')}>
              <TextInput
                value={form.about}
                onChange={(event) => setForm((prev) => ({ ...prev, about: event.target.value }))}
              />
            </Field>
            <Field id="supporter-interests" label={translate('supporter.signup.interests')}>
              <MultiSelect
                value={form.interests}
                onChange={(value) => setForm((prev) => ({ ...prev, interests: value }))}
                data={interestOptions}
                placeholder={translate('supporter.signup.interestsPlaceholder')}
                searchable
              />
            </Field>
            <Field id="supporter-membership" label={translate('supporter.signup.membershipInterest')}>
              <Checkbox
                checked={form.interestedInMembership}
                onChange={(event) => {
                  const checked = event.currentTarget.checked
                  setForm((prev) => ({
                    ...prev,
                    interestedInMembership: checked,
                  }))
                }}
                label={translate('supporter.signup.membershipInterest.checkbox')}
              />
            </Field>
            <Field id="supporter-manifesto" label={translate('supporter.signup.manifesto')}>
              <Checkbox
                checked={form.agreesWithManifesto}
                onChange={(event) => {
                  const checked = event.currentTarget.checked
                  setForm((prev) => ({
                    ...prev,
                    agreesWithManifesto: checked,
                  }))
                }}
                label={translate('supporter.signup.manifesto.checkbox')}
              />
            </Field>
            <Field id="supporter-fb-group" label={translate('supporter.signup.community')}>
              <Checkbox
                checked={form.facebookGroupMember}
                onChange={(event) => {
                  const checked = event.currentTarget.checked
                  setForm((prev) => ({
                    ...prev,
                    facebookGroupMember: checked,
                  }))
                }}
                label={translate('supporter.signup.community.checkbox')}
              />
            </Field>
                  </div>
                </FormSection>
                <div className="form-actions">
                  <Button type="submit" loading={submitting}>
                    {submitting
                      ? translate('supporter.signup.submitting')
                      : translate('supporter.signup.submit')}
                  </Button>
                </div>
                <StatusMessage tone={statusTone} message={status} />
              </form>
            </div>
          </details>
        </div>

        {statusTone === 'success' ? (
          <details className="dashboard-detail supporter-signup-expander supporter-next-steps-expander" open>
            <summary>
              <span>{translate('supporter.signup.video.afterTitle')}</span>
            </summary>
            <div className="dashboard-detail__body supporter-post-submit">
              <div className="module-card supporter-video-card supporter-video-card--after">
                <p className="supporter-video-card__caption">
                  {translate('supporter.signup.video.thankYouCaption')}
                </p>
                {thankYouVideoEmbedUrl ? (
                  <div className="supporter-video-card__frame">
                    <iframe
                      src={thankYouVideoEmbedUrl}
                      title="Next steps video"
                      className="supporter-video-card__embed"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                ) : (
                  <div className="supporter-video-card__placeholder">
                    {translate('supporter.signup.video.placeholder')}
                  </div>
                )}
              </div>

              <div className="module-card supporter-thankyou-card supporter-thankyou-card--flow">
                <div className="supporter-thankyou-card__eyebrow">
                  {translate('supporter.signup.success.eyebrow')}
                </div>
                <div className="supporter-thankyou-card__intro">
                  <h3>{translate('supporter.signup.success.welcomeTitle')}</h3>
                  <p className="supporter-thankyou-card__lead">
                    {translate('supporter.signup.success.welcomeBody1')}
                  </p>
                </div>
                <p className="supporter-thankyou-card__lead">
                  {translate('supporter.signup.success.welcomeBody2')}
                </p>
                {recommendationsLoading ? (
                  <p className="muted">{translate('supporter.signup.success.loading')}</p>
                ) : null}
                {!recommendationsLoading ? (
                  <div className="supporter-thankyou-card__list">
                    <h4 className="supporter-thankyou-card__topics-title">
                      {translate('supporter.signup.success.topicsTitle')}
                    </h4>
                    {(recommendedConversations.length
                      ? recommendedConversations
                      : fallbackSuggestedConversations
                    ).map((conversation) => (
                      <article className="supporter-thankyou-card__item" key={conversation.id}>
                        {conversation.id && !conversation.isFallback ? (
                          <a
                            className="supporter-thankyou-card__topic-link"
                            href={buildConversationLink(conversation.id)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {conversation.topic ||
                              translate('supporter.signup.success.conversationFallback')}
                          </a>
                        ) : (
                          <span className="supporter-thankyou-card__topic-link">
                            {conversation.topic ||
                              translate('supporter.signup.success.conversationFallback')}
                          </span>
                        )}
                      </article>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </details>
        ) : null}
      </div>
    </section>
  )
}
