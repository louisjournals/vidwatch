# Changelog

## 2.0.0

- Restored the project MIT licence (`Copyright (c) 2026 louisjournals`) and
  standardised release metadata on 2.0.0.
- Re-fitted the continuous adaptive sampling curve so every anchor through three
  minutes meets or exceeds the pre-1.4.0 coverage, while retaining the stronger
  1.4.0 values on longer windows. Restored the 10-minute-vs-30-second regression.
- Added `AUDIT_2026-08-16.md`, a fresh independently numbered audit. The old
  external B-numbered report was never recovered, so its missing definitions are
  explicitly historical rather than guessed.
- Added a joint frame × resolution budget for `read`/`quick`: automatic width can
  fall from 512px to a provisional 384px floor, but frame count never falls for
  budget reasons. Explicit `--width` is honoured exactly and over-budget runs warn
  rather than silently downscale or thin.
- Added the zero-image-token `defects` locator for black flashes, freezes, audio
  silence, luma edges, PTS gaps and duplicate shots, reusing the existing
  content-change/transition confirmation and tile-wise comparison paths.
- Added `read --candidates` burst evidence collection. Candidate and explicit
  timestamps sit outside the automatic frame ceiling and survive dedup; JSON frame
  records now include `scene_id`, adjacent `change_score`, and nearest transcript
  line.
- Added provisional `qwen` and `qwen:video` token models using the owner-selected
  /28 compatibility assumption. `qwen` assumes a 256-token host-side image floor;
  `qwen:video` applies 2x temporal grouping and is opt-in because irregularly
  sampled JPEGs can carry false timing if a host turns them into a uniform video
  sequence. Qwen figures remain derived pending API-reported usage calibration.
- Reconciled documentation: `extract` is the primary handoff command, Whisper's
  default is stated once and matches `tx.DEFAULT_MODEL`, Rules are numbered in
  order, the sampling table matches the current planner, and README command/test
  counts match the implemented CLI.

## 1.4.0

- Replaced the old bucketed sampling implementation with a new my-vidwatch
  adaptive coverage curve. Sampling now scales continuously with window length,
  focused windows tighten coverage, and explicit `--fps` remains exact.
- Kept the adaptive sampling implementation entirely within my-vidwatch.
- Updated tests and documentation to describe the adaptive sampling model.

## 1.3.0

Fixes from a two-agent external audit that failed 1.1.0.

### Blockers
- **scan was completely broken.** Timestamp labels were interpolated into
  ffmpeg's `drawtext text=`; a colon is an option separator, so every labelled
  extraction failed on ffmpeg 7 (it parsed on ffmpeg 6, which is why a sandbox
  run missed it). Labels now go through `textfile=`, which has no escaping
  semantics on any version.
- **install.sh destroyed real directories.** A comment promised it never would;
  the next line was `rm -rf`. Real directories are now refused; `--migrate`
  moves them aside. Only symlinks are replaced silently.
- **Whisper detection was a false positive.** The backend was accepted by
  filename, so `openai-whisper` was reported as whisper.cpp and then failed at
  runtime. The binary is now identified by probing `--help`, and both
  whisper.cpp and openai-whisper are supported as first-class local backends
  with distinct provenance labels.
- **Local embedded subtitles were ignored.** A local container with a text
  subtitle track went to Whisper instead of `-map 0:s:0`. Embedded tracks are
  now extracted first, preferring the requested language, reported as
  `embedded`.
- **Sampling degraded silently with video length.** A fixed token budget was
  stretched across any duration, so a 10-minute video got the same frame count
  as a 30-second one. Replaced with duration-based frame control, denser named
  `--start/--end` windows, exact `--fps`, and `--max-tokens` as a warning
  tripwire instead of a density control.

### Other
- Long-edge cap (1.2.0) applies to `max(width, height)`, not width — portrait
  frames no longer bypass the provider limit.
- `quick` subcommand for clips under 3 minutes (1.2.0).

### Historical audit note
The external B-numbered audit report was never recovered; its original finding definitions are unavailable. A fresh audit with independent numbering is recorded in `AUDIT_2026-08-16.md`.

## 1.2.0
- Long-edge cap; `quick` single-pass subcommand.

## 1.1.0
- Slash command, tests, host-agnostic token models.
