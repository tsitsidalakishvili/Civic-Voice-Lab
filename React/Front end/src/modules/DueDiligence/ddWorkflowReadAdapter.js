export const DD_WORKFLOW_CONTRACT_VERSION = 'dd-workflow.v2'
export const DD_WORKFLOW_FIXTURE_VERSION = 'dd-workflow.v2-be0.4'

export const DD_WORKFLOW_STAGES = Object.freeze([
  'intake',
  'identity',
  'sources',
  'investigation',
  'findings',
  'review',
  'decision',
  'monitoring',
  'closed',
])

const STAGE_SET = new Set(DD_WORKFLOW_STAGES)

const LEGACY_STAGE_ALIASES = Object.freeze({
  overview: { stage: 'intake', tool: null, subview: null },
  entities: { stage: 'identity', tool: null, subview: 'entities' },
  resolve: { stage: 'identity', tool: null, subview: 'resolve' },
  checks: { stage: 'sources', tool: 'checks', subview: null },
  sources: { stage: 'sources', tool: null, subview: null },
  media: { stage: 'sources', tool: 'media', subview: null },
  investigate: { stage: 'investigation', tool: 'follow-the-money', subview: null },
  graph: { stage: 'investigation', tool: 'graph', subview: null },
  advanced: { stage: 'investigation', tool: 'advanced', subview: null },
  findings: { stage: 'findings', tool: null, subview: null },
  reports: { stage: 'review', tool: null, subview: 'internal-dossier' },
  publish: { stage: 'review', tool: null, subview: 'decision-brief' },
  decision: { stage: 'decision', tool: null, subview: null },
  history: { stage: 'monitoring', tool: null, subview: 'history' },
  monitor: { stage: 'monitoring', tool: null, subview: null },
  archived: { stage: 'closed', tool: null, subview: 'archive' },
})

export const DD_DEEP_LINK_TYPES = Object.freeze([
  'entity',
  'relationship',
  'statement',
  'evidence',
  'finding',
  'path_run',
  'connector_run',
  'source',
  'decision',
  'report_snapshot',
  'monitoring_run',
  'hypothesis',
  'resolution_candidate',
  'canonical_entity',
  'note',
])

const DEEP_LINK_SET = new Set(DD_DEEP_LINK_TYPES)

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function requireV2(payload, label = 'DD workflow response') {
  if (!isRecord(payload) || payload.contractVersion !== DD_WORKFLOW_CONTRACT_VERSION) {
    throw new Error(`${label} uses an unsupported contract version.`)
  }
  return payload
}

function copyArray(value) {
  return Array.isArray(value) ? [...value] : []
}

export function resolveDdStageAlias(value) {
  const requestedId = typeof value === 'string' ? value.trim().toLowerCase() : ''
  const alias = LEGACY_STAGE_ALIASES[requestedId]

  if (alias) {
    return { requestedId, ...alias, recognized: true, legacyAlias: requestedId !== alias.stage }
  }
  if (STAGE_SET.has(requestedId)) {
    return {
      requestedId,
      stage: requestedId,
      tool: null,
      subview: null,
      recognized: true,
      legacyAlias: false,
    }
  }
  return {
    requestedId,
    stage: null,
    tool: null,
    subview: null,
    recognized: false,
    legacyAlias: false,
  }
}

export function normalizeMaskingDisplay(value, { queue = false } = {}) {
  const source = isRecord(value) ? value : {}
  const state = source.omitted ? 'omitted' : source.masked ? 'masked' : 'visible'
  return {
    state,
    displayValue: source.displayValue ?? source.displayName ?? null,
    value: queue || state !== 'visible' ? null : source.value ?? null,
    masked: source.masked === true,
    omitted: source.omitted === true,
  }
}

export function normalizeDeepLink(target) {
  if (!isRecord(target) || !DEEP_LINK_SET.has(target.type) || typeof target.id !== 'string') {
    return { recognized: false, navigable: false, type: null, id: null }
  }
  return { recognized: true, navigable: true, type: target.type, id: target.id }
}

export function createDdWorkflowReadAdapter(schemaPayload) {
  const schema = requireV2(schemaPayload, 'DD workflow schema')
  if (
    schema.fixtureVersion !== DD_WORKFLOW_FIXTURE_VERSION
    || schema.schemaStatus !== 'read_fixture_frozen'
  ) {
    throw new Error('DD workflow schema is not the frozen BE0.4 read contract.')
  }

  const knownActionCodes = new Set(copyArray(schema.actionCodes))

  function normalizeAction(action) {
    if (!isRecord(action) || !knownActionCodes.has(action.actionCode)) {
      return {
        recognized: false,
        inert: true,
        actionCode: null,
        messageKey: null,
        params: {},
        stage: null,
        method: null,
        route: null,
        blocking: false,
      }
    }
    return {
      recognized: true,
      inert: true,
      actionCode: action.actionCode,
      messageKey: action.messageKey,
      params: isRecord(action.params) ? { ...action.params } : {},
      stage: STAGE_SET.has(action.stage) ? action.stage : null,
      method: action.method,
      route: action.route ?? null,
      blocking: action.blocking === true,
      requiresCsrf: action.requiresCsrf === true,
      requiresIdempotency: action.requiresIdempotency === true,
    }
  }

  function normalizeConnectorState(connector) {
    return {
      connectorId: connector.connectorId,
      labelKey: connector.labelKey,
      eligible: connector.eligible,
      selected: connector.selected,
      required: connector.required,
      eligibilityReasonCode: connector.eligibilityReasonCode,
      neverRun: connector.neverRun,
      latestRunId: connector.latestRunId,
      executionStatus: connector.latestExecutionStatus,
      freshness: connector.freshness,
      reducedCoverage: connector.reducedCoverage,
      blocking: connector.blocking,
      availableActions: copyArray(connector.availableActions).map(normalizeAction),
      retryAction: connector.retryAction ? normalizeAction(connector.retryAction) : null,
      lastAttemptAt: connector.lastAttemptAt,
      lastSuccessAt: connector.lastSuccessAt,
      sourceUpdatedAt: connector.sourceUpdatedAt,
    }
  }

  function normalizeCaseRecord(record) {
    return {
      caseId: record.caseId,
      workflowVersion: record.workflowVersion,
      stage: STAGE_SET.has(record.stage) ? record.stage : null,
      lifecycleStatus: record.lifecycleStatus,
      migrationNeedsReview: record.migrationNeedsReview,
      archivedFromStage: record.archivedFromStage,
      intake: record.intake,
      duplicateCandidates: copyArray(record.duplicateCandidates),
      nextAction: record.nextAction ? normalizeAction(record.nextAction) : null,
      sla: record.sla,
      blockerSummary: record.blockerSummary,
    }
  }

  function normalizeCaseDetail(payload) {
    const value = requireV2(payload, 'DD case detail')
    return {
      caseId: value.caseId,
      case: normalizeCaseRecord(value.case),
      access: value._access,
    }
  }

  function normalizeCaseList(payload) {
    const value = requireV2(payload, 'DD case list')
    return {
      items: copyArray(value.items).map((item) => ({
        caseId: item.caseId,
        workflowVersion: item.workflowVersion,
        stage: STAGE_SET.has(item.stage) ? item.stage : null,
        lifecycleStatus: item.lifecycleStatus,
        subject: {
          ...normalizeMaskingDisplay(item.subject, { queue: true }),
          category: item.subject.category,
        },
        owner: item.owner,
        lastActivityAt: item.lastActivityAt,
        nextAction: item.nextAction ? normalizeAction(item.nextAction) : null,
        sla: item.sla,
        blockerSummary: item.blockerSummary,
      })),
      page: value.page,
      access: value._access,
    }
  }

  function normalizeQueue(payload) {
    const value = requireV2(payload, 'DD queue')
    return {
      items: copyArray(value.items).map((item) => ({
        caseId: item.caseId,
        stage: STAGE_SET.has(item.stage) ? item.stage : null,
        lifecycleStatus: item.lifecycleStatus,
        subject: {
          ...normalizeMaskingDisplay(item.subject, { queue: true }),
          category: item.subject.category,
        },
        owner: item.owner,
        sla: item.sla,
        blockingCount: item.blockingCount,
        unresolvedCandidateCount: item.unresolvedCandidateCount,
        openFindingCount: item.openFindingCount,
        lastActivityAt: item.lastActivityAt,
        nextAction: item.nextAction ? normalizeAction(item.nextAction) : null,
      })),
      page: value.page,
      access: value._access,
    }
  }

  function normalizeConnectorRun(run) {
    return {
      connectorRunId: run.connectorRunId,
      connectorId: run.connectorId,
      executionStatus: run.status,
      resultCount: run.resultCount,
      freshness: run.freshness,
      partialReason: run.partialReason,
      failure: run.failure,
      coverage: run.coverage,
      reducedCoverage: run.reducedCoverage,
      blocking: run.blocking,
      workflowVersionObserved: run.workflowVersionObserved,
      attemptedAt: run.attemptedAt,
      lastSuccessAt: run.lastSuccessAt,
      sourceUpdatedAt: run.sourceUpdatedAt,
      retryAction: run.retryAction ? normalizeAction(run.retryAction) : null,
    }
  }

  function normalizeWorkflow(payload) {
    const value = requireV2(payload, 'DD workflow')
    return {
      caseId: value.caseId,
      workflowVersion: value.workflowVersion,
      stage: STAGE_SET.has(value.stage) ? value.stage : null,
      lifecycleStatus: value.lifecycleStatus,
      migrationNeedsReview: value.migrationNeedsReview,
      completion: copyArray(value.completion),
      blockers: copyArray(value.blockers),
      transitionOffers: copyArray(value.allowedTransitions),
      waivers: copyArray(value.waivers),
      coverage: value.coverage,
      access: value._access,
    }
  }

  function normalizeAssessment(payload) {
    const value = requireV2(payload, 'DD assessment')
    return {
      caseId: value.caseId,
      ...value.assessment,
      access: value._access,
    }
  }

  function normalizeReportSnapshot(snapshot) {
    return {
      snapshotId: snapshot.snapshotId,
      title: snapshot.title,
      snapshotType: snapshot.snapshotType,
      schemaOrigin: snapshot.schemaOrigin,
      createdAt: snapshot.createdAt,
      createdBy: snapshot.createdBy,
      summaryPoints: copyArray(snapshot.summaryPoints).map((point) => ({
        ...point,
        target: point.target ? normalizeDeepLink(point.target) : null,
      })),
      findingIds: copyArray(snapshot.findingIds),
      statementIds: copyArray(snapshot.statementIds),
      pathRunIds: copyArray(snapshot.pathRunIds),
      evidenceIds: copyArray(snapshot.evidenceIds),
      limitations: copyArray(snapshot.limitations),
    }
  }

  function normalizeConnectorStateList(payload) {
    const value = requireV2(payload, 'DD connector state list')
    return {
      caseId: value.caseId,
      items: copyArray(value.items).map(normalizeConnectorState),
      page: value.page,
      access: value._access,
    }
  }

  function normalizeConnectorRunList(payload) {
    const value = requireV2(payload, 'DD connector run list')
    return {
      caseId: value.caseId,
      items: copyArray(value.items).map(normalizeConnectorRun),
      page: value.page,
      access: value._access,
    }
  }

  function normalizeReportList(payload) {
    const value = requireV2(payload, 'DD report list')
    return {
      caseId: value.caseId,
      items: copyArray(value.items).map(normalizeReportSnapshot),
      page: value.page,
      access: value._access,
    }
  }

  return Object.freeze({
    contractVersion: DD_WORKFLOW_CONTRACT_VERSION,
    fixtureVersion: DD_WORKFLOW_FIXTURE_VERSION,
    knownActionCodes: Object.freeze([...knownActionCodes]),
    normalizeAction,
    normalizeAssessment,
    normalizeCaseDetail,
    normalizeCaseList,
    normalizeConnectorRun,
    normalizeConnectorRunList,
    normalizeConnectorState,
    normalizeConnectorStateList,
    normalizeQueue,
    normalizeReportList,
    normalizeReportSnapshot,
    normalizeWorkflow,
  })
}

export function assertDdWorkflowV2(payload, label) {
  return requireV2(payload, label)
}
