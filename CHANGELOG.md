# Changelog

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
  as a 30-second one. Replaced with the upstream control model: duration ladder
  for full scans, a denser ladder for named `--start/--end` windows, `--fps` as
  an uncapped override, and `--max-tokens` demoted to a tripwire that warns
  instead of thinning.

### Other
- Long-edge cap (1.2.0) applies to `max(width, height)`, not width — portrait
  frames no longer bypass the provider limit.
- `quick` subcommand for clips under 3 minutes (1.2.0).
- LICENSE and attribution to Brad Bonanno added.

### Known outstanding
Audit items B1-B4, B6, B8-B11 remain. See the audit report.

## 1.2.0
- Long-edge cap; `quick` single-pass subcommand.

## 1.1.0
- Slash command, tests, host-agnostic token models.
