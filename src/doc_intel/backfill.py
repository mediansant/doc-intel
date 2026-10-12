"""Backfill an existing run directory (data/extractions/<run>/) into DuckDB.

Usage (from the project root):
    python -m doc_intel.backfill            # run_v1
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from doc_intel.extract import SYSTEM_PROMPT
from doc_intel.store import init_db, sha256_bytes, sha256_text

PDF_DIR = Path("data/raw/full_contract_pdf")
PARSED_DIR = Path("data/parsed")
RUNS_DIR = Path("data/extractions")


def backfill(run_id: str = "run_v1") -> None:
    run_dir = RUNS_DIR / run_id
    config = json.loads((run_dir / "run_config.json").read_text())
    # run_v1 predates prompt hashing; the current prompt is the one it used.
    prompt_hash = sha256_text(SYSTEM_PROMPT)
    pdfs = {p.stem: p for p in PDF_DIR.rglob("*.pdf")}

    con = init_db()
    names = [p.stem for p in run_dir.glob("*.json") if p.name != "run_config.json"]
    for name in names:
        md = PARSED_DIR / f"{name}.md"
        con.execute(
            "INSERT INTO documents VALUES (?, ?, 'docling', ?, ?) ON CONFLICT DO NOTHING",
            [
                sha256_bytes(pdfs[name].read_bytes()),
                name,
                len(md.read_text(encoding="utf-8")) if md.exists() else None,
                datetime.fromtimestamp(md.stat().st_mtime) if md.exists() else None,
            ],
        )

    con.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        [run_id, config["model"], prompt_hash, config["schema_hash"],
         datetime.fromtimestamp((run_dir / "run_config.json").stat().st_mtime)],
    )

    # read_text keeps each file's raw JSON; filename = <name>.json joins to documents.
    con.execute(
        f"""
        INSERT INTO extractions
        SELECT ?, d.doc_id, f.content::JSON, NULL, NULL, NULL, f.last_modified::TIMESTAMP
        FROM read_text('{run_dir.as_posix()}/*.json') f
        JOIN documents d
          ON f.filename LIKE '%/' || d.filename || '.json'
        WHERE f.filename NOT LIKE '%/run_config.json'
        ON CONFLICT DO NOTHING
        """,
        [run_id],
    )
    n = con.execute("SELECT count(*) FROM extractions WHERE run_id = ?", [run_id]).fetchone()[0]
    print(f"{run_id}: {n} extractions in DB (of {len(names)} files)")


if __name__ == "__main__":
    backfill(sys.argv[1] if len(sys.argv) > 1 else "run_v1")
