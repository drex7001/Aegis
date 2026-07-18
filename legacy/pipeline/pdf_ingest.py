"""Structured PDF ingestion via opendataloader-pdf (Java CLI), pdfplumber fallback.

opendataloader-pdf ships its own JAR but needs a Java 11+ runtime. The runtime is
looked up in this order (first hit wins):

  1. .tools/jre/bin/java      — project-local JRE, installed by scripts/setup_ingestion.sh
  2. $JAVA_HOME/bin/java
  3. `java` on PATH

Two artefacts are produced per PDF in output/ingest/ (the audit copies):
  <stem>.md     structure-aware markdown (headings, lists, tables) — used downstream
  <stem>.json   full layout tree with bounding boxes — kept for audit/debugging

If no Java runtime (or the package) is available, extraction falls back to the
plain-text pdfplumber loader in pipeline/pdf_loader.py — you still get text, just
without document structure. opendataloader-pdf's content-safety filters (hidden
text, off-page text) stay on, which matters here because extracted text is later
fed to the LLM semantic pass.

Usage as a library:
    from legacy.pipeline.pdf_ingest import convert_pdf
    markdown = convert_pdf("docs/report.pdf")

Usage from the shell:
    python -m pipeline.pdf_ingest docs/report.pdf              # markdown to stdout
    python -m pipeline.pdf_ingest docs/report.pdf -o out.txt
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_JRE_BIN = ROOT / ".tools" / "jre" / "bin"
AUDIT_DIR = ROOT / "output" / "ingest"


def find_java() -> str | None:
    """Path to a java executable, preferring the project-local JRE. None if absent."""
    local = LOCAL_JRE_BIN / "java"
    if local.exists():
        return str(local)
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java"
        if candidate.exists():
            return str(candidate)
    return shutil.which("java")


def _ensure_java_on_path() -> bool:
    """opendataloader-pdf invokes the literal command `java`, so the chosen
    runtime's bin dir is prepended to PATH for this process."""
    java = find_java()
    if not java:
        return False
    bin_dir = str(Path(java).parent)
    current = os.environ.get("PATH", "")
    if bin_dir not in current.split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + current
    return True


def convert_pdf(pdf_path: str | Path, audit_dir: str | Path | None = None) -> str:
    """Extract a PDF to structure-aware markdown; return the markdown text.

    Writes <stem>.md and <stem>.json audit copies into audit_dir (default
    output/ingest/). Falls back to pdfplumber plain text on any failure."""
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    audit = Path(audit_dir) if audit_dir else AUDIT_DIR
    audit.mkdir(parents=True, exist_ok=True)

    if _ensure_java_on_path():
        try:
            import opendataloader_pdf  # lazy: only needed on the structured path

            opendataloader_pdf.convert(
                input_path=[str(pdf)],
                output_dir=str(audit),
                format=["markdown", "json"],
                image_output="off",  # text goes to the LLM pass; image links would dangle
                quiet=True,
            )
            markdown = audit / f"{pdf.stem}.md"
            if markdown.exists():
                return markdown.read_text(encoding="utf-8")
            print(
                f"  [warn] opendataloader-pdf wrote no markdown for {pdf.name}; "
                "falling back to pdfplumber",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001 - any failure degrades to the fallback
            print(
                f"  [warn] opendataloader-pdf failed on {pdf.name} "
                f"({type(exc).__name__}: {exc}); falling back to pdfplumber",
                file=sys.stderr,
            )
    else:
        print(
            "  [warn] no Java runtime found (.tools/jre, JAVA_HOME, or PATH) — "
            "run scripts/setup_ingestion.sh; falling back to pdfplumber",
            file=sys.stderr,
        )

    from legacy.pipeline.pdf_loader import load_pdf_text

    return load_pdf_text(pdf)


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF → structure-aware markdown.")
    parser.add_argument("pdf", help="path to the PDF")
    parser.add_argument("-o", "--out", help="write markdown here instead of stdout")
    args = parser.parse_args()

    text = convert_pdf(args.pdf)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} ({len(text)} chars)")
    else:
        print(text)


if __name__ == "__main__":
    main()
