# Demo Data

This folder contains safe mock data for building a public demo version of Civic Voice Lab / Freedom Square.

The demo data must never contain real supporter names, phones, emails, addresses, or comments.

Recommended workflow:

1. Generate deterministic mock CSV files:

```powershell
python tools/demo/generate_demo_crm_data.py
```

2. Review files in `data/demo/generated/`.

3. Seed a separate demo Neo4j Aura database only after setting demo database credentials:

```powershell
python tools/demo/seed_demo_people.py --apply
```

The seed script defaults to dry-run mode unless `--apply` is provided.
