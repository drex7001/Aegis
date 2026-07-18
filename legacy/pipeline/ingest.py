"""One-command ingestion: turn raw source files into extraction-ready text.

NOTE (speckit T9): governed ingestion now lives in `aegis ingest land` /
`aegis ingest extract` — raw bytes go to the content-addressed evidence vault
with a provenance envelope and a source_record row, and extraction output lands
in the review queue instead of the graph. This module remains for the legacy
file-based prototype flow (data/real/*.txt + build_real_graph.py) until Phase 3.

Routes every file by extension and writes a provenance-headed .txt into
data/real/, where the extraction passes (and `build_real_graph.py --semantic`)
pick it up:

    .pdf                          → opendataloader-pdf structured markdown
                                    (pdfplumber plain-text fallback; audit copies
                                    in output/ingest/)
    .mp4 .mp3 .wav .mkv .m4a …    → Sinhala Whisper transcription (slow on CPU —
                                    hours for long videos; --max-minutes to test)
    .txt .md                      → copied with a provenance header

Usage:
    python -m pipeline.ingest                        # ingest everything new in Files/
    python -m pipeline.ingest docs/report.pdf        # ingest specific files
    python -m pipeline.ingest somefolder/ --force    # re-ingest even if output exists
    python -m pipeline.ingest Files/ --max-minutes 2 # quick-test slice for media files

Already-ingested files (output already in data/real/) are skipped unless --force.
After ingesting, register each new data/real/*.txt in NARRATIVE_DOCS
(build_real_graph.py) and run:  python build_real_graph.py --semantic
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from legacy.pipeline.models import slugify
from legacy.pipeline.transcribe import MEDIA_EXTS

ROOT = Path(__file__).resolve().parents[2]
DROP_ZONE = ROOT / "Files"
REAL_DATA = ROOT / "data/real"

PDF_EXTS = {".pdf"}
TEXT_EXTS = {".txt", ".md"}
SUPPORTED = PDF_EXTS | TEXT_EXTS | MEDIA_EXTS


def _relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(ROOT)
    except ValueError:
        return path


def _header(source: Path, method: str, extra: str = "") -> str:
    return (
        "[INGESTED DOCUMENT]\n"
        f"source_file: {_relative(source)}\n"
        f"method: {method}\n"
        f"ingested_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"{extra}"
        "---\n\n"
    )


def target_for(path: Path, max_minutes: float | None = None) -> Path:
    """Deterministic data/real/ output path for a raw file (slugged stem)."""
    if path.suffix.lower() in MEDIA_EXTS:
        from legacy.pipeline.transcribe import default_output_path

        return default_output_path(path, max_minutes)
    return REAL_DATA / f"{slugify(path.stem)}.txt"


def ingest_file(path: Path, force: bool = False, max_minutes: float | None = None) -> Path | None:
    """Ingest one file into data/real/. Returns the output path, or None if skipped."""
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        print(f"[skip] {path.name}: unsupported extension {ext}")
        return None
    target = target_for(path, max_minutes)
    if target.exists() and not force:
        print(f"[skip] {path.name}: {_relative(target)} already exists (use --force to redo)")
        return None
    REAL_DATA.mkdir(exist_ok=True)

    if ext in PDF_EXTS:
        from legacy.pipeline.pdf_ingest import AUDIT_DIR, convert_pdf

        print(f"[pdf ] {path.name} → {_relative(target)}")
        markdown = convert_pdf(path)
        extra = f"audit_copy: {_relative(AUDIT_DIR)}/{path.stem}.md (+.json layout tree)\n"
        target.write_text(
            _header(path, "opendataloader-pdf structured markdown (pdfplumber fallback on warning above)", extra)
            + markdown,
            encoding="utf-8",
        )
        return target

    if ext in MEDIA_EXTS:
        from legacy.pipeline.transcribe import transcribe_to_file

        print(f"[stt ] {path.name} → {_relative(target)}")
        return transcribe_to_file(path, out_path=target, max_minutes=max_minutes)

    print(f"[text] {path.name} → {_relative(target)}")
    text = path.read_text(encoding="utf-8", errors="replace")
    target.write_text(_header(path, "verbatim copy of source text") + text, encoding="utf-8")
    return target


def iter_candidates(paths: list[str]) -> list[Path]:
    """Expand files/directories into a sorted list of supported, visible files."""
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.extend(
                child
                for child in sorted(p.rglob("*"))
                if child.is_file()
                and not child.name.startswith(".")
                and child.suffix.lower() in SUPPORTED
            )
        elif p.is_file():
            found.append(p)
        else:
            print(f"[skip] {raw}: not found", file=sys.stderr)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw files (PDF/media/text) into data/real/.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=[str(DROP_ZONE)],
        help="files or directories (default: the Files/ drop zone)",
    )
    parser.add_argument("--force", action="store_true", help="re-ingest even if the output exists")
    parser.add_argument(
        "--max-minutes", type=float, help="media only: transcribe just the first N minutes"
    )
    args = parser.parse_args()

    candidates = iter_candidates(args.paths)
    if not candidates:
        print(f"nothing to ingest (looked in: {', '.join(args.paths)})")
        return

    produced: list[Path] = []
    for path in candidates:
        out = ingest_file(path, force=args.force, max_minutes=args.max_minutes)
        if out:
            produced.append(out)

    if produced:
        print("\nIngested", len(produced), "file(s) into data/real/. Next steps:")
        print("  1. Open each output and review it (transcripts especially — machine output).")
        print("  2. Register the file name(s) in NARRATIVE_DOCS in build_real_graph.py:")
        for out in produced:
            print(f'         "{out.name}",')
        print("  3. Run the semantic pass:   python build_real_graph.py --semantic")
        print("  See docs/INGESTION.md for the full workflow.")


if __name__ == "__main__":
    main()
