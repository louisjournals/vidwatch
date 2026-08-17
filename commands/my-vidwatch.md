---
description: Watch or analyse a video from actual on-screen and audio evidence. Narrow questions use the staged reader; full scans produce context and an analyst report.
argument-hint: <video-url-or-path> [question]
allowed-tools: [Bash, Read]
---

Invoke the `my-vidwatch` skill with the user's arguments: $ARGUMENTS

- If no video path/URL was supplied, ask for it.
- If the user asks a narrow question, follow my-vidwatch **Targeted question** mode:
  `quick` for short clips; otherwise `probe` → optional `scan` → narrow `read`.
- If the user asks for a scan/review/analysis/teardown, or supplies a video with
  no narrow question, follow **Full scan / review / teardown / short-form analysis** mode.
  Run `extract`; pass `--intent paid|organic` only when explicitly declared. Inspect
  `brief.md` plus all visual evidence, then write `video-context.md` and
  `analyst-report.md` in the same handoff folder.
- Always load `references/shared.md`. Then load exactly the intent reference named
  by the brief: `references/paid.md` or `references/organic.md`. If intent is not
  declared, ask before intent-specific analysis; never infer it and never load both.
  After the owner answers, rerun the cached `extract` with that explicit `--intent`
  so `brief.md` records the distribution fact before the analyst report is written.
- Do not stop at a handoff or tell the owner to upload the brief to another model.
- Respect coverage limits: if sampling is sparse, describe what was absent from
  the frames seen, not what was absent from the entire video.
