import sys
from pathlib import Path

from docling.document_converter import DocumentConverter

PARSED_DIR = Path("data/parsed")


def parse_pdf(path: str | Path) -> str:
    """Parses a PDF file and returns its content formatted as Markdown."""
    converter = DocumentConverter()
    result = converter.convert(Path(path))
    return result.document.export_to_markdown()


if __name__ == "__main__":
    # Usage: python -m doc_intel.parse <path/to/contract.pdf> [...]
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m doc_intel.parse <pdf> [<pdf> ...]")
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    for arg in sys.argv[1:]:
        pdf = Path(arg)
        print(f"Parsing {pdf.name}...")
        out = PARSED_DIR / f"{pdf.stem}.md"
        out.write_text(parse_pdf(pdf), encoding="utf-8")
        print(f"Saved parsed markdown to: {out}")
