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
    opensanctions: Array.isArray(p.opensanctions) ? p.opensanctions : [],
    news: Array.isArray(p.news) ? p.news : [],
    summary: p.summary && typeof p.summary === 'object' ? p.summary : {},
    warnings: Array.isArray(p.warnings) ? p.warnings : [],
    reportId: apiReport.reportId,
    storedAt: apiReport.createdAt || p.createdAt || null,
  }
}
