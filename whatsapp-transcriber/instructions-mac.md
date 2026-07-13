# Transcribe WhatsApp voice notes on your Mac (free, ~10 min setup)

Everything runs on your own Mac. No accounts, no API keys, no git, no Homebrew.

## Step 1 — Get the audio files out of WhatsApp
On your **phone**, open the group chat:
- iPhone: group name → **Export Chat** → **Attach Media**
- Android: ⋮ menu → More → **Export chat** → **Include media**

Send the export to your Mac (AirDrop / email / Drive). Unzip it — you'll see the
voice notes as files like `00000042-AUDIO-2026-07-03-....opus`, dated so they're
easy to identify. **Only want specific ones?** Make a new folder and copy just
those files into it.

## Step 2 — One-time setup (Terminal)
Open **Terminal** (Cmd+Space, type "terminal") and paste:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

That installs `uv`, a tool that runs Python scripts with zero setup. Close and
reopen Terminal afterwards.

Also save `transcribe.py` (sent along with these instructions) somewhere easy,
e.g. your Downloads folder.

## Step 3 — Transcribe
In Terminal (adjust the two paths to wherever your files are):

```
uv run --with faster-whisper ~/Downloads/transcribe.py ~/Downloads/my-audios
```

- First run downloads the speech model (~500 MB, one time). After that it's instant to start.
- If the voice notes are in Portuguese, add ` --lang pt` at the end (auto-detect works too, forcing is just a bit more accurate).
- If it feels slow, add ` --model base` (faster, slightly less accurate).

## Result
- A `.txt` next to every audio file with its transcription
- `_TRANSCRIPTS.txt` — all of them combined in one file, labeled by filename

## Bonus: fixing Claude Code (optional, unrelated to the above)
Claude Code doesn't actually need git. Skip whatever install path was failing
and use the official installer:

```
curl -fsSL https://claude.ai/install.sh | bash
```

Once it works, you can even skip Steps 2–3 above and just tell Claude Code:
"Transcribe every audio file in ~/Downloads/my-audios using uv with
faster-whisper (free and local), one txt per file plus a combined transcript."
