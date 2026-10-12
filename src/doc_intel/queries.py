"""Analytics queries over the DuckDB store.

Usage (from the project root):
    python -m doc_intel.queries
"""
from __future__ import annotations

from doc_intel.store import init_db

LAW_COUNTS = """
SELECT governing_law, count(*) AS contracts
FROM contract_records
WHERE run_id = 'run_v1'
GROUP BY governing_law
ORDER BY contracts DESC, governing_law NULLS LAST
"""

CAP_NO_NON_COMPETE = """
SELECT filename, governing_law, agreement_date
FROM contract_records
WHERE run_id = 'run_v1' AND cap_on_liability AND NOT non_compete
ORDER BY filename
"""

# Precision/recall per field per run. `support` is what recall rests on.
PRECISION_RECALL = """
SELECT
    run_id,
    field,
    count(*) FILTER (outcome = 'TP') AS tp,
    count(*) FILTER (outcome = 'FP') AS fp,
    count(*) FILTER (outcome = 'FN') AS fn,
    count(*) FILTER (outcome = 'TN') AS tn,
    tp + fn                          AS support,
    round(tp / nullif(tp + fp, 0), 2) AS precision,
    round(tp / nullif(tp + fn, 0), 2) AS recall
FROM eval_outcomes
GROUP BY run_id, field
ORDER BY run_id, field
"""

if __name__ == "__main__":
    con = init_db()
    for title, sql in [
        ("Contracts per governing law (run_v1)", LAW_COUNTS),
        ("Liability cap but no non-compete (run_v1)", CAP_NO_NON_COMPETE),
        ("Precision / recall per field per run", PRECISION_RECALL),
    ]:
        print(f"\n=== {title} ===")
        print(con.sql(sql))
