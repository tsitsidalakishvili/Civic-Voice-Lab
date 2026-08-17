# Deployment and Operations

## Deployment topology

The documented production shape is a static frontend (for example Vercel) and a Python web service (for example Render) connected to managed Neo4j. Hosting vendors are replaceable; preserve TLS, secret management, private administration, backups, logs, and health monitoring.

Frontend: run `npm ci` and `npm run build` from `React/Front end`. The backend container is rooted at `React/Back end/deliberation/api`: install that directory's `requirements.txt` and run `python -m uvicorn app.main:app --host 0.0.0.0 --port $env:PORT`. For a source checkout launched from `React/Back end`, use `python -m uvicorn deliberation.api.app.main:app` instead.

Set the frontend hosting root to `React/Front end` and use the backend API container directory above when using the supplied Dockerfile. Configure the frontend API URL at build time, exact production CORS origins on the backend, and secrets in the host secret store.

## Release checklist

1. Review migration, privacy, public-route, and dependency impact.
2. Run frontend lint, unit tests, and production build; run backend tests for affected routes.
3. Back up Neo4j before schema/data migrations and verify restore instructions.
4. Deploy backend; check `/healthz`, authentication rejection, and one critical read.
5. Deploy frontend; smoke-test access, CRM, one deliberation flow, and the affected module.
6. Verify connector capability/status without sending real data unnecessarily.
7. Monitor errors and latency; record release, operator, revision, and rollback point.

## Observability

Monitor API availability, health state, latency percentiles, 4xx/5xx rates, Neo4j failures, connector failures, jobs, storage growth, and authentication failures. Logs should carry request IDs and stable error codes while excluding tokens, raw personal data, uploaded documents, message bodies, and provider credentials.

Recommended initial targets, pending owner approval: 99.5% monthly availability, 24-hour recovery point objective, and four-hour recovery time objective. These are proposals, not current guarantees.

## Backup and recovery

- Use provider-supported Neo4j snapshots at least daily and before migrations.
- Encrypt backups, restrict restore access, apply source-data retention, and test restore quarterly.
- Back up configuration metadata and source manifests, never plaintext secrets.
- After restore, validate constraints, record counts, critical relationships, authentication, and representative workflows.

## Password authentication during Neo4j outages

When password authentication uses the local access-user file or approved shared credential, the backend can issue and validate a process-local fallback session if Neo4j is temporarily unavailable. The fallback is capped at 2,048 sessions and its minimized audit buffer at 1,000 events; both are lost when the process restarts. Normal idle, absolute, and credential-expiry checks still apply. Treat this as a short outage bridge only: restore Neo4j promptly, record the outage window, and reconcile any missing durable authentication audit evidence before closing the incident. OIDC sessions do not use this fallback.

## Incident runbook

1. Triage severity, impacted users/data, start time, and owner.
2. Contain by disabling an affected connector/public route, rotating secrets, or restricting ingress.
3. Preserve sanitized logs and provider audit events; avoid altering evidence.
4. Recover from a known-good revision/snapshot and verify critical paths.
5. Notify the owner and follow applicable breach or contractual notification requirements.
6. Document timeline, cause, impact, remediation, and follow-up tests.

For a database outage, check `/healthz`, credentials, network allowlists, TLS, service status, and quotas. For a bad release, redeploy the last known-good revision and reverse migrations only with a tested down plan. For a compromised secret, revoke it at the provider first, update the secret store, redeploy, inspect logs, and rotate related credentials.

## Maintenance cadence

- Weekly: documentation drift, dependency/security alerts, failed jobs/connectors, error trends, public endpoints, and backup completion.
- Monthly: access review, secret age, restore evidence, storage/retention, dependency upgrades, and unused integrations.
- Quarterly: disaster-recovery test, threat-model review, privacy/retention review, and incident tabletop.
