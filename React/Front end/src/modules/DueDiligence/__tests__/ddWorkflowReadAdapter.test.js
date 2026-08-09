import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  DD_DEEP_LINK_TYPES,
  DD_WORKFLOW_CONTRACT_VERSION,
  DD_WORKFLOW_FIXTURE_VERSION,
  assertDdWorkflowV2,
  createDdWorkflowReadAdapter,
  normalizeDeepLink,
  normalizeMaskingDisplay,
  resolveDdStageAlias,
} from '../ddWorkflowReadAdapter.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const fixtureRoot = path.resolve(
  here,
  '../../../../../Back end/contracts/dd-workflow/v2/be0.4/fixtures',
)

function fixture(name) {
  return JSON.parse(fs.readFileSync(path.join(fixtureRoot, name), 'utf8'))
}

const schema = fixture('workflow-schema.json')
const adapter = createDdWorkflowReadAdapter(schema)

describe('DD workflow BE0.4 read adapter', () => {
  it('accepts only the exact frozen read contract', () => {
    expect(adapter.contractVersion).toBe(DD_WORKFLOW_CONTRACT_VERSION)
    expect(adapter.fixtureVersion).toBe(DD_WORKFLOW_FIXTURE_VERSION)
    expect(() => assertDdWorkflowV2({ contractVersion: 'dd-workflow.v3' })).toThrow(
      'unsupported contract version',
    )
    expect(() => createDdWorkflowReadAdapter({ ...schema, fixtureVersion: 'draft-be1' })).toThrow(
      'frozen BE0.4 read contract',
    )
  })

  it.each([
    ['overview', 'intake', null, null],
    ['entities', 'identity', null, 'entities'],
    ['resolve', 'identity', null, 'resolve'],
    ['checks', 'sources', 'checks', null],
    ['media', 'sources', 'media', null],
    ['graph', 'investigation', 'graph', null],
    ['advanced', 'investigation', 'advanced', null],
    ['reports', 'review', null, 'internal-dossier'],
    ['publish', 'review', null, 'decision-brief'],
    ['history', 'monitoring', null, 'history'],
    ['archived', 'closed', null, 'archive'],
  ])('maps legacy %s to one stage while retaining tool intent', (legacy, stage, tool, subview) => {
    expect(resolveDdStageAlias(legacy)).toMatchObject({ stage, tool, subview, recognized: true })
  })

  it('fails closed for an unknown stage alias', () => {
    expect(resolveDdStageAlias('risk-score')).toEqual({
      requestedId: 'risk-score',
      stage: null,
      tool: null,
      subview: null,
      recognized: false,
      legacyAlias: false,
    })
  })

  it('preserves every authoritative completion state and workflow field', () => {
    const source = fixture('workflow.json')
    const result = adapter.normalizeWorkflow(source)
    expect(result.workflowVersion).toBe(source.workflowVersion)
    expect(result.completion.map((entry) => entry.state)).toEqual(
      source.completion.map((entry) => entry.state),
    )
    expect(new Set(result.completion.map((entry) => entry.state))).toEqual(
      new Set(['complete', 'incomplete', 'not_applicable', 'unknown']),
    )
    expect(result.blockers).toEqual(source.blockers)
    expect(result.coverage).toEqual(source.coverage)
    expect(result.access).toEqual(source._access)
  })

  it('normalizes case, list and queue envelopes without legacy precedence or raw queue values', () => {
    const caseFixture = fixture('case-detail.json')
    const conflictingCase = {
      ...caseFixture,
      case: { ...caseFixture.case, legacyAliases: { stage: 'decision' } },
    }
    const detail = adapter.normalizeCaseDetail(conflictingCase)
    expect(detail.case.stage).toBe(caseFixture.case.stage)
    expect(detail.case.legacyAliases).toBeUndefined()
    expect(detail.access).toEqual(caseFixture._access)

    const list = adapter.normalizeCaseList(fixture('cases-list.json'))
    expect(list.page).toEqual(fixture('cases-list.json').page)
    expect(list.items.every((item) => item.subject.value === null)).toBe(true)

    const queue = adapter.normalizeQueue(fixture('queue.json'))
    expect(queue.items.every((item) => item.subject.value === null)).toBe(true)
    expect(queue.items.map((item) => item.subject.state)).toEqual(['visible', 'masked', 'omitted'])
    expect(queue.access.policy).toBe('deny-by-default')
  })

  it('keeps connector execution, freshness, zero, failure and never-run semantics distinct', () => {
    const runFixture = fixture('connector-runs-list.json')
    const runs = adapter.normalizeConnectorRunList(runFixture).items
    const byStatus = Object.fromEntries(runs.map((run) => [run.executionStatus, run]))
    expect(byStatus.zero_results.resultCount).toBe(0)
    expect(byStatus.unavailable.resultCount).toBeNull()
    expect(byStatus.permission_required.resultCount).toBeNull()
    expect(byStatus.error.resultCount).toBeNull()
    expect(byStatus.partial.freshness.state).toBe('stale')
    expect(byStatus.partial.partialReason.code).toBe('RESULT_LIMIT_REACHED')
    expect(byStatus.partial.failure).toBeNull()

    const states = adapter.normalizeConnectorStateList(fixture('connectors-list.json')).items
    const selectedNeverRun = states.find((item) => item.neverRun && item.selected)
    const unselectedNeverRun = states.find((item) => item.neverRun && !item.selected)
    expect(selectedNeverRun.executionStatus).toBeNull()
    expect(selectedNeverRun.reducedCoverage).toBe(true)
    expect(selectedNeverRun.availableActions[0]).toMatchObject({
      actionCode: 'start_connector',
      inert: true,
    })
    expect(unselectedNeverRun.reducedCoverage).toBe(false)
  })

  it('preserves masking tri-state and never exposes a queue raw value', () => {
    const identifiers = fixture('case-detail.json').case.intake.identifiers
    expect(identifiers.map((item) => normalizeMaskingDisplay(item).state)).toEqual([
      'visible',
      'masked',
      'omitted',
    ])
    expect(normalizeMaskingDisplay(identifiers[0], { queue: true }).value).toBeNull()

    const queueSubjects = fixture('queue.json').items.map((item) =>
      normalizeMaskingDisplay(item.subject, { queue: true }),
    )
    expect(queueSubjects.map((item) => item.state)).toEqual(['visible', 'masked', 'omitted'])
    expect(queueSubjects.every((item) => item.value === null)).toBe(true)
  })

  it('preserves nullable assessment values, policy and workflow version', () => {
    const noTriage = fixture('assessment.json')
    const result = adapter.normalizeAssessment(noTriage)
    expect(result.workflowVersion).toBe(noTriage.assessment.workflowVersion)
    expect(result.confidence).toBeNull()
    expect(result.triage).toBeNull()
    expect(result.policy).toEqual(noTriage.assessment.policy)

    const withTriage = adapter.normalizeAssessment(fixture('assessment-with-triage.json'))
    expect(withTriage.triage).toMatchObject({ automated: true, deprecated: true })
  })

  it('keeps actions inert, allowlists known codes and ignores unknown codes', () => {
    const known = adapter.normalizeAction(schema.correctionAppealPolicies[0].action)
    expect(known).toMatchObject({ recognized: true, inert: true })
    expect(known.route).toMatch(/^\//)

    expect(adapter.normalizeAction({
      actionCode: 'delete_everything',
      method: 'DELETE',
      route: '/unsafe-for-fe0',
    })).toEqual({
      recognized: false,
      inert: true,
      actionCode: null,
      messageKey: null,
      params: {},
      stage: null,
      method: null,
      route: null,
      blocking: false,
    })
  })

  it('allowlists frozen deep links and makes unknown targets non-navigable', () => {
    for (const type of DD_DEEP_LINK_TYPES) {
      expect(normalizeDeepLink({ type, id: `synthetic-${type}` })).toMatchObject({
        recognized: true,
        navigable: true,
      })
    }
    expect(normalizeDeepLink({ type: 'external_url', id: 'https://example.invalid' })).toEqual({
      recognized: false,
      navigable: false,
      type: null,
      id: null,
    })
  })

  it('uses v2 report fields and preserves legacy nulls without synthesis', () => {
    const reports = adapter.normalizeReportList(fixture('reports-list.json')).items
    const legacy = reports.find((report) => report.schemaOrigin === 'v1_legacy')
    expect(legacy.title).toBeNull()
    expect(legacy.createdAt).toBeNull()
    expect(legacy.createdBy).toBeNull()

    const detail = fixture('report-detail.json').snapshot
    const conflicting = { ...detail, legacyAliases: { title: 'Wrong legacy title' } }
    expect(adapter.normalizeReportSnapshot(conflicting).title).toBe(detail.title)
  })

  it('does not import backend fixtures into the production adapter module', () => {
    const modulePath = path.resolve(here, '../ddWorkflowReadAdapter.js')
    const productionSource = fs.readFileSync(modulePath, 'utf8')
    expect(productionSource).not.toContain('contracts/dd-workflow')
    expect(productionSource).not.toContain('fixtures/')
    expect(productionSource).not.toContain('node:fs')
  })
})
