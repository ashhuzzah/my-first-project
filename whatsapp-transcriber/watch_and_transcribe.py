#!/usr/bin/env python3
# Hands-free WhatsApp voice-note transcriber — no exporting chats.
#
# Watches the folder where WhatsApp Desktop stores incoming voice notes and
# transcribes every new one automatically. Leave WhatsApp Desktop signed in,
# leave this running (e.g. overnight), and collect the text in the morning.
#
# Usage (Mac, overnight — caffeinate keeps the laptop awake):
#   caffeinate -i uv run --with faster-whisper watch_and_transcribe.py
#
#   Options:
#     --dir PATH    folder to watch (default: auto-find WhatsApp Desktop media)
#     --out PATH    where transcripts go (default: ~/Documents/WhatsAppTranscripts)
#     --once        scan once and exit (good for cron) instead of looping
#     --every N     seconds between scans in watch mode (default 300)
#     --lang pt     force language (default: auto-detect per file)
#     --model NAME  whisper size: base|small|medium (default small)
#     --engine offline   use PocketSphinx instead of Whisper (English only,
#                        lower accuracy; for networks that block huggingface.co)
#
# Output, per new voice note: <out>/<filename>.txt, plus everything appended to
# <out>/transcripts-YYYY-MM-DD.txt. A state file remembers what's already done,
# so it never re-transcribes old notes.

import argparse
import datetime
import json
import pathlib
import sys
import time

AUDIO_EXTS = {".opus", ".ogg", ".oga", ".m4a", ".mp3", ".aac", ".wav", ".flac", ".amr", ".mp4"}
MIN_AGE_SECONDS = 15  # skip files still being downloaded/written

def find_whatsapp_media_dirs():
    """Locate WhatsApp Desktop's media folders on this machine."""
    home = pathlib.Path.home()
    candidates = []
    # macOS (App Store / Catalyst app)
    candidates += list((home / "Library" / "Group Containers").glob("*whatsapp*"))
    candidates += list((home / "Library" / "Group Containers").glob("*WhatsApp*"))
    # older Electron app kept some data here
    candidates += list((home / "Library" / "Application Support").glob("WhatsApp*"))
    return [c for c in candidates if c.is_dir()]

def scan_audio(root):
    now = time.time()
    out = []
    for f in root.rglob("*"):
        if f.suffix.lower() in AUDIO_EXTS and f.is_file():
            try:
                if now - f.stat().st_mtime >= MIN_AGE_SECONDS:
                    out.append(f)
            except OSError:
                pass
    return sorted(out)

def make_transcriber(args):
    """Return a transcribe(path) -> str function for the chosen engine."""
    if args.engine == "offline":
        import av
        from av.audio.resampler import AudioResampler
        from pocketsphinx import Decoder
        decoder = Decoder(samprate=16000)

        def transcribe(path):
            pcm = bytearray()
            with av.open(str(path)) as container:
                resampler = AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in container.decode(audio=0):
                    for rf in resampler.resample(frame):
                        pcm += bytes(rf.planes[0])
                for rf in resampler.resample(None):
                    pcm += bytes(rf.planes[0])
            decoder.start_utt()
            decoder.process_raw(bytes(pcm), full_utt=True)
            decoder.end_utt()
            hyp = decoder.hyp()
            return (hyp.hypstr.strip() if hyp else "")
    else:
        from faster_whisper import WhisperModel
        try:
            model = WhisperModel(args.model, device="cpu", compute_type="int8")
        except Exception as e:
            sys.exit(f"Could not load/download the Whisper model: {e}\n"
                     "If this network blocks huggingface.co, retry with --engine offline\n"
                     "(add --with pocketsphinx --with av to the uv command; English only).")

        def transcribe(path):
            segments, info = model.transcribe(str(path), language=args.lang, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()
    return transcribe

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None, help="folder to watch (default: auto-find WhatsApp Desktop media)")
    ap.add_argument("--out", default="~/Documents/WhatsAppTranscripts", help="transcript output folder")
    ap.add_argument("--once", action="store_true", help="scan once and exit instead of watching")
    ap.add_argument("--every", type=int, default=300, help="seconds between scans (watch mode)")
    ap.add_argument("--lang", default=None, help="language code, e.g. pt, en, es (default: auto)")
    ap.add_argument("--model", default="small", help="whisper model size (default: small)")
    ap.add_argument("--engine", choices=["whisper", "offline"], default="whisper")
    args = ap.parse_args()

    if args.dir:
        roots = [pathlib.Path(args.dir).expanduser()]
        if not roots[0].is_dir():
            sys.exit(f"Folder not found: {roots[0]}")
    else:
        roots = find_whatsapp_media_dirs()
        if not roots:
            sys.exit("Couldn't find WhatsApp Desktop's media folder.\n"
                     "Is WhatsApp Desktop installed and signed in on this computer?\n"
                     "(Install from whatsapp.com/download, then Settings > Linked Devices on your phone.)\n"
                     "You can also point at any folder yourself with:  --dir /path/to/folder")
    print("Watching:")
    for r in roots:
        print(f"  {r}")

    out_dir = pathlib.Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    state_file = out_dir / ".processed.json"
    done = set(json.loads(state_file.read_text()) if state_file.exists() else [])

    transcribe = make_transcriber(args)
    print(f"Transcripts -> {out_dir}  (engine: {args.engine})")

    while True:
        new = [f for r in roots for f in scan_audio(r) if str(f) not in done]
        if new:
            print(f"\n{datetime.datetime.now():%H:%M:%S} — {len(new)} new voice note(s)")
        for i, f in enumerate(new, 1):
            print(f"[{i}/{len(new)}] {f.name} ...", flush=True)
            try:
                text = transcribe(f) or "(no speech detected)"
            except Exception as e:
                text = f"(FAILED: {e})"
            (out_dir / (f.name + ".txt")).write_text(text + "\n", encoding="utf-8")
            day_file = out_dir / f"transcripts-{datetime.date.today():%Y-%m-%d}.txt"
            with day_file.open("a", encoding="utf-8") as fh:
                fh.write(f"===== {datetime.datetime.now():%H:%M} {f.name} =====\n{text}\n\n")
            done.add(str(f))
            state_file.write_text(json.dumps(sorted(done)))
            print(f"     -> {text[:80]}{'...' if len(text) > 80 else ''}")
        if args.once:
            print("Scan complete.")
            break
        time.sleep(args.every)

if __name__ == "__main__":
    main()
