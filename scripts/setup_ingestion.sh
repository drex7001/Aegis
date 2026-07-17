#!/usr/bin/env bash
# One-time setup for the data-ingestion stack (docs/INGESTION.md). Idempotent, no root:
#   1. .venv            Python 3.12 virtualenv (uses `uv` if present, else python3 -m venv)
#   2. packages         CPU torch first (small wheels), then legacy/requirements.txt
#   3. .tools/jre       project-local Temurin JRE 21 for opendataloader-pdf
#                       (skipped when `java` or JAVA_HOME already resolves)
#   4. --with-model     optionally pre-download the Sinhala Whisper model (~1 GB)
set -euo pipefail
cd "$(dirname "$0")/.."

# --- 1. virtualenv ---------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
    if command -v uv >/dev/null 2>&1; then
        uv venv .venv --python 3.12
    else
        python3 -m venv .venv
    fi
    echo "created .venv ($(.venv/bin/python --version))"
fi

pipi() {  # install into .venv regardless of how it was created (uv venvs have no pip)
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python .venv/bin/python "$@"
    else
        .venv/bin/pip install "$@"
    fi
}

# --- 2. packages -----------------------------------------------------------
# CPU wheels for torch: the default PyPI build drags in multi-GB CUDA libraries.
pipi torch --index-url https://download.pytorch.org/whl/cpu
pipi -r legacy/requirements.txt

# --- 3. Java runtime for opendataloader-pdf --------------------------------
if [ ! -x .tools/jre/bin/java ] && ! command -v java >/dev/null 2>&1 && [ ! -x "${JAVA_HOME:-/nonexistent}/bin/java" ]; then
    os=$(uname -s | tr '[:upper:]' '[:lower:]'); [ "$os" = darwin ] && os=mac
    case "$(uname -m)" in
        x86_64) arch=x64 ;;
        aarch64 | arm64) arch=aarch64 ;;
        *) arch=$(uname -m) ;;
    esac
    echo "no Java found — installing project-local Temurin JRE 21 into .tools/jre ($os/$arch)"
    mkdir -p .tools
    curl -Ls -o .tools/jre.tar.gz \
        "https://api.adoptium.net/v3/binary/latest/21/ga/$os/$arch/jre/hotspot/normal/eclipse"
    tar -xzf .tools/jre.tar.gz -C .tools
    rm .tools/jre.tar.gz
    ln -sfn "$(cd .tools && ls -d jdk-*-jre | head -1)" .tools/jre
fi

# --- 4. optional model pre-download ----------------------------------------
if [ "${1:-}" = "--with-model" ]; then
    echo "pre-downloading the Sinhala Whisper model (~1 GB, cached in ~/.cache/huggingface)"
    .venv/bin/python -c "from huggingface_hub import snapshot_download as d; print(d('Lingalingeswaran/whisper-small-sinhala'))"
fi

# --- smoke check -----------------------------------------------------------
.venv/bin/python - <<'EOF'
import imageio_ffmpeg, torch, transformers
from legacy.pipeline.pdf_ingest import find_java
print("java        :", find_java() or "MISSING — PDF ingestion will fall back to pdfplumber")
print("ffmpeg      :", imageio_ffmpeg.get_ffmpeg_exe())
print("torch       :", torch.__version__)
print("transformers:", transformers.__version__)
EOF
echo
echo "Setup complete. Ingest data with:  .venv/bin/python -m legacy.pipeline.ingest --help"
