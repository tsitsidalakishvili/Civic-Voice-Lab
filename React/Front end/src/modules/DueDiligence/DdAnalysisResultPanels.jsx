import { getApiBaseUrl } from '../../services/api'

/**
 * Renders stored or live analysis output: summary, warnings, source tables, PDF link.
 */
export function DdAnalysisResultPanels({
  analysisResult,
  onViewFullSources,
  showSourceDetails = true,
  showViewFullSourcesButton = Boolean(onViewFullSources),
}) {
  if (!analysisResult) return null

  return (
    <div className="stack">
      <div className="module-alert module-alert--success">
        Risk level: {analysisResult.summary?.risk_level || 'Unknown'} · Total hits:{' '}
        {analysisResult.summary?.total_hits - 0}
      </div>
      {analysisResult.summary?.risk_score !== undefined ? (
        <p className="muted">Risk score: {analysisResult.summary?.risk_score}/100</p>
      ) : null}
      {analysisResult.summary?.source_notes?.length ? (
        <p className="muted">
          Source note: {analysisResult.summary.source_notes.join(' ')}
        </p>
      ) : null}
      {analysisResult.summary?.risk_rationale?.length ? (
        <ul className="compact-list">
          {analysisResult.summary.risk_rationale.map((item, idx) => (
            <li key={`${item}-${idx}`}>{item}</li>
          ))}
        </ul>
      ) : null}
      {analysisResult.warnings?.length ? (
        <div className="module-alert">
          {analysisResult.warnings.map((warning, idx) => (
            <div key={`${warning}-${idx}`}>{warning}</div>
          ))}
        </div>
      ) : null}
      {analysisResult.reportId ? (
        <div className="filter-row">
          <a
            className="button-secondary"
            href={`${getApiBaseUrl()}/due-diligence/reports/${analysisResult.reportId}/pdf`}
            target="_blank"
            rel="noreferrer"
          >
            Download PDF report
          </a>
          {showViewFullSourcesButton && onViewFullSources ? (
            <button className="button-secondary" type="button" onClick={onViewFullSources}>
              View full sources
            </button>
          ) : null}
          <span className="muted">Stored: {analysisResult.storedAt || '—'}</span>
        </div>
      ) : null}

      {showSourceDetails ? (
        <>
          <details className="dashboard-detail" open>
            <summary>Wikipedia results ({(analysisResult.wikipedia || []).length})</summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Title</span>
                  <span>Summary</span>
                  <span>Link</span>
                </div>
                {(analysisResult.wikipedia || []).length === 0 ? (
                  <div className="table-row empty">No Wikipedia matches.</div>
                ) : (
                  analysisResult.wikipedia.map((row) => (
                    <div className="table-row" key={row.url || row.title}>
                      <span>{row.title || '-'}</span>
                      <span>{row.summary || '-'}</span>
                      <span>
                        {row.url ? (
                          <a href={row.url} target="_blank" rel="noreferrer">
                            View
                          </a>
                        ) : (
                          '-'
                        )}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail" open>
            <summary>Wikidata entity results ({(analysisResult.wikidata || []).length})</summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Label</span>
                  <span>Description</span>
                  <span>Link</span>
                </div>
                {(analysisResult.wikidata || []).length === 0 ? (
                  <div className="table-row empty">No Wikidata matches.</div>
                ) : (
                  analysisResult.wikidata.map((row) => (
                    <div className="table-row" key={row.id || row.label}>
                      <span>{row.label || '—'}</span>
                      <span>{row.description || '—'}</span>
                      <span>
                        {row.url ? (
                          <a href={row.url} target="_blank" rel="noreferrer">
                            View
                          </a>
                        ) : (
                          '—'
                        )}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail" open>
            <summary>OpenSanctions results ({(analysisResult.opensanctions || []).length})</summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Name</span>
                  <span>Schema</span>
                  <span>Datasets</span>
                  <span>Score</span>
                </div>
                {(analysisResult.opensanctions || []).length === 0 ? (
                  <div className="table-row empty">No OpenSanctions matches.</div>
                ) : (
                  analysisResult.opensanctions.map((row) => (
                    <div className="table-row" key={row.id || row.name}>
                      <span>
                        {row.url ? (
                          <a href={row.url} target="_blank" rel="noreferrer">
                            {row.name || '—'}
                          </a>
                        ) : (
                          row.name || '—'
                        )}
                      </span>
                      <span>{row.schema || '—'}</span>
                      <span>{(row.datasets || []).slice(0, 3).join(', ') || '—'}</span>
                      <span>{row.score?.toFixed?.(2) - row.score - '—'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail" open>
            <summary>News / Web results ({(analysisResult.news || []).length})</summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Headline</span>
                  <span>Source</span>
                  <span>Tone</span>
                </div>
                {(analysisResult.news || []).length === 0 ? (
                  <div className="table-row empty">No recent news found.</div>
                ) : (
                  analysisResult.news.map((row) => (
                    <div className="table-row" key={row.url || row.title}>
                      <span>
                        {row.url ? (
                          <a href={row.url} target="_blank" rel="noreferrer">
                            {row.title || '—'}
                          </a>
                        ) : (
                          row.title || '—'
                        )}
                      </span>
                      <span>{row.source || '—'}</span>
                      <span>{row.tone?.toFixed?.(2) - row.tone - '—'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail" open>
            <summary>
              Asset declarations ({(analysisResult.declarations || []).length})
            </summary>
            <div className="dashboard-detail__body">
              <div className="table">
                <div className="table-row table-head">
                  <span>Declarant</span>
                  <span>Role</span>
                  <span>Submitted</span>
                  <span>Profile</span>
                </div>
                {(analysisResult.declarations || []).length === 0 ? (
                  <div className="table-row empty">No asset declarations found.</div>
                ) : (
                  analysisResult.declarations.map((row) => {
                    const counts = row.summary?.counts || {}
                    const profile = [
                      `Properties: ${counts.properties || 0}`,
                      `Bank: ${counts.bankAccounts || 0}`,
                      `Jobs: ${counts.jobs || 0}`,
                      `Contracts: ${counts.contracts || 0}`,
                    ].join(' / ')
                    return (
                      <div className="table-row" key={row.id || row.name}>
                        <span>
                          {row.sourceUrl ? (
                            <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                              {row.name || '-'}
                            </a>
                          ) : (
                            row.name || '-'
                          )}
                        </span>
                        <span>{[row.organization, row.position].filter(Boolean).join(' - ') || '-'}</span>
                        <span>{row.declarationSubmitDate || row.dateEdited || '-'}</span>
                        <span>{profile}</span>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </details>
        </>
      ) : null}
    </div>
  )
}
