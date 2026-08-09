# API Guide

The running FastAPI application publishes the authoritative OpenAPI schema at `/openapi.json` and interactive documentation at `/docs`. This guide describes conventions and route families, not every operation.

## Base and authentication

Local base URL: `http://localhost:8010`. Bearer/API-key modes use `Authorization: Bearer <token>` or the configured API-key header. Password and OIDC modes establish a Secure HttpOnly session and require the configured CSRF header for protected mutations. Never put credentials in URLs, logs, screenshots, or repository files.

Default public rules cover `/health`, `/healthz`, and `/platform/auth/status`. Any public intake/report endpoint must be deliberately added with the narrowest method and exact path supported by the middleware rules.

## Route families

| Prefix | Responsibility |
| --- | --- |
| `/platform` | Authentication, session/OIDC, access-gate, and translation operations |
| `/admin`, `/notices`, `/consents`, `/withdrawals`, `/rights-requests`, `/retention`, `/legal-holds` | Compliance administration, notices, consent/preferences, data-subject requests, retention and legal holds |
| `/crm` | People, signup/invites, segments, events, tasks, campaigns, support, maps and cache |
| `/conversations`, `/comments`, `/votes` | Deliberation lifecycle and participation |
| `/deliberation` | Additional deliberation workflows |
| `/audience-discovery` | Content analysis, segments, messaging, metrics and exports |
| `/due-diligence` | Cases, gated workflow v2, sources, imports, entities, resolution, paths, findings, publications, full checks and connectors |
| `/data-hub` | Connected-data exploration |
| `/data-chat` | AI-assisted questions over approved data context |
| `/translation` | Translation service boundary |

## Contract conventions

- Send and receive JSON unless an endpoint documents file upload/download.
- Use ISO 8601 timestamps with timezone information and treat identifiers as opaque strings.
- Validate maximum file size, row count, text length, and media type before upload.
- Expect `401/403` for access failures, `404` for absent resources, `422` for validation, `429` for rate limits, and `5xx` for dependency/server failures.
- Do not retry unsafe mutations automatically. Add idempotency keys to externally retried write operations.
- Workflow-v2 mutations require `Idempotency-Key`, an approved `X-FS-Purpose-Id`, an authorized session role/purpose/case scope, and optimistic workflow-version checks where specified.
- Avoid leaking internal exceptions or credentials in production responses. The current database exception handlers include an `error` field and require review before internet exposure.

## Change policy

Additive response fields are non-breaking. Removing/renaming fields, narrowing accepted values, changing semantics, or changing public/auth behavior is breaking and requires a migration plan. Before introducing third-party consumers, add a versioned `/api/v1` boundary and contract tests.

For route changes, update the Pydantic schema, tests, OpenAPI description, frontend client, and relevant module documentation together.
