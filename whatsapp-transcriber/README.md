# whatsapp-transcriber

For the user's partner (Mac): transcribe selected WhatsApp voice notes from a group chat to text. Free + local (faster-whisper via uv), no API keys, no git/Homebrew — works around her broken git/Claude Code install.

## What's here
- `watch_and_transcribe.py` — **hands-free mode.** Watches WhatsApp Desktop's media folder and transcribes new voice notes automatically as they arrive — no chat exporting. Leave it running (e.g. overnight with `caffeinate`); transcripts land in `~/Documents/WhatsAppTranscripts`. Requires WhatsApp Desktop signed in.
- `transcribe.py` — **one-shot mode.** Whisper (faster-whisper) via uv: high accuracy, auto language detection (incl. Portuguese), reads `.opus` WhatsApp audio directly. Point it at an exported chat folder. Downloads its speech model from huggingface.co on first run.
- `transcribe_offline.py` — **emergency fallback.** PocketSphinx: the speech model is bundled inside the pip package, so it works even on networks that block everything except PyPI. Much lower accuracy and **English only** — use it only when `transcribe.py` can't download its model.
- `instructions-mac.md` — step-by-step guide to send along with the script (export chat with media from the phone → one `uv` command).

## Usage
```
# hands-free (watches WhatsApp Desktop, transcribes new notes as they arrive):
caffeinate -i uv run --with faster-whisper watch_and_transcribe.py

# one-shot on an exported chat folder (best quality):
uv run --with faster-whisper transcribe.py ~/Downloads/chat-folder

# fallback (English only, works with PyPI-only network access):
uv run --with pocketsphinx --with av transcribe_offline.py ~/Downloads/chat-folder
```
The one-shot tools write one `.txt` next to each audio file plus a combined
`_TRANSCRIPTS.txt`; the watcher writes to `~/Documents/WhatsAppTranscripts`
(one `.txt` per note + a combined file per day) and never re-does old notes.
The watcher also accepts `--engine offline`, `--dir`, `--out`, `--once`,
`--lang`, `--model` — see its header comment.

## Status
- [x] `transcribe.py` — .opus-capable (PyAV bundled, no ffmpeg), per-file .txt + combined `_TRANSCRIPTS.txt`, `--lang`/`--model` flags; now prints a helpful message pointing at the fallback if the model download is blocked
- [x] `transcribe_offline.py` — fully offline fallback, verified end-to-end
- [x] `watch_and_transcribe.py` — hands-free watcher (no chat export needed); scan/state/incremental logic verified end-to-end in sandbox with the offline engine
- [x] `instructions-mac.md` — send her this + the scripts
- [ ] Confirm it worked on her Mac (incl. WhatsApp Desktop media folder auto-discovery)

## Verification (Claude Code cloud sandbox, 2026-07-13)
- `transcribe.py`: installs cleanly via uv from PyPI; CLI works. Could not run to completion **in the sandbox only** because its egress policy blocks huggingface.co (proxy 403) — not a bug in the script. On a normal Mac/home network it will download the model and run.
- `transcribe_offline.py`: verified end-to-end in the sandbox — decoded a real WhatsApp-style `.opus` (and `.wav`), transcribed, wrote per-file `.txt` + `_TRANSCRIPTS.txt`. Accuracy on synthetic (espeak) test audio was rough, as expected for PocketSphinx; real human speech fares better, but Whisper remains far superior.
