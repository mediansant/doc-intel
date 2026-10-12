import json
import hashlib
from pathlib import Path
from doc_intel.extract import MODEL, extract
from doc_intel.schema import ContractRecord

def run_batch():
    sample_path = Path("evals/sample_v1.txt")
    if not sample_path.exists():
        print("Sample file not found at evals/sample_v1.txt. Please create your 20-contract sample list first.")
        return
        
    filenames = [line.strip() for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    run_name = "run_v1"
    output_dir = Path(f"data/extractions/{run_name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Snapshot configuration for reproducibility
    model_name = MODEL
    schema_code = ContractRecord.model_json_schema()
    
    config_snapshot = {
        "model": model_name,
        "schema_hash": hashlib.sha256(json.dumps(schema_code, sort_keys=True).encode()).hexdigest(),
    }
    (output_dir / "run_config.json").write_text(json.dumps(config_snapshot, indent=2))
    
    print(f"Starting batch extraction for {len(filenames)} contracts...")
    for idx, fname in enumerate(filenames, 1):
        md_path = Path("data/parsed") / f"{fname}.md"
        if not md_path.exists():
            print(f"[{idx}/{len(filenames)}] Warning: Parsed markdown missing for {fname} at {md_path}")
            continue
            
        print(f"[{idx}/{len(filenames)}] Extracting: {fname}")
        contract_text = md_path.read_text(encoding="utf-8")
        
        try:
            record = extract(contract_text, model=model_name)
            out_json_path = output_dir / f"{fname}.json"
            out_json_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            print(f"  -> Error extracting {fname}: {e}")

if __name__ == "__main__":
    run_batch()