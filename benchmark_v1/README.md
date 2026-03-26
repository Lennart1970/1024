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

## Run the benchmark

Set at least one provider key in your environment first.

```powershell
$env:OPENAI_API_KEY = "..."
# optional: $env:OPENAI_MODEL = "gpt-5"

$env:ANTHROPIC_API_KEY = "..."
# optional: $env:ANTHROPIC_MODEL = "claude-sonnet-4-5"

python .\benchmark_v1\run_benchmark.py
```

The runner will:
- load questions from `questions.sample.csv`
- create/update `runs`, `models`, and `responses`
- archive raw request/response JSON under `benchmark_v1/raw/`
- compute rough per-question metrics

## Generate the local HTML report

```powershell
python .\benchmark_v1\generate_report.py
```

Then open `benchmark_v1\report.html` in your browser.

## Next likely files

- `models.yaml`
- `.env.example`
- richer question sets
