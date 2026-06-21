# Local Folder Organization

This folder was cleaned on 2026-06-21.

## Main app folders
- `React/` - current React frontend and backend app.
- `CRM/`, `Deliberation/`, `DueDiligence/` - older Streamlit app folders kept intact.

## Local support folders
- `tools/geocoding/` - one-off coordinate/geocoding repair scripts.
- `tools/diagnostics/` - one-off database inspection scripts.
- `tools/migrations/` - import/setup scripts for CRM data and subscription tiers.
- `tools/cypher/` - ad hoc Neo4j Cypher scripts.
- `data/imports/` - original CSV import/source data.
- `data/query_exports/` - Neo4j query CSV exports.
- `docs/exports/` - static HTML exports kept for reference.
- `assets/screenshots/` - screenshots/reference images.

## Removed generated files
Backend logs, React build/dependency caches, Python `__pycache__` folders, temporary CRM map JSON snapshots, and timestamped geocoding result CSVs were removed because they can be regenerated.
