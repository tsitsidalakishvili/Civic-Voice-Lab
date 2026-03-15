## Streamlit (experiments)

Use this folder for rapid prototyping and experiments.

### Run (frontend)
```
streamlit run "Front end/Home.py"
```

### Run (backend)
```
cd "Back end"
python -m uvicorn app:app --host 0.0.0.0 --port 8011
```

### Mock data mode
Set `STREAMLIT_MOCK_DATA=true` to avoid touching production data.

- Quick switch: copy `Front end/.env.experiment` over `Front end/.env`
- When enabled, Neo4j reads/writes are skipped.
 - Use `Front end/.env.production` for a production API base.
