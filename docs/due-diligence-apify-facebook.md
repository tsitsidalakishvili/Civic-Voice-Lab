# Due Diligence: Apify Facebook public-groups connector

Backend prefix: `/due-diligence`

The connector has two independent modes:

1. Import existing output (`runId`, `datasetId`, or exported `items`). This never starts an Actor.
2. Managed Actor runs. This is implemented but disabled by default and fails closed unless the token, feature flag, case allowlist, operator allowlist, and cost budgets are all configured.

The browser must never receive `APIFY_API_TOKEN` and must never call Apify directly.

## Actor registry

Default import/start Actor:

```json
{
  "actorId": "apify~facebook-groups-scraper",
  "name": "apify/facebook-groups-scraper",
  "url": "https://apify.com/apify/facebook-groups-scraper",
  "schemaVersion": "apify-facebook-public-groups-v2",
  "startAllowed": true
}
```

The former Actor `2chN8UQcH1CfxLRNE` remains allowlisted only for importing an existing run/dataset/export. FS will not start it.

Actor prices are dynamic. The capabilities response provides a pricing reference URL and last verification date, not a hard-coded cost calculation. Actual run pricing, usage, charged events, requested cap, build ID, and build number are taken from Apify run metadata.

## Capabilities

`GET /connectors/apify-facebook/capabilities`

Important fields:

```json
{
  "connectorId": "apify-facebook-public-groups",
  "configured": false,
  "enabled": true,
  "killSwitch": {
    "environmentVariable": "FS_APIFY_FACEBOOK_IMPORT_ENABLED",
    "importsEnabled": true
  },
  "actor": {
    "actorId": "apify~facebook-groups-scraper",
    "name": "apify/facebook-groups-scraper",
    "url": "https://apify.com/apify/facebook-groups-scraper",
    "schemaVersion": "apify-facebook-public-groups-v2"
  },
  "actors": [],
  "supportedInputs": ["runId", "datasetId", "items"],
  "maxItemsPerImport": 1000,
  "startsPaidRuns": false,
  "managedRuns": {
    "implemented": true,
    "enabled": false,
    "disabledByDefault": true,
    "requiresServerToken": true,
    "requiresAllowedCase": true,
    "requiresAllowedOperator": true,
    "oneActiveRunPerCase": true,
    "publicGroupUrlsOnly": true,
    "maxItemsPerRun": 500,
    "maxRunChargeUsd": 1.0,
    "monthlyProjectBudgetUsd": 4.5,
    "budgetScope": "FS-managed Apify runs only",
    "statusMode": "polling-or-verified-webhook"
  },
  "privacyPolicy": {},
  "runImportPolicy": {},
  "authentication": {}
}
```

`configured` means the server token exists. Exported `items` can still be imported without that token.

## Import existing output

`POST /cases/{caseId}/social/import/apify-facebook`

Exactly one of `runId`, `datasetId`, or `items` is required.

```json
{
  "actorId": "apify~facebook-groups-scraper",
  "runId": "optional-apify-run-id",
  "datasetId": null,
  "items": null,
  "maxItems": 200,
  "includeTopComments": true,
  "promotePostsToGraph": true,
  "lawfulBasis": "Documented lawful basis",
  "investigationPurpose": "Documented case-specific purpose",
  "retentionDays": 180
}
```

For `runId`, the backend fetches the run and requires `SUCCEEDED`. For `datasetId`, it fetches dataset metadata; if the dataset belongs to a run, that run must also be `SUCCEEDED`. Actor identity is resolved through the allowlisted Actor and compared with `actId`. Running, failed, aborted, and timed-out output is not imported.

Response is the existing full graph payload plus:

```json
{
  "importResult": {
    "runId": "FS import-run ID",
    "sourceId": "graph source ID",
    "actorId": "apify~facebook-groups-scraper",
    "externalRunId": "Apify run ID or empty",
    "externalDatasetId": "Apify dataset ID or empty",
    "itemsReceived": 10,
    "itemsAccepted": 8,
    "itemsRejected": 1,
    "schemaRejectedItems": 1,
    "schemaRejectionReasons": {
      "diagnostic-or-error-row": 1
    },
    "duplicateItems": 1,
    "entitiesProcessed": 20,
    "relationshipsProcessed": 18,
    "evidenceProcessed": 9,
    "retentionExpiresAt": "ISO-8601",
    "retentionEnforcement": "case-scoped-cleanup",
    "rawArtifactPolicy": "checksum-and-source-excerpt-only",
    "actor": {
      "actorId": "apify~facebook-groups-scraper",
      "name": "apify/facebook-groups-scraper",
      "url": "https://apify.com/apify/facebook-groups-scraper",
      "schemaVersion": "apify-facebook-public-groups-v2",
      "resolvedActorId": "Apify immutable Actor ID",
      "buildId": "",
      "buildNumber": ""
    },
    "runStatus": "SUCCEEDED",
    "pricingModel": "PAY_PER_EVENT",
    "usageTotalUsd": 0.12,
    "chargedItemCount": 8,
    "chargedEventCounts": {},
    "requestedCostCapUsd": 1.0,
    "sourceTotalItems": 10,
    "truncated": false,
    "fetchPageCount": 1,
    "fetchedAt": "ISO-8601",
    "inputMode": "run",
    "identityPolicy": "Social display names were saved as sourced aliases on source-scoped profiles; no profile was merged with an official person.",
    "message": "Public Facebook group records were imported with evidence and provenance."
  }
}
```

Full raw JSON is not persisted. FS stores a SHA-256 checksum, a bounded source excerpt, source URL/key, Actor/build/schema provenance, and expiry metadata. Diagnostic/error rows and invalid nested shapes are rejected and counted separately.

## Managed run start

`POST /cases/{caseId}/social/apify-facebook/runs`

Required headers:

- `Idempotency-Key`: 12-200 characters.
- `X-FS-Operator-Id`: must be explicitly allowlisted.
- Normal Freedom Square API authentication.

```json
{
  "actorId": "apify~facebook-groups-scraper",
  "groupUrls": ["https://www.facebook.com/groups/public-group-slug"],
  "maxItems": 100,
  "maxTotalChargeUsd": 1.0,
  "onlyPostsNewerThan": "2026-07-01",
  "includeTopComments": true,
  "promotePostsToGraph": true,
  "lawfulBasis": "Documented lawful basis",
  "investigationPurpose": "Documented case-specific purpose",
  "retentionDays": 180
}
```

Only explicit `facebook.com/groups/...` URLs are accepted. FS passes only `startUrls`, `resultsLimit`, `viewOption=CHRONOLOGICAL`, and the optional date boundary to the Actor. There is no arbitrary Actor input, group discovery, member collection, credentials, or private-group mode.

Both `maxItems` and `maxTotalChargeUsd` are sent to Apify. The request is rejected if it exceeds the server's per-run cap, if the sum of reserved monthly caps would exceed the project budget, or if another managed run is active for the case. A repeated `Idempotency-Key` returns the existing connector run and does not start another Actor.

Success is HTTP `202` with the connector-run shape below.

## Run status

- `GET /cases/{caseId}/social/apify-facebook/runs?limit=50`
- `GET /cases/{caseId}/social/apify-facebook/runs/{connectorRunId}`
- `POST /cases/{caseId}/social/apify-facebook/runs/{connectorRunId}/refresh`

Refresh requires `X-FS-Operator-Id`. It fetches the run from Apify. On `SUCCEEDED`, it imports the verified default dataset through the same importer. A failed import is retained as `import-failed` and can be retried by refresh without starting a new Actor.

```json
{
  "connectorRunId": "connector-run-...",
  "caseId": "case-id",
  "connectorId": "apify-facebook-public-groups",
  "status": "running",
  "retryable": true,
  "actor": {
    "actorId": "apify~facebook-groups-scraper",
    "name": "apify/facebook-groups-scraper",
    "url": "https://apify.com/apify/facebook-groups-scraper",
    "schemaVersion": "apify-facebook-public-groups-v2",
    "resolvedActorId": "",
    "buildId": "",
    "buildNumber": ""
  },
  "external": {
    "runId": "",
    "datasetId": "",
    "runStatus": "RUNNING",
    "statusMessage": ""
  },
  "request": {
    "groupUrls": [],
    "maxItems": 100,
    "maxTotalChargeUsd": 1.0,
    "onlyPostsNewerThan": null,
    "includeTopComments": true,
    "promotePostsToGraph": true,
    "lawfulBasis": "",
    "investigationPurpose": "",
    "retentionDays": 180,
    "operatorId": "operator-id"
  },
  "usage": {
    "pricingModel": "",
    "usageTotalUsd": 0.0,
    "chargedItemCount": 0,
    "chargedEventCounts": {},
    "monthlyProjectBudgetUsd": 4.5,
    "monthlyReservedAtStartUsd": 1.0
  },
  "import": {
    "importRunId": "",
    "sourceId": "",
    "itemsAccepted": 0,
    "itemsRejected": 0,
    "duplicateItems": 0,
    "truncated": false
  },
  "error": null,
  "timestamps": {
    "createdAt": "ISO-8601",
    "startedAt": "ISO-8601",
    "lastCheckedAt": null,
    "completedAt": null
  },
  "idempotencyKeyHash": "SHA-256; raw key is not stored"
}
```

Statuses: `starting`, `start-unknown`, `start-failed`, `running`, `ready-to-import`, `importing`, `import-failed`, `failed`, `completed`.

## Verified webhook

`POST /connectors/apify-facebook/webhooks/run`

Required headers:

- `X-FS-Apify-Webhook-Secret` matching the server secret.
- `X-Apify-Webhook-Dispatch-Id` supplied by Apify.
- Normal FS API authentication unless the operator deliberately makes only this exact route public.

Allowed events: `ACTOR.RUN.SUCCEEDED`, `ACTOR.RUN.FAILED`, `ACTOR.RUN.ABORTED`, and `ACTOR.RUN.TIMED_OUT`.

The dispatch ID is idempotent. The body is used only to locate the managed run; the backend always fetches the run from Apify before changing state or importing output.

## Retention cleanup

`POST /cases/{caseId}/social/retention/cleanup`

Required `X-FS-Operator-Id` and normal API authentication.

```json
{ "dryRun": true }
```

Response:

```json
{
  "caseId": "case-id",
  "dryRun": true,
  "evaluatedAt": "ISO-8601",
  "candidates": {
    "evidence": 0,
    "statements": 0,
    "relationships": 0,
    "entities": 0
  },
  "deleted": {
    "evidence": 0,
    "statements": 0,
    "relationships": 0,
    "entities": 0
  },
  "auditPreserved": ["source metadata", "import run metadata", "checksums/fingerprints"]
}
```

Actual deletion requires `FS_APIFY_FACEBOOK_RETENTION_DELETE_ENABLED=1`. Cleanup removes expired case-scoped source content and unreferenced global social nodes while preserving source/import audit metadata. There is no built-in scheduler; deployment must call dry-run and deletion according to the approved retention process.

## Stable error codes

- `APIFY_IMPORT_DISABLED` — 503.
- `APIFY_ACTOR_NOT_ALLOWLISTED` — 422.
- `APIFY_ACTOR_IMPORT_ONLY` — 403 for managed start.
- `APIFY_ACTOR_MISMATCH` — 422.
- `APIFY_RUN_NOT_READY` — 409, retryable.
- `APIFY_RUN_NOT_IMPORTABLE` — 409, not retryable.
- `APIFY_RUN_DATASET_MISMATCH` — 422.
- `APIFY_NO_IMPORTABLE_RECORDS` — 422.
- `APIFY_MANAGED_START_DISABLED` — 403.
- `APIFY_MANAGED_AUTHORIZATION_NOT_CONFIGURED` — 503.
- `APIFY_MANAGED_OPERATION_FORBIDDEN` — 403.
- `APIFY_RUN_CAP_TOO_HIGH` — 422.
- `APIFY_CASE_RUN_ALREADY_ACTIVE` — 409, retryable.
- `APIFY_MONTHLY_BUDGET_RESERVED` — 409.
- `APIFY_START_OUTCOME_UNKNOWN` — 502; check Console before retrying.
- `APIFY_RETENTION_DELETE_DISABLED` — 403.

## Environment controls

```dotenv
APIFY_API_TOKEN=
FS_APIFY_FACEBOOK_IMPORT_ENABLED=1
FS_APIFY_FACEBOOK_START_ENABLED=0
FS_APIFY_FACEBOOK_ALLOWED_CASES=
FS_APIFY_FACEBOOK_ALLOWED_OPERATORS=
FS_APIFY_FACEBOOK_MAX_RUN_CHARGE_USD=1.00
FS_APIFY_FACEBOOK_MONTHLY_BUDGET_USD=4.50
FS_APIFY_FACEBOOK_WEBHOOK_SECRET=
FS_APIFY_FACEBOOK_RETENTION_DELETE_ENABLED=0
```

Use a scoped, expiring Apify token limited to the selected Actor/task and required storage. FS cannot verify token scope through the API, so token issuance remains an operator responsibility.
