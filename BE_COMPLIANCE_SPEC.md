# Backend compliance specification

Planning only. Implementation requires explicit user approval.

## Core records

### Processing purpose and basis

`ProcessingPurpose`: id, version, owner, workflow, subject groups, allowed fields/actions, Article 5 basis, Article 6 basis where applicable, legitimate-interest/DPIA reference, effective dates, approval and disabled state. Every collection, search, disclosure and export must resolve to an enabled purpose.

### Field classification

`DataFieldPolicy`: field path, classification, required/optional/prohibited by purpose, masking, retention, export/disclosure permissions and counsel decision. Political views, affiliation and former membership are special category.

### Consent ledger and notices

Append-only `NoticeVersion`, `ConsentEvent` and `WithdrawalEvent`. Record subject, purpose, fields/channels, locale, notice/consent version and hash, timestamp, capture source, affirmative action, operator when assisted, evidence and supersession. Consent is never inferred from manifesto agreement or silence.

### Rights requests

`DataSubjectRequest`: request type, identity-verification state, scope, received/due/completed times, extension reason, dispute/block flag, owners, affected systems/vendors/recipients, decisions, fulfilment artifacts and appeal. Support access, copy, correction, deletion/termination, blocking, portability, withdrawal and recipient propagation.

### Retention

Versioned schedules by purpose/data category; expiry queue; legal hold; deletion/depersonalisation result; vendor/recipient deletion; retry/dead-letter and signed job report. Marketing consent proof follows the legally approved period; recommended non-statutory periods remain configurable pending counsel.

### Authorization and audit

Production auth fails closed. Enforce user role + purpose + case + action + field classification on the server. Sensitive values are encrypted and masked by default. Append immutable audit events for authentication, sensitive view/search/export, create/update/link/unlink/delete/block/disclose, review, consent/withdrawal and permission changes. Include actor, subject/resource, case/purpose, time, outcome, fields (not values), source, before/after hashes, request/correlation ID and reason.

### DD evidence and review

Preserve immutable permitted source artifacts or restricted excerpts/hashes, parsed records, temporal source-scoped statements and canonical views. Store authority, licence/terms, publisher, URL, document ID/page/quote, publication/effective/retrieval times, parser/mapping version and corrections/tombstones. Matches store score, component explanations, aliases, identifiers, sources, threshold/version, conflicts, reviewer decision, false-positive reason, appeal/correction and merge/split history.

### Incidents, vendors and transfers

`IncidentRecord` supports discovery, risk assessment, affected categories/subjects, containment, processor notification, 72-hour decision/timer, authority/data-subject notices and evidence. `VendorRegister` and `TransferRegister` store controller/processor role, services/data/purposes, DPA/subprocessors, locations, safeguards/permit, retention/deletion, audits, expiry, owner and kill switch.

## Repository and logging rules

- Synthetic fixtures only; prohibit production exports in repository paths.
- Structured allowlist logging; redact tokens, IDs, addresses, DOB, political fields, queries and evidence bodies.
- Secret scanning and pre-commit/CI data-pattern checks.
- No raw request bodies for signup, CRM, DD or consent endpoints.
- Audit logs are separate from operational logs, tamper-resistant and access restricted.

## Required APIs (contract planning)

- Notice/purpose discovery for signup and privacy dashboard.
- Consent grant/withdrawal and channel suppression.
- Current-subject privacy summary and rights-request lifecycle.
- Authorized sensitive-field reveal with reason and audit.
- DD match explanations/review/appeal/correction/blocking.
- Retention/incident/vendor/transfer administration for authorized roles.
- Production-readiness endpoint returning P0 gate state without sensitive details.

## Backend acceptance tests

- Reject missing/disabled purpose and missing special-category basis.
- Reject pre-bundled or versionless consent; prove withdrawal propagation.
- Verify channel suppression within the approved SLA and no resend after opt-out.
- Deny every unauthorized field/read/export combination; test production auth fail-closed.
- Prove audit coverage and tamper detection without logging sensitive values.
- Clock tests for expiry, hold, deletion, vendor propagation and retries.
- Rights request deadline, block, correction and export tests.
- Match golden tests: name-only remains candidate; explanation and analyst disposition required.
- Publish/export negative tests for disputed, stale, allegation-only and unreviewed records.
- Incident 72-hour timer/tabletop and transfer/vendor kill-switch tests.

## Existing backend conflicts to estimate

- Auth defaults disabled.
- Signup schema requires special/high-risk fields and persists them without the specified governance records.
- General person/export endpoints require a complete field-authorization review.
- Retention/deletion is not a demonstrated cross-system workflow.
- DD provenance is comparatively strong, but access/audit/rights/publication gates need verification and likely extension.

