---
description: Watch or analyse a video from actual on-screen and audio evidence. Narrow questions use the staged reader; full scans produce one report.md.
argument-hint: <video-url-or-path> [question]
allowed-tools: [Bash, Read]
---

Invoke the `my-vidwatch` skill with the user's arguments: $ARGUMENTS

- If no video path/URL was supplied, ask for it.
- If the user asks a narrow question, follow my-vidwatch **Targeted question** mode:
  `quick` for short clips; otherwise `probe` → optional `scan` → narrow `read`.
- If the user asks for a scan/review/analysis/teardown, or supplies a video with
  no narrow question, follow **Full scan / review / teardown / short-form analysis** mode.
  Run `extract`; pass `--intent paid|organic` only when explicitly declared. Read
  `brief.md` first. **HARD STOP:** if it says `intent not declared`, output no
  analysis content whatsoever; the first user-facing line must be only
  `Paid 还是 organic？`. Do not inspect evidence into a diagnosis, load analysis
  references, or write any partial/shared-only report before the owner answers. Then rerun cached `extract` with that explicit
  `--intent`, inspect all visual evidence, and write the final `report.md`.
- For 2+ videos, consolidate all generated `<clip>-handoff/` folders under one
  `~/Downloads/<batch>-handoff/` parent and place `report.md` directly in that parent.
  Do not create a separate report-only folder. Intent is batch-level, so ask only once.
- Once intent is declared, load `references/shared.md` plus exactly the matching
  `references/paid.md` or `references/organic.md`. Never infer intent from the
  footage, CTA, brand, platform, production polish, or editing style, and never load both.
- Do not stop at a handoff or tell the owner to upload the brief to another model.
- Respect coverage limits: if sampling is sparse, describe what was absent from
  the frames seen, not what was absent from the entire video.
