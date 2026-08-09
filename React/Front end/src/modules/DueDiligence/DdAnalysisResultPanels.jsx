import { downloadFile } from '../../services/api'

const moneyTotalsText = (totals) => {
  if (!totals || typeof totals !== 'object') return '-'
  const entries = Object.entries(totals).filter(([, value]) => Number(value) || value === 0)
  if (!entries.length) return '-'
  return entries.map(([currency, value]) => String(value) + ' ' + currency).join(' / ')
}

const compactParts = (parts) => parts.filter(Boolean).join(' - ') || '-'

function DossierList({ title, items, renderItem }) {
  if (!items?.length) return null
  return (
    <div className="dd-dossier-section">
      <h4>{title}</h4>
      <ul className="compact-list">
        {items.slice(0, 4).map((item, idx) => (
          <li key={title + '-' + idx}>{renderItem(item)}</li>
        ))}
      </ul>
    </div>
  )
}

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
    <div className="stack dd-analysis-result">
      <div className={`dd-risk-summary is-${String(analysisResult.summary?.risk_level || 'unknown').toLowerCase()}`}>
        <div className="dd-risk-summary__score">
          <strong>{analysisResult.summary?.risk_score ?? '—'}</strong>
          <span>/100</span>
        </div>
        <div>
          <span className="dd-card-kicker">Automated risk signal</span>
          <h3>{analysisResult.summary?.risk_level || 'Unknown'} risk</h3>
          <p>{analysisResult.summary?.total_hits - 0} findings across the configured evidence sources.</p>
        </div>
      </div>
      {analysisResult.summary?.source_notes?.length ? (
        <div className="dd-source-note"><strong>Coverage note</strong>{analysisResult.summary.source_notes.join(' ')}</div>
      ) : null}
      {analysisResult.summary?.risk_rationale?.length ? (
        <ul className="compact-list dd-risk-rationale">
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
          <button
            className="button-secondary"
            type="button"
            onClick={() => downloadFile(
              `/due-diligence/reports/${analysisResult.reportId}/pdf`,
              `due-diligence-${analysisResult.reportId}.pdf`,
            )}
          >
            Download PDF report
          </button>
          {showViewFullSourcesButton && onViewFullSources ? (
            <button className="button-secondary" type="button" onClick={onViewFullSources}>
              View full sources
            </button>
          ) : null}
          <span className="muted">Stored: {analysisResult.storedAt || '-'}</span>
        </div>
      ) : null}

      {showSourceDetails ? (
        <>
          <details className="dashboard-detail">
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

          <details className="dashboard-detail">
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
                      <span>{row.label || '-'}</span>
                      <span>{row.description || '-'}</span>
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

          <details className="dashboard-detail">
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
                            {row.name || '-'}
                          </a>
                        ) : (
                          row.name || '-'
                        )}
                      </span>
                      <span>{row.schema || '-'}</span>
                      <span>{(row.datasets || []).slice(0, 3).join(', ') || '-'}</span>
                      <span>{row.score?.toFixed?.(2) ?? row.score ?? '-'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
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
                            {row.title || '-'}
                          </a>
                        ) : (
                          row.title || '-'
                        )}
                      </span>
                      <span>{row.source || '-'}</span>
                      <span>{row.tone?.toFixed?.(2) ?? row.tone ?? '-'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <details className="dashboard-detail">
            <summary>
              Asset declarations ({(analysisResult.declarations || []).length})
            </summary>
            <div className="dashboard-detail__body">
              {(analysisResult.declarations || []).length === 0 ? (
                <div className="table-row empty">No asset declarations found.</div>
              ) : (
                <div className="dd-dossier-grid">
                  {analysisResult.declarations.map((row) => {
                    const summary = row.summary || {}
                    const counts = summary.counts || {}
                    const dossier = summary.dossier || {}
                    const declarant = dossier.declarant || {}
                    const financialTotals = [
                      ['Bank', moneyTotalsText(summary.bankAccountTotals)],
                      ['Cash', moneyTotalsText(summary.cashTotals)],
                      ['Job income', moneyTotalsText(summary.jobIncomeTotals)],
                      ['Contracts', moneyTotalsText(summary.contractAmountTotals)],
                      ['Contract income', moneyTotalsText(summary.contractIncomeTotals)],
                      ['In/out', moneyTotalsText(summary.inOutTotals)],
                    ].filter(([, value]) => value && value !== '-')
                    return (
                      <article className="dd-dossier-card" key={row.id || row.name}>
                        <header className="dd-dossier-card__header">
                          <div>
                            <h3>
                              {row.sourceUrl ? (
                                <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                                  {row.name || declarant.name || '-'}
                                </a>
                              ) : (
                                row.name || declarant.name || '-'
                              )}
                            </h3>
                            <p>{compactParts([row.organization || declarant.organization, row.position || declarant.position])}</p>
                          </div>
                          <span>{row.declarationSubmitDate || row.dateEdited || declarant.submitted || '-'}</span>
                        </header>
                        <div className="dd-dossier-stats">
                          <span>Properties: {counts.properties || 0}</span>
                          <span>Vehicles/assets: {counts.movableProperties || 0}</span>
                          <span>Businesses: {(counts.enterprises || 0) + (counts.linkedEnterprises || 0)}</span>
                          <span>Family: {counts.familyMembers || 0}</span>
                          <span>Jobs: {counts.jobs || 0}</span>
                          <span>Contracts: {counts.contracts || 0}</span>
                        </div>
                        <DossierList
                          title="Career and yearly income"
                          items={dossier.careerAndIncome}
                          renderItem={(item) => compactParts([item.owner, item.organization, item.position, item.period && item.endDate ? item.period + ' to ' + item.endDate : item.period, item.amount])}
                        />
                        <DossierList
                          title="Properties"
                          items={dossier.properties}
                          renderItem={(item) => compactParts([item.owner, item.type, item.address, item.area, item.share, item.amount])}
                        />
                        <DossierList
                          title="Businesses"
                          items={[...(dossier.businesses || []), ...(dossier.linkedBusinesses || [])]}
                          renderItem={(item) => compactParts([item.name, item.role || item.relation, item.share, item.amount])}
                        />
                        <DossierList
                          title="Family members"
                          items={dossier.familyMembers}
                          renderItem={(item) => compactParts([item.name, item.relation, item.birthDate, item.position])}
                        />
                        <DossierList
                          title="Vehicles and movable assets"
                          items={dossier.vehiclesAndMovable}
                          renderItem={(item) => compactParts([item.owner, item.type, item.details, item.acquired, item.amount])}
                        />
                        {financialTotals.length ? (
                          <div className="dd-dossier-section">
                            <h4>Financial totals</h4>
                            <div className="dd-dossier-finance">
                              {financialTotals.map(([label, value]) => (
                                <span key={label}>{label}: {value}</span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </article>
                    )
                  })}
                </div>
              )}
            </div>
          </details>
        </>
      ) : null}
    </div>
  )
}
