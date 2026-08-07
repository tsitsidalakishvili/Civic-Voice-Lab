# Frontend compliance specification

Planning only. Implementation requires explicit user approval and approved backend contracts.

## Public signup

- Show a short Georgian notice with English option and expandable full notice before fields.
- State controller/DPO contact, purposes/bases, recipients, transfers, retention and rights.
- Label every field required or optional and explain the consequence of omitting required data.
- Default to minimum fields. Prefer age eligibility/year and municipality/district over full DOB/exact address.
- Political affiliation/views/former membership are special category and removed by default; if approved, display a separate explanation and unticked written-consent control.
- Manifesto agreement, application submission, privacy acknowledgement, special-category consent, analytics, public display and outreach must be distinct.
- Email, SMS, phone and WhatsApp opt-ins are separate, unticked and purpose-specific. Explain that WhatsApp groups may expose membership/number to participants.
- Confirmation shows recorded choices and direct withdrawal/privacy-dashboard links.

## Privacy dashboard and outreach

- Display active purposes, field categories, sources, notice/consent versions, recipients/transfers and retention criteria.
- Permit equally easy channel withdrawal/unsubscribe and show suppression status.
- Support access/copy, correction, deletion/termination, blocking, portability, withdrawal and appeal requests with identity verification, due date and status.
- Never require the user to contact staff through the marketing channel to opt out.

## Staff CRM

- Mask full DOB, exact address, personal IDs, political fields and private contact details by default.
- Reveal requires authorization, a reason and re-authentication where appropriate; the server remains authoritative.
- Show purpose/case context and audit indicator for sensitive actions.
- Exports disclose selected fields, purpose, recipient and retention, and require explicit confirmation/approval.
- Segments cannot use prohibited political/vulnerability/protected-trait inference.

## Due diligence

- Every statement displays assertion label: fact/source-stated, official finding, allegation, inference/hypothesis or analyst assessment.
- Show publisher, authority tier, URL/document, publication/effective/retrieval dates, freshness, licence and exact evidence locator.
- Show contradictions, corrections, stale/taken-down/disputed status and block disputed facts from release.
- Match UI shows total score, component reasons, aliases/identifiers, sources, threshold/version and conflicts; name-only hits remain unresolved.
- Analyst controls include accept, reject, defer, false positive, request correction and appeal/review history.
- Relatives/associates are contextual relationships without inherited risk labels.
- Publishing/exporting requires resolved identity, evidence-backed accepted findings, human review and legal/editorial approval; show blockers plainly.

## FE acceptance tests

- No pre-ticked or bundled consent; keyboard/screen-reader labels and Georgian/English notice versions render correctly.
- Required/optional behavior matches backend policy and failed optional consent does not block core application unless legally necessary.
- Withdrawal is as easy as opt-in and immediately reflected across channels.
- Unauthorized users never receive sensitive values in DOM/network responses, not merely hidden CSS.
- DD snapshots clearly distinguish allegation/inference from fact and show provenance/freshness.
- Name-only sanction/PEP fixture cannot be accepted automatically; analyst reason and correction/appeal routes work.
- Release button remains blocked for disputes, unresolved candidates, missing evidence or legal/editorial approval.
- No sensitive values are emitted to console, analytics, error reporting or URLs.

## Existing frontend conflicts to estimate

- Public signup currently requires full DOB, exact address, social profile, former-party membership, interests, WhatsApp choice and membership interest.
- The required manifesto checkbox does not constitute granular privacy/special-category/marketing consent.
- No layered notice, field-purpose explanation, consent-version display or privacy dashboard is evident in the reviewed signup.
- DD UI has strong workflow/provenance foundations but needs verified sensitive masking, match explanation, correction/appeal and legal release gates.

