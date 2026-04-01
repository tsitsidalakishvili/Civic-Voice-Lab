import { useEffect, useMemo, useState } from 'react'
import { useTextTranslations } from '../hooks/useTextTranslations'
import { getJson } from '../services/api'
import { LanguageSelect, StatusMessage } from '../ui'
import { Line, Doughnut, Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js'

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
)

const REFRESH_INTERVAL_MS = 30000

const REPORT_COPY = {
  en: {
    liveDashboard: 'Live public dashboard',
    refreshing: 'Refreshing every 30s',
    surveySummary: 'Survey summary',
    heroDescription:
      'Public view of live survey participation, trend signals, consensus areas, and points of disagreement.',
    lastRefresh: 'Last refresh',
    participation: 'Participation',
    visitorsToVoters: 'Visitors who became voters',
    largestCluster: 'Largest cluster',
    participants: 'participants',
    waitingForData: 'Waiting for data',
    conversation: 'Conversation',
    highlightedStatements: 'highlighted statements',
    views: 'Views',
    surveyVisits: 'Survey page visits',
    participantsLabel: 'Participants',
    peopleWhoVoted: 'People who cast votes',
    comments: 'Comments',
    uniqueCommenters: 'unique commenters',
    voteDepth: 'Vote depth',
    totalVotes: 'total votes',
    voteDepthHint:
      'Average statement votes per person who voted (total votes ÷ participants).',
    participationTrend: 'Participation trend',
    participationTrendHint: 'Traffic, voting, and comment activity over time.',
    liveSeries: 'Live series',
    engagementSnapshot: 'Engagement snapshot',
    engagementSnapshotHint: 'How many visitors become participants and commenters.',
    viewToVoter: 'View to voter conversion',
    voterToCommenter: 'Voter to commenter conversion',
    potentialAgreements: 'Potential agreements',
    noBridgeStatements: 'No standout bridge statements yet.',
    mostAgreed: 'Most agreed',
    waitingConsensus: 'Waiting for stronger consensus',
    mostContested: 'Most contested',
    noMajorSplit: 'No major split yet',
    clusterRelationships: 'Cluster relationships',
    clusterRelationshipsHint: 'Negative values signal stronger disagreement between groups.',
    similarity: 'similarity',
    latestViewSpike: 'Latest view spike',
    noViewTrend: 'No view trend yet',
    latestVoteSpike: 'Latest vote spike',
    noVoteTrend: 'No vote trend yet',
    clusterSizes: 'Cluster sizes',
    clusterSizesHint: 'Relative size of opinion groups in the survey.',
    consensusLeaders: 'Consensus leaders',
    consensusLeadersHint: 'Statements that attracted the broadest agreement.',
    ranked: 'ranked',
    noConsensus: 'No consensus statements yet.',
    debateHotspots: 'Debate hotspots',
    debateHotspotsHint: 'Statements where participants are most split.',
    hotspots: 'hotspots',
    noHotspots: 'No polarizing statements yet.',
    opinionClusters: 'Opinion clusters',
    opinionClustersHint: 'Top agreement and disagreement signals by cluster.',
    topAgree: 'Top agree',
    noAgree: 'No standout agreement yet.',
    topDisagree: 'Top disagree',
    noDisagree: 'No standout disagreement yet.',
    consensus: 'Consensus',
    polarizing: 'Polarizing',
    responses: 'responses',
    agreement: 'Agreement',
    consensusScore: 'Consensus score',
    polarityScore: 'Polarity score',
    agree: 'Agree',
    disagree: 'Disagree',
    pass: 'Pass',
    live: 'Live',
  },
  ka: {
    liveDashboard: 'ცოცხალი საჯარო დაფა',
    refreshing: 'განახლება ყოველ 30 წამში',
    surveySummary: 'გამოკითხვის შეჯამება',
    heroDescription:
      'საჯარო ხედი გამოკითხვის ცოცხალ მონაწილეობაზე, ტრენდებზე, კონსენსუსის ზონებსა და აზრთა სხვადასხვაობაზე.',
    lastRefresh: 'ბოლო განახლება',
    participation: 'მონაწილეობა',
    visitorsToVoters: 'ვიზიტორებიდან ამომრჩევლებად ქცეული',
    largestCluster: 'ყველაზე დიდი კლასტერი',
    participants: 'მონაწილე',
    waitingForData: 'ველოდებით მონაცემებს',
    conversation: 'საუბარი',
    highlightedStatements: 'გამოკვეთილი განცხადება',
    views: 'ნახვები',
    surveyVisits: 'გამოკითხვის გვერდის ვიზიტები',
    participantsLabel: 'მონაწილეები',
    peopleWhoVoted: 'ხმის მიმცემი ადამიანები',
    comments: 'კომენტარები',
    uniqueCommenters: 'უნიკალური კომენტატორი',
    voteDepth: 'ხმის მიცემის სიღრმე',
    totalVotes: 'სულ ხმები',
    voteDepthHint:
      'საშუალო ხმები თითო ამომრჩეველზე, რომელმაც მონაწილეობა მიიღო (სულ ხმები ÷ მონაწილეები).',
    participationTrend: 'მონაწილეობის ტრენდი',
    participationTrendHint: 'დროში ტრაფიკი, ხმის მიცემა და კომენტარების აქტივობა.',
    liveSeries: 'ცოცხალი სერია',
    engagementSnapshot: 'ჩართულობის სურათი',
    engagementSnapshotHint: 'რამდენი ვიზიტორი ხდება მონაწილე და კომენტატორი.',
    viewToVoter: 'ნახვიდან ხმის მიცემამდე კონვერსია',
    voterToCommenter: 'ამომრჩევლიდან კომენტატორამდე კონვერსია',
    potentialAgreements: 'შესაძლო შეთანხმებები',
    noBridgeStatements: 'გამორჩეული დამაკავშირებელი განცხადებები ჯერ არ ჩანს.',
    mostAgreed: 'ყველაზე მეტად შეთანხმებული',
    waitingConsensus: 'უფრო ძლიერი კონსენსუსის მოლოდინში',
    mostContested: 'ყველაზე სადავო',
    noMajorSplit: 'მნიშვნელოვანი გაყოფა ჯერ არ ჩანს',
    clusterRelationships: 'კლასტერებს შორის კავშირები',
    clusterRelationshipsHint: 'უარყოფითი მნიშვნელობები ჯგუფებს შორის უფრო ძლიერ უთანხმოებას ნიშნავს.',
    similarity: 'მსგავსება',
    latestViewSpike: 'ბოლო ნახვების პიკი',
    noViewTrend: 'ნახვების ტრენდი ჯერ არ არის',
    latestVoteSpike: 'ბოლო ხმების პიკი',
    noVoteTrend: 'ხმების ტრენდი ჯერ არ არის',
    clusterSizes: 'კლასტერების ზომები',
    clusterSizesHint: 'გამოკითხვაში აზრის ჯგუფების შედარებითი ზომა.',
    consensusLeaders: 'კონსენსუსის ლიდერები',
    consensusLeadersHint: 'განცხადებები, რომლებმაც ყველაზე ფართო თანხმობა მოიზიდა.',
    ranked: 'რეიტინგში',
    noConsensus: 'კონსენსუსის განცხადებები ჯერ არ არის.',
    debateHotspots: 'დებატის ცხელი წერტილები',
    debateHotspotsHint: 'განცხადებები, რომლებზეც მონაწილეები ყველაზე მეტად იყოფიან.',
    hotspots: 'ცხელი წერტილი',
    noHotspots: 'პოლარიზებული განცხადებები ჯერ არ არის.',
    opinionClusters: 'აზრის კლასტერები',
    opinionClustersHint: 'კლასტერების მიხედვით თანხმობისა და უთანხმოების მთავარი სიგნალები.',
    topAgree: 'უმაღლესი თანხმობა',
    noAgree: 'გამორჩეული თანხმობა ჯერ არ არის.',
    topDisagree: 'უმაღლესი უთანხმოება',
    noDisagree: 'გამორჩეული უთანხმოება ჯერ არ არის.',
    consensus: 'კონსენსუსი',
    polarizing: 'პოლარიზებული',
    responses: 'პასუხი',
    agreement: 'თანხმობა',
    consensusScore: 'კონსენსუსის ქულა',
    polarityScore: 'პოლარობის ქულა',
    agree: 'ვეთანხმები',
    disagree: 'არ ვეთანხმები',
    pass: 'გავატარებ',
    live: 'ცოცხლად',
  },
}

const formatCompactNumber = (value, language = 'en') =>
  new Intl.NumberFormat(language || 'en', { notation: 'compact', maximumFractionDigits: 1 }).format(
    Number(value || 0),
  )

const formatPercent = (value) => `${Math.round(Number(value || 0) * 100)}%`

const formatTimestamp = (value) => {
  if (!value) return 'Live'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Live'
  return parsed.toLocaleString()
}

const normalizeDateLabel = (value) => {
  if (!value) return ''
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const combineActivitySeries = (stats) => {
  const sources = [
    { key: 'views_over_time', label: 'Views' },
    { key: 'votes_over_time', label: 'Votes' },
    { key: 'comments_over_time', label: 'Comments' },
  ]
  const dates = Array.from(
    new Set(
      sources.flatMap(({ key }) =>
        Array.isArray(stats?.[key]) ? stats[key].map((entry) => entry.date) : [],
      ),
    ),
  ).sort()
  return {
    labels: dates.map(normalizeDateLabel),
    datasets: sources.map(({ key, label }) => ({
      label,
      values: dates.map((date) => {
        const match = (stats?.[key] || []).find((entry) => entry.date === date)
        return Number(match?.count || 0)
      }),
    })),
  }
}

const buildStatementChart = (item) => ({
  labels: ['Agree', 'Disagree', 'Pass'],
  datasets: [
    {
      data: [item?.agree_count || 0, item?.disagree_count || 0, item?.pass_count || 0],
      backgroundColor: ['#22c55e', '#f97316', '#94a3b8'],
      borderWidth: 0,
    },
  ],
})

const activityChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'bottom',
      labels: { usePointStyle: true, boxWidth: 8 },
    },
  },
  scales: {
    x: { grid: { display: false } },
    y: { beginAtZero: true, ticks: { precision: 0 } },
  },
}

const barChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false } },
    y: { beginAtZero: true, max: 100 },
  },
}

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '70%',
  plugins: { legend: { display: false } },
}

const collectReportTexts = (report) => {
  const values = []
  const push = (...items) => {
    items.forEach((item) => {
      if (typeof item === 'string' && item.trim()) values.push(item)
    })
  }
  push(report?.name)
  push(...(report?.potential_agreements || []))
  ;(report?.metrics?.consensus || []).forEach((item) => push(item?.text))
  ;(report?.metrics?.polarizing || []).forEach((item) => push(item?.text))
  ;(report?.clusters || []).forEach((cluster) => {
    push(...(cluster?.top_agree || []))
    push(...(cluster?.top_disagree || []))
  })
  return Array.from(new Set(values))
}

function MetricCard({ label, value, detail, hint, tone = 'default' }) {
  return (
    <div className={`public-dashboard__metric public-dashboard__metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <span className="muted">{detail}</span>
      {hint ? <p className="public-dashboard__metric-hint">{hint}</p> : null}
    </div>
  )
}

function StatementCard({ item, tone, copy, translateReportText }) {
  const sentimentClass = tone === 'consensus' ? 'success' : 'warning'
  return (
    <article className={`public-dashboard__statement public-dashboard__statement--${tone}`}>
      <div className="public-dashboard__statement-head">
        <span className={`pill pill--${sentimentClass}`}>
          {tone === 'consensus' ? copy.consensus : copy.polarizing}
        </span>
        <span className="muted">
          {item.participation || 0} {copy.responses}
        </span>
      </div>
      <h4>{translateReportText(item.text)}</h4>
      <div className="public-dashboard__statement-meters">
        <div>
          <span>{copy.agreement}</span>
          <strong>{formatPercent(item.agreement_ratio)}</strong>
        </div>
        <div>
          <span>{copy.consensusScore}</span>
          <strong>{Math.round((item.consensus_score || 0) * 100)}</strong>
        </div>
        <div>
          <span>{copy.polarityScore}</span>
          <strong>{Math.round((item.polarity_score || 0) * 100)}</strong>
        </div>
      </div>
      <div className="public-dashboard__statement-chart">
        <Doughnut data={buildStatementChart(item)} options={doughnutOptions} />
      </div>
      <div className="public-dashboard__vote-split">
        <span>
          {copy.agree} {item.agree_count || 0}
        </span>
        <span>
          {copy.disagree} {item.disagree_count || 0}
        </span>
        <span>
          {copy.pass} {item.pass_count || 0}
        </span>
      </div>
    </article>
  )
}

function HeroStamp({ label, value, detail }) {
  return (
    <div className="public-dashboard__hero-stamp">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  )
}

export function DeliberationPublicReport({ shareId, t, language, languages, onLanguageChange }) {
  const translate = t || ((key) => key)
  const copy = REPORT_COPY[language] || REPORT_COPY.en
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastRefreshAt, setLastRefreshAt] = useState('')

  useEffect(() => {
    if (!shareId) return
    let cancelled = false

    const loadReport = async ({ withLoading = false } = {}) => {
      if (withLoading) setLoading(true)
      try {
        const payload = await getJson(`/reports/public/${shareId}`, {
          cacheMs: 0,
          forceRefresh: true,
        })
        if (cancelled) return
        setReport(payload?.payload || null)
        setError('')
        setLastRefreshAt(new Date().toISOString())
      } catch (err) {
        if (cancelled) return
        setError(err.message || 'Unable to load report.')
      } finally {
        if (!cancelled && withLoading) setLoading(false)
      }
    }

    loadReport({ withLoading: true })
    const timer = window.setInterval(() => {
      loadReport()
    }, REFRESH_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [shareId])

  const consensus = report?.metrics?.consensus || []
  const polarizing = report?.metrics?.polarizing || []
  const stats = report?.stats || {}
  const reportTexts = useMemo(() => collectReportTexts(report), [report])
  const { translateText: translateReportText } = useTextTranslations(reportTexts, language, {
    enabled: Boolean(reportTexts.length && language),
  })
  const activitySeries = useMemo(() => combineActivitySeries(stats), [stats])
  const activityData = useMemo(
    () => ({
      labels: activitySeries.labels,
      datasets: [
        {
          label: 'Views',
          data: activitySeries.datasets[0]?.values || [],
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.12)',
          fill: true,
          tension: 0.35,
        },
        {
          label: 'Votes',
          data: activitySeries.datasets[1]?.values || [],
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37, 99, 235, 0.12)',
          fill: true,
          tension: 0.35,
        },
        {
          label: 'Comments',
          data: activitySeries.datasets[2]?.values || [],
          borderColor: '#f97316',
          backgroundColor: 'rgba(249, 115, 22, 0.12)',
          fill: true,
          tension: 0.35,
        },
      ],
    }),
    [activitySeries],
  )
  const participationRate =
    stats.views > 0 ? Math.min(1, Number(stats.voters || 0) / Number(stats.views || 1)) : 0
  const commentRate =
    stats.voters > 0 ? Math.min(1, Number(stats.commenters || 0) / Number(stats.voters || 1)) : 0
  const clusterSizeData = useMemo(
    () => ({
      labels: (report?.clusters || []).map((cluster) => cluster.cluster_id),
      datasets: [
        {
          data: (report?.clusters || []).map((cluster) => Number(cluster.size || 0)),
          backgroundColor: ['#2563eb', '#7c3aed', '#f97316', '#14b8a6', '#e11d48'],
          borderRadius: 12,
        },
      ],
    }),
    [report?.clusters],
  )
  const largestCluster = useMemo(() => {
    const clusters = report?.clusters || []
    if (!clusters.length) return null
    return [...clusters].sort((a, b) => Number(b.size || 0) - Number(a.size || 0))[0]
  }, [report?.clusters])
  const latestViewsEntry = stats?.views_over_time?.length
    ? stats.views_over_time[stats.views_over_time.length - 1]
    : null
  const latestVotesEntry = stats?.votes_over_time?.length
    ? stats.votes_over_time[stats.votes_over_time.length - 1]
    : null
  const topConsensus = consensus[0] || null
  const topPolarizing = polarizing[0] || null

  return (
    <section className="public-report public-dashboard">
      <div className="page-language page-language--questionnaire">
        <LanguageSelect
          language={language}
          languages={languages}
          onLanguageChange={onLanguageChange}
          label={translate('language.label')}
        />
      </div>
      <header className="public-report__header public-dashboard__hero">
        <div className="public-dashboard__hero-copy">
          <div className="public-dashboard__hero-meta">
            <span className="pill">{copy.liveDashboard}</span>
            <span className="public-dashboard__live-dot">
              <span className="public-dashboard__live-pulse" />
              {copy.refreshing}
            </span>
          </div>
          <h2>{translateReportText(report?.name, copy.surveySummary) || copy.surveySummary}</h2>
          <p>{copy.heroDescription}</p>
        </div>
        <div className="public-dashboard__hero-side">
          <HeroStamp
            label={copy.lastRefresh}
            value={formatTimestamp(lastRefreshAt || report?.generated_at)}
          />
          <HeroStamp
            label={copy.participation}
            value={formatPercent(participationRate)}
            detail={copy.visitorsToVoters}
          />
          <HeroStamp
            label={copy.largestCluster}
            value={largestCluster ? `${largestCluster.cluster_id}` : copy.live}
            detail={
              largestCluster
                ? `${largestCluster.size} ${copy.participants}`
                : copy.waitingForData
            }
          />
          <HeroStamp
            label={copy.conversation}
            value={report?.conversation_id?.slice(0, 8) || copy.live}
            detail={`${consensus.length + polarizing.length} ${copy.highlightedStatements}`}
          />
        </div>
      </header>
      {loading ? (
        <div className="questionnaire-card questionnaire-card--empty">
          <h3>{translate('questionnaire.loadingTitle')}</h3>
          <p className="muted">{translate('questionnaire.loadingBody')}</p>
        </div>
      ) : null}
      <StatusMessage tone="error" message={error} />
      {report ? (
        <div className="stack report-stack public-dashboard__stack">
          <div className="public-dashboard__metrics">
            <MetricCard
              label={copy.views}
              value={formatCompactNumber(stats.views, language)}
              detail={copy.surveyVisits}
              tone="sky"
            />
            <MetricCard
              label={copy.participantsLabel}
              value={formatCompactNumber(stats.voters, language)}
              detail={copy.peopleWhoVoted}
              tone="blue"
            />
            <MetricCard
              label={copy.comments}
              value={formatCompactNumber(stats.comments, language)}
              detail={`${formatCompactNumber(stats.commenters, language)} ${copy.uniqueCommenters}`}
              tone="amber"
            />
            <MetricCard
              label={copy.voteDepth}
              value={stats.votes_per_participant ?? 0}
              detail={`${formatCompactNumber(stats.votes, language)} ${copy.totalVotes}`}
              hint={copy.voteDepthHint}
              tone="violet"
            />
          </div>

          <div className="public-dashboard__grid">
            <div className="module-card public-dashboard__card public-dashboard__card--trend">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.participationTrend}</h3>
                  <p className="muted">{copy.participationTrendHint}</p>
                </div>
                <div className="pill">{copy.liveSeries}</div>
              </div>
              <div className="public-dashboard__chart public-dashboard__chart--lg">
                <Line data={activityData} options={activityChartOptions} />
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--snapshot">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.engagementSnapshot}</h3>
                  <p className="muted">{copy.engagementSnapshotHint}</p>
                </div>
              </div>
              <div className="public-dashboard__mini-meters">
                <div className="public-dashboard__mini-meter">
                  <div className="public-dashboard__mini-meter-bar">
                    <span style={{ width: `${Math.max(participationRate * 100, 6)}%` }} />
                  </div>
                  <div className="public-dashboard__mini-meter-meta">
                    <strong>{formatPercent(participationRate)}</strong>
                    <span className="muted">{copy.viewToVoter}</span>
                  </div>
                </div>
                <div className="public-dashboard__mini-meter">
                  <div className="public-dashboard__mini-meter-bar public-dashboard__mini-meter-bar--warm">
                    <span style={{ width: `${Math.max(commentRate * 100, 6)}%` }} />
                  </div>
                  <div className="public-dashboard__mini-meter-meta">
                    <strong>{formatPercent(commentRate)}</strong>
                    <span className="muted">{copy.voterToCommenter}</span>
                  </div>
                </div>
              </div>
              <div className="public-dashboard__key-points">
                <h4>{copy.potentialAgreements}</h4>
                {report?.potential_agreements?.length ? (
                  <ul className="report-list">
                    {report.potential_agreements.slice(0, 5).map((item) => (
                      <li key={item}>{translateReportText(item)}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">{copy.noBridgeStatements}</p>
                )}
              </div>
              <div className="public-dashboard__snapshot-notes">
                <div className="public-dashboard__snapshot-note">
                  <span>{copy.mostAgreed}</span>
                  <strong>
                    {translateReportText(topConsensus?.text, copy.waitingConsensus) || copy.waitingConsensus}
                  </strong>
                </div>
                <div className="public-dashboard__snapshot-note">
                  <span>{copy.mostContested}</span>
                  <strong>{translateReportText(topPolarizing?.text, copy.noMajorSplit) || copy.noMajorSplit}</strong>
                </div>
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--relationships">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.clusterRelationships}</h3>
                  <p className="muted">{copy.clusterRelationshipsHint}</p>
                </div>
              </div>
              <div className="public-dashboard__similarity-list">
                {(report?.cluster_similarity || []).map((item) => {
                  const intensity = Math.min(Math.abs(Number(item.similarity || 0)) * 100, 100)
                  return (
                    <div className="public-dashboard__similarity-row" key={`${item.cluster_a}-${item.cluster_b}`}>
                      <div className="public-dashboard__similarity-meta">
                        <strong>
                          {item.cluster_a} vs {item.cluster_b}
                        </strong>
                        <span className="muted">
                          {Number(item.similarity || 0).toFixed(2)} {copy.similarity}
                        </span>
                      </div>
                      <div className="public-dashboard__similarity-bar">
                        <span style={{ width: `${Math.max(intensity, 8)}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="public-dashboard__activity-footer">
                <div>
                  <span>{copy.latestViewSpike}</span>
                  <strong>
                    {latestViewsEntry
                      ? `${normalizeDateLabel(latestViewsEntry.date)} · ${latestViewsEntry.count}`
                      : copy.noViewTrend}
                  </strong>
                </div>
                <div>
                  <span>{copy.latestVoteSpike}</span>
                  <strong>
                    {latestVotesEntry
                      ? `${normalizeDateLabel(latestVotesEntry.date)} · ${latestVotesEntry.count}`
                      : copy.noVoteTrend}
                  </strong>
                </div>
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--sizes">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.clusterSizes}</h3>
                  <p className="muted">{copy.clusterSizesHint}</p>
                </div>
              </div>
              <div className="public-dashboard__chart">
                <Bar data={clusterSizeData} options={barChartOptions} />
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--section">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.consensusLeaders}</h3>
                  <p className="muted">{copy.consensusLeadersHint}</p>
                </div>
                <div className="pill pill--success">{consensus.length} {copy.ranked}</div>
              </div>
              <div className="public-dashboard__statement-grid">
                {consensus.length ? (
                  consensus.slice(0, 2).map((item) => (
                    <StatementCard
                      key={item.id}
                      item={item}
                      tone="consensus"
                      copy={copy}
                      translateReportText={translateReportText}
                    />
                  ))
                ) : (
                  <p className="muted">{copy.noConsensus}</p>
                )}
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--section">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.debateHotspots}</h3>
                  <p className="muted">{copy.debateHotspotsHint}</p>
                </div>
                <div className="pill pill--warning">{polarizing.length} {copy.hotspots}</div>
              </div>
              <div className="public-dashboard__statement-grid">
                {polarizing.length ? (
                  polarizing.slice(0, 2).map((item) => (
                    <StatementCard
                      key={item.id}
                      item={item}
                      tone="polarizing"
                      copy={copy}
                      translateReportText={translateReportText}
                    />
                  ))
                ) : (
                  <p className="muted">{copy.noHotspots}</p>
                )}
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--full">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>{copy.opinionClusters}</h3>
                  <p className="muted">{copy.opinionClustersHint}</p>
                </div>
              </div>
              <div className="public-dashboard__cluster-grid">
                {(report?.clusters || []).map((cluster) => (
                  <article className="public-dashboard__cluster-card" key={cluster.cluster_id}>
                    <div className="public-dashboard__cluster-head">
                      <strong>{cluster.cluster_id}</strong>
                      <span className="pill">{cluster.size} participants</span>
                    </div>
                    <div>
                      <span className="public-dashboard__list-label">{copy.topAgree}</span>
                      {cluster.top_agree?.length ? (
                        <ul className="report-list">
                          {cluster.top_agree.slice(0, 3).map((item) => (
                            <li key={`${cluster.cluster_id}-agree-${item}`}>
                              {translateReportText(item)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">{copy.noAgree}</p>
                      )}
                    </div>
                    <div>
                      <span className="public-dashboard__list-label">{copy.topDisagree}</span>
                      {cluster.top_disagree?.length ? (
                        <ul className="report-list">
                          {cluster.top_disagree.slice(0, 3).map((item) => (
                            <li key={`${cluster.cluster_id}-disagree-${item}`}>
                              {translateReportText(item)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">{copy.noDisagree}</p>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
