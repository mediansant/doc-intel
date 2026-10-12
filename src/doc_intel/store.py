"""DuckDB store: append-only extraction runs, raw JSON plus typed view.

A run is one (model, prompt, schema) combination. Extractions are only ever
inserted, never updated, so "did v2 beat v1?" is a query over eval_outcomes.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import duckdb
from pydantic import BaseModel

DB_PATH = Path("data/doc_intel.duckdb")

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id      VARCHAR PRIMARY KEY,   -- sha256 of the PDF bytes
    filename    VARCHAR,
    parser      VARCHAR,
    n_chars     INTEGER,
    parsed_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    run_id         VARCHAR PRIMARY KEY,
    model          VARCHAR,
    prompt_hash    VARCHAR,
    schema_version VARCHAR,
    created_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extractions (
    run_id        VARCHAR REFERENCES runs(run_id),
    doc_id        VARCHAR REFERENCES documents(doc_id),
    record        JSON,                -- the full ContractRecord
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    extracted_at  TIMESTAMP,
    PRIMARY KEY (run_id, doc_id)
);

CREATE TABLE IF NOT EXISTS eval_outcomes (
    run_id  VARCHAR,
    doc_id  VARCHAR,
    field   VARCHAR,
    outcome VARCHAR                    -- TP / FP / FN / TN, one row each
);

CREATE OR REPLACE VIEW contract_records AS
SELECT
    e.run_id,
    e.doc_id,
    d.filename,
    record->>'governing_law'                          AS governing_law,
    from_json(record->'parties', '["VARCHAR"]')       AS parties,
    TRY_CAST(record->>'agreement_date' AS DATE)       AS agreement_date,
    record->>'renewal_term'                           AS renewal_term,
    (record->>'cap_on_liability')::BOOLEAN            AS cap_on_liability,
    (record->>'non_compete')::BOOLEAN                 AS non_compete,
    record,
    e.extracted_at
FROM extractions e
JOIN documents d USING (doc_id);
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def init_db(path: str | Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def already_extracted(
    con: duckdb.DuckDBPyConnection,
    doc_id: str,
    model: str,
    prompt_hash: str,
    schema_version: str,
) -> bool:
    """Idempotency key: document hash + model + prompt hash + schema version."""
    row = con.execute(
        """
        SELECT 1
        FROM extractions e
        JOIN runs r USING (run_id)
        WHERE e.doc_id = ? AND r.model = ? AND r.prompt_hash = ? AND r.schema_version = ?
        LIMIT 1
        """,
        [doc_id, model, prompt_hash, schema_version],
    ).fetchone()
    return row is not None


def save_extraction(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    doc_id: str,
    record: BaseModel | str,
    *,
    model: str,
    prompt_hash: str,
    schema_version: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
) -> None:
    """Append one extraction. Creates the run row on first use; never updates.

    Raises if (run_id, doc_id) already exists. The doc must be in `documents`.
    """
    record_json = record if isinstance(record, str) else record.model_dump_json()
    now = datetime.now()
    con.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        [run_id, model, prompt_hash, schema_version, now],
    )
    con.execute(
        "INSERT INTO extractions VALUES (?, ?, ?, ?, ?, ?, ?)",
        [run_id, doc_id, record_json, input_tokens, output_tokens, latency_ms, now],
    )
