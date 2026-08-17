# my-vidwatch — audit brief

**Repo:** `~/.agents/skills/my-vidwatch` · **Version:** 2.2.0 · MIT

## What this is

An agent skill that owns the evidence-to-judgment loop for video. The local CLI remains a
host-agnostic evidence engine — metadata, transcript, frames, defects and `brief.md` — and
the skill now also carries the shared plus paid/organic analysis references used by the
host to produce `video-context.md` and `analyst-report.md`. Distribution intent is an
explicit caller fact (`paid` or `organic`), never inferred from pixels.

`vidwatch.py` is a thin CLI over sibling modules including `cache`, `dedup`, `defects`,
`frames`, `media`, `teardown`, `transcript`, `vendors`, and `util`.

Commands: `quick` · `probe` · `defects` · `scan` · `read` · `extract` · `cache`

**Hard constraints.** Python stdlib only. No API keys, no outbound model calls, no audio
egress. `ffmpeg`/`ffprobe` required; `yt-dlp` and `whisper.cpp` optional. Host-agnostic —
must run anywhere a shell command and an image read are available.

**House standard.** Every number in the docs is measured on this code, not assumed. The
Design notes section exists so choices are auditable rather than folklore.

## What I need

A fresh audit producing its **own numbered findings**. Not a continuation of the old
numbering — see below.

For each finding: severity, `file:line`, how to reproduce, and whether it is a contained
fix or needs a design decision. Do not fix anything; report only.

## Why the old audit numbering is gone

CHANGELOG 1.3.0 says *"Audit items B1-B4, B6, B8-B11 remain. See the audit report."*

That report was produced by an external two-agent review and was never committed. It is
not in the repo and not in git history. B3, B4, B6, B8, B9 and B10 survive only as
scattered code comments and tests; B1, B2 and B11 have no surviving definition.

**Read those surviving comments first** and fold whatever they describe into your own
findings. Then the stale CHANGELOG line gets rewritten to say the items are unrecovered.

## Current state

Two phases committed. `my-vidwatch` working tree is clean.

| Phase | Commit | What changed |
|---|---|---|
| 1 — Licence | `00e84ce` | MIT LICENSE added, `Copyright (c) 2026 louisjournals`, README Licence section, version scheme unified to 2.0.0 |
| 2 — Coverage | `0900415` | Continuous adaptive sampling curve retained but re-fitted to meet or exceed pre-1.4.0 frame counts at every window under 3 min; 10min-vs-30s regression test restored |

## History that should shape where you look

**1.1.0 failed an external audit.** The blockers fixed in 1.3.0 are the pattern to expect:

- `drawtext text=` broke on ffmpeg 7 but parsed on ffmpeg 6, so a sandbox run missed it
- `install.sh` ran `rm -rf` on real directories under a comment promising it never would
- Whisper backend identified by filename, so `openai-whisper` was reported as whisper.cpp
- Embedded subtitle tracks silently bypassed in favour of transcription
- Sampling density silently degraded with video length

**1.4.0 repeated the pattern.** A rewrite of the sampling ladder cut frame counts ~45%
between 15s and 2min while the full suite stayed green — the regression test pinning the
old behaviour was deleted alongside the code it guarded. Phase 2 reverted the coverage
loss.

The common thread is **silent degradation under a passing test suite**, and
**version-dependent ffmpeg behaviour that one environment hides**. Weight the audit
accordingly.

## Known open issues — already logged, no need to re-report

- SKILL.md states the whisper default four different ways. The default is
  `large-v3-turbo` (`tx.DEFAULT_MODEL`). The headline `extract` example passes
  `--whisper-model medium`, contradicting the rule six lines below it.
- Rules list is numbered 1, 7, 2, 3, 4, 5, 6.
- README says "three stages" above a four-row table, and never mentions `extract` — the
  primary command in 2.0.0.
- CHANGELOG points at the missing audit report.

## Planned next, not yet built — flag anything that would conflict

- **Joint frame × resolution budget.** Frames and per-frame resolution share one visual
  budget per vendor. Constraint: degrades resolution only, never frame count. Budget as a
  density control was a 1.3.0 blocker (see comment at `vidwatch.py:125`).
- **`defects` subcommand.** A deterministic locator running before `read` — blackdetect,
  freezedetect, silencedetect, signalstats luma spikes, PTS gaps, duplicate-shot via the
  existing tile hash. Zero image tokens, reusing `dedup.content_changes` and
  `confirm_transitions`.
- **Burst sampling.** `read` densifies locally around candidate timestamps. Evidence
  collection, not detection — 8–12 FPS hits a single 30fps frame only 27–40% of the time.
- **Qwen vendor token model.** 32×32 spatial and 2× temporal compression makes a frame far
  cheaper than any existing vendor entry.

## Scope question I have not settled

Whether this audit runs now or after the four items above land. They change sampling,
budget and add a module, so auditing now means auditing code about to be replaced. If you
think the order should be the other way, say so.
