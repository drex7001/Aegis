"""Sinhala speech-to-text: video/audio → timestamped transcript in data/real/.

Model: Lingalingeswaran/whisper-small-sinhala (openai/whisper-small fine-tuned on
Sinhala Common Voice, Apache-2.0). Downloaded from Hugging Face on first use
(~1 GB, cached under ~/.cache/huggingface; override with HF_HOME).

Audio is decoded to 16 kHz mono with the static ffmpeg bundled in imageio-ffmpeg,
so no system ffmpeg is required. Any container/codec ffmpeg understands works:
.mp4 .mkv .mov .webm .mp3 .wav .m4a .aac .flac .ogg .opus …

CPU-only works but is slow (measured ~6× real-time on a 6-core box: a 30-minute
video takes ~3 hours). The file is processed in 10-minute blocks and the output
.txt is rewritten after each block, so long runs show progress, survive
interruption, and can be inspected while still running. Use --max-minutes for a
quick test slice first.

Transcripts are MACHINE OUTPUT: names, figures, and dates may be misrecognised
(the header embedded in every transcript says so). Verify against the audio
before promoting any fact to the curated dataset (legacy/pipeline/real_dataset.py).

Usage:
    python -m pipeline.transcribe Files/videoplayback.mp4                  # full file
    python -m pipeline.transcribe Files/videoplayback.mp4 --max-minutes 2  # quick test
    python -m pipeline.transcribe interview.mp3 --out data/real/interview.txt
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_DATA = ROOT / "data/real"

DEFAULT_MODEL = os.getenv("SINHALA_ASR_MODEL", "Lingalingeswaran/whisper-small-sinhala")
SAMPLE_RATE = 16_000
BLOCK_SECONDS = 600  # outer processing block: progress + incremental writes

MEDIA_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
}

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _ffmpeg() -> str:
    import imageio_ffmpeg  # lazy: bundled static binary

    return imageio_ffmpeg.get_ffmpeg_exe()


def media_duration(path: str | Path) -> float | None:
    """Duration in seconds, parsed from the ffmpeg banner (no ffprobe bundled)."""
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True
    )
    match = _DURATION_RE.search(proc.stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def load_audio(path: str | Path, start: float = 0.0, duration: float | None = None):
    """Decode any media file to a 16 kHz mono float32 numpy array via ffmpeg pipe."""
    import numpy as np  # lazy: keeps `--help` fast

    cmd = [_ffmpeg(), "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"]

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace")[-400:]
        raise RuntimeError(f"ffmpeg failed on {path}: {tail}")
    return np.frombuffer(proc.stdout, dtype=np.float32)


_ASR_CACHE: dict[str, object] = {}


def build_asr(model_id: str | None = None):
    """Load the ASR pipeline once per process (first call downloads the model)."""
    model_id = model_id or DEFAULT_MODEL
    if model_id not in _ASR_CACHE:
        from transformers import pipeline as hf_pipeline  # lazy: imports torch
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        _ASR_CACHE[model_id] = hf_pipeline("automatic-speech-recognition", model=model_id)
    return _ASR_CACHE[model_id]


def hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _transcript_header(source: Path, model_id: str, audio_seconds: float, language: str) -> str:
    return (
        "[MACHINE TRANSCRIPT — AUTOMATIC SPEECH RECOGNITION OUTPUT]\n"
        f"source_media: {source}\n"
        f"model: {model_id}\n"
        f"language: {language}\n"
        f"audio_duration: {hms(audio_seconds)}\n"
        f"transcribed_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        "note: Machine transcription — proper names, figures, and dates may be\n"
        "  misrecognised. Verify against the source audio before promoting any fact\n"
        "  to the curated dataset. Timestamps are [HH:MM:SS] offsets into the media.\n"
        "---\n\n"
    )


def transcribe_media(
    path: str | Path,
    max_minutes: float | None = None,
    model_id: str | None = None,
    language: str = "sinhala",
    batch_size: int = 4,
    on_block_done=None,
) -> dict:
    """Transcribe a media file; returns {text, lines, audio_seconds, elapsed_seconds, model_id}.

    `on_block_done(lines, done_seconds, total_seconds)` is called after each
    10-minute block with all timestamped lines so far (used for incremental writes)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    model_id = model_id or DEFAULT_MODEL

    total = media_duration(path) or 0.0
    limit = min(total, max_minutes * 60) if max_minutes else total
    asr = build_asr(model_id)

    lines: list[str] = []
    started = time.time()
    offset = 0.0
    while True:
        remaining = (limit - offset) if limit else None  # None: duration unknown, run to EOF
        if remaining is not None and remaining < 0.5:
            break
        block_len = min(BLOCK_SECONDS, remaining) if remaining is not None else BLOCK_SECONDS
        audio = load_audio(path, start=offset, duration=block_len)
        if audio.size < SAMPLE_RATE * 0.25:  # nothing meaningful left to decode
            break
        result = asr(
            {"array": audio, "sampling_rate": SAMPLE_RATE},
            chunk_length_s=30,
            batch_size=batch_size,
            return_timestamps=True,
            generate_kwargs={"language": language, "task": "transcribe"},
        )
        for chunk in result.get("chunks", []) or [{"timestamp": (0.0, None), "text": result["text"]}]:
            start_ts = chunk["timestamp"][0] or 0.0
            text = chunk["text"].strip()
            if text:
                lines.append(f"[{hms(offset + start_ts)}] {text}")
        offset += audio.size / SAMPLE_RATE
        if on_block_done:
            on_block_done(lines, min(offset, limit or offset), limit or offset)
        if audio.size < (block_len - 1.0) * SAMPLE_RATE:  # decoded short of the request: EOF
            break

    return {
        "lines": lines,
        "text": "\n".join(lines),
        "audio_seconds": min(offset, limit) if limit else offset,
        "elapsed_seconds": time.time() - started,
        "model_id": model_id,
    }


def default_output_path(media: Path, max_minutes: float | None = None) -> Path:
    """data/real/<slug>_transcript.txt (test slices get a _firstNmin suffix)."""
    from legacy.pipeline.models import slugify

    suffix = f"_first{max_minutes:g}min" if max_minutes else ""
    return REAL_DATA / f"{slugify(media.stem)}_transcript{suffix}.txt"


def transcribe_to_file(
    path: str | Path,
    out_path: str | Path | None = None,
    max_minutes: float | None = None,
    model_id: str | None = None,
    language: str = "sinhala",
    batch_size: int = 4,
) -> Path:
    """Transcribe and write the provenance-headed transcript. Returns the output path.

    The file is rewritten after every 10-minute block (with an IN PROGRESS marker),
    so a long run can be watched with `tail -f` and survives interruption."""
    media = Path(path)
    out = Path(out_path) if out_path else default_output_path(media, max_minutes)
    out.parent.mkdir(parents=True, exist_ok=True)

    total = media_duration(media) or 0.0
    limit = min(total, max_minutes * 60) if max_minutes else total
    model = model_id or DEFAULT_MODEL
    try:
        rel_media = media.resolve().relative_to(ROOT)
    except ValueError:
        rel_media = media
    header = _transcript_header(rel_media, model, limit, language)

    print(f"transcribing {media.name}: {hms(limit)} of audio with {model}")
    print(f"  (CPU is ~6x real-time — expect roughly {hms(limit * 6)}; watch with: tail -f {out})")

    def write_progress(lines: list[str], done: float, of: float) -> None:
        body = "\n".join(lines)
        out.write_text(
            header + body + f"\n\n[... IN PROGRESS — transcribed {hms(done)} of {hms(of)} ...]\n",
            encoding="utf-8",
        )
        print(f"  [{hms(done)} / {hms(of)}] {len(lines)} segments", flush=True)

    result = transcribe_media(
        media,
        max_minutes=max_minutes,
        model_id=model_id,
        language=language,
        batch_size=batch_size,
        on_block_done=write_progress,
    )

    out.write_text(header + result["text"] + "\n", encoding="utf-8")
    rtf = result["elapsed_seconds"] / result["audio_seconds"] if result["audio_seconds"] else 0
    print(
        f"done: {hms(result['audio_seconds'])} of audio in {hms(result['elapsed_seconds'])} "
        f"(~{rtf:.1f}x real-time) → {out}"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinhala speech-to-text (video/audio → .txt).")
    parser.add_argument("media", help="video or audio file")
    parser.add_argument("--out", help="output .txt (default: data/real/<slug>_transcript.txt)")
    parser.add_argument("--max-minutes", type=float, help="transcribe only the first N minutes")
    parser.add_argument("--model", help=f"HF model id (default: {DEFAULT_MODEL})")
    parser.add_argument("--language", default="sinhala", help="whisper language (default: sinhala)")
    parser.add_argument("--batch-size", type=int, default=4, help="chunks decoded per batch")
    args = parser.parse_args()

    transcribe_to_file(
        args.media,
        out_path=args.out,
        max_minutes=args.max_minutes,
        model_id=args.model,
        language=args.language,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
