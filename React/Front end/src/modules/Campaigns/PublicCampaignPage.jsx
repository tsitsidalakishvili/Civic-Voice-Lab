import { useEffect, useMemo, useState } from 'react'
import { getJson, requestJson } from '../../services/api'
import { Field, FormSection, StatusMessage } from '../../ui'

export function PublicCampaignPage({ campaignId, t }) {
  const [campaign, setCampaign] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [fundingSummary, setFundingSummary] = useState(null)
  const [milestones, setMilestones] = useState([])
  const [expenses, setExpenses] = useState([])
  const [proofArtifacts, setProofArtifacts] = useState([])
  const [partners, setPartners] = useState([])
  const [contributions, setContributions] = useState([])
  const [transparency, setTransparency] = useState(null)
  const [auditEvents, setAuditEvents] = useState([])
  const [volunteers, setVolunteers] = useState([])
  const [volunteerForm, setVolunteerForm] = useState({
    name: '',
    email: '',
    phone: '',
    role: '',
    notes: '',
  })
  const [volunteerStatus, setVolunteerStatus] = useState('')
  const [volunteerError, setVolunteerError] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({
    city: '',
    status: '',
    category: '',
    sortBy: 'progress',
  })
  const [contributionForm, setContributionForm] = useState({
    amount: '',
    currency: 'GEL',
    contributorName: '',
    contributorEmail: '',
    isAnonymous: false,
    donorVisibility: 'public',
    termsAccepted: false,
    privacyAccepted: false,
    note: '',
  })
  const [contributionStatus, setContributionStatus] = useState('')
  const [contributionError, setContributionError] = useState('')

  const isDetail = Boolean(campaignId)
  const settledContributions = useMemo(
    () =>
      contributions.filter(
        (item) => (item.paymentStatus || '').toLowerCase() === 'succeeded',
      ),
    [contributions],
  )
  const approvedExpenses = useMemo(
    () =>
      expenses.filter(
        (item) =>
          !item.approvalStatus ||
          (item.approvalStatus || '').toLowerCase() === 'approved',
      ),
    [expenses],
  )

  const publicCampaigns = useMemo(() => {
    const visible = campaigns.filter(
      (item) => (item.campaignVisibility || 'Public') === 'Public',
    )
    const filtered = visible.filter((item) => {
      const matchesCity = filters.city
        ? (item.locationCity || '')
            .toLowerCase()
            .includes(filters.city.toLowerCase())
        : true
      const matchesStatus = filters.status ? item.status === filters.status : true
      const matchesCategory = filters.category
        ? item.campaignCategory === filters.category
        : true
      return matchesCity && matchesStatus && matchesCategory
    })
    const sorted = [...filtered].sort((a, b) => {
      if (filters.sortBy === 'progress') {
        const aProgress = a.fundingTargetAmount
          ? (a.fundsRaisedAmount || 0) / a.fundingTargetAmount
          : 0
        const bProgress = b.fundingTargetAmount
          ? (b.fundsRaisedAmount || 0) / b.fundingTargetAmount
          : 0
        return bProgress - aProgress
      }
      if (filters.sortBy === 'target') {
        return (b.fundingTargetAmount || 0) - (a.fundingTargetAmount || 0)
      }
      return (a.name || '').localeCompare(b.name || '')
    })
    return sorted
  }, [campaigns, filters])

  useEffect(() => {
    if (isDetail) return
    setLoading(true)
    setError('')
    getJson('/crm/campaigns')
      .then((payload) => setCampaigns(Array.isArray(payload) ? payload : []))
      .catch((err) =>
        setError(err.message || 'Unable to load public campaigns.'),
      )
      .finally(() => setLoading(false))
  }, [isDetail])

  useEffect(() => {
    if (!campaignId) return
    setLoading(true)
    setError('')
    Promise.all([
      getJson(`/crm/campaigns/${campaignId}`),
      getJson(`/crm/campaigns/${campaignId}/funding-summary`).catch(() => null),
      getJson(`/crm/campaigns/${campaignId}/milestones`).catch(() => []),
      getJson(`/crm/campaigns/${campaignId}/expenses`).catch(() => []),
      getJson(`/crm/campaigns/${campaignId}/proof`).catch(() => []),
      getJson(`/crm/campaigns/${campaignId}/partners`).catch(() => []),
      getJson(`/crm/campaigns/${campaignId}/contributions`).catch(() => []),
      getJson(`/crm/campaigns/${campaignId}/transparency`).catch(() => null),
      getJson(`/crm/campaigns/${campaignId}/audit`).catch(() => []),
      getJson(`/crm/campaigns/${campaignId}/volunteers`).catch(() => []),
    ])
      .then(
        ([
          campaignPayload,
          fundingPayload,
          milestonesPayload,
          expensesPayload,
          proofPayload,
          partnersPayload,
          contributionsPayload,
          transparencyPayload,
          auditPayload,
          volunteerPayload,
        ]) => {
          setCampaign(campaignPayload)
          setFundingSummary(fundingPayload)
          setMilestones(Array.isArray(milestonesPayload) ? milestonesPayload : [])
          setExpenses(Array.isArray(expensesPayload) ? expensesPayload : [])
          setProofArtifacts(Array.isArray(proofPayload) ? proofPayload : [])
          setPartners(Array.isArray(partnersPayload) ? partnersPayload : [])
          setContributions(
            Array.isArray(contributionsPayload) ? contributionsPayload : [],
          )
          setTransparency(transparencyPayload)
          setAuditEvents(Array.isArray(auditPayload) ? auditPayload : [])
          setVolunteers(Array.isArray(volunteerPayload) ? volunteerPayload : [])
        },
      )
      .catch((err) => setError(err.message || 'Unable to load campaign.'))
      .finally(() => setLoading(false))
  }, [campaignId])

  const handleContributionSubmit = async (event) => {
    event.preventDefault()
    if (!campaignId) return
    const amountValue = Number(contributionForm.amount)
    if (!amountValue || amountValue <= 0) {
      setContributionError('Enter a valid amount.')
      return
    }
    if (!contributionForm.termsAccepted || !contributionForm.privacyAccepted) {
      setContributionError('Please accept the terms and privacy policy.')
      return
    }
    setContributionError('')
    setContributionStatus('')
    try {
      const checkout = await requestJson(
        `/crm/campaigns/${campaignId}/contributions/checkout`,
        {
          method: 'POST',
          payload: {
            amount: amountValue,
            currency: contributionForm.currency,
            contributorName: contributionForm.contributorName.trim(),
            contributorEmail: contributionForm.contributorEmail.trim(),
            isAnonymous:
              contributionForm.donorVisibility === 'anonymous' ||
              contributionForm.isAnonymous,
            donorVisibility: contributionForm.donorVisibility,
            termsAccepted: contributionForm.termsAccepted,
            privacyAccepted: contributionForm.privacyAccepted,
            note: contributionForm.note.trim(),
          },
        },
      )
      if (checkout?.contributionId) {
        await requestJson('/crm/payments/webhook', {
          method: 'POST',
          payload: {
            campaignId,
            contributionId: checkout.contributionId,
            paymentStatus: 'succeeded',
          },
        })
      }
      setContributionForm({
        amount: '',
        currency: contributionForm.currency,
        contributorName: '',
        contributorEmail: '',
        isAnonymous: false,
        donorVisibility: 'public',
        termsAccepted: false,
        privacyAccepted: false,
        note: '',
      })
      setContributionStatus('Thanks! Your contribution is recorded.')
      const [updatedSummary, updatedContributions] = await Promise.all([
        getJson(`/crm/campaigns/${campaignId}/funding-summary`).catch(() => null),
        getJson(`/crm/campaigns/${campaignId}/contributions`).catch(() => []),
      ])
      setFundingSummary(updatedSummary)
      setContributions(
        Array.isArray(updatedContributions) ? updatedContributions : [],
      )
    } catch (err) {
      setContributionError(err.message || 'Unable to record contribution.')
    }
  }

  const handleVolunteerSubmit = async (event) => {
    event.preventDefault()
    if (!campaignId) return
    if (!volunteerForm.name.trim()) {
      setVolunteerError('Enter your name.')
      return
    }
    setVolunteerError('')
    setVolunteerStatus('')
    try {
      await requestJson(`/crm/campaigns/${campaignId}/volunteers`, {
        method: 'POST',
        payload: {
          name: volunteerForm.name.trim(),
          email: volunteerForm.email.trim(),
          phone: volunteerForm.phone.trim(),
          role: volunteerForm.role.trim(),
          notes: volunteerForm.notes.trim(),
        },
      })
      setVolunteerForm({
        name: '',
        email: '',
        phone: '',
        role: '',
        notes: '',
      })
      setVolunteerStatus('Thanks for signing up.')
      const updatedVolunteers = await getJson(
        `/crm/campaigns/${campaignId}/volunteers`,
      ).catch(() => [])
      setVolunteers(Array.isArray(updatedVolunteers) ? updatedVolunteers : [])
    } catch (err) {
      setVolunteerError(err.message || 'Unable to submit volunteer info.')
    }
  }

  if (!isDetail) {
    return (
      <div className="public-campaign">
        <header className="public-campaign__header">
          <h1>{t?.('campaign.public.title') || 'Problem-Solving Campaigns'}</h1>
          <p className="muted">
            {t?.('campaign.public.subtitle') ||
              'Support local solutions with transparent, funded campaigns.'}
          </p>
        </header>
        <div className="module-card">
          <div className="form-grid">
            <input
              className="input"
              placeholder={t?.('campaign.public.filterCity') || 'Filter by city'}
              value={filters.city}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, city: event.target.value }))
              }
            />
            <select
              className="select"
              value={filters.status}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, status: event.target.value }))
              }
            >
              <option value="">
                {t?.('campaign.public.filterStatus') || 'All statuses'}
              </option>
              {Array.from(
                new Set(campaigns.map((item) => item.status || '')),
              )
                .filter(Boolean)
                .map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
            </select>
            <select
              className="select"
              value={filters.category}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, category: event.target.value }))
              }
            >
              <option value="">
                {t?.('campaign.public.filterCategory') || 'All categories'}
              </option>
              {Array.from(
                new Set(campaigns.map((item) => item.campaignCategory || '')),
              )
                .filter(Boolean)
                .map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
            </select>
            <select
              className="select"
              value={filters.sortBy}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, sortBy: event.target.value }))
              }
            >
              <option value="progress">
                {t?.('campaign.public.sortProgress') || 'Sort by % funded'}
              </option>
              <option value="target">
                {t?.('campaign.public.sortTarget') || 'Sort by target'}
              </option>
              <option value="name">
                {t?.('campaign.public.sortName') || 'Sort by name'}
              </option>
            </select>
          </div>
        </div>
        {error ? <div className="module-alert">{error}</div> : null}
        {loading ? <p className="muted">Loading campaigns…</p> : null}
        <div className="module-tiles">
          {publicCampaigns.map((item) => {
            const progress = item.fundingTargetAmount
              ? Math.min(
                  ((item.fundsRaisedAmount || 0) / item.fundingTargetAmount) *
                    100,
                  100,
                )
              : 0
            const link = `/?campaign_public=1&campaign_id=${encodeURIComponent(
              item.campaignId,
            )}`
            return (
              <a
                key={item.campaignId}
                href={link}
                className="module-tile"
                rel="noreferrer"
              >
                <div className="module-tile__header">
                  <h3>{item.name}</h3>
                  <span className="pill">{item.status || 'Funding'}</span>
                </div>
                <p className="muted">
                  {item.problemTitle || item.objective || 'Local problem solving'}
                </p>
                <div className="questionnaire-progress">
                  <div className="questionnaire-progress__track">
                    <div
                      className="questionnaire-progress__bar"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <span className="questionnaire-progress__label">
                    {progress.toFixed(0)}%
                  </span>
                </div>
                <div className="metric-row">
                  <span>{t?.('campaign.public.raised') || 'Raised'}</span>
                  <strong>
                    {(item.fundsRaisedAmount || 0).toLocaleString()}{' '}
                    {item.currency || 'GEL'}
                  </strong>
                </div>
              </a>
            )
          })}
        </div>
      </div>
    )
  }

  const displayCurrency =
    fundingSummary?.currency || campaign?.currency || 'GEL'
  const raisedAmount = Number(
    fundingSummary?.fundsRaisedAmount ?? campaign?.fundsRaisedAmount ?? 0,
  )
  const targetAmount = Number(
    fundingSummary?.fundingTargetAmount ?? campaign?.fundingTargetAmount ?? 0,
  )
  const fundingProgress = targetAmount
    ? Math.min((raisedAmount / targetAmount) * 100, 100)
    : 0
  const timelineStart = campaign?.executionStartDate || campaign?.startDate || '—'
  const timelineEnd =
    campaign?.expectedCompletionDate || campaign?.endDate || '—'
  const allocatedOperations =
    fundingSummary?.allocatedOperations ??
    fundingSummary?.allocated_operations ??
    0
  const allocatedExecution =
    fundingSummary?.allocatedExecution ??
    fundingSummary?.allocated_execution ??
    0

  return (
    <div className="public-campaign">
      {error ? <div className="module-alert">{error}</div> : null}
      {loading && !campaign ? <p className="muted">Loading campaign…</p> : null}
      {campaign && (
        <div className="stack">
          <header className="public-campaign__header">
            <div>
              <h1>{campaign.name}</h1>
              <p className="muted">
                {campaign.problemTitle || campaign.objective}
              </p>
            </div>
            <span className="pill">{campaign.status || 'Funding'}</span>
          </header>

          <div className="module-card">
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
            <div className="module-grid">
              <div className="metric-row">
                <span>{t?.('campaign.public.raised') || 'Raised'}</span>
                <strong>
                  {raisedAmount.toLocaleString()} {displayCurrency}
                </strong>
              </div>
              <div className="metric-row">
                <span>{t?.('campaign.public.target') || 'Target'}</span>
                <strong>
                  {targetAmount.toLocaleString()} {displayCurrency}
                </strong>
              </div>
              <div className="metric-row">
                <span>{t?.('campaign.public.contributors') || 'Contributors'}</span>
                <strong>{fundingSummary?.contributorCount ?? 0}</strong>
              </div>
            </div>
          </div>

          <div className="module-grid">
            <div className="module-card">
              <h3>{t?.('campaign.public.problem') || 'Problem statement'}</h3>
              <p className="muted">
                {campaign.problemDescription ||
                  campaign.objective ||
                  'Campaign problem statement not yet defined.'}
              </p>
              <div className="metric-row">
                <span>{t?.('campaign.public.location') || 'Location'}</span>
                <strong>
                  {[campaign.locationCity, campaign.locationDistrict]
                    .filter(Boolean)
                    .join(', ') || '—'}
                </strong>
              </div>
              <div className="metric-row">
                <span>{t?.('campaign.public.timeline') || 'Timeline'}</span>
                <strong>
                  {timelineStart} → {timelineEnd}
                </strong>
              </div>
            </div>
            <div className="module-card">
              <h3>{t?.('campaign.public.budget') || 'Budget breakdown'}</h3>
              <div className="metric-row">
                <span>{t?.('campaign.public.operationalFee') || 'Operational fee'}</span>
                <strong>
                  {campaign.operationalFeeAmount || 0} {displayCurrency}
                </strong>
              </div>
              <div className="metric-row">
                <span>{t?.('campaign.public.executionBudget') || 'Execution budget'}</span>
                <strong>
                  {campaign.executionBudgetAmount || 0} {displayCurrency}
                </strong>
              </div>
              <div className="metric-row">
                <span>
                  {t?.('campaign.public.allocatedOperations') ||
                    'Allocated to operations'}
                </span>
                <strong>
                  {allocatedOperations} {displayCurrency}
                </strong>
              </div>
              <div className="metric-row">
                <span>
                  {t?.('campaign.public.allocatedExecution') ||
                    'Allocated to execution'}
                </span>
                <strong>
                  {allocatedExecution} {displayCurrency}
                </strong>
              </div>
              <p className="muted">
                {t?.('campaign.public.budgetHint') ||
                  'Operations cover platform and verification costs.'}
              </p>
            </div>
          </div>

          {transparency ? (
            <div className="module-card">
              <h3>{t?.('campaign.public.transparency') || 'Transparency summary'}</h3>
              <div className="module-grid">
                <div className="metric-row">
                  <span>{t?.('campaign.public.spent') || 'Spent'}</span>
                  <strong>
                    {transparency.amountSpent} {displayCurrency}
                  </strong>
                </div>
                <div className="metric-row">
                  <span>{t?.('campaign.public.remaining') || 'Remaining'}</span>
                  <strong>
                    {transparency.remainingBalance} {displayCurrency}
                  </strong>
                </div>
                <div className="metric-row">
                  <span>{t?.('campaign.public.proofCount') || 'Proof items'}</span>
                  <strong>{transparency.proofCount}</strong>
                </div>
                <div className="metric-row">
                  <span>{t?.('campaign.public.expenseCount') || 'Expenses'}</span>
                  <strong>{transparency.expenseCount}</strong>
                </div>
              </div>
            </div>
          ) : null}

          <FormSection
            title={t?.('campaign.public.contribute') || 'Contribute now'}
            description={
              t?.('campaign.public.contributeDesc') ||
              'Support this problem-solving campaign directly.'
            }
          >
            {contributionError ? (
              <StatusMessage tone="error">{contributionError}</StatusMessage>
            ) : null}
            {contributionStatus ? (
              <StatusMessage tone="success">{contributionStatus}</StatusMessage>
            ) : null}
            <form className="stack" onSubmit={handleContributionSubmit}>
              <div className="form-grid">
                <Field
                  id="contribution-amount"
                  label={t?.('campaign.public.amount') || 'Amount'}
                  type="number"
                  min="0"
                  value={contributionForm.amount}
                  onChange={(event) =>
                    setContributionForm((prev) => ({
                      ...prev,
                      amount: event.target.value,
                    }))
                  }
                />
                <Field
                  id="contribution-currency"
                  label={t?.('campaign.public.currency') || 'Currency'}
                  as="select"
                  value={contributionForm.currency}
                  onChange={(event) =>
                    setContributionForm((prev) => ({
                      ...prev,
                      currency: event.target.value,
                    }))
                  }
                  options={[
                    { value: 'GEL', label: 'GEL' },
                    { value: 'USD', label: 'USD' },
                    { value: 'EUR', label: 'EUR' },
                  ]}
                />
              </div>
              <Field
                id="contribution-name"
                label={t?.('campaign.public.name') || 'Name'}
                value={contributionForm.contributorName}
                onChange={(event) =>
                  setContributionForm((prev) => ({
                    ...prev,
                    contributorName: event.target.value,
                  }))
                }
              />
              <Field
                id="contribution-email"
                label={t?.('campaign.public.email') || 'Email'}
                type="email"
                value={contributionForm.contributorEmail}
                onChange={(event) =>
                  setContributionForm((prev) => ({
                    ...prev,
                    contributorEmail: event.target.value,
                  }))
                }
              />
              <Field
                id="contribution-visibility"
                label={t?.('campaign.public.visibility') || 'Visibility'}
                as="select"
                value={contributionForm.donorVisibility}
                onChange={(event) =>
                  setContributionForm((prev) => ({
                    ...prev,
                    donorVisibility: event.target.value,
                  }))
                }
                options={[
                  { value: 'public', label: t?.('campaign.public.visibilityPublic') || 'Public' },
                  { value: 'anonymous', label: t?.('campaign.public.visibilityAnonymous') || 'Anonymous' },
                  { value: 'private', label: t?.('campaign.public.visibilityPrivate') || 'Private' },
                ]}
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
                {t?.('campaign.public.anonymous') || 'Contribute anonymously'}
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={contributionForm.termsAccepted}
                  onChange={(event) =>
                    setContributionForm((prev) => ({
                      ...prev,
                      termsAccepted: event.target.checked,
                    }))
                  }
                />
                {t?.('campaign.public.termsAccept') ||
                  'I agree to the donation terms'}
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={contributionForm.privacyAccepted}
                  onChange={(event) =>
                    setContributionForm((prev) => ({
                      ...prev,
                      privacyAccepted: event.target.checked,
                    }))
                  }
                />
                {t?.('campaign.public.privacyAccept') ||
                  'I agree to the privacy policy'}
              </label>
              <Field
                id="contribution-note"
                label={t?.('campaign.public.note') || 'Note'}
                as="textarea"
                value={contributionForm.note}
                onChange={(event) =>
                  setContributionForm((prev) => ({
                    ...prev,
                    note: event.target.value,
                  }))
                }
              />
              <button className="button" type="submit">
                {t?.('campaign.public.submit') || 'Submit contribution'}
              </button>
            </form>
          </FormSection>

          <FormSection
            title={t?.('campaign.public.volunteerTitle') || 'Join the workday'}
            description={
              t?.('campaign.public.volunteerDesc') ||
              'Volunteer for local action days and updates.'
            }
          >
            {volunteerError ? (
              <StatusMessage tone="error">{volunteerError}</StatusMessage>
            ) : null}
            {volunteerStatus ? (
              <StatusMessage tone="success">{volunteerStatus}</StatusMessage>
            ) : null}
            <form className="stack" onSubmit={handleVolunteerSubmit}>
              <Field
                id="volunteer-name"
                label={t?.('campaign.public.volunteerName') || 'Full name'}
                value={volunteerForm.name}
                onChange={(event) =>
                  setVolunteerForm((prev) => ({
                    ...prev,
                    name: event.target.value,
                  }))
                }
              />
              <div className="form-grid">
                <Field
                  id="volunteer-email"
                  label={t?.('campaign.public.volunteerEmail') || 'Email'}
                  value={volunteerForm.email}
                  onChange={(event) =>
                    setVolunteerForm((prev) => ({
                      ...prev,
                      email: event.target.value,
                    }))
                  }
                />
                <Field
                  id="volunteer-phone"
                  label={t?.('campaign.public.volunteerPhone') || 'Phone'}
                  value={volunteerForm.phone}
                  onChange={(event) =>
                    setVolunteerForm((prev) => ({
                      ...prev,
                      phone: event.target.value,
                    }))
                  }
                />
              </div>
              <Field
                id="volunteer-role"
                label={t?.('campaign.public.volunteerRole') || 'Preferred role'}
                value={volunteerForm.role}
                onChange={(event) =>
                  setVolunteerForm((prev) => ({
                    ...prev,
                    role: event.target.value,
                  }))
                }
              />
              <Field
                id="volunteer-notes"
                label={t?.('campaign.public.volunteerNotes') || 'Notes'}
                as="textarea"
                value={volunteerForm.notes}
                onChange={(event) =>
                  setVolunteerForm((prev) => ({
                    ...prev,
                    notes: event.target.value,
                  }))
                }
              />
              <button className="button" type="submit">
                {t?.('campaign.public.volunteerSubmit') || 'Join'}
              </button>
            </form>
            {volunteers.length > 0 ? (
              <p className="muted">
                {t?.('campaign.public.volunteerCount') || 'Volunteers'}:{' '}
                {volunteers.length}
              </p>
            ) : null}
          </FormSection>

          <div className="module-card">
            <h3>{t?.('campaign.public.timelineLog') || 'Timeline activity'}</h3>
            {auditEvents.length === 0 ? (
              <p className="muted">
                {t?.('campaign.public.noTimeline') || 'No activity yet.'}
              </p>
            ) : (
              <ul className="compact-list">
                {auditEvents.slice(0, 8).map((event, idx) => (
                  <li key={`${event.eventType}-${idx}`}>
                    {event.summary}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="module-grid">
            <div className="module-card">
              <h3>{t?.('campaign.public.milestones') || 'Milestones'}</h3>
              {milestones.length === 0 ? (
                <p className="muted">
                  {t?.('campaign.public.noMilestones') || 'No milestones yet.'}
                </p>
              ) : (
                <ul className="compact-list">
                  {milestones.map((milestone) => (
                    <li key={milestone.milestoneId}>
                      {milestone.title} — {milestone.status}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="module-card">
              <h3>{t?.('campaign.public.expenses') || 'Budget spent so far'}</h3>
              {approvedExpenses.length === 0 ? (
                <p className="muted">
                  {t?.('campaign.public.noExpenses') || 'No expenses yet.'}
                </p>
              ) : (
                <ul className="compact-list">
                  {approvedExpenses.map((expense) => (
                    <li key={expense.expenseId}>
                      {expense.category} — {expense.amount} {expense.currency}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="module-grid">
            <div className="module-card">
              <h3>{t?.('campaign.public.proof') || 'Proof of work'}</h3>
              {proofArtifacts.length === 0 ? (
                <p className="muted">
                  {t?.('campaign.public.noProof') || 'No proof uploaded yet.'}
                </p>
              ) : (
                <ul className="compact-list">
                  {proofArtifacts.map((artifact) => (
                    <li key={artifact.proofId}>
                      {artifact.artifactType} — {artifact.caption || artifact.url}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="module-card">
              <h3>{t?.('campaign.public.partners') || 'Partners'}</h3>
              {partners.length === 0 ? (
                <p className="muted">
                  {t?.('campaign.public.noPartners') || 'No partners listed yet.'}
                </p>
              ) : (
                <ul className="compact-list">
                  {partners.map((partner) => (
                    <li key={partner.partnerId}>
                      {partner.name} — {partner.role || 'Partner'}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="module-card">
            <h3>{t?.('campaign.public.recentSupport') || 'Recent support'}</h3>
            {settledContributions.length === 0 ? (
              <p className="muted">
                {t?.('campaign.public.noContributions') ||
                  'Be the first to contribute.'}
              </p>
            ) : (
              <ul className="compact-list">
                {settledContributions.slice(0, 5).map((contrib) => (
                  <li key={contrib.contributionId}>
                    {contrib.isAnonymous
                      ? t?.('campaign.public.anonymousLabel') || 'Anonymous'
                      : contrib.contributorName || 'Supporter'}{' '}
                    — {contrib.amount} {contrib.currency}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
