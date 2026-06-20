import { useEffect, useMemo, useState } from 'react'
import { Button, Checkbox, MultiSelect, Select, TextInput } from '@mantine/core'
import { getJson, requestJson } from '../services/api'
import { useTextTranslations } from '../hooks/useTextTranslations'
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
  'განათლება',
  'გარემოს დაცვა & ცხოველთა უფლებები',
  'დემოკრატიზაცია',
  'ემიგრაცია & დიასპორა',
  'კულტურა',
  'რეგიონული განვითარება & თვითმმართველობის საკითხები',
  'სოციალური პოლიტიკა',
  'საგარეო პოლიტიკა',
  'სტრატეგიული კომუნიკაცია, მედია და ანალიტიკა',
  'თავდაცვა და ეროვნული უსაფრთხოება',
  'საპროტესტო აქციებში მონაწილეობა',
  'საინფორმაციო და საგანმანათლებლო შეხვედრებში მონაწილეობა',
  'მხარდამჭერების მობილიზაცია',
  'ონლაინ კამპანიაში მონაწილეობა & ინფორმაციის გავრცელება',
  'თარგმნა',
]

const INTEREST_KEYWORDS = {
  'განათლება': ['განათლება', 'სკოლა', 'სტუდენტ', 'მასწავლებელი'],
  'გარემოს დაცვა & ცხოველთა უფლებები': ['გარემო', 'გარემოს დაცვა', 'ცხოველები', 'ეკოლოგია'],
  'დემოკრატიზაცია': ['დემოკრატია', 'დემოკრატიზაცია', 'არჩევნები'],
  'ემიგრაცია & დიასპორა': ['ემიგრაცია', 'დიასპორა', 'ემიგრანტები'],
  'კულტურა': ['კულტურა', 'ხელოვნება', 'კულტურული'],
  'რეგიონული განვითარება & თვითმმართველობის საკითხები': ['რეგიონი', 'თვითმმართველობა', 'რეგიონული'],
  'სოციალური პოლიტიკა': ['სოციალური', 'პოლიტიკა', 'სოციალური პოლიტიკა'],
  'საგარეო პოლიტიკა': ['საგარეო', 'პოლიტიკა', 'საგარეო პოლიტიკა'],
  'სტრატეგიული კომუნიკაცია, მედია და ანალიტიკა': ['კომუნიკაცია', 'მედია', 'ანალიტიკა'],
  'თავდაცვა და ეროვნული უსაფრთხოება': ['თავდაცვა', 'უსაფრთხოება', 'ეროვნული'],
  'საპროტესტო აქციებში მონაწილეობა': ['პროტესტი', 'აქცია', 'საპროტესტო'],
  'საინფორმაციო და საგანმანათლებლო შეხვედრებში მონაწილეობა': ['ინფორმაცია', 'განათლება', 'შეხვედრა'],
  'მხარდამჭერების მობილიზაცია': ['მობილიზაცია', 'მხარდამჭერები', 'მობილიზება'],
  'ონლაინ კამპანიაში მონაწილეობა & ინფორმაციის გავრცელება': ['ონლაინ', 'კამპანია', 'ინფორმაცია'],
  'თარგმნა': ['თარგმანი', 'თარგმნა', 'თარჯიმანი'],
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
  const getInitialSupporterType = () => {
    if (typeof window === 'undefined') return 'Supporter'
    const raw = new URLSearchParams(window.location.search).get('supporter_type') || ''
    return raw.toLowerCase().includes('member') ? 'Member' : 'Supporter'
  }
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    birthDate: '',
    email: '',
    phone: '',
    address: '',
    profession: '',
    socialMedia: '',
    formerPartyMember: '',
    timeAvailability: '',
    interests: [],
    whatsappGroup: '',
    interestedInMembership: '',
    additionalComments: '',
    agreesWithManifesto: false,
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
      { value: 'კვირის ნებისმიერ დღეს სამუშაო საათებში', label: 'კვირის ნებისმიერ დღეს სამუშაო საათებში' },
      { value: 'კვირის ნებისმიერ დღეს მხოლოდ არასამუშაო საათებში', label: 'კვირის ნებისმიერ დღეს მხოლოდ არასამუშაო საათებში' },
      { value: 'შაბათ-კვირას', label: 'შაბათ-კვირას' },
      { value: 'Other', label: 'Other' },
    ],
    [translate],
  )
  const interestOptions = useMemo(
    () =>
      INTEREST_VALUES.map((value) => ({
        value,
        label: value,
      })),
    [],
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
  const recommendedConversationTexts = useMemo(
    () => recommendedConversations.map((conversation) => conversation?.topic || ''),
    [recommendedConversations],
  )
  const { translateText: translateConversationText } = useTextTranslations(
    recommendedConversationTexts,
    language,
    { enabled: Boolean(recommendedConversationTexts.length && language) },
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
    if (!form.firstName.trim() || !form.lastName.trim() || !form.email.trim()) {
      setStatus('გთხოვთ, შეავსოთ სავალდებულო ველები: სახელი, გვარი და ელ. ფოსტა')
      setStatusTone('error')
      return
    }
    if (!form.agreesWithManifesto) {
      setStatus('გთხოვთ, დაეთანხმოთ მანიფესტს')
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
          birthDate: form.birthDate,
          email: form.email.trim(),
          phone: form.phone.trim(),
          address: form.address.trim(),
          profession: form.profession.trim(),
          socialMedia: form.socialMedia.trim(),
          formerPartyMember: form.formerPartyMember,
          timeAvailability: form.timeAvailability,
          interests: form.interests,
          whatsappGroup: form.whatsappGroup,
          interestedInMembership: form.interestedInMembership,
          additionalComments: form.additionalComments.trim(),
          agreesWithManifesto: !!form.agreesWithManifesto,
          inviteCode: inviteCode || '',
        },
      })
      setStatus('თქვენი განაცხადი წარმატებით გაიგზავნა! მადლობა დაინტერესებისთვის.')
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
        birthDate: '',
        email: '',
        phone: '',
        address: '',
        profession: '',
        socialMedia: '',
        formerPartyMember: '',
        timeAvailability: '',
        interests: [],
        whatsappGroup: '',
        interestedInMembership: '',
        additionalComments: '',
        agreesWithManifesto: false,
      }))
    } catch (err) {
      setStatus(err.message || 'შეცდომა განაცხადის გაგზავნისას. გთხოვთ, სცადოთ თავიდან.')
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
            <FormSection title="პერსონალური ინფორმაცია">
              <Field id="supporter-first-name" label="სახელი *" required>
                <TextInput
                  value={form.firstName}
                  onChange={(event) => setForm((prev) => ({ ...prev, firstName: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-last-name" label="გვარი *" required>
                <TextInput
                  value={form.lastName}
                  onChange={(event) => setForm((prev) => ({ ...prev, lastName: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-birth-date" label="დაბადების თარიღი *" required>
                <TextInput
                  type="date"
                  value={form.birthDate}
                  onChange={(event) => setForm((prev) => ({ ...prev, birthDate: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-phone" label="ტელეფონის ნომერი *" required>
                <TextInput
                  value={form.phone}
                  onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-email" label="ელ. ფოსტა *" required>
                <TextInput
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-address" label="საცხოვრებელი ადგილი (ქალაქი, ქუჩის ნომერი) *" required>
                <TextInput
                  value={form.address}
                  onChange={(event) => setForm((prev) => ({ ...prev, address: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-profession" label="პროფესია / საქმიანობის სფერო *" required>
                <TextInput
                  value={form.profession}
                  onChange={(event) => setForm((prev) => ({ ...prev, profession: event.target.value }))}
                  required
                />
              </Field>
              <Field id="supporter-social-media" label="სოციალური ქსელები (Facebook / Instagram) *" required>
                <TextInput
                  value={form.socialMedia}
                  onChange={(event) => setForm((prev) => ({ ...prev, socialMedia: event.target.value }))}
                  required
                />
              </Field>
            </FormSection>

            <FormSection title="გაგვეცანით">
              <Field id="supporter-former-party-member" label="ყოფილხართ თუ არა რომელიმე პოლიტიკური პარტიის წევრი? *" required>
                <Select
                  value={form.formerPartyMember}
                  onChange={(value) => setForm((prev) => ({ ...prev, formerPartyMember: value || '' }))}
                  data={[
                    { value: 'დიახ', label: 'დიახ' },
                    { value: 'არა', label: 'არა' },
                  ]}
                  required
                />
              </Field>
              <Field id="supporter-time-availability" label="რა დროს დაუთმობთ ჩვენს საქმიანობას ? *" required>
                <Select
                  value={form.timeAvailability}
                  onChange={(value) => setForm((prev) => ({ ...prev, timeAvailability: value || '' }))}
                  data={availabilityOptions}
                  required
                />
              </Field>
              <Field id="supporter-interests" label="გთხოვთ, მონიშნოთ თქვენთვის საინტერესო თემები და მიმართულებები: *" required>
                <MultiSelect
                  value={form.interests}
                  onChange={(value) => setForm((prev) => ({ ...prev, interests: value }))}
                  data={interestOptions}
                  placeholder="აირჩიეთ თემები"
                  searchable
                  required
                />
              </Field>
              <Field id="supporter-whatsapp-group" label="დაგამატოთ თუ არა WhatsApp მხარდამჭერთა ჯგუფში? *" required>
                <Select
                  value={form.whatsappGroup}
                  onChange={(value) => setForm((prev) => ({ ...prev, whatsappGroup: value || '' }))}
                  data={[
                    { value: 'დიახ', label: 'დიახ' },
                    { value: 'არა', label: 'არა' },
                  ]}
                  required
                />
              </Field>
              <Field id="supporter-membership-interest" label="გსურთ თუ არა ჩვენი პარტიის წევრობა? *" required>
                <Select
                  value={form.interestedInMembership}
                  onChange={(value) => setForm((prev) => ({ ...prev, interestedInMembership: value || '' }))}
                  data={[
                    { value: 'დიახ', label: 'დიახ' },
                    { value: 'არა', label: 'არა' },
                  ]}
                  required
                />
              </Field>
              <Field id="supporter-additional-comments" label="სივრცე დამატებითი კომენტარისთვის">
                <TextInput
                  value={form.additionalComments}
                  onChange={(event) => setForm((prev) => ({ ...prev, additionalComments: event.target.value }))}
                />
              </Field>
              <Field id="supporter-manifesto" label="გავეცანი &quot;თავისუფლების მოედნის&quot; მანიფესტს და სრულად ვიზიარებ მასში გაცხადებულ იდეებს. *" required>
                <Checkbox
                  checked={form.agreesWithManifesto}
                  onChange={(event) => {
                    const checked = event.currentTarget.checked
                    setForm((prev) => ({
                      ...prev,
                      agreesWithManifesto: checked,
                    }))
                  }}
                  label="ვეთანხმები მანიფესტს"
                  required
                />
              </Field>
            </FormSection>
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
                            {translateConversationText(
                              conversation.topic,
                              translate('supporter.signup.success.conversationFallback'),
                            )
                            ||
                              translate('supporter.signup.success.conversationFallback')}
                          </a>
                        ) : (
                          <span className="supporter-thankyou-card__topic-link">
                            {translateConversationText(
                              conversation.topic,
                              translate('supporter.signup.success.conversationFallback'),
                            )
                            ||
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
