---
description: Watch a video (URL or local path) and answer questions grounded in what is on screen and in the audio. Staged so long videos cost a bounded number of image tokens: transcript first, then frames only where they are needed.
argument-hint: <video-url-or-path> [question]
allowed-tools: [Bash, Read]
---

Invoke the `my-vidwatch` skill (defined in SKILL.md) with the user's arguments: $ARGUMENTS

**If the clip is under ~3 minutes, run `quick` and stop.** One pass, transcript
plus dense frames. Staging is overhead at that length. `quick` refuses anything
longer and names the staged commands, so you cannot get this wrong.

For longer video, follow the staged pipeline and do not skip ahead:

1. **`probe` first, always.** It costs zero image tokens and returns duration, a
   timestamped transcript, and a motion profile. If the transcript already answers
   the question, answer from it and stop — do not extract frames to confirm
   something you can already read.
2. **`scan` only if you must see the video and do not know where to look.** It
   returns contact sheets for locating a moment. Tiles are too small to read
   on-screen text; take the timestamp and move on.
3. **`read` on one narrow window.** Pass `--start`/`--end`. Use `--width 1024`
   when the answer depends on on-screen text. Windows wider than 10 minutes are
   refused by design — narrow, or `scan` first.

When reporting back, respect the coverage block `read` prints. If the sampling
interval is over ~2s, say something is absent from *the frames you saw*, never
from the video.

If the user gave no arguments, ask for a video URL or local path before starting.
If they named a moment ("around 2:30", "the last 30 seconds"), go straight from
`probe` to a focused `read` on that window and skip `scan`.
