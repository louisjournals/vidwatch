"""Timeline analysis for teardown mode.

Why this exists
---------------
A two-agent review of a real 79s vertical ad produced a genuinely useful
teardown — hook assessment, a 7.3s dead gap right after the product name, and
"the first 18.5 seconds is only two shots" — while seeing ZERO frames. All of it
came from transcript timing plus cut structure.

That is the finding this module is built on. For hook, pacing and strategy
questions the answer lives in the timeline, not in the pixels: a 7-second
silence is invisible in any single frame, and shot rhythm is a property of the
gaps between cuts. Frames cost ~620 tokens each on 9:16 footage; the whole
timeline costs a few hundred.

So teardown reports structure first and spends almost nothing on images. Frames
stay available through `read` for the one question structure cannot answer:
what does the screen actually say.

Pure functions only — no ffmpeg, no I/O. Everything here operates on data the
other stages already produced.
"""
from __future__ import annotations

from util import fmt_ts

DEFAULT_SILENCE_GAP = 2.0


def shot_table(transitions: list[float], duration: float) -> list[dict]:
    """Shot boundaries from clustered transition timestamps.

    Transitions mark where a shot ENDS, so shots are the intervals between
    them, bookended by 0 and the clip duration. Pass the clustered list, not
    raw detections: a cross-fade fires the detector several times and would
    otherwise show up as a run of impossible 0.03s shots.
    """
    if duration <= 0:
        return []
    marks = [0.0] + [t for t in sorted(transitions) if 0 < t < duration] + [duration]
    shots = []
    for i in range(len(marks) - 1):
        start, end = marks[i], marks[i + 1]
        length = end - start
        if length <= 0.01:
            continue
        shots.append({
            "index": len(shots) + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "seconds": round(length, 3),
        })
    return shots


def pacing_summary(shots: list[dict]) -> dict:
    """Median, range and the longest held shot — the shape of the edit."""
    if not shots:
        return {"count": 0}
    lengths = sorted(s["seconds"] for s in shots)
    mid = len(lengths) // 2
    median = (lengths[mid] if len(lengths) % 2
              else (lengths[mid - 1] + lengths[mid]) / 2)
    longest = max(shots, key=lambda s: s["seconds"])
    return {
        "count": len(shots),
        "median": round(median, 2),
        "shortest": round(lengths[0], 2),
        "longest": round(lengths[-1], 2),
        "longest_at": longest["start"],
    }


def annotate_audio(
    gaps: list[dict],
    silence: list[tuple[float, float]],
    *,
    has_audio: bool = True,
) -> list[dict]:
    """Mark each transcript gap as genuinely silent or as having audio under it.

    Measured on a real ad: all four transcript gaps had music playing and ffmpeg
    found no silence anywhere. Calling those "silence" was a factual error, and
    a disclaimer beneath a wrong label does not repair it. A gap with music is a
    pacing choice; a gap that is actually silent is a much stronger signal.
    """
    if not has_audio:
        # No audio stream at all, which is normal for a screen recording.
        # Calling that "audio playing" is the same class of error as calling a
        # music bed "silence".
        for g in gaps:
            g["silent_fraction"] = 1.0
            g["audio"] = "no audio track"
        return gaps

    for g in gaps:
        covered = 0.0
        for st, en in silence:
            covered += max(0.0, min(g["end"], en) - max(g["start"], st))
        span = max(1e-6, g["end"] - g["start"])
        ratio = covered / span
        g["silent_fraction"] = round(ratio, 3)
        g["audio"] = ("silent" if ratio >= 0.6
                      else "partly silent" if ratio >= 0.2
                      else "audio playing")
    return gaps


def silence_gaps(
    segments: list[dict],
    duration: float,
    *,
    min_gap: float = DEFAULT_SILENCE_GAP,
) -> list[dict]:
    """Stretches with no speech, derived from transcript timing.

    Includes the head (before the first word) and tail (after the last),
    because a slow open is a hook problem and a dead tail is a loop problem —
    both matter more than a gap in the middle.

    This reads the transcript, not audio levels, so it finds "nobody is
    talking". Pass the result through annotate_audio() with real silence spans
    to learn whether anything is actually playing underneath.
    """
    if duration <= 0:
        return []
    spans = sorted(
        ((float(s["start"]), float(s["end"])) for s in segments if s.get("end")),
        key=lambda p: p[0],
    )
    gaps: list[dict] = []

    def add(start: float, end: float, where: str) -> None:
        length = end - start
        if length >= min_gap:
            gaps.append({
                "start": round(start, 3), "end": round(end, 3),
                "seconds": round(length, 3), "where": where,
            })

    if not spans:
        add(0.0, duration, "whole clip")
        return gaps

    add(0.0, spans[0][0], "opening")
    cursor = spans[0][1]
    for start, end in spans[1:]:
        if start > cursor:
            add(cursor, start, "mid")
        cursor = max(cursor, end)
    add(cursor, duration, "ending")
    return gaps


def speech_density(segments: list[dict], duration: float) -> float:
    """Fraction of the clip with speech, 0-1. Overlaps counted once."""
    if duration <= 0 or not segments:
        return 0.0
    spans = sorted(
        ((float(s["start"]), float(s["end"])) for s in segments if s.get("end")),
        key=lambda p: p[0],
    )
    total = 0.0
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    total += cur_end - cur_start
    return min(1.0, round(total / duration, 4))


def hook_window(segments: list[dict], seconds: float = 3.0) -> str:
    """Whatever is said in the first few seconds — the hook, verbatim."""
    words = [s["text"].strip() for s in segments if float(s["start"]) < seconds]
    return " ".join(w for w in words if w)


def render(
    *,
    meta: dict,
    duration: float,
    shots: list[dict],
    pacing: dict,
    gaps: list[dict],
    density: float,
    transcript: dict,
    sheet: dict | None,
    est_tokens: int,
    max_shot_rows: int = 30,
) -> list[str]:
    """Human/agent-readable teardown. Structure first, pixels last."""
    out: list[str] = []
    src = meta.get("source", "?")
    dims = (f"{meta.get('width')}x{meta.get('height')}"
            if meta.get("width") else "?")
    out.append(f"source     {src}")
    if meta.get("title"):
        out.append(f"title      {meta['title']}")
    out.append(f"duration   {fmt_ts(duration)}   {dims}"
               + (f" @ {meta.get('fps')}fps" if meta.get("fps") else ""))
    out.append("")

    out.append("PACING")
    if pacing.get("count"):
        per_min = pacing["count"] / (duration / 60.0) if duration else 0.0
        out.append(f"  {pacing['count']} shots, {per_min:.1f}/min   "
                   f"median {pacing['median']}s   "
                   f"range {pacing['shortest']}-{pacing['longest']}s")
        out.append(f"  longest hold {pacing['longest']}s at "
                   f"{fmt_ts(pacing['longest_at'])}")
    else:
        out.append("  no transitions detected - single continuous shot")
    out.append("")

    if shots:
        out.append("SHOTS")
        rows = shots[:max_shot_rows]
        for s in rows:
            bar = "#" * min(40, max(1, int(round(s["seconds"] * 2))))
            out.append(f"  {s['index']:>3}  {fmt_ts(s['start'])}-{fmt_ts(s['end'])}"
                       f"  {s['seconds']:>6.2f}s  {bar}")
        if len(shots) > max_shot_rows:
            out.append(f"  ... {len(shots) - max_shot_rows} more")
        out.append("")

    out.append(f"SPEECH     {density * 100:.0f}% of the clip has speech")
    hook = hook_window(transcript.get("segments") or [])
    if hook:
        out.append(f"HOOK       first 3s: {hook}")
    out.append("")

    out.append(f"NO SPEECH  transcript gaps (>= {DEFAULT_SILENCE_GAP}s), with what "
               "the audio track is actually doing")
    if gaps:
        for g in gaps:
            audio = g.get("audio", "unchecked")
            flag = "  <-- genuinely silent" if audio == "silent" else ""
            out.append(f"  {fmt_ts(g['start'])}-{fmt_ts(g['end'])}  "
                       f"{g['seconds']:>5.1f}s  ({g['where']}, {audio}){flag}")
        out.append("  'audio playing' means music or sound design continues, so the")
        out.append("  gap is a pacing choice. 'genuinely silent' is dead air and a")
        out.append("  much stronger signal.")
    else:
        out.append("  none")
    out.append("")

    if sheet:
        out.append("VISUAL")
        out.append(f"  {sheet['path']}")
        out.append(f"  {sheet['cols']}x{sheet['rows']} tiles, row-major: "
                   f"{', '.join(sheet['tiles'])}")
        out.append("  Tiles are small on purpose - for overall look, not for")
        out.append("  reading on-screen text. For that: read --start T --end T")
        out.append("     --width 1024")
    out.append("")
    out.append(f"COST       ~{est_tokens:,} image tokens "
               f"({transcript.get('source', '?')} transcript)")
    return out


# ---------------------------------------------------------- handoff brief

def findings(
    *,
    duration: float,
    shots: list[dict],
    pacing: dict,
    gaps: list[dict],
    density: float,
    transcript: dict,
    cut_method: str,
) -> list[dict]:
    """Provisional observations, each paired with how to check it.

    Deliberately not conclusions. Everything here is derived from timing and
    pixel differences, and the two things that go wrong most often - how many
    real edits there are, and what a brand is called - are both settled in
    seconds by a reader looking at the frames. So each finding carries a
    `verify` line, which makes it cheap to overturn rather than something to
    copy.
    """
    out: list[dict] = []

    if shots and duration > 0:
        head = [sh for sh in shots if sh["start"] < duration * 0.3]
        # span runs to where the opening ends, not the sum of shot lengths - a
        # single shot spanning the whole clip is not a "slow open", it is a clip
        # with almost no cuts, which is a different observation.
        span = head[-1]["end"] if head else 0.0
        if head and len(head) <= 3 and span < duration * 0.6:
            marks = ", ".join(fmt_ts(sh["start"]) for sh in head[:3])
            out.append({
                "note": f"The first {fmt_ts(span)} is only {len(head)} shot(s), "
                        f"{span / duration * 100:.0f}% of the clip.",
                "verify": f"Compare the frames at {marks}. Same setup, or "
                          "genuinely different?",
            })

    per_min = pacing.get("count", 0) / (duration / 60.0) if duration else 0.0
    if pacing.get("count") and per_min >= 10 and cut_method.startswith("scene"):
        out.append({
            "note": f"{pacing['count']} shots reported ({per_min:.1f}/min). Treat "
                    "this as an UPPER BOUND, not a measurement.",
            "verify": "On fast-moving footage the detector cannot separate a cut "
                      "from camera movement inside one setup. Count the real cuts "
                      "yourself from adjacent frames.",
        })
    elif cut_method.startswith("content-change"):
        out.append({
            "note": "Scene detection found nothing, so transitions came from "
                    "sampled content comparison - typical of slides or "
                    "cross-fades.",
            "verify": "Boundaries are approximate to about one second.",
        })

    for g in gaps:
        audio = g.get("audio", "unchecked")
        if audio == "silent":
            out.append({
                "note": f"{fmt_ts(g['start'])}-{fmt_ts(g['end'])} is "
                        f"{g['seconds']:.1f}s of genuine silence ({g['where']}).",
                "verify": "Confirmed against the audio track, not just the "
                          "transcript. Check whether anything visual carries it.",
            })
        elif g["seconds"] >= 4.0:
            state = {
                "audio playing": "but the audio track continues",
                "partly silent": "with the audio dropping out part way",
                "no audio track": "and the file has no audio track at all",
            }.get(audio, "audio state unchecked")
            out.append({
                "note": f"{fmt_ts(g['start'])}-{fmt_ts(g['end'])}: "
                        f"{g['seconds']:.1f}s with nobody speaking, {state} "
                        f"({g['where']}).",
                "verify": "Look at the frames in this span. Is there a visual "
                          "payoff, or does attention have nothing to hold?",
            })

    if density < 0.5 and duration > 10:
        out.append({
            "note": f"Only {density * 100:.0f}% of the clip has speech.",
            "verify": "Check whether the silent majority is doing visual work.",
        })

    src = transcript.get("source", "")
    if src.startswith(("whisper", "openai-whisper")):
        out.append({
            "note": f"Transcript is machine-generated ({src}). Brand and product "
                    "names are the least reliable part.",
            "verify": "Read the actual names off the frames before using them "
                      "anywhere.",
        })

    return out


def render_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{fmt_ts(s['start'])}] {s['text']}" for s in segments)


def build_brief(
    *,
    goal: str = "",
    meta: dict,
    duration: float,
    shots: list[dict],
    pacing: dict,
    gaps: list[dict],
    density: float,
    transcript: dict,
    cut_method: str,
    frame_files: list[tuple[float, str]],
) -> str:
    """The markdown half of a handoff: paste this, upload the frames."""
    L: list[str] = []
    title = meta.get("title") or str(meta.get("source", "clip")).rsplit("/", 1)[-1]
    L.append(f"# {title}")
    L.append("")
    L.append(f"- Duration: **{fmt_ts(duration)}** ({duration:.1f}s)")
    if meta.get("width"):
        L.append(f"- Frame: {meta['width']}x{meta['height']}"
                 + (f" @ {meta.get('fps')}fps" if meta.get("fps") else ""))
    L.append(f"- Speech: {density * 100:.0f}% of runtime")
    L.append(f"- Transcript source: `{transcript.get('source')}`")
    L.append(f"- Shots reported: {pacing.get('count', 0)} (method: {cut_method})")
    L.append(f"- Images attached: {len(frame_files)}, evenly spaced across the clip")
    L.append("")
    if goal:
        L.append("## What the owner asked for")
        L.append("")
        L.append("> " + goal.replace(chr(10), chr(10) + "> "))
        L.append("")
        L.append("**Answer this in your first reply.** The owner has already")
        L.append("stated it once; asking them to restate it wastes the round trip")
        L.append("this document exists to avoid.")
        L.append("")
        L.append("If the goal needs a decision — recut existing footage versus")
        L.append("reshoot, short version versus long, which hook to lead with —")
        L.append("make the call, say why, and deliver the thing. A closing")
        L.append("question like \"shall I write the shot list?\" hands the work")
        L.append("back. Recommend, then produce. Flag the alternative in a line")
        L.append("so they can overrule you.")
        L.append("")
    else:
        L.append("## No goal was supplied")
        L.append("")
        L.append("Nobody recorded what this teardown is for, so infer it from the")
        L.append("footage and say what you inferred. Whoever ran the extraction")
        L.append("should have passed `--goal`.")
        L.append("")

    L.append("## How to read this")
    L.append("")
    L.append("Everything below is derived from audio timing and pixel differences.")
    L.append("The findings are **starting points, not conclusions** - each one says")
    L.append("how to check it against the attached frames. Overturn them freely;")
    L.append("the frames are the evidence, this document is only a map.")
    L.append("")
    L.append("**Cross-check the frames against the timeline.** They answer different")
    L.append("questions and a reader working from either one alone misses things:")
    L.append("")
    L.append("- Where does the strongest proof land? Compare that timestamp with the")
    L.append("  no-speech gaps. A viewer who sits through a 7-second gap and *then*")
    L.append("  waits for proof is a different problem from proof merely arriving")
    L.append("  late, and it needs a different fix.")
    L.append("- Which shots are longest? A 9-second opening shot is a hook decision,")
    L.append("  not an accident.")
    L.append("- Any gap the frames do not fill visually is where attention has")
    L.append("  nothing to hold. Those are the drop-off candidates.")
    L.append("")

    fnd = findings(duration=duration, shots=shots, pacing=pacing, gaps=gaps,
                   density=density, transcript=transcript, cut_method=cut_method)
    if fnd:
        L.append("## Findings to verify")
        L.append("")
        for i, f in enumerate(fnd, 1):
            L.append(f"{i}. {f['note']}")
            L.append(f"   - *Check:* {f['verify']}")
        L.append("")

    sheets = any("[" in name for _, name in frame_files)
    L.append("## Attached images")
    L.append("")
    if sheets:
        L.append("Contact sheets, read left-to-right then top-to-bottom. Each tile")
        L.append("has its timestamp burned in, so quote the timestamp rather than")
        L.append("the tile position.")
        L.append("")
        L.append("| Sheet | Tiles (row-major) |")
        L.append("|---|---|")
        for _, name in frame_files:
            fn, _, stamps = name.partition("  [")
            L.append(f"| `{fn}` | {stamps.rstrip(']')} |")
    else:
        L.append("| # | Time | File |")
        L.append("|---|---|---|")
        for i, (ts, name) in enumerate(frame_files, 1):
            L.append(f"| {i} | {fmt_ts(ts)} | `{name}` |")
    L.append("")

    if shots:
        L.append("## Shot table")
        L.append("")
        L.append("| # | Start | End | Seconds |")
        L.append("|---|---|---|---|")
        for sh in shots:
            L.append(f"| {sh['index']} | {fmt_ts(sh['start'])} | "
                     f"{fmt_ts(sh['end'])} | {sh['seconds']:.2f} |")
        L.append("")

    L.append("## No-speech gaps")
    L.append("")
    if gaps:
        L.append("| Start | End | Seconds | Where | Audio track |")
        L.append("|---|---|---|---|---|")
        for g in gaps:
            L.append(f"| {fmt_ts(g['start'])} | {fmt_ts(g['end'])} | "
                     f"{g['seconds']:.1f} | {g['where']} | "
                     f"{g.get('audio', 'unchecked')} |")
        L.append("")
        L.append("`audio playing` was measured on the audio track, so those gaps")
        L.append("are a pacing choice rather than dead air.")
    else:
        L.append("None.")
    L.append("")

    L.append("## Transcript")
    L.append("")
    segs = transcript.get("segments") or []
    if segs:
        L.append("```")
        L.append(render_transcript(segs))
        L.append("```")
    else:
        L.append("_None._")
    L.append("")
    return "\n".join(L)
