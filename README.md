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
cost image tokens — so the real question is *which* evidence to extract.

| Command | Cost | Purpose |
|---|---|---|
| `extract` | local preprocessing | Primary handoff command: builds `brief.md` plus timestamped sheets/frames for another model or person to review. |
| `quick` | one call | Short clips (under ~3 min): transcript + dense frames in a single pass. Refuses longer clips. |
| `probe` | 0 image tokens | Duration, transcript, and motion profile. Usually answers the question or narrows the window. |
| `defects` | 0 image tokens | Deterministic black/freeze/silence/luma/PTS/duplicate-shot locator; nearby detector hits merge into one event candidate before visual reading. |
| `scan` | ~1-3k tokens | Contact sheets for locating a moment across a longer video. |
| `read` | ~5-20k tokens | Dense evidence frames on one bounded window, with optional local burst sampling around candidate timestamps. |

The transcript does the searching. Deterministic detectors locate defects. Frames
do the seeing.

```bash
python3 scripts/vidwatch.py extract ~/Movies/clip.mp4 --goal "review the edit"
python3 scripts/vidwatch.py quick   ~/Movies/clip.mp4
python3 scripts/vidwatch.py probe  "https://youtu.be/..."
python3 scripts/vidwatch.py defects ~/Movies/clip.mp4
python3 scripts/vidwatch.py read   ~/Movies/clip.mp4 --start 9:35 --end 9:55 --width 1024
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
- **Per-host token models.** `--vendor` supports Anthropic, OpenAI, Gemini and
  provisional Qwen image/video-sequence models. The generic model always uses
  the highest estimate, while an omitted `--width` can spend resolution down to
  the 384px floor without ever reducing frame count.
- **Local transcription.** whisper.cpp or openai-whisper on your machine. No keys,
  no audio egress.
- **Windowed, cached scene detection.** Detection costs a full decode, so it runs
  only on the range being read and the result persists.

Full command reference, measurements and rationale: [SKILL.md](SKILL.md).

## Tests

```bash
python3 -m pytest tests -q     # 124 tests, clips synthesised with ffmpeg, no network
```

## Licence

MIT. See [LICENSE](LICENSE).

