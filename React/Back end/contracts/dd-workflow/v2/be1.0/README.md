# Due Diligence workflow BE1.0 contract

This is the frozen `dd-workflow.v2-be1.0` contract for the BE1 mutation boundary, accepted after RC2 frontend review. It is additive to the immutable `dd-workflow.v2-be0.4` read contract. Freezing the contract does not activate v2, deploy code, migrate data, authorize FE1 implementation or authorize BE2+ behavior.

## Status and runtime boundary

- Read contract: `dd-workflow.v2`, fixture `dd-workflow.v2-be0.4`.
- Mutation contract: `dd-workflow.v2-be1.0`.
- Frozen artifact: `dd-workflow.v2-be1.0` with schema status `mutation_contract_frozen`.
- Feature flag: `FS_DD_WORKFLOW_V2_ENABLED`; missing or false means every unique v2 route returns a sanitized 404 and the legacy behavior remains unchanged.
- When the flag is on, legacy case creation, direct status PATCH, direct decision, archive and hard-delete writes are rejected before database mutation.
- Every response is `Cache-Control: no-store` and carries `X-FS-DD-Contract-Version: dd-workflow.v2`.
- All BE2+ actions in this pack are explicitly `x-executable: false` and have no approved request schema.

The schema and OpenAPI use pack-relative references to the sibling immutable `../be0.4` directory. Consumers must distribute BE1.0 together with that exact BE0.4 pack and verify its declared hash. The enabled BE1 read surface is workflow schema, case list/detail, queue and workflow. Connector state/run, assessment and report read paths are all listed with resolvable BE0 contract references but explicitly return sanitized `501` while their later-milestone runtime is unavailable; BE1 does not pretend to return partial BE0 envelopes.

No live activation is safe until the BE1 projection migration has been reviewed and applied through its separate double-gated operator process.

## Executable BE1 operations

| Operation | Route | Result event |
| --- | --- | --- |
| Create v2 case | `POST /due-diligence/cases/v2` | `caseCreatedEvent` |
| Full intake replacement | `PUT /due-diligence/cases/{caseId}/intake` | `intakeEvent` |
| Duplicate lead scan | `POST /due-diligence/cases/{caseId}/duplicate-candidates/scan` | `scanEvent` |
| Duplicate lead decision | `POST /due-diligence/cases/{caseId}/duplicate-candidates/{candidateCaseId}/decisions` | `decisionEvent` |
| Exact workflow transition | `POST /due-diligence/cases/{caseId}/transitions` | `transitionEvent` |

All mutation responses include the authoritative frozen BE0 `case` and `workflow` read models, `workflowVersion`, `idempotentReplay`, the operation event, and `_access`.

## Security and privacy invariants

- Cookie authentication, CSRF, exact Origin/Referer checks, role authorization, case scope, purpose scope and field policy are backend controls. Rendering or hiding an action is never authorization.
- OpenAPI declares the opaque `__Host-fs_session` cookie security scheme and requires `X-FS-CSRF` on every executable mutation. The token is bootstrapped by `GET /auth/me`; exact Origin/Referer validation remains a shared middleware control.
- Mutations accept OIDC or the approved local-file session. Actor identity, method, time and statement code are server-issued. A client attestation is exactly `{ "attested": true }`; extra fields fail with a sanitized 422.
- `X-FS-Purpose-Id` is required. On create and intake replacement it equals the proposed `processingPurposeId`. Existing and proposed purposes must be authorized. BE1 does not reclassify an established purpose.
- The accepted identifier vocabulary is limited to non-personal deterministic identifiers. Raw values are checked by collection policy, HMACed for matching, and never persisted or returned. Personal national IDs are prohibited.
- Duplicate candidates are masked investigative leads. A name-only match never confirms identity, creates a finding or merges cases. `link_existing` records only a case relationship; `mergePerformed` remains false. `open_existing` is a separately authorized GET navigation action.
- Purpose/authorization and policy-decision blockers are non-waivable. Waivers require an attestation, non-empty reason and atomic validation of the complete required set.

## Concurrency and idempotency

Every mutation requires an ASCII `Idempotency-Key` of 12..200 characters, matching the established shared contract. The backend computes a keyed canonical request digest scoped to operation and route.

1. Same key and same canonical body returns the original stored response before checking the now-stale `expectedWorkflowVersion`.
2. Same key and a different canonical body returns `DD_IDEMPOTENCY_KEY_REUSED`.
3. A new key then evaluates optimistic concurrency. A stale version returns `DD_WORKFLOW_VERSION_CONFLICT` with fresh masked blockers and transition offers.

`workflowVersion` increments exactly once when a committed workflow-visible digest changes. A no-op intake replacement or identical scan may append an operation event without incrementing the visible version. Duplicate decisions and transitions always change visible state and increment once.

## Policy decisions still provisional

Retention classes, coverage threshold/version and allowed identifier types are operator configuration, not frontend constants or permanent legal conclusions. A provisional retention class creates a non-waivable `decisionRequired` blocker. Counsel/product decisions can change configuration without renaming core stages.

Runtime configuration names:

- `FS_DD_WORKFLOW_V2_ENABLED`
- `FS_DD_WORKFLOW_V2_RETENTION_CLASSES_JSON`
- `FS_DD_WORKFLOW_V2_ALLOWED_IDENTIFIER_TYPES`
- `FS_DD_WORKFLOW_V2_MINIMUM_COVERAGE`
- `FS_DD_WORKFLOW_V2_POLICY_VERSION`
- `FS_DD_WORKFLOW_V2_MIGRATION_WRITE_ENABLED`

Identifier and idempotency digests reuse the platform's existing compliance/session keyed-hash facility; BE1 introduces no separate secret variable.

## Migration tooling

`tools/dd_workflow_be1_migration.py` is dry-run first. It accepts a synthetic fixture without database access. Database reading requires an explicit `--database`; applying and rollback additionally require the write flag plus an exact confirmation token. Rollback removes only new BE1 projections/events/idempotency nodes and never deletes legacy cases or source evidence.

Example synthetic dry run:

```powershell
.venv/Scripts/python.exe tools/dd_workflow_be1_migration.py --fixture contracts/dd-workflow/v2/be1.0/fixtures/migration-legacy-cases.json
```

## Validation

From the backend directory, with the contract test dependency installed:

```powershell
python -m unittest discover -s contracts/dd-workflow/v2/be1.0/tests -p "test_*.py" -v
```

The tests validate request/event/error fixtures, nullable and controlled boundaries, actor-spoof rejection, identifier privacy, BE1 route inventory, BE2+ non-executability, synthetic-only data and both BE0/BE1 aggregate hashes.
