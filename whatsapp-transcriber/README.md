# whatsapp-transcriber

For the user's partner (Mac): transcribe selected WhatsApp voice notes from a group chat to text. Free + local (faster-whisper via uv), no API keys, no git/Homebrew — works around her broken git/Claude Code install.

## What's here
- `transcribe.py` — **the main tool.** Whisper (faster-whisper) via uv: high accuracy, auto language detection (incl. Portuguese), reads `.opus` WhatsApp audio directly. Downloads its speech model from huggingface.co on first run.
- `transcribe_offline.py` — **emergency fallback.** PocketSphinx: the speech model is bundled inside the pip package, so it works even on networks that block everything except PyPI. Much lower accuracy and **English only** — use it only when `transcribe.py` can't download its model.
- `instructions-mac.md` — step-by-step guide to send along with the script (export chat with media from the phone → one `uv` command).

## Usage
```
# main (best quality, needs huggingface.co reachable on first run):
uv run --with faster-whisper transcribe.py ~/Downloads/chat-folder

# fallback (English only, works with PyPI-only network access):
uv run --with pocketsphinx --with av transcribe_offline.py ~/Downloads/chat-folder
```
Both write one `.txt` next to each audio file plus a combined `_TRANSCRIPTS.txt`.

## Status
- [x] `transcribe.py` — .opus-capable (PyAV bundled, no ffmpeg), per-file .txt + combined `_TRANSCRIPTS.txt`, `--lang`/`--model` flags; now prints a helpful message pointing at the fallback if the model download is blocked
- [x] `transcribe_offline.py` — fully offline fallback, verified end-to-end
- [x] `instructions-mac.md` — send her this + the script
- [ ] Confirm it worked on her Mac

## Verification (Claude Code cloud sandbox, 2026-07-13)
- `transcribe.py`: installs cleanly via uv from PyPI; CLI works. Could not run to completion **in the sandbox only** because its egress policy blocks huggingface.co (proxy 403) — not a bug in the script. On a normal Mac/home network it will download the model and run.
- `transcribe_offline.py`: verified end-to-end in the sandbox — decoded a real WhatsApp-style `.opus` (and `.wav`), transcribed, wrote per-file `.txt` + `_TRANSCRIPTS.txt`. Accuracy on synthetic (espeak) test audio was rough, as expected for PocketSphinx; real human speech fares better, but Whisper remains far superior.
