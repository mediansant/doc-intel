import random
from pathlib import Path

def generate_sample():
    random.seed(42)  # Fixed random seed for reproducibility
    parsed_dir = Path("data/parsed")
    all_files = sorted([f.stem for f in parsed_dir.glob("*.md")])
    
    if len(all_files) < 20:
        sample = all_files
    else:
        sample = random.sample(all_files, 20)
        
    evals_dir = Path("evals")
    evals_dir.mkdir(parents=True, exist_ok=True)
    
    sample_path = evals_dir / "sample_v1.txt"
    sample_path.write_text("\n".join(sample), encoding="utf-8")
    print(f"Saved {len(sample)} contract names to {sample_path}")

if __name__ == "__main__":
    generate_sample()