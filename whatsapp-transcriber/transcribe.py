#!/usr/bin/env python3
# WhatsApp voice-note transcriber — free, local, no API keys.
# Reads .opus WhatsApp audio directly (no ffmpeg install needed).
#
# Usage:
#   uv run --with faster-whisper transcribe.py ~/Downloads/chat-folder
#   uv run --with faster-whisper transcribe.py file1.opus file2.opus
#   Options: --lang pt   (force language; default auto-detects per file)
#            --model base|small|medium  (default small; base = faster, less accurate)
#
# Output: one .txt next to each audio + _TRANSCRIPTS.txt with everything combined.

import argparse
import pathlib
import sys

AUDIO_EXTS = {".opus", ".ogg", ".oga", ".m4a", ".mp3", ".aac", ".wav", ".flac", ".amr", ".mp4"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="folder(s) and/or audio file(s)")
    ap.add_argument("--lang", default=None, help="language code, e.g. pt, en, es (default: auto)")
    ap.add_argument("--model", default="small", help="whisper model size (default: small)")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        path = pathlib.Path(p).expanduser()
        if path.is_dir():
            files += sorted(f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS)
        elif path.is_file():
            files.append(path)
        else:
            print(f"!! not found: {path}")
    if not files:
        sys.exit("No audio files found.")

    print(f"{len(files)} audio file(s). Loading model '{args.model}' "
          "(first run downloads it, ~a few hundred MB)...")
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
    except Exception as e:
        sys.exit(f"Could not load/download the Whisper model: {e}\n"
                 "If this network blocks huggingface.co, use the offline fallback instead:\n"
                 "  uv run --with pocketsphinx --with av transcribe_offline.py <folder>\n"
                 "(lower accuracy, English only, but needs nothing beyond PyPI)")

    combined = []
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name} ...", flush=True)
        try:
            segments, info = model.transcribe(str(f), language=args.lang, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip() or "(no speech detected)"
        except Exception as e:
            text = f"(FAILED: {e})"
        f.with_suffix(f.suffix + ".txt").write_text(text + "\n", encoding="utf-8")
        combined.append(f"===== {f.name} =====\n{text}\n")
        print(f"     -> {text[:80]}{'...' if len(text) > 80 else ''}")

    out_dir = files[0].parent
    (out_dir / "_TRANSCRIPTS.txt").write_text("\n".join(combined), encoding="utf-8")
    print(f"\nDone. Combined transcript: {out_dir / '_TRANSCRIPTS.txt'}")

if __name__ == "__main__":
    main()
