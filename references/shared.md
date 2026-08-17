# Shared short-form video analysis reference

Load this reference for every full `my-vidwatch` analysis. Then load **exactly one** intent reference: `paid.md` or `organic.md`. Never load both intent references into the same analysis context unless the owner explicitly asks to compare two distribution plans.

## Intent is a distribution fact

`brief.md` is authoritative about declared intent.

- `paid` means the owner says this version is being distributed as paid media.
- `organic` means the owner says this version is being distributed organically.
- `not declared` means **ask the owner before intent-specific analysis**. Do not infer intent from the footage, CTA, brand presence, production polish, platform, or topic. The same edit can be distributed both ways.

## How to read `brief.md`

The brief is a map, not the verdict. Cross-read it with every supplied sheet/frame. Observed pixels/audio outrank machine inferences.

### Four landmines — check every time

**1. Whisper can hallucinate speech.** Music-only or text-only footage can produce plausible repeated phrases. Treat suspicious repetition, language mismatches, and speech unsupported by the visual context as unreliable. Do not invent VO from a transcript merely because text exists in `brief.md`.

**2. Shot count is an upper bound, not ground truth.** Fast movement can look like a transition. Before quoting pacing or cuts-per-minute, inspect adjacent evidence around candidate boundaries and distinguish actual edits from movement inside one setup.

**3. Names are the least trustworthy transcript tokens.** Brand, product, branch, model and person names must be verified from readable frames or another owner-supplied source. Never put an unverified machine-transcribed name into a script.

**4. Frame size constrains picture reuse, not the whole asset.** Low-resolution picture may be unsuitable for delivery while its audio, VO, timing or structural idea remains usable. Report picture usability separately from audio/script usability.

### Cross-read frames against the timeline

For every diagnosis:

- Locate the first appearance of the strongest proof and convert its timestamp to runtime percentage: `proof_time / duration × 100`.
- Inspect the longest shots and the distribution of shot lengths, not only the shot count.
- Cross-check no-speech gaps against visible action; a quiet section with strong visual payoff is different from dead air.
- Identify repeated information and visually attractive shots that add no new understanding.
- Respect sampling coverage. If the evidence interval is sparse, say a thing was absent from **the sampled frames**, not absent from the entire video.

## Shared scoring axes

Paid and organic analyses begin with the same three 1–10 axes. Intent-specific references add their own later axes.

1. **Frame 0 + Hook** — does the first visual state and first line make the right viewer understand or anticipate something, and does the video pay that promise?
2. **Retention** — does each beat create a concrete reason to watch the next beat, without a hook-to-body collapse, repetition or dead explanation?
3. **Payoff + Proof** — does the video satisfy the promise with visible/audible evidence, and is the strongest proof placed where it can still matter?

Do not inflate scores to reward effort. Mark an axis `N/A` only with a reason.

## Frame 0 and first 1.5 seconds

Frame 0 must already communicate a state, action, contrast, result, problem or clear promise. Movement alone is not enough.

Useful starts include:

- visible state change or before/after contrast
- subject already acting: opening, pouring, writing, demonstrating, moving toward a goal
- proof shown before explanation
- readable specific promise immediately on screen

Weak starts include logo/title cards, fades, greetings, frozen expressions, dead air, or visually busy movement with no relevance signal.

Inside roughly the first 1.5 seconds, the viewer should be able to understand what the piece is about and what result, tension, mistake, demonstration or transformation is coming. This is a structural review window, not a platform ranking threshold.

## Retention architecture

A hook buys attention; the rest of the edit must keep earning it.

Use duration as a structural constraint rather than forcing one template:

- **2–7s:** visual loop, meme, transformation, or pattern interrupt
- **8–15s:** one insight, reveal, or fast demonstration
- **15–30s:** hook → tension → payoff
- **30–60s:** story, tutorial, or proof-led teaching
- **60s+:** only when each section creates a fresh reason to continue

These are editing-structure categories from the analysis framework, not platform ranking thresholds or performance benchmarks.

### Beat-boundary method — produce a number

1. Split the video into meaningful beats using changes in idea, shot function, argument, demonstration, location, speaker or payoff state.
2. At every beat boundary ask: **“What makes this viewer watch the next 3 seconds?”**
3. If there is no concrete answer in the preceding/current beat, mark that boundary as unsupported.
4. Report `unsupported boundaries / total boundaries` and list the timestamps.
5. Convert the first unsupported boundary to runtime percentage and include it in the diagnosis, the same way evidence placement is reported.

Example output shape: `Retention debt: 3/8 beat boundaries unsupported; first at 00:11.2 (28% of runtime).`

This is evidence about the edit, not a claim about an algorithmic completion threshold.

### Hook → body gear shift

Find the exact point where the hook ends and the body begins. Ask whether the video changes from **giving/showing** to **explaining/setup**. A strong opening followed by a sudden explanatory slowdown is a retention failure even when the hook itself scores well. Quote the shift timestamp and describe what changed: action→talk, proof→context, specific→generic, fast→static, or unresolved→already explained.

### Shot-length distribution and pacing

Use the shot table as a distribution:

- note the shortest, median and longest meaningful shot lengths
- identify clusters of unusually long holds or hyper-short cuts
- compare long holds with what the frame is accomplishing
- do not equate faster cuts with better retention; a long proof shot can earn its time while a short decorative cut can still be empty

### On-screen text reading load

Measure text against how long it is actually readable on screen.

- Count visible Chinese characters for Chinese text and words for English text; do not pretend they are interchangeable units.
- Record the display duration and whether text changes while the viewer is also expected to inspect proof or action.
- Flag sections where the viewer must choose between reading and seeing the evidence.
- Compare density within the same video/language rather than importing a universal characters-per-second benchmark unless the owner supplies one.

## Message density

Normally nominate:

- one primary message the viewer can repeat
- one supporting idea
- one ending action/thought

Name the hero line. Demote or cut material competing for equal importance. Repetition and beautiful shots with no new information are runtime without retention work.

## Claim / proof audit

List each meaningful claim and its evidence.

For every claim, mark one of:

- **proven in frame/audio** — evidence is directly present
- **partially supported** — evidence supports a narrower claim
- **unsupported** — the footage does not substantiate it

Only two fixes for an unsupported claim: show proof, or narrow the wording. Never strengthen copy to compensate for missing evidence. Before/after proof must be honestly comparable; differences in exposure, angle, distance or treatment can invalidate the comparison.

## Execution risk

Report execution risk separately from strategic quality: `Low / Medium / High` plus the single biggest failure mode.

Check acting/VO dependency, locations, props, wardrobe, transition precision, lighting, sound, shot count, edit complexity, and whether imperfect execution would make the idea confusing or staged.

## Material usability

Report separately from the strategic score:

- picture resolution/crop suitability
- usable audio/VO even when picture is weak
- burned-in text and watermarks
- subtitle obstruction of faces/products/proof
- whether existing shots can support the claims
- reshoot/re-record dependencies

### Text findings: three grades

Never dump every language issue into one “typo” list.

| Grade | Meaning | Action |
|---|---|---|
| **Confirmed error / 确定错字** | provably wrong character/spelling | fix it |
| **Poor wording / 用词不当** | grammar/collocation/readability problem, not a typo | recommend, label as wording |
| **Needs confirmation / 待确认** | non-standard but may be local/trade/house usage | ask; do not overwrite local vernacular |

## Self-review discipline

Before delivering a rebuild or recommendation, run the same rubric against your own proposal.

- If you criticised late proof, calculate your proposed proof placement.
- If you criticised message overload, inspect every proposed beat/EDL row for multiple jobs.
- If you criticised unsupported claims, prove every new line you introduced.
- If you criticised weak relevance in frame 0, verify your new relevance signal is actually present in the first frame/line.
- Recalculate stated runtimes and score averages.
- Distinguish verified timecodes from inherited/unverified ones.

A flaw criticised in the source and quietly reproduced in the recommendation is a failed rebuild, not a trade-off.

## Platform-fact discipline

Do not use ranking-weight percentages, traffic-share percentages, “X times more valuable” multipliers, universal completion thresholds, or marketing-blog benchmarks. Translate them into observable questions instead:

- **Save:** does this give someone a concrete reason to save it?
- **Send/share:** is there a specific person worth sending this to?
- **Retention:** does every beat give a reason to watch the next beat?

Platform behavior claims must come from an official platform source with URL + read date, a directly observable interface fact with observation date, or be omitted.

### Instagram / Meta Reels — sound and captions

Do **not** claim that Reels are “mostly watched muted.” Meta's current Reels-ad material says Reels default to sound-on and recommends 9:16 video with quality audio and key messages in the safe zone. Instagram's official ranking explainer names information about the Reel, including its audio track, among content signals; a completely silent export removes that signal and may reduce visibility, but Meta does not publish a numerical weight for it. Instagram also provides closed-caption controls; captions are required here so the creative still makes sense to viewers who choose sound-off, not because a majority-muted share has been established. Analysis rule: deliver a real audio track rather than an unintentionally silent export, **and** make the piece understandable with captions/text when sound is off.

Official sources, read 2026-08-17:
- https://www.facebook.com/business/ads/facebook-instagram-reels-ads
- https://www.facebook.com/help/instagram/7487270478066359
- https://about.instagram.com/blog/announcements/instagram-ranking-explained

### Instagram Reel technical facts

Instagram's help centre currently accepts Reel aspect ratios from 1.91:1 through 9:16, with minimum 30 FPS and 720px resolution. For a mobile-first rebuild, prefer 9:16 when that matches the intended placement rather than presenting 9:16 as the only uploadable ratio.

Official source, read 2026-08-17:
- https://www.facebook.com/help/instagram/1038071743007909
