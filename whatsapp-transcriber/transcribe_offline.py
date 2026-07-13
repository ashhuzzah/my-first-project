#!/usr/bin/env python3
# Fallback WhatsApp voice-note transcriber — 100% offline, English only.
#
# Unlike transcribe.py (which needs to download a Whisper model from
# huggingface.co on first run), this uses PocketSphinx: the speech model is
# bundled inside the pip package, so it works even on networks where only
# PyPI is reachable. Trade-off: noticeably lower accuracy, and English only.
# Use transcribe.py whenever you can; use this when you can't.
#
# Usage:
#   uv run --with pocketsphinx --with av transcribe_offline.py ~/Downloads/chat-folder
#   uv run --with pocketsphinx --with av transcribe_offline.py file1.opus file2.opus
#
# Output: one .txt next to each audio + _TRANSCRIPTS.txt with everything combined.

import argparse
import pathlib
import sys

AUDIO_EXTS = {".opus", ".ogg", ".oga", ".m4a", ".mp3", ".aac", ".wav", ".flac", ".amr", ".mp4"}

def decode_to_pcm16k(path):
    """Decode any audio file to 16 kHz mono 16-bit PCM bytes (what PocketSphinx wants)."""
    import av
    from av.audio.resampler import AudioResampler
    pcm = bytearray()
    with av.open(str(path)) as container:
        resampler = AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for rf in resampler.resample(frame):
                pcm += bytes(rf.planes[0])
        for rf in resampler.resample(None):  # flush
            pcm += bytes(rf.planes[0])
    return bytes(pcm)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="folder(s) and/or audio file(s)")
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

    print(f"{len(files)} audio file(s). Loading offline English model (bundled, no download)...")
    from pocketsphinx import Decoder
    decoder = Decoder(samprate=16000)

    combined = []
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name} ...", flush=True)
        try:
            pcm = decode_to_pcm16k(f)
            decoder.start_utt()
            decoder.process_raw(pcm, full_utt=True)
            decoder.end_utt()
            hyp = decoder.hyp()
            text = (hyp.hypstr.strip() if hyp else "") or "(no speech detected)"
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
