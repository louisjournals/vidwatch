---
name: my-vidwatch
description: >
  Watch a video — local file or URL — and answer questions grounded in what is
  actually on screen and in the audio. Use for any request to watch, review,
  summarise, or locate a moment in a video, screen recording, reel, talk or
  lecture: "what hook did this open with", "when does the UI break in this
  recording", "summarise this talk", "what's on screen at 2:30", "find the part
  where they mention pricing". Works on .mp4/.mov/.mkv/.webm and any URL yt-dlp
  supports (YouTube, TikTok, Instagram, Loom, X, Vimeo). Host-agnostic: runs on
  any agent that can execute a shell command and read an image file.
  Transcription runs locally via whisper.cpp — no API keys, no audio egress.
argument-hint: "<video-url-or-path> [question]"
allowed-tools: Bash, Read
user-invocable: true
version: 2.0.0
license: MIT
---

# my-vidwatch

**Any question about a video — hooks, pacing, structure, strategy, "why did this
work" — starts with `extract`. There is no other analysis command.**

```bash
python3 SCRIPTS/vidwatch.py extract "<url-or-path>" --whisper-model medium
```

Produces a handoff folder — `brief.md` plus a few contact sheets — for cases
where the judgement happens somewhere else: a chat window, a smarter model, or
the owner reading it themselves.

**After running it you MUST surface both artifacts in the chat, ready to
download.** Attach or link `brief.md` and every file in `frames/`. Printing the
output path is not enough: the person then has to go dig through Finder, and the
whole point of this stage is that they hand the files onward immediately. If the
host cannot attach files, print the absolute path of each one on its own line so
they are one click from opening.

Then say what to do with them: paste `brief.md`, upload the sheets.

Offering your own read afterwards is fine and often useful — just do it **in
addition, never instead of** attaching the files. If you do, flag it as
provisional: `brief.md`'s findings each carry a `Check:` line, so a view formed
from the brief alone rests on less evidence than a reader looking at the sheets
will have.

**One flag to set, the rest to leave alone.**

```bash
python3 SCRIPTS/vidwatch.py extract "<url-or-path>" \
  --goal "what the owner told you they want from this"
```

**`--goal` is required in practice. Ask for it before running.** If the owner has
not said what the teardown is for, ask — one question, then run. Their answer
goes into `--goal` verbatim, in their words, not your paraphrase.

This exists because the reader on the other end otherwise closes with "shall I
write the shot list?" or "do you want a recut or a reshoot?" — pushing the
decision back to someone who already stated it to you. The goal travels with the
files so it only has to be said once.

Include what they told you: the platform, the target length, whether they are
recutting existing footage or planning a reshoot, what they are optimising for,
anything they said about their audience. More context beats less; this field has
no length limit.

- **Do NOT pass `--out`.** Output belongs in `~/Downloads/<clip>-handoff/`,
  where the owner already looks for files to forward. A session or working
  directory is the wrong place: they cannot find it, and the whole point of this
  stage is that the files get handed onward within seconds.
- **Do NOT pass `--whisper-model`.** The default is already `large-v3-turbo`.
  Naming a smaller model to save time produced ten transcription errors on a
  real ad, the product name among them.
- **Do NOT pass `--frames` or `--grid`.** The defaults sample one moment per
  second and pick a grid that keeps tiles legible for the clip's aspect ratio.

Override only when the owner asks for something specific.

Defaults: 12 evenly spaced moments packed into 2x2 sheets, 540px per tile, three
files. Chat interfaces handle many attachments badly, and a 3x3 grid would
shrink each tile below the ~512px where burned-in captions stop being legible.
Adjust with `--frames`, `--grid COLS ROWS`, or `--layout frames` for one file per
moment.

**Short clip (under ~3 minutes)? Use `quick` and stop reading.** One pass,
transcript plus dense frames. Staging exists to stop a long video eating the
budget before you know where to look; under a few minutes that reasoning
inverts and three calls to cover 30 seconds is pure overhead.

```
quick   short clips: transcript + dense frames      one call
```

Anything longer goes through three stages, cheapest first. **Always start with
`probe`** — it costs no image tokens and usually answers the question outright or
narrows it to a 30-second window.

```
probe   metadata + transcript + motion profile      0 image tokens
scan    whole-video contact sheets                  ~1-3k image tokens
read    dense full-resolution frames on a window    ~5-20k image tokens
```

`SCRIPTS` below means the `scripts/` folder next to this file. Every command is a
plain `python3` invocation with text on stdout, so any host that can run a shell
command and open a JPEG can drive this — no host-specific tooling required.

---

## Rules

1. **Under ~3 minutes, use `quick`.** It refuses anything longer and points you
   at the staged path, so you cannot get this wrong by accident.
7. **Never skip `probe` on a long video.** Reading frames first spends the budget
   before you know where the answer is.
2. **Never `read` a window wider than 10 minutes.** The tool refuses by design.
   `scan` first, then read the window that matters. `--force` overrides it, but
   the result is a sampling interval too coarse to be worth the tokens.
3. **Frames are samples, not the video.** If the reported interval is over ~2s,
   never say something is absent from the video — only that it is absent from
   the frames you saw. `read` prints the interval; quote it when it matters.
4. **Stop when the transcript is enough.** Summaries, quotes and "what did they
   say about X" almost never need frames. Reading 100 images to answer a question
   the captions already answered is the most common way to waste a budget here.
5. **Set the token model once.** Export `VIDWATCH_VENDOR` to match the host, or
   pass `--vendor`. Without it the budget uses conservative worst-case costs.
6. **Do not clean up.** Media stays cached on purpose so follow-ups are instant.
   Use `cache --purge` only when asked.

---

## quick — short clips

```bash
python3 SCRIPTS/vidwatch.py quick "<url-or-path>"
```

Transcript and dense frames in one call. Refuses clips over `--max-duration`
(default 180s) and names the staged commands instead. Takes the same
`--width`, `--max-tokens`, `--vendor`, `--mode`, `--dedup-threshold` and
`--no-whisper` flags as `read`.

## Stage 1 — probe

```bash
python3 SCRIPTS/vidwatch.py probe "<url-or-path>"
```

Returns duration, resolution, a timestamped transcript, and a **motion profile**
(scene cuts per minute, sampled rather than fully decoded so it stays cheap).

Read the motion profile before deciding anything:

| Profile | cuts/min | What it means |
|---|---|---|
| static | < 1 | Held frames. The transcript carries the content. Few frames needed. |
| low motion | 1-4 | Talking head or screencast. Scene frames track structure cheaply. |
| edited | 4-15 | Regular cuts. Scene mode fits; full coverage costs real tokens. |
| high motion | >= 15 | Fast cutting. Sampling **will** miss things. Narrow before reading. |

Flags: `--no-cuts` (skip the motion profile, and for URLs skip the video download
entirely — captions only), `--no-whisper` (never transcribe locally),
`--whisper-model tiny|base|small|medium|large-v3`, `--language en|zh|auto`.

## Stage 2 — scan

Only when you need to *see* the video and don't know where to look.

```bash
python3 SCRIPTS/vidwatch.py scan "<url-or-path>" --max-tokens 3000
```

Produces contact sheets with the timestamp burned into each tile, plus a
row-major legend. Open the sheets as images to locate the moment, then stop.
Tiles are 256px wide — deliberately too small to read on-screen text. Do not try
to answer detail questions from a sheet; take the timestamp to `read`.

## Stage 3 — read

```bash
python3 SCRIPTS/vidwatch.py read "<url-or-path>" --start 2:15 --end 2:45
```

Prints frame paths with timestamps, the transcript for that window, and a
coverage block. Open each frame path as an image using whatever image-reading
capability the host provides.

| Flag | Use |
|---|---|
| `--start` / `--end` | `SS`, `MM:SS`, or `HH:MM:SS`. Required in practice. |
| `--width 1024` | Reading on-screen text: slides, terminals, code, captions. Default 512 answers "what is happening". |
| `--vendor` | `anthropic`, `openai`, `gemini`, `generic`. Sets the token model behind `--max-tokens`. |
| `--fps N` | Force a sampling rate. Bypasses the frame cap entirely — a stated rate is honoured on a 30-second clip and a 30-minute one alike. You own the cost. |
| `--max-tokens N` | Budget **tripwire**, default 20000. Warns and reports the affordable window; never silently widens the interval. |
| `--max-frames N` | Ladder ceiling, default 100. |
| `--timestamps 1:02 1:14` | Force these moments in; they survive dedup. Read the transcript first, then target the moments the speaker flags ("as you can see here"). |
| `--mode scene\|keyframe\|uniform` | Default `scene`. `keyframe` is fastest. `uniform` gives even coverage regardless of content. |
| `--no-dedup` | Keep visually near-identical frames. Use when you are hunting a tiny on-screen change and would rather pay than miss it. |
| `--dedup-threshold N` | Default 2.0. Lower keeps more. Raise on very grainy footage. |

Timestamps are the requested seek positions. The decoder returns the first frame
at or after each one, so error is bounded by one frame interval (0.04s at 25fps).

## Sampling rate

Frame count comes from duration, not from the token budget. Two ladders:

| Window | Full scan (no `--start/--end`) | Named window |
|---|---|---|
| 5s | 12 frames | 10 (2fps) |
| 15s | 15 (1fps) | 30 (2fps) |
| 30s | 30 (1fps) | 60 (2fps) |
| 1 min | 40 | 80 |
| 2 min | 60 (every 2s) | 100 |
| 10 min | 80 | 100 |
| 30 min | 100 (every 18s) | 100 |

**Naming a window buys density** — roughly 2-3x at the same cost, because
narrowing the range is the signal that you want detail. Coverage does thin on a
long full scan; that is why `--fps` exists as an uncapped override.

Portrait costs about 3x landscape per frame at the same `--width` (621 vs 197
tokens at 512 wide), because the frame is taller. 60 vertical frames is ~37k
tokens; 60 landscape frames is ~12k. The rate ladder is the same either way, so
check the printed estimate on 9:16 footage.

## Flags that exist on every stage

`--json` on `probe`, `scan`, `read`, `quick` and `extract` gives machine-readable
output with the same numbers. `--vendor` takes
`generic|anthropic|anthropic:hires|openai:4o|openai:5|openai:5-high|gemini`; the
aliases `claude`, `gpt` and `google` also work.

`scan` additionally takes `--start`/`--end`, `--tiles`, `--tile-width`,
`--grid COLS ROWS`, and its own `--mode`. It caps internally at 200 tiles. If one
sheet would exceed `--max-tokens` it shrinks the tile width and warns, and
refuses outright rather than overspending.

`probe` takes `--sub-langs` to override which caption languages yt-dlp requests.
`--whisper-model` accepts `tiny|base|small|medium|large-v3|large-v3-turbo` and
defaults to `large-v3-turbo`. Do not drop to `small` to save time: on a real ad
it produced ten errors a reviewer had to correct off the frames, the product
name among them.

`read` and `quick` take `--max-frames` as a ladder ceiling.

`setup.py --check` is silent and returns an exit code only (0 ready, 2 required
tooling missing, 3 optional missing). `setup.py --json` is the structured form.

`VIDWATCH_CACHE` relocates the cache. `VIDWATCH_VENDOR` sets the default token
model. `VIDWATCH_SCENE_PRESCALE=0` disables scene-detection prescaling.

Cached scene-cut windows satisfy narrower later requests. Extracted frames are
content-addressed by (timestamp, width, labelled), so an identical read reuses
them instead of re-running ffmpeg.

Any container ffmpeg can open works, not only the extensions listed above.

## Cache

```bash
python3 SCRIPTS/vidwatch.py cache                # list
python3 SCRIPTS/vidwatch.py cache --purge <key>  # drop one entry
python3 SCRIPTS/vidwatch.py cache --trim 10      # LRU-trim to 10 GB
```

Downloads, transcripts, scene cuts and frames persist under
`~/.cache/my-vidwatch/`. This is what makes the loop cheap: `probe`, then `scan`,
then two `read` calls on the same video downloads once and detects cuts once.

---

## Worked pattern

> "What's the hook in this 12-minute reel breakdown, and does the pricing slide
> show annual or monthly?"

```bash
# 1. free
probe "$URL"
#    -> 12:04, 8.2 cuts/min (edited), captions present
#    -> transcript shows "let's talk pricing" around 9:40

# 2. hook = the opening. narrow window, normal width.
read "$URL" --start 0 --end 0:20 --width 512

# 3. pricing slide = on-screen text. narrow window, high resolution.
read "$URL" --start 9:35 --end 9:55 --width 1024
```

Two reads, roughly 12k image tokens, no `scan` needed because the transcript
located the moment. That is the intended shape: **the transcript does the
searching, frames do the seeing.**

---

## Install

A self-contained folder with no Python dependencies beyond the standard library.
`install.sh` symlinks it into every agent skills directory it finds:

```bash
bash install.sh          # symlink into detected hosts
bash install.sh --copy   # copy instead, for filesystems without symlinks
```

Hosts that share one skills directory (a common setup is both `~/.claude/skills`
and `~/.codex/skills` symlinked to `~/.agents/skills`) are detected by real path
and installed once. If the folder already sits inside that shared directory, the
installer says so and does nothing rather than replacing it.

Or place it by hand — the layout is the same everywhere:

```bash
ln -s "$PWD" ~/.claude/skills/my-vidwatch      # Claude Code
ln -s "$PWD" ~/.codex/skills/my-vidwatch       # Codex
ln -s "$PWD" ~/.cursor/skills/my-vidwatch      # Cursor
ln -s "$PWD" ~/.gemini/skills/my-vidwatch      # Gemini CLI
ln -s "$PWD" ~/.config/agents/skills/my-vidwatch
```

For a host with no skills directory, point it at `SKILL.md` from your
`AGENTS.md` / project instructions — the file is self-describing and the CLI is
the whole interface.

Then check dependencies:

```bash
python3 scripts/setup.py
```

Required: `ffmpeg`, `ffprobe`. Optional: `yt-dlp` (URL sources), `whisper-cpp`
(transcription when a video has no captions).

```bash
brew install ffmpeg yt-dlp whisper-cpp                 # macOS
sudo apt install ffmpeg && pipx install yt-dlp         # Debian/Ubuntu
```

The whisper model (`small`, 466 MB, multilingual) downloads on first use into the
cache. `setup.py` reports what is missing and the exact install command; it never
installs anything itself.

Slash command: `/my-vidwatch <video-url-or-path> [question]` (via
`commands/my-vidwatch.md`). The skill is also model-invoked from its description
on hosts that support that.

Tests: `python3 -m pytest tests -q` (clips synthesised with ffmpeg, no network).

---

## Token models

Frame count is derived from a token budget, so the budget is only meaningful if
the cost model matches the host reading the frames. Providers do not agree:

| Frame | anthropic | openai | gemini |
|---|---|---|---|
| 512x288 | 197 | 255 | 258 |
| 1024x576 | 786 | 765 | 516 |

Selection order is `--vendor`, then `$VIDWATCH_VENDOR`, then `generic`. The
generic model takes the highest estimate at every size, so an unconfigured host
under-fills its budget rather than overspending. `--width` is also capped per
model, since every provider downscales past some point and extra pixels then cost
tokens for no detail.

These are documented estimates, not billing. Providers resize server-side and
revise tokenizers between versions; check your host's own counter if exact cost
matters.

---

## Credit

A derivative of the MIT-licensed `watch` skill by Brad Bonanno
(https://github.com/bradautomates/claude-video). The staged pipeline, the
sampling ladders in the table above, the frame-dedup approach and the CLI shape
all originate there. See LICENSE and CHANGELOG.md.

## Design notes

Kept here so the choices are auditable rather than folklore. Every number below
was measured on this code, not assumed.

**Staging over a single pass.** A one-shot "extract N frames across the whole
video" pipeline spends its budget before it knows where the answer is. On a
50-minute video a 100-frame cap is one frame every ~30 seconds, which is
decorative. Probe is free and usually narrows the question by itself.

**Dedup scores the loudest tile, not the whole frame.** A whole-frame mean
difference cannot see a localised change. Measured on macOS 15 / ffmpeg 7.1.1
through the tool's own path (512px JPEG at q3, downscaled to 128x128 grayscale,
split into 16x16 tiles, 0-255 scale):

| Frame pair | whole-frame mean | loudest tile |
|---|---|---|
| held slide, clean encode | 0.00 | 0.00 |
| held slide under grain | — | 1.00 median, 1.33 max |
| two digits change in a 26px caption | **0.026** | **4.88** |
| caption line appears | **0.200** | **26.94** |
| hard cut between two similar slides | 20.50 | 76.39 |

The grain row is `noise=alls=22:allf=t+u` at CRF 30 — the complete expression
matters, because `noise=alls=22` alone measures a 0.00 median floor and `allf=t`
measures around 2.48. Quoting a floor without the flags is meaningless.

Against a 2.0 threshold a whole-frame mean drops both bold rows —
indistinguishable from a held slide. Those are exactly the changes you were
looking for. Scoring the loudest of 256 tiles separates them, but only on clean
sources: on real compressed vertical footage the quiet floor measured 1.797
median and 4.547 max, which OVERLAPS the 4.88 weakest real signal. No threshold
separates overlapping ranges, which is why dedup gates itself on the clip's own
measured floor and skips rather than guessing. See `--dedup`.

The thumbnail is 128x128, not 32x32, because thin text strokes average into the
background at smaller sizes: the same two-digit change scores 1.75 at 32x32,
3.31 at 64x64 and 4.88 at 128x128, so a 2.0 threshold silently loses it below
128. Comparison is against the last frame *kept*, not the previous candidate, so
slow fades accumulate.

**Scene threshold 0.15, not the usual 0.30.** A hard cut between two similarly
lit slides scored 0.10-0.20 and was missed at both 0.20 and 0.30. Heavy grain
produced zero false positives down to 0.15. The asymmetry justifies the bias: a
false-positive cut becomes one more candidate and gets thinned by the cap or
collapsed by dedup, while a false-negative cut is permanent.

**Scene detection is windowed and cached.** It costs a full decode of whatever
range it is given — roughly 107ms per second of 1080p25, about 5 minutes for a
50-minute video. So it runs only on the window being read, and the result
persists. `probe`'s motion profile uses six 20-second samples instead, costing
the same two minutes of decode whether the source is 3 minutes or 3 hours.
Downscaling before the scene filter does not help: 15.6s versus 12.7s on the same
clip with byte-identical results, because the scale filter costs more than it
saves.

**Local transcription only.** whisper.cpp on the machine, `small` multilingual by
default. No API keys, no audio egress. Slower than a hosted endpoint; that is the
trade.

**One ffmpeg landmine, commented at the call site.** Concatenated JPEGs read from
a pipe need `-c:v mjpeg` stated explicitly, or the probe fails on the
non-seekable input and the muxer reports the misleading "output file does not
contain any stream". Verified on both ffmpeg 6.1.1 and 7.1.1.

A previously documented `tile`/`nb_frames` flush bug was NOT reproducible on
ffmpeg 7.1.1 and has been deleted rather than softened — almost certainly an
ffmpeg 6 artifact, like the `drawtext` colon parsing that broke `scan`.
