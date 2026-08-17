---
name: my-vidwatch
description: >
  Use when a video, reel, paid ad, organic short-form post, screen recording,
  talk, lecture, local media file, or supported video URL must be watched,
  scanned, reviewed, summarised, diagnosed, compared, or answered from actual
  visual/audio evidence, including paid/organic creative strategy, recut analysis,
  hook and retention review, pacing, defects, and locating exact moments.
argument-hint: "<video-url-or-path> [question]"
allowed-tools: Bash, Read
user-invocable: true
version: 2.3.1
license: MIT
---

# my-vidwatch

One skill owns the whole evidence-to-judgment loop. **Do not stop after extracting
frames and a brief when the user asked for a full scan, review, teardown, or
analysis.** The scan is evidence collection; the job is not done until `report.md`
is written.

## Choose the path

### A — Targeted question

Use this when the user asks one narrow thing such as "what happens at 2:30",
"what hook did this open with", "find the UI bug", or "what did they say about
pricing".

- Under ~3 minutes: use `quick`.
- Longer video: `probe` first, then `scan` only when location is unknown, then a
  narrow `read` when visual detail is needed.
- Answer the question directly from the evidence.
- Do **not** force `report.md` for a narrow question unless the user also asked
  for a full analysis.

### B — Full scan / review / teardown / short-form analysis

Use this when the user asks to scan, watch, review, analyse, teardown, audit,
compare, or strategise around a whole video, or invokes `my-vidwatch` with a video
but no narrow question. Paid and organic strategy use the same evidence pass but
**different declared distribution intents**.

1. Run `extract` for every source video in the request.
2. Read each generated `brief.md` **before doing any analysis**. If it says
   `intent not declared`, stop immediately and ask the intent question below as the
   first user-facing line. Do not inspect the evidence into a diagnosis, load an
   intent-specific reference, or write any part of `report.md` yet.
3. Once intent is declared, read every contact sheet/frame artifact. A transcript
   or brief alone is not enough for visual claims.
4. Write the final human-facing analysis as `report.md`.
5. Surface each machine-owned `brief.md`, the visual evidence, and `report.md` in
   the chat. Do not tell the owner to paste/upload them into another model as the
   normal next step.

`brief.md` stays machine-owned. Never rewrite, merge, summarise into, or replace it
with model-authored prose. It is the extraction record. If the model thinks the
brief is wrong, say so in `report.md`; do not silently mutate the input record.

```bash
python3 SCRIPTS/vidwatch.py extract "<url-or-path>" \
  --goal "<owner goal, or default full video report>" \
  [--intent paid|organic]
```

If the owner already stated a goal, pass it to `--goal` verbatim. If they did
**not** state one, do **not** stop to ask: use `full video report` as the default
goal and proceed.

`--intent` is different: pass it **only when the owner/caller has explicitly said
paid or organic**. The CLI records that fact and never infers it. If `brief.md`
says `intent not declared`, the **first user-facing message must be exactly one
short question:**

`Paid 还是 organic？`

Do not prepend analysis, explain why the question is needed, list the difference
between the two intents, or append a partial/shared-only report. Wait for the owner
to answer one word. Then rerun the cached `extract` with that explicit `--intent`,
load `shared.md` plus the matching intent reference, and produce the complete
`report.md` once. Callers who want to avoid this round trip can pass
`--intent paid|organic` directly on the first `extract`.

Intent is still a distribution-side fact. Never infer it from the footage, CTA,
brand presence, platform, production polish, or editing style.

### Required full-scan output — `report.md`

The final human-facing analysis is **one `report.md`**, not separate context and
analyst files. Organise for reading order — conclusion first, evidence second —
not by a global fact/inference split.

For one video, use this order:

1. **Blockers** — only when present; anything that makes the current deliverable
   unusable or changes the production class (re-render/reshoot) goes first.
2. **判断 / Judgment** — one sentence.
3. **哪里好 / What works** — only the strengths that matter to the decision.
4. **哪里要改 / What to change** — ranked by impact.
5. **怎么改 / How to change** — executable recut/re-render/reshoot/test actions.
6. **依据 / Evidence**
   - timeline
   - names/text observed from sampled frames, with provenance labels
   - retention boundary table using visual evidence + shot-table timing
   - claim/proof audit
   - material usability

Each judgment appears **once**. Evidence supports it later; do not restate the same
360p issue, typo, proof-placement percentage, unsupported claim, or timeline point
in several sections.

`brief.md` remains the untouched machine record. `report.md` may disagree with it,
but never edits or rewrites it.

The current `extract` CLI may still print legacy next-step names for the former
`video-context.md` + `analyst-report.md` handoff. That stdout is extraction-layer
legacy prose, not the final artifact contract. **This SKILL.md owns the final
analysis output: write `report.md` only.** Do not create the two legacy files just
because the extractor mentions them.

### Multiple videos in one run

`--intent` is **batch-level**, never per-video. Pass the same declared value to
every `extract` in the batch. Each video keeps its own `brief.md`, and each brief
records that same batch declaration. If intent is undeclared, ask **once, before
any batch analysis**, using the same one-line question above. After the owner
answers, apply that one declared intent to every cached `extract` in the batch.

For **every batch of 2+ videos, use one parent batch folder**. Do not leave the
individual handoff folders scattered directly in `~/Downloads`, and do not create
a separate folder just for the report. Use this layout:

```text
~/Downloads/<batch>-handoff/
  report.md
  <clip-1>-handoff/
    brief.md
    frames/
  <clip-2>-handoff/
    brief.md
    frames/
  ...
```

Choose a short batch name from the requested clips, e.g. `0895-0897-handoff` for
0895, 0896 and 0897. Run normal cached `extract` for each source first, then move
each generated `<clip>-handoff/` folder into the batch parent. `report.md` lives
**directly in the batch parent** beside those video folders. Never create
`<batch>-report/`, `report-handoff/`, or another report-only directory.

For **2–5 videos**, output one `report.md` for the whole batch:

- Start with **跨视频重复项 / Cross-video repeated findings**. Include only issues,
  strengths, template defects, proof patterns, or structural mechanisms that occur
  in at least two videos. Maximum **5** items. If nothing repeats, leave this
  section empty rather than inventing a theme.
- Then give each video its own compact section using the single-video order above.
- A repeated issue belongs in the cross-video section once; per-video sections may
  point to its local timestamp but must not re-explain the same diagnosis.

The point of this section is to find system/template failures that a single-video
report cannot see. Example: the same `LOW BEAN` burned-in graphic in 0896 and 0897
is not two independent spelling errors; it is a shared template defect, so the fix
belongs in the template/project source rather than two export-specific patches.

For **more than 5 videos**, keep the batch `report.md` to the cross-video section
plus one-sentence judgment per video. Put detailed per-video analysis in separate
files inside each video's own handoff folder so the batch report stays usable.

For a **single video**, do **not** output a cross-video section at all.

### Reference loading

Reference loading is intent-gated. **Do not load analysis references until intent
is declared.** Once it is declared, read `references/shared.md` plus exactly one
matching intent reference:

- `paid` → `references/shared.md` + `references/paid.md`
- `organic` → `references/shared.md` + `references/organic.md`
- `not declared` → load neither analysis path yet; ask `Paid 还是 organic？` and wait.

Do not load all three references “just in case”, and do not produce a shared-only
partial analysis while waiting. The first three judgment axes and all evidence
landmines live in shared; paid/organic add only the distribution-specific layer.
No performance data means the diagnosis is a hypothesis; never invent ranking
weights, traffic shares or universal benchmarks. Never infer intent from footage,
CTA, brand presence, platform, production polish, or editing style.

Write `report.md` in the owner's language unless they requested another language.

### Acquisition fallback for URLs

Direct ingest is always the default. If URL acquisition/download fails, do **not**
automatically retry and do **not** automatically start screen recording. Ask the
owner which recovery path they want:

- **Retry direct ingest** — retry the original URL path once.
- **Try screen-recording fallback** — capture the actually rendered player/UI as a
  local recording, then feed that local recording back into the normal
  `quick`/`probe`/`scan`/`read` pipeline.

Screen recording is an acquisition fallback, not a new analysis mode. Prefer the
original local/downloaded media whenever direct ingest works because it preserves
source quality and avoids real-time playback overhead. Use the recording path when
direct ingest cannot access the media or when the owner specifically wants the
rendered UI, captions, overlays, or app/player behavior included in the analysis.
Do not start screen recording without the owner's explicit choice after the
failure.

**One flag to set, the rest to leave alone.**

- **Do NOT pass `--out`.** Let `extract` create its normal
  `~/Downloads/<clip>-handoff/` bundle. For a single-video run, write `report.md`
  inside that handoff folder. For **2+ videos**, after extraction create one
  `~/Downloads/<batch>-handoff/` parent, move every generated `<clip>-handoff/`
  into it, and write the one batch `report.md` directly in that parent. Do not
  create a separate report folder. A session working directory is the wrong place
  because the owner cannot reliably find or reopen the finished evidence.
- **Do NOT pass `--whisper-model` unless the owner is intentionally overriding
  transcription quality/cost.** Leave the CLI default unchanged for normal runs.
- **Do NOT pass `--frames` or `--grid`.** For `extract`, the default derives the
  evidence count from duration (about one moment per second, minimum 12, maximum
  120) and picks a grid that keeps tiles legible for the clip's aspect ratio.
  `quick` and `read` use the separate adaptive sampling policy documented below.

Override only when the owner asks for something specific.

By default those evenly spaced moments are packed into aspect-ratio-aware sheets
at 540px per tile. Chat interfaces handle many attachments badly, so the layout
keeps each tile useful while limiting upload count. Adjust with `--frames`,
`--grid COLS ROWS`, or `--layout frames` for one file per moment.

**Targeted question on a short clip (under ~3 minutes)? Use `quick` and stop.**
One pass, transcript plus dense frames. This shortcut belongs to **Path A only**.
A full scan/review in **Path B still uses `extract` regardless of duration** so it
can create the evidence bundle for the required `report.md`.

```
quick   short clips: transcript + dense frames      one call
```

A targeted question on anything longer goes through three stages, cheapest
first. **Always start with `probe`** — it costs no image tokens and usually
answers the question outright or narrows it to a 30-second window.

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

1. **Path A only: under ~3 minutes, use `quick`.** Path B full analysis uses
   `extract` at every duration because it must produce the evidence bundle for
   `report.md`.
2. **Path A only: never skip `probe` on a long video.** Reading frames first
   spends the budget before you know where the answer is.
3. **Never `read` a window wider than 10 minutes.** The tool refuses by design.
   `scan` first, then read the window that matters. `--force` overrides it, but
   the result is a sampling interval too coarse to be worth the tokens.
4. **Frames are samples, not the video.** If the reported interval is over ~2s,
   never say something is absent from the video — only that it is absent from
   the frames you saw. `read` prints the interval; quote it when it matters.
5. **Path A: stop when the transcript is enough.** Summaries, quotes and "what
   did they say about X" almost never need frames. **Path B is different:** a full
   context/report pass must inspect the extracted visual evidence before making
   visual, material-usability, proof, hook, or CTA judgments.
6. **Set the token model once.** Export `VIDWATCH_VENDOR` to match the host, or
   pass `--vendor`. Without it the budget uses conservative worst-case costs.
7. **Do not clean up.** Media stays cached on purpose so follow-ups are instant.
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
`--whisper-model tiny|base|small|medium|large-v3|large-v3-turbo`,
`--language en|zh|auto`.

## defects — deterministic locator

Run before `read` when the task is to find editing/technical defects:

```bash
python3 SCRIPTS/vidwatch.py defects "<url-or-path>"
```

Uses local ffmpeg/ffprobe only — zero image tokens, no model call. It reports
candidate timestamps for black flashes, freezes, actual audio silence, abrupt
luma changes, PTS gaps and repeated non-adjacent shots. Human output prints a
ready `read --start ... --end ... --candidates T` command; `--json` returns
`{t, kind, severity, evidence}` records. Detection finds the candidate; `read`
burst sampling collects visual evidence around it.

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
| `--width 1024` | Reading on-screen text: slides, terminals, code, captions. An explicit width is honoured exactly. If omitted, resolution is budget-managed from 512px down to a provisional 384px floor; frame count is never reduced to fit budget. |
| `--vendor` | `anthropic`, `openai`, `gemini`, `qwen`, `qwen:video`, `generic`. Sets the token model behind the joint frame × resolution budget. |
| `--fps N` | Force a sampling rate. Bypasses the frame cap entirely — a stated rate is honoured on a 30-second clip and a 30-minute one alike. You own the cost. |
| `--max-tokens N` | Budget **tripwire**, default 20000. Warns and reports the affordable window; never silently widens the interval. |
| `--max-frames N` | Automatic-sampling frame ceiling, default 100. |
| `--timestamps 1:02 1:14` | Force these exact moments in outside the automatic frame ceiling; they survive dedup. |
| `--candidates 1:02 1:14` | Known defect/event timestamps. Adds protected local burst samples without reducing baseline coverage elsewhere. |
| `--burst-fps N` / `--burst-radius S` | Evidence density around candidates; defaults to 10fps within ±0.5s. Detection still belongs to `defects`. |
| `--mode scene\|keyframe\|uniform` | Default `scene`. `keyframe` is fastest. `uniform` gives even coverage regardless of content. |
| `--no-dedup` | Keep visually near-identical frames. Use when you are hunting a tiny on-screen change and would rather pay than miss it. |
| `--dedup-threshold N` | Default 2.0. Lower keeps more. Raise on very grainy footage. |

Timestamps are the requested seek positions. The decoder returns the first frame
at or after each one, so error is bounded by one frame interval (0.04s at 25fps).

## Sampling rate

Frame count comes from duration, not from the token budget. Automatic sampling
uses a smooth coverage curve rather than duration buckets: the desired interval
grows with the square root of the window length and is capped at 4 seconds before
the frame ceiling is applied. A named `--start/--end` window tightens that
interval by 1.75x because the caller has already identified the part that needs
closer inspection.

Typical defaults with `--max-frames 100`:

| Window | Wide / whole clip | Named window |
|---|---|---|
| 5s | 12 frames | 18 frames |
| 15s | 17 | 30 |
| 30s | 40 | 60 |
| 1 min | 60 | 100 |
| 2 min | 70 | 100 |
| 3 min | 80 | 100 |
| 10 min | 100 | 100 |
| 30 min | 100 | 100 |

The curve is continuous, so crossing 30s or 60s never causes a sudden jump in
sampling behaviour. `--fps` remains an exact uncapped override when a specific
coverage rate matters more than automatic cost control.

Portrait costs about 3x landscape per frame at the same `--width` (621 vs 197
tokens at 512 wide), because the frame is taller. 60 vertical frames is ~37k
tokens; 60 landscape frames is ~12k. The rate ladder is the same either way, so
check the printed estimate on 9:16 footage.

## Flags that exist on every stage

`--json` on `probe`, `defects`, `scan`, `read`, `quick` and `extract` gives
machine-readable output. `--vendor` on budgeted frame-reading stages takes
`generic|anthropic|anthropic:hires|openai:4o|openai:5|openai:5-high|gemini|qwen|qwen:video`;
the aliases `claude`, `gpt`, `google` and `qwen3-vl` also work.

`scan` additionally takes `--start`/`--end`, `--tiles`, `--tile-width`,
`--grid COLS ROWS`, and its own `--mode`. It caps internally at 200 tiles. If one
sheet would exceed `--max-tokens` it shrinks the tile width and warns, and
refuses outright rather than overspending.

`probe` takes `--sub-langs` to override which caption languages yt-dlp requests.
`--whisper-model` accepts `tiny|base|small|medium|large-v3|large-v3-turbo` and
defaults to `large-v3-turbo`. Do not drop to `small` to save time: on a real ad
it produced ten errors a reviewer had to correct off the frames, the product
name among them.

`read` and `quick` take `--max-frames` as the automatic-sampling ceiling.

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

The selected whisper.cpp model downloads on first use into the cache. `setup.py`
reports what is missing and the exact install command; it never installs anything
itself.

Slash command: `/my-vidwatch <video-url-or-path> [question]` (via
`commands/my-vidwatch.md`). The skill is also model-invoked from its description
on hosts that support that.

Tests: `python3 -m pytest tests -q` (clips synthesised with ffmpeg, no network).

---

## Token models

Frame count comes from the sampling plan and is never reduced by the visual
budget. With no explicit `--width`, frames and per-frame resolution share
`--max-tokens`: resolution may fall from 512px to the provisional 384px floor.
An explicit `--width` is exact; if either an explicit width or the 384px floor
still exceeds budget, the tool warns and proceeds at full frame count. The
estimate is only meaningful if the cost model matches the host reading the
frames. Providers do not agree:

| Frame | anthropic | openai:4o | gemini |
|---|---|---|---|
| 512x288 | 209 | 255 | 258 |
| 1024x576 | 777 | 765 | 516 |

Selection order is `--vendor`, then `$VIDWATCH_VENDOR`, then `generic`. The
generic model takes the highest estimate at every size, so an unconfigured host
uses the most conservative resolution budget. Explicit `--width` is never
silently changed; provider-side resizing remains the provider's behaviour, not a
reason for my-vidwatch to override the caller.

These are documented estimates, not billing. Providers resize server-side and
revise tokenizers between versions; check your host's own counter if exact cost
matters.

---

## Design notes

Kept here so the choices are auditable rather than folklore. Numbers are measured
on this code unless a section explicitly marks them provisional or derived.

**Staging over a single pass.** A one-shot "extract N frames across the whole
video" pipeline spends its budget before it knows where the answer is. On a
50-minute video a 100-frame cap is one frame every ~30 seconds, which is
decorative. Probe is free and usually narrows the question by itself.

**Joint frame × resolution budget.** Frame count is coverage and is never spent
as the budget control. When `--width` is omitted, the default 512px width may be
reduced until the selected vendor's full frame set fits `--max-tokens`, stopping
at **384px**. That 384px floor is **provisional**, not a measured legibility
threshold. Explicit `--width` is a caller instruction and is honoured exactly;
if it or the managed 384px floor is still over budget, warn and keep all frames.
Resolution is sized against the full pre-dedup selection; frames dropped by dedup
therefore do not retroactively buy higher resolution. `read --json` reports the
resolution-budget, extracted, and after-dedup counts separately.

TODO: measure the real resolution floor on 9:16 footage with burned-in captions.
The nearby ~512px caption-legibility statement in the extract section was not
measured to Design-notes standard. On 9:16 video `--width` is the narrow edge,
so a frame has roughly **3.15×** the pixels of 16:9 landscape at the same width;
the floor must be calibrated on portrait footage rather than inferred from
landscape.

**Qwen token estimates are provisional.** The current model follows the
Qwen3-VL processor configuration: `patch_size=16` with `merge_size=2`, giving a
/32 merged spatial grid after processor alignment. Thus 512x288 -> 16x9 = 144
spatial tokens for `qwen` image-path input. `qwen:video` is opt-in and applies 2x
temporal grouping, giving 72 tokens/frame for that same example. The processor's
`shortest_edge=65536` floor is only 64 merged visual tokens, below every width
my-vidwatch normally emits, so no additional image-token floor is applied here.
These figures are **derived, not measured**. TODO: verify both models against
API-reported usage before treating the estimates as calibrated.

`qwen:video` also has a semantic warning unrelated to token maths: scene-mode
sampling and dedup produce **irregularly spaced frames**. Feeding those JPEGs to
a host as one Qwen video sequence gives the model a uniform-timing signal that
is false, which can corrupt temporal reasoning even if the token estimate is
arithmetically correct. Use `qwen:video` only when the host preserves real frame
timing or when timing is irrelevant; otherwise use conservative `qwen` image
semantics.

**Burst sampling is evidence collection, not detection.** `read --candidates`
adds dense local samples around timestamps already found by `defects` or another
locator while leaving baseline coverage unchanged elsewhere. The default is
10fps inside +/-0.5s. Even 8-12fps cannot guarantee a single bad frame in 30fps
footage, so Phase 5 does the deterministic finding and burst sampling gathers
human/model-readable evidence around it.

**Deterministic defect thresholds.** Calibrated on 320x180, 30fps synthetic
fixtures encoded through libx264. A planted 0.15s black flash was measured as
0.167s and produced a 219-point YAVG edge; a planted 1.0s freeze measured
1.033s; planted silence measured exactly 1.000s; a 0.5s PTS discontinuity on a
33.3ms cadence measured as a 0.533s packet gap; and an A->B->A repeated shot
measured a tile delta of 0.0. The module constants are therefore: blackdetect
`d=0.03`, `pix_th=0.10`, flash <=0.25s; freezedetect `n=-50dB`, `d=0.50`;
silencedetect `noise=-35dB`, `d=0.50`; luma edge >=40 YAVG points; PTS gap >
`max(0.10s, 3x median cadence)`; duplicate-shot tile delta <=2.0. Duplicate-shot
boundaries are found with the existing `content_changes` + `confirm_transitions`
path at 0.25s sampling, then compared with the existing tile-wise score. Detector
hits whose timestamps fall within a 0.25s anchored merge window collapse into one
event candidate so one physical defect produces one burst-evidence request.

**Structural suppression does not change detector thresholds.** Before merging,
luma-spike hits that coincide within that same 0.25s window with a scene cut already
confirmed by `dedup.confirm_transitions` are dropped as intentional edit structure.
Silence is suppressed only when its entire span sits between two cached transcript
segments; silence overlapping a segment remains a dropout candidate. If no transcript
is cached, silence is never suppressed by guesswork.

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

**Local transcription only.** whisper.cpp or openai-whisper runs on the machine;
normal runs use the CLI model default documented above. No API keys, no audio
egress. Slower than a hosted endpoint; that is the trade.

**One ffmpeg landmine, commented at the call site.** Concatenated JPEGs read from
a pipe need `-c:v mjpeg` stated explicitly, or the probe fails on the
non-seekable input and the muxer reports the misleading "output file does not
contain any stream". Verified on both ffmpeg 6.1.1 and 7.1.1.

A previously documented `tile`/`nb_frames` flush bug was NOT reproducible on
ffmpeg 7.1.1 and has been deleted rather than softened — almost certainly an
ffmpeg 6 artifact, like the `drawtext` colon parsing that broke `scan`.
