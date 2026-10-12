"""Score a saved extraction run against CUAD's master_clauses.csv.

Usage (from the project root):
    python -m doc_intel.score                # scores run_v1
    python -m doc_intel.score run_v2

Outcomes go to the eval_outcomes table in DuckDB (run `python -m doc_intel.backfill`
first so the documents exist). Re-scoring a run replaces its rows.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from doc_intel.matchers import (
    classify, classify_set, exact, loose_text,
    norm_bool, norm_date, norm_law, norm_parties, norm_text,
)
from doc_intel.queries import PRECISION_RECALL
from doc_intel.store import init_db

SAMPLE_PATH = Path("evals/sample_v1.txt")
CSV_PATH = Path("data/raw/master_clauses.csv")
RUNS_DIR = Path("data/extractions")

# field -> (exact ground-truth column, normaliser, scorer)
# Parties uses the raw span column: its labelled spans ARE the values.
FIELDS = {
    "agreement_date":   ("Agreement Date-Answer",   norm_date,    lambda e, t: classify(e, t, exact)),
    "governing_law":    ("Governing Law-Answer",    norm_law,     lambda e, t: classify(e, t, exact)),
    "cap_on_liability": ("Cap On Liability-Answer", norm_bool,    lambda e, t: classify(e, t, exact)),
    "non_compete":      ("Non-Compete-Answer",      norm_bool,    lambda e, t: classify(e, t, exact)),
    "parties":          ("Parties",                 norm_parties, classify_set),
    "renewal_term":     ("Renewal Term-Answer",     norm_text,    lambda e, t: classify(e, t, loose_text)),
}
PER_ITEM_FIELDS = {"parties"}  # scored per party, so counts won't sum to n contracts

_EXT = re.compile(r"\.(pdf|txt)$", re.IGNORECASE)


def doc_key(name: str) -> str:
    """Filename without extension, for an exact (not substring) join."""
    return _EXT.sub("", str(name).strip()).lower()


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map each field to its real column name; fail loudly if one is missing."""
    by_lower = {c.strip().lower(): c for c in df.columns}
    resolved = {}
    for field, (wanted, _, _) in FIELDS.items():
        if wanted.lower() not in by_lower:
            raise KeyError(f"{field}: no column named {wanted!r}. Columns: {list(df.columns)}")
        resolved[field] = by_lower[wanted.lower()]
    return resolved


def load_truth(csv_path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    df = pd.read_csv(csv_path)
    df["_key"] = df[df.columns[0]].map(doc_key)
    dupes = df["_key"][df["_key"].duplicated()].tolist()
    if dupes:
        raise ValueError(f"Duplicate filenames in ground truth: {dupes}")
    return df.set_index("_key"), resolve_columns(df)


def score_run(run_name: str = "run_v1"):
    filenames = [l.strip() for l in SAMPLE_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    truth_df, columns = load_truth(CSV_PATH)
    run_dir = RUNS_DIR / run_name

    con = init_db()
    doc_ids = dict(con.execute("SELECT filename, doc_id FROM documents").fetchall())
    outcome_rows = []  # (run_id, doc_id, field, outcome)

    counts = {f: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for f in FIELDS}
    failures = {f: [] for f in FIELDS}
    scored, skipped = 0, []

    for fname in filenames:
        json_path = run_dir / f"{fname}.json"
        key = doc_key(fname)
        if not json_path.exists():
            skipped.append((fname, "no extraction file"))
            continue
        if key not in truth_df.index:
            skipped.append((fname, "no ground-truth row"))
            continue
        if fname not in doc_ids:
            skipped.append((fname, "not in documents table"))
            continue
        extracted = json.loads(json_path.read_text(encoding="utf-8"))
        row = truth_df.loc[key]
        scored += 1

        for field, (_, normalise, scorer) in FIELDS.items():
            raw_ext, raw_truth = extracted.get(field), row[columns[field]]
            ext, truth = normalise(raw_ext), normalise(raw_truth)
            outcomes = scorer(ext, truth)
            for outcome in outcomes:
                counts[field][outcome] += 1
                outcome_rows.append((run_name, doc_ids[fname], field, outcome))
            if "FP" in outcomes or "FN" in outcomes:
                failures[field].append({
                    "file": fname, "outcomes": outcomes,
                    "ext": ext, "truth": truth,
                    "raw_ext": raw_ext, "raw_truth": raw_truth,
                    "evidence": extracted.get(f"{field}_evidence"),
                })

    # ---- self-checks: the harness should tell you when it is wrong ----
    if skipped:
        print(f"\n!! SKIPPED {len(skipped)} of {len(filenames)} contracts:")
        for fname, why in skipped:
            print(f"   {why}: {fname}")
    for field, c in counts.items():
        if field in PER_ITEM_FIELDS:
            continue
        # a wrong value adds one FP and one FN, so count contracts, not outcomes
        wrong = sum(1 for f in failures[field] if f["outcomes"] == ["FP", "FN"])
        contracts = c["TP"] + c["TN"] + c["FP"] + c["FN"] - wrong
        assert contracts == scored, f"{field}: outcomes cover {contracts} contracts, expected {scored}"

    # ---- persist outcomes (system of record), then print the table from SQL ----
    con.execute("DELETE FROM eval_outcomes WHERE run_id = ?", [run_name])
    con.executemany("INSERT INTO eval_outcomes VALUES (?, ?, ?, ?)", outcome_rows)
    print(f"\n=== {run_name}: {scored} of {len(filenames)} contracts scored ===")
    print(con.execute(f"SELECT * FROM ({PRECISION_RECALL}) WHERE run_id = ?", [run_name]).df().to_markdown(index=False))
    print("(parties is scored per party; a wrong value counts as FP and FN)")

    # ---- failures ----
    print("\n=== Failure list ===")
    for field, items in failures.items():
        if not items:
            continue
        print(f"\n--- {field} ({len(items)}) ---")
        for f in items:
            print(f"File: {f['file']}  [{'+'.join(sorted(set(f['outcomes'])))}]")
            print(f"  Extracted : {f['ext']!r}")
            print(f"  Truth     : {f['truth']!r}")
            print(f"  Raw ext   : {f['raw_ext']!r}")
            print(f"  Raw truth : {f['raw_truth']!r}")
            print(f"  Evidence  : {f['evidence']}")
    return counts, failures


if __name__ == "__main__":
    score_run(sys.argv[1] if len(sys.argv) > 1 else "run_v1")