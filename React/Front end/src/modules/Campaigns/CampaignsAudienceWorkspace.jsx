import React, { useMemo, useRef, useState } from 'react'
import Papa from 'papaparse'
import { IconBolt, IconBrandInstagram, IconBrandTiktok, IconBrandX, IconChartDots, IconUsers } from '@tabler/icons-react'
import { CivicStatGrid, StatusMessage } from '../../ui'
import {
  CAMPAIGN_FORMATS,
  NICHES,
  buildSnapshot,
  computeTrend,
  formatCompact,
  inferNiche,
  influenceTierFor,
  initials,
  matchCreators,
  projectCampaign,
  rosterSummary,
  rosterToRows,
  rowsToRoster,
  seedRoster,
} from './talentMatchData'
import './talentmatch.css'

const SNAPSHOT_KEY = 'tm-follower-snapshots-v1'

// Snapshot history is persisted in the browser so follower-trend arrows reflect
// real change over time rather than fabricated deltas.
function loadSnapshots() {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    const raw = window.localStorage.getItem(SNAPSHOT_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function persistSnapshots(snapshots) {
  if (typeof window === 'undefined' || !window.localStorage) return
  try {
    window.localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshots))
  } catch {
    /* storage full or blocked — trends simply stay unavailable */
  }
}

// Stock-ticker style follower-trend indicator.
function TrendCell({ trend }) {
  if (!trend) return <span className="tm-trend tm-trend-new">· new</span>
  const glyph = trend.dir === 'up' ? '▲' : trend.dir === 'down' ? '▼' : '▬'
  const sign = trend.pct > 0 ? '+' : ''
  return (
    <span className={`tm-trend tm-trend-${trend.dir}`} title={`vs snapshot ${trend.days}d ago`}>
      <span className="tm-trend-arrow">{glyph}</span>
      {sign}
      {trend.pct}%<span className="tm-trend-days">{trend.days}d</span>
    </span>
  )
}

const TABS = [
  { id: 'match', label: 'Match' },
  { id: 'roster', label: 'Roster' },
]

const FORMAT_OPTIONS = Object.entries(CAMPAIGN_FORMATS).map(([value, cfg]) => ({
  value,
  label: cfg.label,
}))

const COUNT_OPTIONS = [
  { value: 3, label: 'Top 3' },
  { value: 6, label: 'Top 6' },
  { value: 10, label: 'Top 10' },
]

function normalizeTab(tab) {
  return TABS.some((t) => t.id === tab) ? tab : 'match'
}

function scoreClass(score) {
  if (score >= 80) return 'tm-score-great'
  if (score >= 65) return 'tm-score-good'
  return 'tm-score-ok'
}

export function CampaignsAudienceWorkspace({
  activeTabOverride,
  onTabChange,
  showTabs = false,
  showIntro = false,
}) {
  const [roster, setRoster] = useState(() => seedRoster())
  // Standalone (showTabs) tab clicks are tracked locally; in the shell the
  // sidebar drives the tab through activeTabOverride, so pendingTab stays null.
  const [pendingTab, setPendingTab] = useState(null)

  // Match tab state
  const [campaignInput, setCampaignInput] = useState('')
  const [formatKey, setFormatKey] = useState('reel')
  const [numRecs, setNumRecs] = useState(6)
  const [analysis, setAnalysis] = useState(null)
  const [matchError, setMatchError] = useState('')

  // Roster tab state
  const [filterNiche, setFilterNiche] = useState('all')
  const [search, setSearch] = useState('')
  const [importStatus, setImportStatus] = useState(null)
  const [refreshStatus, setRefreshStatus] = useState(null)
  const [snapshots, setSnapshots] = useState(() => loadSnapshots())
  const fileInputRef = useRef(null)

  const activeTab = normalizeTab(pendingTab || activeTabOverride)

  const selectTab = (tabId) => {
    setPendingTab(tabId)
    onTabChange?.(tabId)
  }

  const summary = useMemo(() => rosterSummary(roster), [roster])

  const pulseItems = useMemo(
    () => [
      { label: 'Messengers', value: String(summary.count), icon: <IconUsers size={18} />, color: 'civic' },
      { label: 'Combined reach', value: formatCompact(summary.totalReach), icon: <IconChartDots size={18} />, color: 'blue' },
      { label: 'Avg engagement', value: `${summary.avgEng}%`, icon: <IconBolt size={18} />, color: 'orange' },
      { label: 'On X / TikTok', value: String(summary.withX + summary.withTikTok), icon: <IconBrandX size={18} />, color: 'grape' },
    ],
    [summary],
  )

  const filteredRoster = useMemo(() => {
    const term = search.trim().toLowerCase()
    return roster
      .filter((r) => filterNiche === 'all' || r.niche === filterNiche)
      .filter((r) => !term || r.name.toLowerCase().includes(term))
      .sort((a, b) => b.total - a.total)
  }, [roster, filterNiche, search])

  const runMatch = () => {
    const input = campaignInput.trim()
    if (!input) {
      setMatchError('Enter a campaign, issue, or cause to analyze.')
      return
    }
    setMatchError('')
    const niche = inferNiche(input)
    const matches = matchCreators(roster, niche, input, numRecs)
    const top = matches[0]
    const note = top
      ? `Detected issue area: ${niche}. Strongest messenger is ${top.name} (${top.score}% fit, ${formatCompact(
          top.total,
        )} reach). Matching runs locally on your roster — connect an AI backend for live issue research.`
      : `Detected issue area: ${niche}. No messengers in the current roster to match — import a roster first.`
    setAnalysis({ brandName: input, niche, matches, formatKey, note })
  }

  const handleImportClick = () => fileInputRef.current?.click()

  const handleImportFile = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    Papa.parse(file, {
      skipEmptyLines: true,
      complete: (result) => {
        try {
          const next = rowsToRoster(result.data)
          if (!next.length) {
            setImportStatus({ tone: 'error', message: 'No rows found. Expected columns: Name, Instagram, IG Followers, TikTok, TT Followers, X/Twitter, X Followers, Eng%, Niche.' })
            return
          }
          setRoster(next)
          setFilterNiche('all')
          setSearch('')
          setImportStatus({ tone: 'success', message: `Imported ${next.length} messengers.` })
        } catch (err) {
          setImportStatus({ tone: 'error', message: `Import failed: ${err.message}` })
        }
      },
      error: (err) => setImportStatus({ tone: 'error', message: `Import failed: ${err.message}` }),
    })
    event.target.value = ''
  }

  const handleExport = () => {
    const csv = Papa.unparse(rosterToRows(roster))
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'messenger-roster.csv'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handleRefresh = () => {
    setRefreshStatus({
      tone: 'info',
      message:
        'Live follower refresh runs server-side (Instagram / TikTok via Apify) and is not configured in this build. Import an updated CSV to refresh figures for now.',
    })
  }

  const handleRecordSnapshot = () => {
    const next = [...snapshots, buildSnapshot(roster)].slice(-24) // keep last 24 snapshots
    persistSnapshots(next)
    setSnapshots(next)
    const when = new Date().toLocaleDateString()
    setRefreshStatus({
      tone: 'success',
      message:
        snapshots.length === 0
          ? `Baseline snapshot recorded (${when}). Import updated follower figures later and trend arrows will show the real change.`
          : `Snapshot #${next.length} recorded (${when}). Trend arrows now compare against the latest history.`,
    })
  }

  const renderMatch = () => {
    const projection = analysis ? projectCampaign(analysis.matches, analysis.formatKey) : null
    return (
      <div className="tm-layout">
        <aside className="module-card tm-rail">
          <div>
            <h3>Find messengers for your campaign</h3>
            <p className="muted" style={{ fontSize: 12.5 }}>
              Enter a campaign, issue, or cause. We infer the issue area and rank the messengers best placed to amplify it, with reach projections.
            </p>
          </div>

          <div className="tm-field">
            <label className="tm-field-label" htmlFor="tm-brand">Campaign, issue, or cause</label>
            <input
              id="tm-brand"
              className="tm-input"
              type="text"
              placeholder="e.g. EU integration  ·  healthcare reform  ·  get-out-the-vote"
              value={campaignInput}
              onChange={(e) => setCampaignInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') runMatch()
              }}
            />
          </div>

          <div className="tm-field">
            <label className="tm-field-label" htmlFor="tm-format">Content format</label>
            <select id="tm-format" className="tm-select" value={formatKey} onChange={(e) => setFormatKey(e.target.value)}>
              {FORMAT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="tm-field">
            <label className="tm-field-label" htmlFor="tm-count">Number of recommendations</label>
            <select id="tm-count" className="tm-select" value={numRecs} onChange={(e) => setNumRecs(Number(e.target.value))}>
              {COUNT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <button className="tm-analyze" type="button" onClick={runMatch}>Analyze &amp; Match</button>
          {matchError ? <StatusMessage tone="error" message={matchError} /> : null}

          {analysis ? (
            <div className="tm-ai-box">
              <div className="tm-ai-box-label">Campaign analysis</div>
              <div>{analysis.note}</div>
            </div>
          ) : null}

          <div className="tm-how">
            <strong>How projections work</strong><br />
            Reach = avg views × format multiplier (Reel ×1.9, Post ×1.0, Story ×0.5, Collab ×2.8).<br />
            Engagement = followers × eng rate × format bonus.<br />
            Clicks = format CTR × engagements (Story 15%, Collab 18%, Post 10%, Reel 8%).
          </div>
        </aside>

        <section>
          {!analysis ? (
            <div className="tm-empty">
              <div className="tm-empty-icon">◎</div>
              <div className="tm-empty-title">No analysis yet</div>
              <div className="tm-empty-sub">Enter a campaign, issue, or cause and click Analyze to get matched messengers with reach projections.</div>
            </div>
          ) : (
            <>
              <div className="tm-results-head">
                <span className="tm-results-brand">{analysis.brandName}</span>
                <span className={`tm-niche tm-niche-${analysis.niche}`}>{analysis.niche}</span>
                <span className="tm-results-meta">
                  {projection.format.label} · {analysis.matches.length} messengers
                </span>
              </div>

              <div className="tm-proj-grid">
                <div className="tm-proj-card reach">
                  <div className="tm-proj-lbl">Estimated reach</div>
                  <div className="tm-proj-val">{formatCompact(projection.reach)}</div>
                  <div className="tm-proj-sub">Total views across {analysis.matches.length} posts · ×{projection.format.reach} multiplier</div>
                </div>
                <div className="tm-proj-card eng">
                  <div className="tm-proj-lbl">Estimated engagement</div>
                  <div className="tm-proj-val">{formatCompact(projection.eng)}</div>
                  <div className="tm-proj-sub">Likes, comments &amp; shares · {projection.engRate}% rate</div>
                </div>
                <div className="tm-proj-card clicks">
                  <div className="tm-proj-lbl">Estimated clicks</div>
                  <div className="tm-proj-val">{formatCompact(projection.clicks)}</div>
                  <div className="tm-proj-sub">Profile visits &amp; link clicks · {(projection.format.click * 100).toFixed(0)}% CTR</div>
                </div>
              </div>

              <div className="tm-how-calc">
                <strong>Projection formula:</strong> Reach = avg views × {projection.format.reach} ({projection.format.label}).
                Engagement = followers × eng% × {projection.format.eng}. Clicks = {(projection.format.click * 100).toFixed(0)}% of engagements.
              </div>

              <div className="tm-sec-label">Best-matched messengers</div>
              <div className="tm-inf-grid">
                {analysis.matches.map((creator, i) => {
                  const voucher = influenceTierFor(creator.total)
                  return (
                    <div key={creator.name} className={`tm-inf-card ${i < 2 ? 'top' : ''}`}>
                      {i < 2 ? <div className="tm-top-badge">Top pick</div> : null}
                      <div className="tm-inf-head">
                        <div>
                          <div className="tm-inf-name">{creator.name}</div>
                          <span className={`tm-niche tm-niche-${creator.niche}`}>{creator.niche}</span>{' '}
                          <span className={`tm-data-tag ${creator.real ? 'tm-data-real' : 'tm-data-est'}`}>
                            {creator.real ? 'REAL' : 'estimated'}
                          </span>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className={`tm-score-num ${scoreClass(creator.score)}`}>{creator.score}%</div>
                          <div className="tm-score-lbl">match</div>
                        </div>
                      </div>
                      <div className="tm-reason">{creator.reason}</div>
                      <div className="tm-metrics">
                        <div className="tm-metric">
                          <div className="tm-metric-val">{formatCompact(creator.total)}</div>
                          <div className="tm-metric-lbl">Followers</div>
                        </div>
                        <div className="tm-metric">
                          <div className="tm-metric-val">{formatCompact(Math.round(creator.avgViews * projection.format.reach))}</div>
                          <div className="tm-metric-lbl">Est. views</div>
                        </div>
                        <div className="tm-metric">
                          <div className="tm-metric-val">{formatCompact(Math.round(creator.total * (creator.eng / 100) * projection.format.eng))}</div>
                          <div className="tm-metric-lbl">Est. eng.</div>
                        </div>
                      </div>
                      <div className="tm-plat-row">
                        {creator.igF ? <span>IG {formatCompact(creator.igF)}</span> : null}
                        {creator.ttF ? <span>TT {formatCompact(creator.ttF)}</span> : null}
                        {creator.xF ? <span>X {formatCompact(creator.xF)}</span> : null}
                        <span style={{ marginLeft: 'auto' }}>{creator.eng}% eng</span>
                      </div>
                      <div className="tm-links">
                        {creator.ig ? <a className="tm-link-btn" href={creator.ig} target="_blank" rel="noreferrer">Instagram</a> : null}
                        {creator.tt ? <a className="tm-link-btn" href={creator.tt} target="_blank" rel="noreferrer">TikTok</a> : null}
                        {creator.x ? <a className="tm-link-btn" href={creator.x} target="_blank" rel="noreferrer">X / Twitter</a> : null}
                      </div>
                      {voucher ? (
                        <div className="tm-voucher">
                          <div>
                            <div className="tm-voucher-tier">{voucher.tier} voice</div>
                            <div className="tm-voucher-brands">{voucher.reach}</div>
                          </div>
                          <div className="tm-voucher-value">{formatCompact(creator.total)}</div>
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </section>
      </div>
    )
  }

  const renderRoster = () => (
    <div className="stack" style={{ display: 'grid', gap: 16 }}>
      <CivicStatGrid title="Roster pulse" items={pulseItems} />

      <div className="module-card">
        <div className="card-header">
          <div>
            <h3>Messenger roster</h3>
            <p className="muted">{filteredRoster.length} of {roster.length} messengers</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="button-secondary" type="button" onClick={handleImportClick}>Import CSV</button>
            <button className="button-secondary" type="button" onClick={handleExport}>Export CSV</button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              style={{ display: 'none' }}
              onChange={handleImportFile}
            />
          </div>
        </div>

        {importStatus ? <StatusMessage tone={importStatus.tone} message={importStatus.message} /> : null}

        <div className="filter-row" style={{ marginTop: 12, alignItems: 'center' }}>
          <button
            type="button"
            className={`button-secondary button-secondary--small ${filterNiche === 'all' ? 'is-active' : ''}`}
            aria-pressed={filterNiche === 'all'}
            onClick={() => setFilterNiche('all')}
          >
            All
          </button>
          {NICHES.map((niche) => (
            <button
              key={niche}
              type="button"
              className={`button-secondary button-secondary--small ${filterNiche === niche ? 'is-active' : ''}`}
              aria-pressed={filterNiche === niche}
              onClick={() => setFilterNiche(niche)}
              style={{ textTransform: 'capitalize' }}
            >
              {niche}
            </button>
          ))}
          <input
            className="tm-search"
            style={{ marginLeft: 'auto' }}
            type="text"
            placeholder="Search messengers…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="tm-table-wrap" style={{ marginTop: 12 }}>
          <table className="tm-table">
            <thead>
              <tr>
                <th>Messenger</th>
                <th>Topic</th>
                <th>Total</th>
                <th>Trend</th>
                <th>Instagram</th>
                <th>TikTok</th>
                <th>X</th>
                <th>Eng%</th>
                <th>Tier</th>
                <th>Data</th>
                <th>Links</th>
              </tr>
            </thead>
            <tbody>
              {filteredRoster.map((r) => {
                const voucher = influenceTierFor(r.total)
                return (
                  <tr key={r.name}>
                    <td>
                      <span style={{ display: 'flex', alignItems: 'center' }}>
                        <span className={`tm-av tm-av-${r.niche}`}>{initials(r.name)}</span>
                        <span className="tm-name">{r.name}</span>
                      </span>
                    </td>
                    <td><span className={`tm-niche tm-niche-${r.niche}`}>{r.niche}</span></td>
                    <td>{formatCompact(r.total)}</td>
                    <td><TrendCell trend={computeTrend(r, snapshots)} /></td>
                    <td>{r.igF ? formatCompact(r.igF) : '—'}</td>
                    <td>{r.ttF ? formatCompact(r.ttF) : '—'}</td>
                    <td>{r.xF ? formatCompact(r.xF) : '—'}</td>
                    <td>{r.eng}%</td>
                    <td>{voucher ? voucher.tier : '—'}</td>
                    <td><span className={`tm-data-tag ${r.real ? 'tm-data-real' : 'tm-data-est'}`}>{r.real ? 'REAL' : 'est'}</span></td>
                    <td>
                      {r.ig ? (
                        <a className="tm-tlink tm-tlink-icon" href={r.ig} target="_blank" rel="noreferrer" aria-label={`${r.name} on Instagram`} title="Instagram">
                          <IconBrandInstagram size={16} stroke={1.8} />
                        </a>
                      ) : null}
                      {r.tt ? (
                        <a className="tm-tlink tm-tlink-icon" href={r.tt} target="_blank" rel="noreferrer" aria-label={`${r.name} on TikTok`} title="TikTok">
                          <IconBrandTiktok size={16} stroke={1.8} />
                        </a>
                      ) : null}
                      {r.x ? (
                        <a className="tm-tlink tm-tlink-icon" href={r.x} target="_blank" rel="noreferrer" aria-label={`${r.name} on X / Twitter`} title="X / Twitter">
                          <IconBrandX size={16} stroke={1.8} />
                        </a>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="module-card">
        <div className="card-header">
          <div>
            <h3>Live follower data &amp; trends</h3>
            <p className="muted">
              Record a snapshot to track follower growth. Trend arrows (▲ ▼ ▬) show the real change
              between the two most recent snapshots — {snapshots.length} recorded so far.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="button-secondary" type="button" onClick={handleRecordSnapshot}>Record snapshot</button>
            <button className="button-secondary" type="button" onClick={handleRefresh}>Refresh real data</button>
          </div>
        </div>
        {refreshStatus ? <StatusMessage tone={refreshStatus.tone} message={refreshStatus.message} /> : null}
      </div>
    </div>
  )

  return (
    <section className="module tm-module">
      {showIntro ? (
        <div className="module-card section-intro">
          <h3>Campaigns &amp; Audience</h3>
          <p className="muted">Match campaigns, issues, and causes to the messengers who can amplify them, with reach projections.</p>
        </div>
      ) : null}

      {showTabs ? (
        <div className="subtabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id ? 'subtab active' : 'subtab'}
              onClick={() => selectTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {activeTab === 'roster' ? renderRoster() : renderMatch()}
    </section>
  )
}
