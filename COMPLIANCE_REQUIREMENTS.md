# FS Georgia compliance requirements and rollout gates

Status: planning baseline, 2026-08-07. This is product/compliance engineering guidance, not Georgian legal advice. No application implementation is authorized by this document.

Primary references:

- Law of Georgia on Personal Data Protection, publication 8: https://www.matsne.gov.ge/en/document/view/5827307?publication=8
- Official campaign direct-marketing guidance: https://pdps.ge/en/content/979/5173/Announcement-on-the-use-of-direct-marketing-for-pre-election-campaigns--agitation--processes

The cited Matsne page warns that publication 8 is not the final edition. Georgian counsel must validate the current Georgian consolidated text and subordinate acts before production.

## Product boundaries

FS must operate three purpose-bound workflows rather than one broad supporter-intelligence store:

1. Membership/application administration.
2. Separately consented outreach by channel.
3. Restricted, case-and-purpose-bound due diligence.

No solely automated adverse outcome is permitted. Public or scraped data remains personal data; public visibility is not, by itself, permission for bulk reuse, incompatible processing or publication.

## Requirements matrix

| ID | Requirement | BE control | FE control | Owner | Priority | Evidence/test | Status |
|---|---|---|---|---|---|---|---|
| GOV-01 | Processing must have a specified purpose and justified Article 5/6 basis | Purpose/basis registry; reject writes/searches lacking allowed purpose; version basis decisions | Show purpose and required/optional status before collection; require DD case purpose | Privacy lead + BE/FE | P0 | Unit/API tests; approved processing register | Gap |
| GOV-02 | Political views, affiliation and former membership are special-category data | Field classification; Article 6 basis; restricted store and disclosure rules | Special-category explanation; unticked written consent where used | Privacy lead | P0 | Schema audit; consent/basis test | Gap |
| MIN-01 | Necessity and minimisation | Make full DOB, exact address, social profiles and interests optional or remove; validate approved fields per purpose | Ask only approved minimum; explain consequences for genuinely required fields | Product + Privacy | P0 | Form/schema diff; field-purpose inventory | Conflict |
| TRN-01 | Layered Article 24 notice and indirect-source notice | Store notice versions/hash, locale, effective dates and source notices | Georgian/English short notice + expandable full notice; source notice in DD | Privacy + FE | P0 | Content/legal sign-off; accessibility test | Gap |
| CON-01 | Consent must be specific, active and provable | Append-only consent ledger with purpose, fields/channels, action, version, timestamp, source, withdrawal | Separate unticked controls; no bundling with manifesto/application | BE + FE | P0 | Consent replay/audit test | Conflict |
| MKT-01 | Direct marketing requires consent regardless of source | Channel-specific opt-in/suppression; stop within 7 working days; retain proof through campaign and one year after | Per-channel opt-ins; one-step unsubscribe/STOP; withdrawal confirmation | Campaign owner | P0 | End-to-end opt-out SLA test | Gap |
| RIGHTS-01 | Access, copy, correction, deletion/termination, blocking, portability, withdrawal and appeal | DSR case workflow, identity verification, deadlines, holds, recipient propagation and completion evidence | Privacy dashboard and request/status/correction/appeal UI | Privacy operations | P0 | 10-working-day SLA simulation; export/delete test | Gap |
| RET-01 | Keep data only while necessary | Retention schedule, expiry jobs, legal holds, tombstones and vendor deletion | Show retention/expiry where relevant; allow authorized deletion/withdrawal | Data owner + BE | P0 | Clock-based deletion tests; job reports | Gap |
| SEC-01 | Appropriate security | Production auth fail-closed; MFA for privileged users; encryption; secrets; rate limits; backups | Secure session UX; no sensitive client logs/analytics | Security | P0 | Security test; restore test | Conflict: auth defaults off |
| RBAC-01 | Least privilege and sensitive-field restrictions | Role/purpose/case/field authorization on every read/export/write | Mask restricted fields; hide unavailable actions; re-auth for export | Security + BE/FE | P0 | Authorization matrix tests | Gap |
| AUD-01 | Demonstrable accountability | Immutable audit events for login, view, search, export, create/edit/link/delete/disclose and permission changes | Show relevant audit history to authorized reviewers | Compliance + BE | P0 | Tamper/coverage tests; sample audit export | Partial/unknown |
| DD-01 | DD must be case/purpose bound and evidence based | Require case/purpose; source URL/publisher/dates/licence/hash/quote/page; source-scoped statements | Show provenance, authority, freshness and exact evidence | DD owner | P0 | API contract and source trace test | Partial |
| DD-02 | Fact and assessment must be distinguished | Assertion kind and verification state; contradiction and correction history | Label fact, official finding, allegation, inference and analyst assessment | DD owner | P0 | Fixture/render tests | Partial-good |
| DD-03 | Identity matches require explainability and review | Deterministic/composite matching; name-only candidate; review/false-positive/appeal record | Score, component reasons, aliases, sources, thresholds and analyst disposition | DD owner | P0 | Golden match tests; false-positive workflow | Partial |
| DD-04 | No automatic adverse decision or guilt by association | Block automatic acceptance/rejection/publication; relatives as context only | Human-review and correction/appeal gates; warnings | Legal/editorial | P0 | Negative tests; publish gate test | Partial |
| INC-01 | Incident registration and notification workflow | Incident register, risk assessment, processor escalation and 72-hour workflow | Staff incident intake/status UI if in scope | Security + Privacy | P0 | Tabletop and timer test | Gap |
| VEN-01 | Processor/vendor and transfer governance | Vendor/subprocessor/transfer register, DPA and permit status; block unapproved connector | Show unavailable/permission-gated source states | Procurement + Privacy | P1, P0 before affected vendor | Contract/register audit | Gap |
| DPIA-01 | High-risk processing requires DPIA | Store DPIA scope, risks, controls, approval/version and review dates | Link applicable notices/controls; no UI activation before approval | DPO/Privacy | P1, P0 before DD/political production | Signed DPIA | Gap |
| REPO-01 | No production data/secrets in repo, logs, fixtures or analytics | Structured redaction, synthetic fixtures, secret scanning, short log retention | Prevent sensitive analytics payloads and console logging | Engineering + Security | P0 | Repo/log scan; telemetry inspection | At risk |

## Data inventory and minimisation decisions

| Data | Classification | Default | Allowed use/condition | UI/storage rule |
|---|---|---|---|---|
| Name and basic contact | Personal | Collect minimum | Application/member administration; outreach only with channel consent | Mask outside authorized roles |
| Political views/alignment | Special category | Do not collect by default | Written consent or counsel-approved Article 6 basis with safeguards | Separate control; never infer silently |
| Political affiliation | Special category | Do not collect by default | Necessary association activity with documented basis | Restricted field; no third-party disclosure without basis/consent |
| Former political membership | Special category | Optional/remove | Only if necessary and counsel-approved | Separate written consent/basis; strict retention |
| Exact residential address | High-risk personal/location | Remove or optional | Only documented eligibility/mailing need | Prefer municipality/district; confidential exact address |
| Full date of birth | High-risk identifier | Remove or optional | Identity/age verification where necessary | Prefer year/age band; mask full value |
| Social profile URLs | Personal/platform data | Optional user-supplied only | Documented purpose and compatible platform terms | Source-scoped; no automatic identity merge |
| Interests/segments | Potentially sensitive/inferred | Controlled optional tags | Non-sensitive operational interests only | Ban vulnerability and protected-trait inference |
| WhatsApp/email/SMS/phone preference | Consent/communication data | Unticked opt-in | Specific channel and purpose | Separate ledger and withdrawal state |
| Relatives/associates | Third-party personal data | DD exception only | Necessary case question, separate basis, restricted access/notice analysis | Context only, never guilt/risk inheritance |
| Sanctions/PEP/adverse media | Risk/profiling data | DD only | Evidence-backed, human-reviewed, corrected and time-bound | Explain match and distinguish allegation/status |

## Acceptance criteria

### P0 before public signup

- Georgian and English layered notice contains controller/DPO, purposes/bases, required fields and consequences, recipients, transfers, retention and rights.
- Manifesto agreement is not used as privacy consent.
- Political/former-membership fields are removed or covered by a separate valid special-category basis and unticked written consent.
- Full DOB, exact address and social profiles are removed or optional with approved necessity.
- Each outreach channel has its own unticked opt-in and withdrawal route.
- Server records the exact notice and consent versions; no production data reaches Git, logs or analytics.

### P0 before staff production access

- Authentication fails closed in production; privileged users use MFA; no shared accounts.
- RBAC and field permissions are enforced server-side for view/search/export/write.
- Immutable audits cover sensitive reads, searches, exports, mutations, disclosures and permission changes.
- Incident, processing, vendor and transfer registers exist; backup restoration and access reviews are tested.

### P0 before DD production or release

- Every search has an authorized case and purpose.
- Every material claim links to exact permitted evidence, authority and freshness.
- Fact/official finding/allegation/inference/analyst assessment are distinct.
- Name-only matches remain candidates; all material matches require analyst disposition and correction/appeal.
- Public export/release requires legal/editorial approval; no automated adverse decision.
- Retention, reverification, dispute blocking and source-takedown propagation operate end to end.

### P1 rollout

- DPIAs completed for political CRM, segmentation, DD/social graph, outreach and vendors.
- Legitimate-interest assessments and processor DPAs approved.
- Transfer map and required permits completed.
- Abuse, accessibility, anti-discrimination, training, vendor review, breach tabletop and rights-SLA tests completed.

## Open questions for Georgian counsel

1. Does FS legally qualify as the political association contemplated by Article 6(1)(k)?
2. Which applicants, volunteers, petition signers, event attendees and supporters constitute persons in “regular contact,” and from what point?
3. Which current State Audit Office subordinate rules define DPO/DPIA thresholds, incident criteria, forms and adequacy destinations after the supervisory transition?
4. Which vendors/locations require transfer permission, particularly hosting, backups, email, analytics and Meta/WhatsApp?
5. What statutory party, election, accounting, membership/application and claims retention periods apply?
6. What additional election-cycle notice, canvassing, voter-data, campaign-finance and communication duties apply?
7. What legal/editorial standard applies to DD publication, allegations and correction rights?
8. Which indirect-notice exceptions, if any, apply to each public-source DD connector?

## Existing design conflicts (reported, not changed)

- `PublicSupporterSignup.jsx` requires full DOB, exact address, social profiles, former-party membership, interests, WhatsApp choice and membership interest.
- The visible required checkbox is manifesto agreement, not a versioned privacy notice or granular consent.
- `routes_crm_people.py` requires and persists those fields for pending signups without a demonstrated purpose/basis/consent ledger or expiry job.
- `FS_AUTH_ENABLED` defaults to false in backend configuration; production must fail closed.
- DD code contains useful provenance, assertion-kind and unresolved-social-identity patterns, but field-level RBAC, immutable sensitive-access/export auditing, DSR/dispute blocking and enforceable retention are not demonstrated.
- Social/Apify retention currently appears to be metadata without a demonstrated deletion job.

