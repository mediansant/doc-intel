# doc-intel

Structured extraction from legal contracts, scored against the [CUAD](https://www.atticusprojectai.org/cuad) ground truth.

Pipeline: PDF → Markdown (Docling) → typed record (OpenAI structured output) → DuckDB → eval against `master_clauses.csv`.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
echo "OPENAI_API_KEY=sk-..." > .env   # .env is git-ignored
```

Place the CUAD data under `data/raw/` (`master_clauses.csv`, `full_contract_pdf/`, `full_contract_txt/`).

## Extracted fields

Defined in [schema.py](src/doc_intel/schema.py); each has a verbatim evidence quote.

`governing_law`, `parties`, `agreement_date`, `renewal_term`, `cap_on_liability`, `non_compete`

## Workflow

Run everything from the project root.

| Step | Command | Output |
|---|---|---|
| Parse a PDF | `uv run python -m doc_intel.parse <file.pdf>` | `data/parsed/<name>.md` |
| Draw the 20-contract sample | `uv run python -m doc_intel.helper` | `evals/sample_v1.txt` |
| Extract the sample | `uv run python -m doc_intel.run_extraction` | `data/extractions/run_v1/*.json` |
| Load run into DuckDB | `uv run python -m doc_intel.backfill [run]` | `data/doc_intel.duckdb` |
| Score against CUAD | `uv run python -m doc_intel.score [run]` | precision/recall table + failure list |
| Analytics queries | `uv run python -m doc_intel.queries` | |
| Tests (offline, no API cost) | `uv run pytest evals` | 31 tests |

Note: `parsed/` must contain the sampled contracts before extraction.

## API

```bash
unset VIRTUAL_ENV   # avoids uv's mismatched-environment warning
uv run uvicorn doc_intel.api:app --reload
```

Open http://127.0.0.1:8000/docs to try it by hand: `POST /extract` → Try it out → choose a PDF. The first upload calls OpenAI; uploading the same file again returns `cached: true`.

- `GET /health`
- `POST /extract` — multipart PDF upload (max 50 MB). Returns the `ContractRecord`; results are cached in DuckDB by PDF hash + model + prompt + schema.

## Tests

`uv run pytest evals` runs offline. `test_api.py` uses FastAPI's `TestClient` with `extract`, Docling and the DuckDB file mocked. It covers a successful extraction, a repeated upload (`cached: true`, model called once), a non-PDF (415), an oversized file (413), parse failures (422) and model failures (502, not cached).

## Layout

```
src/doc_intel/
  schema.py          ContractRecord (pydantic)
  extract.py         prompt, MODEL, OpenAI call
  parse.py           Docling PDF → Markdown
  run_extraction.py  batch extraction of the sample
  store.py           DuckDB schema + append-only inserts
  backfill.py        load a run directory into DuckDB
  matchers.py        normalisers + TP/FP/FN/TN classification
  score.py           eval harness
  queries.py         SQL analytics
  api.py             FastAPI service
evals/               test_matchers.py, test_api.py, sample list, saved results
exploration.ipynb    CUAD label exploration
```

## Results (run_v1, gpt-4o-mini, 20 contracts)

| Field | Precision | Recall |
|---|---|---|
| agreement_date | 0.90 | 0.95 |
| governing_law | 0.95 | 0.95 |
| cap_on_liability | 1.00 | 0.22 |
| non_compete | 0.80 | 0.33 |
| parties (per party) | 0.98 | 0.48 |
| renewal_term | 0.08 | 0.09 |

Weak spots: liability cap and non-compete recall, party coverage, and free-text `renewal_term` (needs a structured schema).

## Known data quirk

CUAD contains `ADUROBIOTECH,...CONSULTING AGREEMENT(1)` as a byte-identical copy of the non-`(1)` file. Both have ground-truth rows, so both are kept.
