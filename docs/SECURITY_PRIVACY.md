# Security, Privacy, and Responsible Use

Treat CRM, deliberation, audience-inference, and due-diligence data as confidential or restricted unless the platform owner approves otherwise. Political affiliation or inference, identity documents, financial evidence, credentials, and investigative material require an explicit purpose and legal basis, named access, minimization, enhanced audit controls, and strict retention.

## Required controls before production

- Keep `FS_AUTH_ENABLED=1`, configure a strong bearer token or API key, and narrowly define public rules.
- Use TLS and exact production CORS origins. CORS is not authentication.
- Store secrets in an approved secret manager; rotate them and separate environments.
- Restrict Neo4j network access and use a least-privilege database identity.
- Apply request-size and rate limits to public intake, uploads, AI, search, and connectors.
- Disable unused integrations, honor kill switches, sanitize logs/exports, and protect caches.
- Review global error responses before public exposure; do not disclose internal dependency details.

## Privacy lifecycle

Before collection, record purpose, owner, categories, source, consent or other lawful basis, recipients/processors, retention, deletion method, and automated inference. Collect only what is needed and provide appropriate correction/deletion handling.

Retention periods are not defined in this repository. The owner must approve schedules for imports, graph data, rejected signups, deliberation content, evidence, exports, caches, logs, and backups. Do not retain by convenience or delete material subject to a legal hold.

## AI and automated analysis

- AI output, sentiment, clusters, identity matches, risk indicators, and reach projections are suggestions, not verified facts.
- Require human review before adverse action, exclusion, publication, or identity merge.
- Do not send restricted data to a provider until contract, region, retention, training-use, and access terms are approved.
- Record provider/model, timestamp, input provenance, prompt/version where practical, and reviewer decision.
- Test Georgian and English quality, bias, and failure modes; preserve a non-AI path for critical workflows.

## Investigation and publication

Use lawful, authorized sources and respect source terms. Maintain provenance from source to statement, entity, finding, and publication. Separate allegations, hypotheses, and verified evidence. Identity matches need reproducible reasoning and reviewer approval. Publications require source availability, redaction, appropriate legal/right-of-reply review, and correction/retraction procedures.

## Security reporting

Never place secrets or personal data in a public issue. Report vulnerabilities privately to the platform owner with the affected component, synthetic reproduction, impact, and containment. Add a root `SECURITY.md` with a monitored contact before external release.

