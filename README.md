# my-vidwatch

Give any AI agent the ability to watch a video and answer questions grounded in
what is on screen and in the audio — not in the title, and not in a transcript
alone.

Works with any agent that can run a shell command and open an image file:
Claude Code, Codex, Cursor, Gemini CLI, Copilot, or a bare script. No Python
dependencies beyond the standard library. No API keys.

```bash
bash install.sh
python3 scripts/setup.py          # what's missing, and how to install it
```

## How it works

Nothing "watches" a video. Video becomes frames plus an audio track, and frames
cost image tokens — so the only real question is *which* frames. This tool
answers that in three stages, cheapest first:

| Stage | Cost | Purpose |
|---|---|---|
| `quick` | one call | Short clips (under ~3 min): transcript + dense frames in a single pass. Refuses longer clips. |
| `probe` | 0 image tokens | Duration, transcript, and a motion profile (cuts/min). Usually answers the question or narrows it to a 30-second window. |
| `scan` | ~1-3k tokens | Contact sheets of the whole video with timestamps burned in. For *locating*, not reading. |
| `read` | ~5-20k tokens | Dense full-resolution frames on one bounded window. Refuses windows over 10 minutes. |

The transcript does the searching. Frames do the seeing.

```bash
python3 scripts/vidwatch.py quick  ~/Movies/clip.mp4          # short clip, one pass
python3 scripts/vidwatch.py probe "https://youtu.be/..."
python3 scripts/vidwatch.py read  "https://youtu.be/..." --start 9:35 --end 9:55 --width 1024
```

Downloads, transcripts and scene cuts are cached under `~/.cache/my-vidwatch/`,
so a follow-up question on the same video costs nothing to set up.

## What it does differently

- **Tile-wise deduplication.** Whole-frame difference checks drop the frame where
  a subtitle changed or a number ticked over, because a small region barely moves
  a global average. This scores the loudest of 256 tiles instead. Measured: a
  two-digit caption change scores 0.02 on a whole-frame mean and 4.27 tile-wise.
- **Honest coverage.** Every read prints its sampling interval and states plainly
  what could have fallen between frames.
- **Per-host token models.** `--vendor anthropic|openai|gemini` — the same frame
  costs 786, 765 or 516 tokens depending on who is reading it, so a shared
  formula would misprice two hosts out of three.
- **Local transcription.** whisper.cpp on your machine. No keys, no audio egress.
- **Windowed, cached scene detection.** Detection costs a full decode, so it runs
  only on the range being read and the result persists.

Full command reference, measurements and rationale: [SKILL.md](SKILL.md).

## Tests

```bash
python3 -m pytest tests -q     # 109 tests, clips synthesised with ffmpeg, no network
```

