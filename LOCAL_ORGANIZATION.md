# Local Folder Organization

This folder was cleaned on 2026-06-25 without changing deployment roots.

## Active product
- `React/` - current deployed React/FastAPI product.
- `React/Front end/` - Vite frontend. Keep this path until Vercel settings are updated.
- `React/Back end/` - FastAPI backend. Keep this path until Render settings are updated.

## Legacy apps
- `legacy/CRM/` - older CRM app kept for reference.
- `legacy/Deliberation/` - older deliberation app kept for reference.
- `legacy/DueDiligence/` - older due diligence app kept for reference.

New product features should go into `React/`, not the legacy folders.

## Local support folders
- `tools/geocoding/` - one-off coordinate/geocoding repair scripts.
- `tools/diagnostics/` - one-off database inspection scripts.
- `tools/migrations/` - import/setup scripts for CRM data and subscription tiers.
- `tools/cypher/` - ad hoc Neo4j Cypher scripts.
- `data/imports/` - original CSV import/source data.
- `data/query_exports/` - Neo4j query CSV exports.
- `docs/exports/` - static HTML exports kept for reference.
- `assets/screenshots/` - screenshots/reference images.

## Generated local files
- `runtime/logs/` - local server logs, ignored by git.
- `outputs/` - generated local output, ignored by git.
- React builds, dependency folders, Python caches, virtualenvs, and runtime cache snapshots are ignored by git.
