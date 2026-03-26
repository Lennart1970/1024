# benchmark_v1

Minimal SQLite database scaffold for the LLM divergence benchmark.

## Files

- `schema.sql` — v1 schema
- `init_db.py` — creates the SQLite database from the schema
- `questions.sample.csv` — tiny starter question set
- `benchmark.sqlite` — created after running `init_db.py`

## Create the database

```powershell
python .\benchmark_v1\init_db.py
```

## Inspect the schema

```powershell
python -c "import sqlite3; c=sqlite3.connect(r'benchmark_v1/benchmark.sqlite'); print(c.execute(\"select name from sqlite_master where type='table' order by name\").fetchall())"
```

## Suggested next files

- `run_benchmark.py`
- `generate_report.py`
- `models.yaml`
- `.env.example`
