import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO

import duckdb
from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter
from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from doc_intel.extract import MODEL, SYSTEM_PROMPT, extract
from doc_intel.schema import ContractRecord
from doc_intel.store import (
    already_extracted,
    init_db,
    save_extraction,
    sha256_bytes,
    sha256_text,
)

PARSER = "docling"
PROMPT_HASH = sha256_text(SYSTEM_PROMPT)
SCHEMA_VERSION = sha256_text(json.dumps(ContractRecord.model_json_schema(), sort_keys=True))[:12]
# One run per (model, prompt, schema) combination, so repeat uploads share it.
RUN_ID = sha256_text(f"{MODEL}|{PROMPT_HASH}|{SCHEMA_VERSION}")[:12]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.converter = DocumentConverter()  # loaded once
    app.state.db = init_db()
    yield
    app.state.db.close()


app = FastAPI(title="Document intelligence", lifespan=lifespan)


class ExtractionResponse(BaseModel):
    doc_id: str
    run_id: str
    cached: bool
    record: ContractRecord


@app.get("/health")
def health():
    return {"status": "ok"}


def _cached_record(con: duckdb.DuckDBPyConnection, doc_id: str) -> ContractRecord | None:
    if not already_extracted(con, doc_id, MODEL, PROMPT_HASH, SCHEMA_VERSION):
        return None
    row = con.execute(
        """
        SELECT e.record::VARCHAR
        FROM extractions e JOIN runs r USING (run_id)
        WHERE e.doc_id = ? AND r.model = ? AND r.prompt_hash = ? AND r.schema_version = ?
        LIMIT 1
        """,
        [doc_id, MODEL, PROMPT_HASH, SCHEMA_VERSION],
    ).fetchone()
    return ContractRecord.model_validate_json(row[0])


@app.post("/extract", response_model=ExtractionResponse)
def extract_contract(file: UploadFile):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Only PDF files are supported")

    doc_id = sha256_bytes(data)
    # DuckDB connections aren't thread-safe; this handler runs in a threadpool.
    con = app.state.db.cursor()
    try:
        record = _cached_record(con, doc_id)
        if record is not None:
            return ExtractionResponse(doc_id=doc_id, run_id=RUN_ID, cached=True, record=record)

        filename = file.filename or f"{doc_id}.pdf"
        try:
            result = app.state.converter.convert(
                DocumentStream(name=filename, stream=BytesIO(data))
            )
            markdown = result.document.export_to_markdown()
        except Exception as e:
            raise HTTPException(422, f"Could not parse PDF: {e}")
        if not markdown.strip():
            raise HTTPException(422, "No text could be extracted from the PDF")

        start = time.perf_counter()
        try:
            record = extract(markdown, model=MODEL)
        except Exception as e:
            raise HTTPException(502, f"Extraction failed: {e}")
        latency_ms = int((time.perf_counter() - start) * 1000)
        if record is None:  # model refusal / unparsable output
            raise HTTPException(502, "Model returned no structured record")

        con.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [doc_id, filename, PARSER, len(markdown), datetime.now()],
        )
        try:
            save_extraction(
                con, RUN_ID, doc_id, record,
                model=MODEL, prompt_hash=PROMPT_HASH, schema_version=SCHEMA_VERSION,
                latency_ms=latency_ms,
            )
        except duckdb.ConstraintException:
            # A concurrent request for the same document won the race.
            return ExtractionResponse(doc_id=doc_id, run_id=RUN_ID, cached=True, record=record)

        return ExtractionResponse(doc_id=doc_id, run_id=RUN_ID, cached=False, record=record)
    finally:
        con.close()
