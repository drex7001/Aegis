"""PDF text extraction for PCoI reports / judgments (pdfplumber).

Usage as a library:
    from legacy.pipeline.pdf_loader import load_pdf_text, split_paragraphs

Usage from the shell (dumps extracted text to stdout):
    python -m pipeline.pdf_loader path/to/report.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def load_pdf_text(path: str | Path) -> str:
    """Extract text from every page, joined with blank lines."""
    import pdfplumber  # lazy: only needed when actually reading PDFs

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    return "\n\n".join(pages)


def split_paragraphs(text: str, min_chars: int = 200) -> list[str]:
    """Split into narrative paragraphs big enough to be worth an LLM call.
    Consecutive short blocks are merged until they reach min_chars."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    paragraphs: list[str] = []
    buffer = ""
    for block in blocks:
        buffer = f"{buffer}\n\n{block}".strip() if buffer else block
        if len(buffer) >= min_chars:
            paragraphs.append(buffer)
            buffer = ""
    if buffer:
        paragraphs.append(buffer)
    return paragraphs


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m pipeline.pdf_loader <file.pdf>")
    print(load_pdf_text(sys.argv[1]))
