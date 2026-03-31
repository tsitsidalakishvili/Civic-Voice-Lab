import { useEffect, useMemo, useState } from 'react'
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

const formatCompactNumber = (value) =>
  new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(
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

function MetricCard({ label, value, detail, tone = 'default' }) {
  return (
    <div className={`public-dashboard__metric public-dashboard__metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <span className="muted">{detail}</span>
    </div>
  )
}

function StatementCard({ item, tone }) {
  const sentimentClass = tone === 'consensus' ? 'success' : 'warning'
  return (
    <article className={`public-dashboard__statement public-dashboard__statement--${tone}`}>
      <div className="public-dashboard__statement-head">
        <span className={`pill pill--${sentimentClass}`}>
          {tone === 'consensus' ? 'Consensus' : 'Polarizing'}
        </span>
        <span className="muted">{item.participation || 0} responses</span>
      </div>
      <h4>{item.text}</h4>
      <div className="public-dashboard__statement-meters">
        <div>
          <span>Agreement</span>
          <strong>{formatPercent(item.agreement_ratio)}</strong>
        </div>
        <div>
          <span>Consensus score</span>
          <strong>{Math.round((item.consensus_score || 0) * 100)}</strong>
        </div>
        <div>
          <span>Polarity score</span>
          <strong>{Math.round((item.polarity_score || 0) * 100)}</strong>
        </div>
      </div>
      <div className="public-dashboard__statement-chart">
        <Doughnut data={buildStatementChart(item)} options={doughnutOptions} />
      </div>
      <div className="public-dashboard__vote-split">
        <span>Agree {item.agree_count || 0}</span>
        <span>Disagree {item.disagree_count || 0}</span>
        <span>Pass {item.pass_count || 0}</span>
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
            <span className="pill">Live public dashboard</span>
            <span className="public-dashboard__live-dot">
              <span className="public-dashboard__live-pulse" />
              Refreshing every 30s
            </span>
          </div>
          <h2>{report?.name || 'Survey summary'}</h2>
          <p>
            Public view of live survey participation, trend signals, consensus areas, and points of
            disagreement.
          </p>
        </div>
        <div className="public-dashboard__hero-side">
          <HeroStamp
            label="Last refresh"
            value={formatTimestamp(lastRefreshAt || report?.generated_at)}
          />
          <HeroStamp
            label="Participation"
            value={formatPercent(participationRate)}
            detail="Visitors who became voters"
          />
          <HeroStamp
            label="Largest cluster"
            value={largestCluster ? `${largestCluster.cluster_id}` : 'Live'}
            detail={largestCluster ? `${largestCluster.size} participants` : 'Waiting for data'}
          />
          <HeroStamp
            label="Conversation"
            value={report?.conversation_id?.slice(0, 8) || 'Live'}
            detail={`${consensus.length + polarizing.length} highlighted statements`}
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
              label="Views"
              value={formatCompactNumber(stats.views)}
              detail="Survey page visits"
              tone="sky"
            />
            <MetricCard
              label="Participants"
              value={formatCompactNumber(stats.voters)}
              detail="People who cast votes"
              tone="blue"
            />
            <MetricCard
              label="Comments"
              value={formatCompactNumber(stats.comments)}
              detail={`${formatCompactNumber(stats.commenters)} unique commenters`}
              tone="amber"
            />
            <MetricCard
              label="Vote depth"
              value={stats.votes_per_participant ?? 0}
              detail={`${formatCompactNumber(stats.votes)} total votes`}
              tone="violet"
            />
          </div>

          <div className="public-dashboard__grid">
            <div className="module-card public-dashboard__card public-dashboard__card--trend">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Participation trend</h3>
                  <p className="muted">Traffic, voting, and comment activity over time.</p>
                </div>
                <div className="pill">Live series</div>
              </div>
              <div className="public-dashboard__chart public-dashboard__chart--lg">
                <Line data={activityData} options={activityChartOptions} />
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--snapshot">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Engagement snapshot</h3>
                  <p className="muted">How many visitors become participants and commenters.</p>
                </div>
              </div>
              <div className="public-dashboard__mini-meters">
                <div className="public-dashboard__mini-meter">
                  <div className="public-dashboard__mini-meter-bar">
                    <span style={{ width: `${Math.max(participationRate * 100, 6)}%` }} />
                  </div>
                  <div className="public-dashboard__mini-meter-meta">
                    <strong>{formatPercent(participationRate)}</strong>
                    <span className="muted">View to voter conversion</span>
                  </div>
                </div>
                <div className="public-dashboard__mini-meter">
                  <div className="public-dashboard__mini-meter-bar public-dashboard__mini-meter-bar--warm">
                    <span style={{ width: `${Math.max(commentRate * 100, 6)}%` }} />
                  </div>
                  <div className="public-dashboard__mini-meter-meta">
                    <strong>{formatPercent(commentRate)}</strong>
                    <span className="muted">Voter to commenter conversion</span>
                  </div>
                </div>
              </div>
              <div className="public-dashboard__key-points">
                <h4>Potential agreements</h4>
                {report?.potential_agreements?.length ? (
                  <ul className="report-list">
                    {report.potential_agreements.slice(0, 5).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No standout bridge statements yet.</p>
                )}
              </div>
              <div className="public-dashboard__snapshot-notes">
                <div className="public-dashboard__snapshot-note">
                  <span>Most agreed</span>
                  <strong>{topConsensus?.text || 'Waiting for stronger consensus'}</strong>
                </div>
                <div className="public-dashboard__snapshot-note">
                  <span>Most contested</span>
                  <strong>{topPolarizing?.text || 'No major split yet'}</strong>
                </div>
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--relationships">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Cluster relationships</h3>
                  <p className="muted">Negative values signal stronger disagreement between groups.</p>
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
                        <span className="muted">{Number(item.similarity || 0).toFixed(2)} similarity</span>
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
                  <span>Latest view spike</span>
                  <strong>
                    {latestViewsEntry
                      ? `${normalizeDateLabel(latestViewsEntry.date)} · ${latestViewsEntry.count}`
                      : 'No view trend yet'}
                  </strong>
                </div>
                <div>
                  <span>Latest vote spike</span>
                  <strong>
                    {latestVotesEntry
                      ? `${normalizeDateLabel(latestVotesEntry.date)} · ${latestVotesEntry.count}`
                      : 'No vote trend yet'}
                  </strong>
                </div>
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--sizes">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Cluster sizes</h3>
                  <p className="muted">Relative size of opinion groups in the survey.</p>
                </div>
              </div>
              <div className="public-dashboard__chart">
                <Bar data={clusterSizeData} options={barChartOptions} />
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--section">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Consensus leaders</h3>
                  <p className="muted">Statements that attracted the broadest agreement.</p>
                </div>
                <div className="pill pill--success">{consensus.length} ranked</div>
              </div>
              <div className="public-dashboard__statement-grid">
                {consensus.length ? (
                  consensus.slice(0, 2).map((item) => (
                    <StatementCard key={item.id} item={item} tone="consensus" />
                  ))
                ) : (
                  <p className="muted">No consensus statements yet.</p>
                )}
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--section">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Debate hotspots</h3>
                  <p className="muted">Statements where participants are most split.</p>
                </div>
                <div className="pill pill--warning">{polarizing.length} hotspots</div>
              </div>
              <div className="public-dashboard__statement-grid">
                {polarizing.length ? (
                  polarizing.slice(0, 2).map((item) => (
                    <StatementCard key={item.id} item={item} tone="polarizing" />
                  ))
                ) : (
                  <p className="muted">No polarizing statements yet.</p>
                )}
              </div>
            </div>

            <div className="module-card public-dashboard__card public-dashboard__card--full">
              <div className="public-dashboard__section-head">
                <div>
                  <h3>Opinion clusters</h3>
                  <p className="muted">Top agreement and disagreement signals by cluster.</p>
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
                      <span className="public-dashboard__list-label">Top agree</span>
                      {cluster.top_agree?.length ? (
                        <ul className="report-list">
                          {cluster.top_agree.slice(0, 3).map((item) => (
                            <li key={`${cluster.cluster_id}-agree-${item}`}>{item}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">No standout agreement yet.</p>
                      )}
                    </div>
                    <div>
                      <span className="public-dashboard__list-label">Top disagree</span>
                      {cluster.top_disagree?.length ? (
                        <ul className="report-list">
                          {cluster.top_disagree.slice(0, 3).map((item) => (
                            <li key={`${cluster.cluster_id}-disagree-${item}`}>{item}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">No standout disagreement yet.</p>
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
