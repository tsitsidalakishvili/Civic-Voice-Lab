/**
 * Map GET /due-diligence/reports/:id into the same shape as POST /analyze for UI reuse.
 */
export function normalizeStoredReportToAnalysisResult(apiReport) {
  if (!apiReport) return null
  const p = apiReport.payload || {}
  return {
    subject: apiReport.subject || p.subject || '',
    subjectType: apiReport.subjectType || p.subjectType || 'Person',
    caseId: apiReport.caseId ?? p.caseId ?? null,
    wikidata: Array.isArray(p.wikidata) ? p.wikidata : [],
    wikipedia: Array.isArray(p.wikipedia) ? p.wikipedia : [],
    opensanctions: Array.isArray(p.opensanctions) ? p.opensanctions : [],
    news: Array.isArray(p.news) ? p.news : [],
    declarations: Array.isArray(p.declarations) ? p.declarations : [],
    media: p.media && typeof p.media === 'object' ? p.media : null,
    aiReport: p.aiReport && typeof p.aiReport === 'object' ? p.aiReport : null,
    summary: p.summary && typeof p.summary === 'object' ? p.summary : {},
    warnings: Array.isArray(p.warnings) ? p.warnings : [],
    reportId: apiReport.reportId,
    storedAt: apiReport.createdAt || p.createdAt || null,
  }
}


