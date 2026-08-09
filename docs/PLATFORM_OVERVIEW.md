# Platform Overview

## Purpose

Freedom Square brings civic and organizational workflows into one connected workspace. It supports teams that need to organize people, design outreach, collect structured public input, investigate entities and evidence, and analyze relationships. Because these workflows can involve sensitive personal and political data, least-privilege access and human review are core operating requirements.

## Product modules

| Module | Primary workflows | Typical output |
| --- | --- | --- |
| CRM / Network | People, profiles, supporter intake, invitations, events, tasks, segments, maps | Searchable relationship records and reusable audiences |
| Campaigns & Audience | Describe a campaign or cause, match messengers, project reach, manage/import/export roster | Ranked messenger matches and campaign projections |
| Deliberation | Create conversations, distribute questionnaires, collect votes/comments, moderate, analyze and report | Participation data, themes, sentiment, consensus and reports |
| Due Diligence | Register sources, import evidence, resolve identities, trace graph paths, curate findings, publish | Provenance-backed investigation cases and findings |
| Audience Discovery | Crawl or upload content, cluster it, confirm segments, develop messaging, export results | Evidence-linked audience segments and messaging suggestions |
| Data Hub / Data Chat | Inspect connectors and graph data; ask assisted data questions | Connected-data views and AI-assisted summaries |
| Admin | Operational and data controls | Configuration and maintenance actions |

Public views support supporter signup, event registration, campaign sharing, deliberation questionnaires, and public reports. Public access must be intentionally configured; do not assume a UI route is safe merely because it is public-facing.

## Roles

The current implementation supports bearer/API-key access, exact-email password sessions for a small team, and organization OIDC. The newer due-diligence workflow enforces `admin`, `compliance`, and `investigator` roles plus purpose and case scopes, but authorization is not yet uniformly fine-grained across every legacy module. Use the [private deployment baseline](PRIVATE_DEPLOYMENT.md) and separate environments or gateways where privileges materially differ.

Recommended operational roles:

- **Platform owner:** accountable for purpose, risk acceptance, retention, and production access.
- **Administrator:** configures integrations, users/access, imports, and recovery.
- **Operator/analyst:** manages CRM, campaigns, deliberation, and investigations within an approved purpose.
- **Reviewer/editor:** verifies identity matches, evidence, findings, moderation, and publication.
- **Participant/public user:** accesses only deliberately exposed intake, registration, questionnaire, or report flows.
- **Developer:** changes code and migrations without routine access to production personal data.

## Lifecycle

1. Define the purpose, audience, owner, retention rule, and acceptable sources.
2. Collect or import the minimum necessary data with provenance and consent/legal-basis records.
3. Normalize and connect entities in Neo4j; preserve source identifiers and review ambiguous matches.
4. Analyze or act through a module. Treat AI, sentiment, clustering, matching, and projections as decision support.
5. Require human review for moderation, identity resolution, adverse findings, and publication.
6. Export or publish only approved data; redact personal data and preserve citations.
7. Retain, archive, correct, or delete data according to the approved policy and audit record.

## Current limitations

- Authorization maturity differs by module. OIDC and scoped due-diligence authorization exist, while legacy routes still require a deliberate access review.
- Exact-email password-file authentication is intended only for a very small private team; organization OIDC with MFA is the target as risk or user count grows.
- Health checks verify the API/database path but do not establish full business readiness for every external connector.
- Several integrations are optional and degrade or return configuration errors when credentials are absent.
- Legacy Streamlit applications remain for reference and should not receive new production work by default.
