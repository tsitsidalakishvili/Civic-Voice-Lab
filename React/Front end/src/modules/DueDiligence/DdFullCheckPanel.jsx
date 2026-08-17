import React, { useState } from 'react'
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleMinus,
  IconPlayerPlay,
  IconSettings,
} from '@tabler/icons-react'
import { downloadFile, requestJson } from '@/services/api'

/**
 * Presentation metadata per source status.
 *
 * "no-data" and "error" are deliberately different: no-data means the source
 * ran and matched nothing (normal), error means the source failed.
 * "not-configured"/"blocked" are informational - the operator has to enable
 * them - so they must never be painted as a failure.
 */
const SOURCE_STATUS_META = {
  ok: { tone: 'ok', chip: 'Data found', Icon: IconCircleCheck },
  'no-data': { tone: 'no-data', chip: 'Nothing found', Icon: IconCircleMinus },
  setup: { tone: 'setup', chip: 'Needs setup', Icon: IconSettings },
  error: { tone: 'error', chip: 'Could not run', Icon: IconAlertTriangle },
}

function resolveSourceTone(source) {
  const status = String(source?.status || '').toLowerCase()
  if (status === 'ok') return SOURCE_STATUS_META.ok
  if (source?.requiresConfiguration || status === 'not-configured' || status === 'blocked') {
    return SOURCE_STATUS_META.setup
  }
  if (status === 'error') return SOURCE_STATUS_META.error
  return SOURCE_STATUS_META['no-data']
}

const formatCheckedAt = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

const hitLabel = (count) => {
  const value = Number(count) || 0
  return `${value} ${value === 1 ? 'hit' : 'hits'}`
}

function FullCheckSourceRow({ source }) {
  const { tone, chip, Icon } = resolveSourceTone(source)
  return (
    <li className={`dd-full-check__source is-${tone}`}>
      <span className="dd-full-check__source-icon">
        <Icon size={17} />
      </span>
      <div className="dd-full-check__source-body">
        <div className="dd-full-check__source-head">
          <strong>{source.label || source.id}</strong>
          <span className={`dd-full-check__chip is-${tone}`}>{chip}</span>
          <span className="dd-full-check__hits">{hitLabel(source.hitCount)}</span>
        </div>
        {source.detail ? <p>{source.detail}</p> : null}
      </div>
    </li>
  )
}

/**
 * One baseline collection: press a single button, then review coverage and
 * evidence before promoting any signal into a finding.
 */
export function DdFullCheckPanel({ caseId, subjectLabel, onCompleted }) {
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [downloading, setDownloading] = useState(false)

  const downloadPdf = async (reportId) => {
    setDownloading(true)
    setError('')
    try {
      await downloadFile(`/due-diligence/reports/${reportId}/pdf`, `due-diligence-${reportId}.pdf`)
    } catch (err) {
      setError(err?.message || 'Could not download the PDF report.')
    } finally {
      setDownloading(false)
    }
  }

  const handleRun = async () => {
    if (!caseId || running) return
    setError('')
    setRunning(true)
    try {
      const payload = await requestJson(`/due-diligence/cases/${caseId}/full-check`, {
        method: 'POST',
        payload: {},
      })
      setResult(payload)
      if (onCompleted) onCompleted(payload)
    } catch (err) {
      setResult(null)
      setError(
        err?.message ||
          'The full check failed and the server returned no error message.',
      )
    } finally {
      setRunning(false)
    }
  }

  const summary = result?.summary || {}
  const sources = result?.sources || []
  const riskLevel = summary.riskLevel || 'Unknown'
  const sourcesChecked = Number(summary.sourcesChecked ?? sources.length) || 0
  const sourcesWithData = Number(summary.sourcesWithData) || 0
  const needsSetup = Number(summary.sourcesRequiringConfiguration) || 0
  const headline = `${sourcesWithData} of ${sourcesChecked} sources returned evidence`

  return (
    <div className="module-card module-card__wide dd-full-check">
      <div className="card-header">
        <div>
          <span className="dd-card-kicker">Baseline collection</span>
          <h3>Collect available evidence</h3>
          <p className="muted">
            Checks approved sources for{' '}
            {subjectLabel ? <strong>{subjectLabel}</strong> : 'the selected case'} and
            keeps unavailable sources distinct from confirmed zero results.
          </p>
        </div>
      </div>

      <div className="dd-full-check__action">
        <button
          className="button dd-run-button"
          type="button"
          onClick={handleRun}
          disabled={!caseId || running}
        >
          <IconPlayerPlay size={16} />
          {running ? 'Collecting evidence…' : 'Run baseline collection'}
        </button>
        {!caseId ? (
          <span className="muted">Select or create a case first.</span>
        ) : running ? (
          <span className="muted">
            Checking all sources. This usually takes 30-60 seconds - you can leave this
            open.
          </span>
        ) : (
          <span className="muted">Review source coverage and identity matches after collection.</span>
        )}
      </div>

      {running ? (
        <div className="dd-full-check__progress" role="progressbar" aria-label="Full check in progress">
          <span />
        </div>
      ) : null}

      {error ? <div className="module-alert">{error}</div> : null}

      {result ? (
        <div className="dd-full-check__result">
          <div className={`dd-risk-summary is-${String(riskLevel).toLowerCase()}`}>
            <div className="dd-risk-summary__score">
              <strong>{Number(summary.riskScore) || 0}</strong>
              <span>/100</span>
            </div>
            <div>
              <span className="dd-card-kicker">Automated triage — not a decision</span>
              <h3>{headline}</h3>
              <p>
                {`${riskLevel} triage · ${Number(summary.riskScore) || 0}/100. `}
                {needsSetup
                  ? ` ${needsSetup} ${needsSetup === 1 ? 'source needs' : 'sources need'} setup by your operator.`
                  : ''}
              </p>
            </div>
          </div>

          <ul className="dd-full-check__sources">
            {sources.map((source) => (
              <FullCheckSourceRow key={source.id || source.label} source={source} />
            ))}
          </ul>

          {result.warnings?.length ? (
            <details className="dashboard-detail dd-full-check__warnings">
              <summary>Technical notes ({result.warnings.length})</summary>
              <div className="dashboard-detail__body">
                <ul className="compact-list">
                  {result.warnings.map((warning, idx) => (
                    <li key={`${warning}-${idx}`}>{warning}</li>
                  ))}
                </ul>
              </div>
            </details>
          ) : null}

          <div className="filter-row dd-full-check__footer">
            {result.reportId ? (
              // A plain link cannot send X-FS-Purpose-Id, so the export 403s.
              // downloadFile() applies the purpose header for us.
              <button
                className="button-secondary"
                type="button"
                onClick={() => downloadPdf(result.reportId)}
                disabled={downloading}
              >
                {downloading ? 'Preparing PDF…' : 'Download PDF report'}
              </button>
            ) : null}
            <span className="muted">Checked {formatCheckedAt(result.generatedAt)}</span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
