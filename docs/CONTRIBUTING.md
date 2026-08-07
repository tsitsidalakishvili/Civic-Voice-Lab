# Testing and Contribution Guide

Create a focused branch, preserve unrelated work, and keep code, tests, safe configuration examples, and documentation together. `main` should remain deployable. Follow [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) for repository conventions.

## Checks

```powershell
cd "React/Front end"
npm ci
npm run lint
npm run test -- --run
npm run build

cd "../Back end/deliberation/api"
python -m pytest app/tests
```

If pytest is absent, install it as a local development dependency. Tests that call databases or external services must be explicitly marked, isolated from unit tests, and use non-production accounts and data.

## Definition of done

- Acceptance criteria and edge cases are covered.
- Validation, authorization, privacy, audit/provenance, failure, and retry behavior are considered.
- Tests cover changed behavior; frontend build and lint pass.
- API schemas and clients agree; breaking changes have a migration plan.
- New environment variables appear in a safe example and configuration documentation.
- User, operations, security, data-model, and module documents are updated as applicable.
- No credentials, real personal data, output, caches, logs, dependencies, virtualenv, or build artifacts are committed.
- A reviewer can deploy, verify, monitor, and roll back the change.

## Test strategy

- Unit: normalization, scoring, authorization rules, transformations, and UI states.
- API: validation, access denied/allowed, domain behavior, not-found/conflict, dependency failure, and response contracts.
- Integration: Neo4j constraints/queries, import/export round trips, connector adapters, and caches in isolated environments.
- End-to-end: access gate, CRM search/edit, public intake, deliberation participation/report, investigation flow, and data-hub navigation.
- Non-functional: accessibility, localization, upload limits, rate limits, latency, backup/restore, and sensitive-data leakage.

Use synthetic fixtures. Minimize and irreversibly de-identify any production-shaped data before it enters development.

## Documentation review checklist

Use `git diff --name-only` since the last review. Compare frontend modules, router inclusions, route decorators, environment reads, requirements/package files, migrations, hosting configuration, and public/auth rules against `docs/README.md`. Validate Markdown links and commands. Update the review date only after completing the checks; log unresolved discrepancies under Known gaps.

