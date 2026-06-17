# FS Due Diligence (Standalone Directory)

This folder is a standalone Due Diligence Streamlit app inside the monorepo.

It shares:
- one Deliberation backend (when links/workflows call it)
- one Neo4j database
- shared app modules under `/crm`

## Run locally

From repo root:

```bash
streamlit run DueDiligence/app.py
```

## Deploy

Use this file as app entrypoint:

- `DueDiligence/app.py`
