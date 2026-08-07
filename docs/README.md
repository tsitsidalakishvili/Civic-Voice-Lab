# Documentation

This directory is the canonical documentation set for the current product under `React/`. Files under `legacy/` are historical references, not production instructions.

## Audience map

| Need | Document |
| --- | --- |
| Understand the product and modules | [Platform overview](PLATFORM_OVERVIEW.md) |
| Install and run locally | [Getting started](GETTING_STARTED.md) |
| Understand components and data flow | [Architecture](ARCHITECTURE.md) |
| Integrate with the backend | [API guide](API_GUIDE.md) and live `/docs` |
| Deploy, monitor, back up, or recover | [Operations](OPERATIONS.md) |
| Handle access, privacy, and investigations safely | [Security and privacy](SECURITY_PRIVACY.md) |
| Test, review, and contribute changes | [Contributing](CONTRIBUTING.md) |
| Find repository locations | [Project structure](PROJECT_STRUCTURE.md) |
| Work on campaigns | [Campaigns technical specification](campaigns_module_technical_spec.md) |
| Work on investigation integrations | [OpenSanctions stack](due-diligence-opensanctions-stack.md), [FollowTheMoney](due-diligence-follow-the-money.md) |

## Documentation standard

Documentation changes are required when a change affects behavior, API contracts, configuration, data shape, permissions, deployment, operating procedures, or user-visible workflows. Prefer facts verified from code and tests. Mark proposals as proposals and never copy secrets, personal data, or production identifiers into examples.

Each weekly review should:

1. Compare changed source files with this index and linked documents.
2. Check route prefixes, environment variables, package requirements, module names, run commands, and deployment settings.
3. Update the relevant documents and the review date below.
4. Run link/path checks and applicable product tests.
5. Record unresolved gaps under **Known gaps** rather than inventing behavior.

Last repository review: **2026-08-07**

## Known gaps

- A formal production SLA, RTO, and RPO have not been approved; recommended starting targets are identified in the operations guide.
- Data retention periods and lawful bases require owner/legal approval.
- Production hosting, alert destinations, and secret-manager ownership must be recorded by the operator without committing secrets.
- The live OpenAPI schema is the authoritative endpoint-level request/response reference; stable versioned API contracts are not yet published.

