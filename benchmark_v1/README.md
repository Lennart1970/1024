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

## Install dependencies

```powershell
python -m pip install -r .\benchmark_v1\requirements.txt
```

## Run the benchmark

The runner automatically reads `benchmark_v1\.env` if it exists.

### Validate questions first (preflight)

```powershell
python .\benchmark_v1\validate_questions.py
```

```powershell
python .\benchmark_v1\run_benchmark.py
```

The runner will:
- load questions from `questions.sample.csv`
- create/update `runs`, `models`, and `responses`
- archive raw request/response JSON under `benchmark_v1/raw/`
- compute rough per-question metrics

## Rotation logic (what "exciting" means)

`cycle_questions.py` rotates active questions using prior benchmark outcomes:

- drop the 6 least exciting active questions
- add up to 12 new questions (bank first, then inactive high-divergence questions, then generated follow-ups)

Exciting is computed from historical metrics (higher is better):

- 60% deep-dive/divergence priority
- 25% lexical divergence
- 15% stance divergence

## Generate the local HTML report

```powershell
python .\benchmark_v1\generate_report.py
```

Then open `benchmark_v1\report.html` in your browser.

## Next likely files

- `models.yaml`
- `.env.example`
- richer question sets
