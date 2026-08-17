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

## Shared judgment axes

Paid and organic analyses begin with the same three judgment axes. These are editorial judgments, not measurements, so do **not** average them into one score or present a cross-axis number as if it were objective.

1. **Frame 0 + Hook** — does the first visual state and first line make the right viewer understand or anticipate something, and does the video pay that promise?
2. **Retention** — does the edit visually earn continued attention beat by beat, without a hook-to-body collapse, long unearned holds, reading overload, repetition or dead explanation?
3. **Payoff + Proof** — does the video satisfy the promise with visible/audible evidence, and is the strongest proof placed where it can still matter?

For each axis use a short qualitative judgment such as `Strong / Mixed / Weak / Blocked` plus the evidence that caused it. `N/A` needs a reason.

### Blockers outrank the axes

A **blocker** is a finding that makes the current deliverable unusable or makes a proposed fix impossible without a different production action: for example an export below the intended delivery floor, a baked-in false claim/critical typo that requires the project file, or a required proof shot that does not exist. Put blockers above all other judgments. Never average a blocker together with otherwise competent structure and produce a reassuring middle score.

## Frame 0 and first 1.5 seconds

Frame 0 must already communicate a state, action, contrast, result, problem or clear promise. Movement alone is not enough.

Useful starts include:

- visible state change or before/after contrast
- subject already acting: opening, pouring, writing, demonstrating, moving toward a goal
- proof shown before explanation
- readable specific promise immediately on screen

Weak starts include logo/title cards, fades, greetings, frozen expressions, dead air, or visually busy movement with no relevance signal.

Inside roughly the first 1.5 seconds, the viewer should be able to understand what the piece is about and what result, tension, mistake, demonstration or transformation is coming. This is a structural review window, not a platform ranking threshold.

## Retention architecture — visual first

A hook buys attention; the rest of the edit must keep earning it **on screen**. Transcript logic may explain why a beat exists, but it cannot by itself prove retention.

Use duration as a structural constraint rather than forcing one template:

- **2–7s:** visual loop, meme, transformation, or pattern interrupt
- **8–15s:** one insight, reveal, or fast demonstration
- **15–30s:** hook → tension → payoff
- **30–60s:** story, tutorial, or proof-led teaching
- **60s+:** only when each section creates a fresh reason to continue

These are editing-structure categories from the analysis framework, not platform ranking thresholds or performance benchmarks.

### Beat-boundary method — visual evidence is mandatory

Split the video into meaningful beats. For **every boundary**, answer in this order:

1. **Visible change:** what visibly changes at this moment — subject, action, camera state, composition, location, proof state, object state, overlay, or demonstrable result? If there is no visible change, mark retention debt **even if the argument/transcript flows perfectly**.
2. **Shot length:** read the shot table from `brief.md`. State the current shot length and compare it with the clip's average meaningful-shot length. Any shot longer than **2× the clip average** must be called out separately and justified by what the viewer is getting during the hold.
3. **Reading load:** is the viewer being asked to read while also inspecting action/proof? Record the visible text load and whether the picture underneath helps, competes, or is unrelated.
4. **Content bridge:** only after the three visual checks, state what the idea/VO promises next. Content can strengthen a visually supported boundary, but **content alone cannot make a boundary pass or fail**.

Use a table with at least:

`Boundary | visible change | shot length vs average | reading load | content bridge | result`

`Result` may be `supported / debt / unscored`. A boundary with insufficient sampled visual evidence is `unscored`; it **never counts in the debt numerator**. Keep the original denominator visible and separately disclose unscored boundaries so missing evidence cannot masquerade as good retention.

Report: `Retention debt: unsupported / total boundaries; unscored: N; first visually-supported debt at T (runtime %).` Every counted debt row must cite actual visual evidence from a sampled frame/contact sheet plus the shot-table timing. If a row has only transcript/content reasoning, it does not qualify for the numerator.

### 0897 correction examples — content and visuals can disagree

These two failures are the reason this method is visual-first:

- **00:24–00:32:** content is concrete and relevant — real headlight problems. Visually, however, it becomes face-less workshop B-roll jumping between teardown close-ups. The content is stronger than the retention picture. Treat it as a likely attention-loss section unless the frames show a clear visual progression; do not pass it merely because the problem list is specific.
- **00:32–00:41:** the issue is not “company administration is boring.” The visual problem is **three place names plus three storefront photos inside nine seconds while unrelated workshop B-roll continues underneath**. That is reading-load competition and information stacking. Diagnose the overloaded visual task, not the topic category.

### Hook → body gear shift

Find the exact point where the hook ends and the body begins. Describe the **visual** shift first: action→static talk, proof→generic B-roll, face→object-only coverage, fast visual change→long hold, simple overlay→dense reading, or another observable change. Then add the content shift (giving/showing→explaining/setup, specific→generic, unresolved→already explained). A purely rhetorical “the video starts explaining” diagnosis is incomplete without the picture change that accompanies it.

### Shot-length distribution and pacing — use the brief

The shot table is mandatory evidence, not decoration.

- calculate the average meaningful-shot length for the clip and inspect the median/longest holds
- list every meaningful shot longer than **2× the average**
- state how much runtime those long holds consume together
- judge whether each long hold contains changing visual information, proof, readable detail, or merely static delivery
- do not equate faster cuts with better retention; a long proof shot can earn its time while a short decorative cut can still be empty

A report that discusses retention without using the shot table is incomplete. In the 79s 0897 example, two roughly 9-second static talking holds consume about **23% of runtime**; that is a larger retention risk than many transcript-level beat transitions and must be surfaced.

### On-screen text reading load

Measure text against how long it is actually readable on screen.

- Count visible Chinese characters for Chinese text and words for English text; do not pretend they are interchangeable units.
- Record the display duration and whether text changes while the viewer is also expected to inspect proof or action.
- Flag sections where the viewer must choose between reading and seeing the evidence.
- Flag dense stacked locations/names/specifications separately from ordinary subtitles.
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

Report separately from the strategic judgments:

- picture resolution/crop suitability
- usable audio/VO even when picture is weak
- burned-in text and watermarks
- subtitle obstruction of faces/products/proof
- whether existing shots can support the claims
- recut / re-render / reshoot / re-record dependencies

### Machine measurement vs sampled-frame observation

Do not label every visual reading as an unqualified `fact`.

- **Machine-measured:** metadata or deterministic output such as duration, pixel dimensions, fps, shot-table timing, detected silence, or a file hash.
- **Observed from sampled frame:** something the model read from one or more extracted images. This is evidence, but sampling and image-reading can miss small or transient details.
- **Inference:** interpretation built from those observations.

When absence matters, write `not visible in the sampled frames reviewed` rather than `does not appear in the video` unless the evidence truly covers the whole event. Example: 0897 was reported as having no website, but the 00:40 sample contained a partial `www.bxautolighting.c...` on the polo. The failure was not the video; it was the image read. Label the provenance so a missed visual detail does not masquerade as a machine measurement.

### Recut vs re-render vs reshoot

Use these as separate cost classes:

- **Recut:** reorder/trim existing rendered footage without changing baked visual content.
- **Re-render:** return to the project/source layers because burned-in text, graphics, masks, overlays, grading, or compositing must change.
- **Reshoot:** capture new picture/audio because the needed evidence or action does not exist.

Any recommendation that reuses a shot containing a baked-in defect while also claiming that defect will be fixed is **not recut-only**. State the re-render dependency explicitly. Example: using 0897 `01:05–01:08` as a new frame 0 also carries the baked `LOW BEAN` text; fixing that opening requires the project file/re-render, not merely dragging the clip earlier on the timeline.

### Text findings: three grades

Never dump every language issue into one “typo” list.

| Grade | Meaning | Action |
|---|---|---|
| **Confirmed error / 确定错字** | provably wrong character/spelling in a stable readable state | fix it |
| **Poor wording / 用词不当** | grammar/collocation/readability problem, not a typo | recommend, label as wording |
| **Needs confirmation / 待确认** | non-standard, ambiguous, local/trade usage, or an incomplete kinetic-text state | verify before changing |

**1 fps kinetic-super rule.** At roughly 1 fps sampling, a kinetic title/subtitle is often captured mid-animation rather than at its settled text state. Any apparent missing/reordered characters in an intermediate animation state are **Needs confirmation**, never a Confirmed error, unless another stable frame proves the final rendered text. Example: in 0897 the 00:28 sample showed `车灯 够` while the intended line was animating toward `车灯不够亮`; that sample alone cannot prove a typo.

## Self-review discipline

Before delivering a rebuild or recommendation, run the same rubric against your own proposal.

- If you criticised late proof, calculate your proposed proof placement.
- If you criticised message overload, inspect every proposed beat/EDL row for multiple jobs.
- If you criticised unsupported claims, prove every new line you introduced.
- If you criticised weak relevance in frame 0, verify your new relevance signal is actually present in the first frame/line.
- Recalculate stated runtimes, proof-placement percentages and retention-debt arithmetic. There is no cross-axis average score.
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
