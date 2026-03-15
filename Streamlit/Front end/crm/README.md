# FS CRM (Standalone Directory)

This folder is a standalone CRM Streamlit app inside the monorepo.

It shares:
- the same Neo4j database (`crm/db/neo4j.py`)
- the same shared code under `/crm`

## Run locally

From repo root:

```bash
streamlit run CRM/app.py
```

Or from this folder:

```bash
cd CRM
streamlit run app.py
```

## Deploy

Use this file as app entrypoint:

- `CRM/app.py`
