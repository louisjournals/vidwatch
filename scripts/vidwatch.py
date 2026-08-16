#!/usr/bin/env python3
"""my-vidwatch — staged video reading for AI agents.

Three stages, cheapest first:

  quick   short clips (<3 min): transcript + dense frames in one pass.
  probe   metadata + transcript + motion profile. Zero image tokens.
  scan    whole-video contact sheets. ~1-3k image tokens.
  read    dense full-resolution frames on a bounded window.

The staging is the point. A single-pass "extract N frames across the whole
video and hand them over" pipeline spends its entire budget before it knows
where the answer is; on anything over ten minutes it produces a sampling
interval so wide that the frames are decorative. Probe is free and usually
narrows the question to a 30-second window on its own.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cache as cachemod
import dedup as dedupmod
import defects as defectsmod
import frames as framesmod
import media
import teardown as td
import transcript as tx
import vendors
from util import (
    VidwatchError,
    even_sample,
    fmt_dur,
    fmt_ts,
    parse_ts,
    warn,
)

DEFAULT_READ_BUDGET = 20_000
DEFAULT_SCAN_BUDGET = 3_000
DEFAULT_WIDTH = 512
MANAGED_WIDTH_FLOOR = 384
GUARD_WINDOW_SECONDS = 600.0
BAR = "=" * 62


# --------------------------------------------------------------------- shared

def prepare(source: str, *, need_video: bool) -> tuple[cachemod.RunCache, dict, Path | None]:
    """Resolve source -> (cache, meta, local media path). Downloads only if needed."""
    rc = cachemod.RunCache(source)
    meta = rc.read_json("meta.json") or {}

    if rc.is_url:
        if not meta.get("duration"):
            info = media.ytdlp_metadata(source)
            meta.update({"source": source, **info})
            rc.write_json("meta.json", meta)
        path = rc.local_media()
        if need_video and path is None:
            path = media.download_video(rc)
        if path is not None:
            meta.update(media.probe_file(path))
            meta["source"] = source
            rc.write_json("meta.json", meta)
    else:
        path = rc.local_media()
        if not meta.get("duration"):
            meta.update(media.probe_file(path))
            meta["source"] = str(path)
            rc.write_json("meta.json", meta)

    return rc, meta, path


def resolve_window(meta: dict, start_arg, end_arg) -> tuple[float, float]:
    duration = float(meta.get("duration") or 0.0)
    start = parse_ts(start_arg) or 0.0
    end = parse_ts(end_arg)
    if end is None:
        end = duration if duration else start + 60.0
    if duration:
        start = max(0.0, min(start, max(0.0, duration - 0.1)))
        end = min(end, duration)
    if end <= start:
        raise VidwatchError(f"empty window: {fmt_ts(start)} -> {fmt_ts(end)}")
    return start, end


def transitions_for(rc, path, duration: float) -> tuple[list[float], str]:
    """Transitions, falling back to content sampling when scene detection is blind.

    A slide deck or screencast can score zero scene cuts while visibly changing
    several times, which collapses the whole clip into one shot and makes the
    pacing analysis useless. When the scene rate is implausibly low for the
    duration, re-check by sampling.
    """
    raw = media.get_cuts(rc, path)
    cuts = media.cluster_cuts(raw)
    per_min = len(cuts) / (duration / 60.0) if duration else 0.0
    if duration >= 15 and per_min < 1.0:
        # Scene detection is blind to slides and cross-fades.
        sampled = dedupmod.content_changes(path, duration)
        if len(sampled) > len(cuts):
            return media.cluster_cuts(sampled), "content-change"

    if cuts:
        # The 0.15 threshold needed to catch low-contrast cuts also fires on
        # camera shake and flashes inside one continuous setup. Confirm each
        # candidate actually separates two different-looking frames.
        confirmed = dedupmod.confirm_transitions(path, cuts)
        if confirmed and len(confirmed) < len(cuts):
            return confirmed, f"scene+confirmed ({len(cuts)}->{len(confirmed)})"
        return confirmed or cuts, "scene"
    return cuts, "scene"


def budget_guard(
    frames: int, width: int, height: int, fps: float, model, max_tokens: int
) -> None:
    """Warn when the chosen rate exceeds the budget. Never silently thin.

    The budget used to BE the density control, which is how coverage quietly
    degraded on long video. It is now only a tripwire that reports.
    """
    per = model.tokens(width, height)
    est = per * frames
    if est <= max_tokens:
        return
    affordable = max(1, max_tokens // max(1, per))
    window = affordable / fps if fps > 0 else 0.0
    warn(
        f"this read is ~{est:,} image tokens ({frames} frames x {per} at "
        f"{width}x{height}), over the {max_tokens:,} budget. Rate was kept at "
        f"{fps:g}fps rather than thinned. {max_tokens:,} tokens buys "
        f"{affordable} frames = about {window:.0f}s of window at this rate. "
        f"Narrow --start/--end, lower --width, or raise --max-tokens."
    )


def frame_size_for_width(width: int, meta: dict) -> tuple[int, int]:
    """Return an exact requested width and aspect-preserving height."""
    src_w = meta.get("width") or 16
    src_h = meta.get("height") or 9
    w = max(2, int(width))
    h = max(2, round(w * src_h / src_w))
    return w, h


def resolve_read_frame_size(
    requested_width: int | None,
    *,
    frames: int,
    meta: dict,
    model,
    max_tokens: int,
    fps: float,
) -> tuple[int, int, str]:
    """Joint frame x resolution budget without ever changing frame count.

    Explicit --width is a caller instruction, exactly like explicit --fps: keep
    it even when it exceeds the visual budget and warn. Only the implicit
    default width is budget-managed. It may shrink from DEFAULT_WIDTH to the
    provisional MANAGED_WIDTH_FLOOR, never below it; if the floor still exceeds
    budget we keep every frame and warn rather than silently thinning coverage.
    """
    if requested_width is not None:
        w, h = frame_size_for_width(requested_width, meta)
        budget_guard(frames, w, h, fps, model, max_tokens)
        return w, h, "explicit"

    chosen: tuple[int, int] | None = None
    for candidate in range(DEFAULT_WIDTH, MANAGED_WIDTH_FLOOR - 1, -2):
        w, h = frame_size_for_width(candidate, meta)
        if model.tokens(w, h) * frames <= max_tokens:
            chosen = (w, h)
            break

    if chosen is None:
        w, h = frame_size_for_width(MANAGED_WIDTH_FLOOR, meta)
        budget_guard(frames, w, h, fps, model, max_tokens)
        warn(
            f"default frame width reached the provisional {MANAGED_WIDTH_FLOOR}px "
            "resolution floor; keeping all frames at that floor despite the budget"
        )
        return w, h, "managed-floor"

    w, h = chosen
    if w < DEFAULT_WIDTH:
        warn(
            f"default frame width reduced {DEFAULT_WIDTH} -> {w}px so {frames} frames "
            f"fit the {max_tokens:,} token visual budget ({model.name}); frame count "
            "was not changed"
        )
        return w, h, "managed"
    return w, h, "default"


def motion_profile(cuts_per_min: float) -> tuple[str, str]:
    """Classify pacing and say what it implies for frame spend."""
    if cuts_per_min < 1.0:
        return ("static", (
            "Held frames dominate. The transcript carries most of the content; "
            "frames matter only where something is shown."))
    if cuts_per_min < 4.0:
        return ("low motion", (
            "Talking-head or screencast pacing. Scene-cut frames track the "
            "structure well at low cost."))
    if cuts_per_min < 15.0:
        return ("edited", (
            "Regularly cut footage. Scene mode is a good fit; expect to spend "
            "real tokens for full coverage."))
    return ("high motion", (
        "Fast cutting or heavy camera movement. Frame sampling WILL miss things "
        "between samples — narrow the window before reading rather than "
        "scanning wide."))


# ---------------------------------------------------------------------- probe

def cmd_probe(args) -> int:
    need_video = not cachemod.is_url(args.source) or args.cuts
    rc, meta, path = prepare(args.source, need_video=need_video)

    if path is None and args.cuts:
        path = media.download_video(rc)
        meta.update(media.probe_file(path))
        rc.write_json("meta.json", meta)

    trans = tx.build_transcript(
        rc,
        use_whisper=not args.no_whisper,
        model=args.whisper_model,
        language=args.language,
        lang_pref=args.sub_langs,
    )

    density = None
    if args.cuts and path is not None:
        density = rc.read_json("density.json")
        if density is None:
            density = media.estimate_cut_density(path, float(meta.get("duration") or 0.0))
            rc.write_json("density.json", density)

    duration = float(meta.get("duration") or 0.0)
    segs = trans["segments"]
    words = tx.word_count(segs)

    if args.json:
        payload = {
            "cache_key": rc.key, "cache_dir": str(rc.dir), "meta": meta,
            "transcript": trans, "motion": density,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    out = [BAR, "MY-VIDWATCH PROBE", BAR]
    out.append(f"source     {meta.get('source', args.source)}")
    if meta.get("title"):
        out.append(f"title      {meta['title']}")
    out.append(
        f"duration   {fmt_ts(duration)} ({duration:.1f}s)"
        + (f"   {meta.get('width')}x{meta.get('height')}" if meta.get("width") else "")
        + (f" @ {meta.get('fps')}fps" if meta.get("fps") else "")
    )
    out.append(f"media      {'downloaded' if path else 'not downloaded (captions only)'}"
               f"   cache={rc.key}")
    out.append("")

    if density:
        per_min = density["cuts_per_min"]
        kind, advice = motion_profile(per_min)
        basis = ("whole file" if density["exact"]
                 else f"sampled {density['sampled_seconds']:.0f}s of {fmt_ts(duration)}")
        out.append("MOTION PROFILE")
        raw = density.get("raw_cuts")
        detail = f"  {per_min:.1f} transitions/min  -> {kind}   ({basis})"
        if raw and raw > density["total_cuts"]:
            detail += (f"\n  {raw} raw detections collapsed to {density['total_cuts']} "
                       "(flashes and cross-fades fire the detector repeatedly)")
        out.append(detail)
        out.append(f"  {advice}")
        out.append("")
    elif args.cuts:
        out.append("MOTION PROFILE  unavailable (no local media)")
        out.append("")

    out.append(f"TRANSCRIPT  source={trans['source']}  segments={len(segs)}  words={words}"
               f"  ~{int(words * 1.35)} text tokens")
    if segs:
        out.append("")
        out.append(tx.render(segs))
    else:
        out.append("  (none — no captions found"
                   + (" and whisper disabled)" if args.no_whisper else " and whisper produced nothing)"))
    out.append("")

    out.append("NEXT")
    if duration > GUARD_WINDOW_SECONDS:
        out.append(f"  This is {fmt_ts(duration)} long. Do NOT dense-read the whole thing.")
        out.append("  1. If the transcript already answers the question, stop here — zero image tokens.")
        out.append("  2. If you need to see the video, run `scan` for a whole-video overview.")
        out.append("  3. Then `read --start/--end` on the one window that matters.")
    else:
        out.append("  Short enough to read directly:")
        out.append(f"  read '{args.source}' --start 0 --end {int(duration)}")
    out.append(BAR)
    print("\n".join(out))
    return 0


# -------------------------------------------------------------------- defects

def cmd_defects(args) -> int:
    rc, meta, path = prepare(args.source, need_video=True)
    if path is None:
        raise VidwatchError("defects needs the video file; download failed")

    candidates = defectsmod.locate(path, meta)
    if args.json:
        print(json.dumps(candidates, indent=2, ensure_ascii=False))
        return 0

    print(BAR)
    print("MY-VIDWATCH DEFECTS")
    print(BAR)
    if not candidates:
        print("no deterministic defect candidates found")
        print(BAR)
        return 0

    quoted_source = shlex.quote(args.source)
    quoted_cli = shlex.quote(str(Path(__file__).resolve()))
    for c in candidates:
        t = float(c["t"])
        st = max(0.0, t - 0.75)
        en = min(float(meta.get("duration") or t + 0.75), t + 0.75)
        print(f"{fmt_ts(t, ms=True):>12}  {c['severity']:<6}  {c['kind']}")
        print(f"  evidence: {json.dumps(c['evidence'], ensure_ascii=False)}")
        print(f"  read --start {st:.3f} --end {en:.3f}: python3 {quoted_cli} read "
              f"{quoted_source} --start {st:.3f} --end {en:.3f}")
    print(BAR)
    return 0


# ----------------------------------------------------------------------- scan

def cmd_scan(args) -> int:
    model = vendors.resolve(args.vendor)
    rc, meta, path = prepare(args.source, need_video=True)
    if path is None:
        raise VidwatchError("scan needs the video file; download failed")

    start, end = resolve_window(meta, args.start, args.end)
    window = end - start

    tile_w = args.tile_width
    tile_h = max(1, round(tile_w * (meta.get("height") or 9) / (meta.get("width") or 16)))
    cols, rows = (args.grid if args.grid else (0, 0))

    # Solve tile count from the token budget rather than guessing a frame count.
    if args.tiles:
        n_tiles = args.tiles
    else:
        per_sheet_cap = 25
        # Cost is per sheet, not per tile, so solve for how many full sheets the
        # budget affords and multiply by the tiles each sheet holds.
        c0, r0 = framesmod.grid_for(per_sheet_cap)
        # B6: an earlier version forced at least one sheet with max(1, ...),
        # which quietly blew the budget - a portrait clip spent 4,025 tokens
        # against a requested 3,000. The budget is a limit, so shrink the tiles
        # until one sheet fits, and refuse rather than silently overspend.
        def sheet_tokens(tw: int) -> int:
            th = max(1, round(tw * (meta.get("height") or 9) / (meta.get("width") or 16)))
            return max(1, model.tokens((tw + 4) * c0, (th + 4) * r0))

        per_sheet_tokens = sheet_tokens(tile_w)
        while per_sheet_tokens > args.max_tokens and tile_w > 96:
            tile_w = max(96, int(tile_w * 0.8))
            per_sheet_tokens = sheet_tokens(tile_w)
        if per_sheet_tokens > args.max_tokens:
            raise VidwatchError(
                f"one contact sheet costs ~{per_sheet_tokens:,} tokens even at the "
                f"{tile_w}px minimum tile, over the {args.max_tokens:,} budget.\n"
                f"This source is {meta.get('width')}x{meta.get('height')}; portrait "
                "sheets are tall and therefore dear.\n"
                f"Raise --max-tokens to at least {per_sheet_tokens:,}, or use "
                "`teardown` which reports structure for far less."
            )
        if tile_w != args.tile_width:
            warn(f"tile width reduced {args.tile_width} -> {tile_w}px to fit the "
                 f"{args.max_tokens:,} token budget")
        affordable_sheets = max(1, args.max_tokens // per_sheet_tokens)
        n_tiles = max(4, min(200, affordable_sheets * per_sheet_cap))

    times, strategy = framesmod.select_candidates(
        rc, path, mode=args.mode, start=start, end=end, target=n_tiles
    )
    times = even_sample(times, n_tiles)

    rid = framesmod.run_id(stage="scan", start=start, end=end, n=len(times),
                           w=tile_w, mode=args.mode)
    frame_dir = rc.path("frames", rid)
    got = framesmod.extract(path, times, frame_dir, width=tile_w, label=True)

    sheets: list[dict] = []
    per_sheet = 25 if not cols else cols * rows
    groups = [got[i:i + per_sheet] for i in range(0, len(got), per_sheet)]
    for gi, group in enumerate(groups):
        c, r = (cols, rows) if cols else framesmod.grid_for(len(group))
        dest = rc.path("sheets", f"{rid}_s{gi:02d}.jpg")
        framesmod.build_sheet([p for _, p in group], dest, cols=c, rows=r,
                              tile_width=tile_w)
        w, h = framesmod.frame_dims(dest)
        sheets.append({
            "path": str(dest), "cols": c, "rows": r,
            "tiles": [fmt_ts(t) for t, _ in group],
            "width": w, "height": h, "tokens": model.tokens(w, h),
        })

    total_tokens = sum(s["tokens"] for s in sheets)
    interval = window / max(1, len(got))

    if args.json:
        print(json.dumps({"cache_key": rc.key, "sheets": sheets,
                          "strategy": strategy, "vendor": model.name,
                          "interval_seconds": round(interval, 2),
                          "est_image_tokens": total_tokens}, indent=2))
        return 0

    out = [BAR, "MY-VIDWATCH SCAN", BAR]
    out.append(f"window     {fmt_ts(start)} -> {fmt_ts(end)}  ({fmt_dur(window)})")
    out.append(f"tiles      {len(got)} via {strategy}   one tile every ~{interval:.1f}s")
    out.append(f"sheets     {len(sheets)}   est {total_tokens} image tokens "
               f"total ({model.name} model)")
    out.append("")
    out.append("READ THESE IMAGES:")
    for i, s in enumerate(sheets):
        out.append(f"  [{i}] {s['path']}   {s['cols']}x{s['rows']}, "
                   f"{s['width']}x{s['height']}, ~{s['tokens']} tokens")
        out.append(f"      row-major timestamps: {', '.join(s['tiles'])}")
    out.append("")
    out.append("WHAT THIS IS NOT")
    out.append(f"  A tile every ~{interval:.1f}s at {tile_w}px wide. Tiles are too small to")
    out.append("  read on-screen text reliably. Use this to LOCATE the moment, then:")
    out.append(f"  read '{args.source}' --start <T> --end <T> --width 1024")
    out.append(BAR)
    print("\n".join(out))
    return 0


# ----------------------------------------------------------------------- read

def cmd_read(args) -> int:
    model = vendors.resolve(args.vendor)
    rc, meta, path = prepare(args.source, need_video=True)
    if path is None:
        raise VidwatchError("read needs the video file; download failed")

    start, end = resolve_window(meta, args.start, args.end)
    window = end - start

    if window > GUARD_WINDOW_SECONDS and not args.force:
        raise VidwatchError(
            f"window is {fmt_ts(window)}, over the {fmt_ts(GUARD_WINDOW_SECONDS)} guard.\n"
            "A dense read this wide spends the whole budget on a sampling interval too\n"
            "coarse to be worth it. Run `scan` first to locate the moment, then read a\n"
            "narrow window. Pass --force to override if you genuinely want the wide pass."
        )

    focused = args.start is not None or args.end is not None
    fps, cap, rate_label = framesmod.sampling_plan(
        window, focused=focused, fps_override=args.fps,
        max_frames=args.max_frames or framesmod.DEFAULT_MAX_FRAMES,
    )
    width, est_h, resolution_mode = resolve_read_frame_size(
        args.width, frames=cap, meta=meta, model=model,
        max_tokens=args.max_tokens, fps=fps,
    )

    explicit = [parse_ts(t) for t in (args.timestamps or [])]
    explicit = [t for t in explicit if t is not None and start <= t <= end]

    times, strategy = framesmod.select_candidates(
        rc, path, mode=args.mode, start=start, end=end, target=cap
    )
    times = even_sample(times, max(1, cap - len(explicit)))
    times = sorted(set(times) | set(explicit))

    rid = framesmod.run_id(stage="read", start=start, end=end, w=width,
                           mode=args.mode, cap=cap, ex=tuple(explicit))
    frame_dir = rc.path("frames", rid)
    got = framesmod.extract(path, times, frame_dir, width=width, label=False)

    protect = {i for i, (t, _) in enumerate(got)
               if any(abs(t - e) < 0.05 for e in explicit)}

    mode = "off" if args.no_dedup else args.dedup
    if mode == "off":
        kept_paths = [p for _, p in got]
        stats = {"candidates": len(got), "kept": len(got), "dropped": 0,
                 "threshold": None, "gated": False}
    else:
        kept_paths, stats = dedupmod.dedup(
            [p for _, p in got], threshold=args.dedup_threshold,
            protect=protect, gate=(mode == "auto"),
        )

    keep_set = set(kept_paths)
    kept = [(t, p) for t, p in got if p in keep_set]
    if len(kept) > cap:
        kept = even_sample(kept, cap)

    w, h = framesmod.frame_dims(kept[0][1])
    per_frame = model.tokens(w, h)
    total_tokens = per_frame * len(kept)
    interval = window / max(1, len(kept))

    trans = rc.read_json("transcript.json") or {"source": "not built", "segments": []}
    win_text = tx.render(trans["segments"], start, end) if trans["segments"] else ""

    if args.json:
        print(json.dumps({
            "cache_key": rc.key,
            "window": [start, end],
            "strategy": strategy,
            "rate": {"fps": fps, "mode": rate_label, "target": cap},
            "dedup": stats,
            "frames": [{"t": t, "ts": fmt_ts(t, ms=True), "path": str(p)} for t, p in kept],
            "frame_size": [w, h],
            "resolution_mode": resolution_mode,
            "vendor": model.name,
            "est_image_tokens": total_tokens,
            "interval_seconds": round(interval, 3),
            "transcript_window": win_text,
        }, indent=2, ensure_ascii=False))
        return 0

    out = [BAR, "MY-VIDWATCH READ", BAR]
    out.append(f"window     {fmt_ts(start)} -> {fmt_ts(end)}  ({fmt_dur(window)})")
    out.append(f"rate       {rate_label}   target {cap} frames "
               f"({fps:g}fps requested)")
    out.append(f"selection  {strategy}   {stats['candidates']} candidates -> "
               f"{len(kept)} frames")
    if stats.get("gated"):
        out.append(f"dedup      SKIPPED - {stats['reason']}")
    elif stats.get("dropped"):
        out.append(f"dedup      {stats['dropped']} dropped, floor "
                   f"{stats.get('floor')}, threshold {stats['threshold']}, "
                   f"loudest dropped {stats.get('max_dropped_delta')}")
    elif not args.no_dedup:
        out.append(f"dedup      nothing dropped — every frame differs somewhere "
                   f"(threshold {stats['threshold']})")
    out.append(f"frames     {w}x{h}   ~{per_frame} tokens each   "
               f"~{total_tokens} total ({model.name} model)")
    out.append("")

    out.append("COVERAGE — READ THIS BEFORE TRUSTING THE FRAMES")
    out.append(f"  {len(kept)} frames across {fmt_dur(window)} = one frame every "
               f"~{interval:.2f}s ({1/interval if interval else 0:.2f}fps achieved).")
    if interval > 2.0:
        out.append(f"  Anything visible for less than ~{interval:.1f}s can fall entirely")
        out.append("  between two frames and will be invisible. Do not conclude that")
        out.append("  something is absent from the video — only that it is absent from")
        out.append("  these frames. Narrow the window to sample denser.")
    else:
        out.append("  Dense enough that brief events are likely captured, though sub-"
                   f"{interval:.2f}s events can still slip through.")
    out.append("")

    out.append("FRAMES (read each as an image):")
    for t, p in kept:
        out.append(f"  t={fmt_ts(t, ms=True)}  {p}")
    out.append("")

    if win_text:
        out.append(f"TRANSCRIPT IN WINDOW  ({trans['source']})")
        out.append(win_text)
    else:
        out.append(f"TRANSCRIPT IN WINDOW  none ({trans['source']})")
    out.append("")
    out.append(f"cache      {rc.dir}")
    out.append(BAR)
    print("\n".join(out))
    return 0


# ---------------------------------------------------------------------- quick

QUICK_MAX_SECONDS = 180.0


def cmd_quick(args) -> int:
    """One pass: transcript plus dense frames over the whole clip.

    Staging exists to stop a long video eating the budget before you know where
    to look. Under a few minutes that reasoning inverts — three subprocess
    invocations to cover 30 seconds is pure overhead, the sampling interval is
    dense whatever you do, and the token budget is never the binding
    constraint. So short clips get one call, and the guard sends anything long
    back to probe.
    """
    model = vendors.resolve(args.vendor)
    rc, meta, path = prepare(args.source, need_video=True)
    if path is None:
        raise VidwatchError("quick needs the video file; download failed")

    duration = float(meta.get("duration") or 0.0)
    if duration > args.max_duration and not args.force:
        raise VidwatchError(
            f"{fmt_ts(duration)} is over the {fmt_ts(args.max_duration)} quick limit.\n"
            "One dense pass over something this long spends the budget on a sampling\n"
            "interval too coarse to be useful. Use the staged path instead:\n"
            f"  probe '{args.source}'      # free, usually locates the moment\n"
            f"  read  '{args.source}' --start <T> --end <T>\n"
            "Pass --force to override."
        )

    trans = tx.build_transcript(
        rc,
        use_whisper=not args.no_whisper,
        model=args.whisper_model,
        language=args.language,
    )

    start, end = 0.0, duration
    fps, cap, rate_label = framesmod.sampling_plan(
        duration, focused=False, fps_override=args.fps,
        max_frames=args.max_frames or framesmod.DEFAULT_MAX_FRAMES,
    )
    width, est_h, resolution_mode = resolve_read_frame_size(
        args.width, frames=cap, meta=meta, model=model,
        max_tokens=args.max_tokens, fps=fps,
    )

    times, strategy = framesmod.select_candidates(
        rc, path, mode=args.mode, start=start, end=end, target=cap
    )
    times = even_sample(times, cap)
    rid = framesmod.run_id(stage="quick", w=width, mode=args.mode, cap=cap)
    got = framesmod.extract(path, times, rc.path("frames", rid), width=width)

    mode = "off" if args.no_dedup else args.dedup
    if mode == "off":
        kept = got
        stats = {"candidates": len(got), "kept": len(got), "dropped": 0,
                 "threshold": None, "gated": False}
    else:
        kept_paths, stats = dedupmod.dedup(
            [p for _, p in got], threshold=args.dedup_threshold,
            gate=(mode == "auto"),
        )
        keep_set = set(kept_paths)
        kept = [(t, p) for t, p in got if p in keep_set]

    w, h = framesmod.frame_dims(kept[0][1])
    per_frame = model.tokens(w, h)
    total = per_frame * len(kept)
    interval = duration / max(1, len(kept))
    text = tx.render(trans["segments"]) if trans["segments"] else ""

    if args.json:
        print(json.dumps({
            "cache_key": rc.key, "duration": duration, "strategy": strategy,
            "rate": {"fps": fps, "mode": rate_label, "target": cap},
            "dedup": stats, "vendor": model.name, "frame_size": [w, h],
            "resolution_mode": resolution_mode,
            "est_image_tokens": total, "interval_seconds": round(interval, 3),
            "frames": [{"t": t, "ts": fmt_ts(t, ms=True), "path": str(p)}
                       for t, p in kept],
            "transcript_source": trans["source"], "transcript": text,
        }, indent=2, ensure_ascii=False))
        return 0

    out = [BAR, "MY-VIDWATCH QUICK", BAR]
    out.append(f"source     {meta.get('source', args.source)}")
    out.append(f"duration   {fmt_ts(duration)}"
               + (f"   {meta.get('width')}x{meta.get('height')}" if meta.get("width") else ""))
    out.append(f"rate       {rate_label}   target {cap} frames "
               f"({fps:g}fps requested)")
    out.append(f"selection  {strategy}   {stats['candidates']} candidates -> "
               f"{len(kept)} frames")
    if stats.get("gated"):
        out.append(f"dedup      SKIPPED - {stats['reason']}")
    elif stats.get("dropped"):
        out.append(f"dedup      {stats['dropped']} dropped, floor "
                   f"{stats.get('floor')}, threshold {stats['threshold']}")
    elif mode != "off":
        out.append(f"dedup      nothing dropped - every frame differs "
                   f"(floor {stats.get('floor')}, threshold {stats['threshold']})")
    out.append(f"frames     {w}x{h}   ~{per_frame} tokens each   ~{total} total "
               f"({model.name} model)")
    out.append("")
    out.append("COVERAGE")
    out.append(f"  {len(kept)} frames across {fmt_dur(duration)} = one frame every "
               f"~{interval:.2f}s ({(1 / interval) if interval else 0:.2f}fps achieved).")
    if interval > 2.0:
        out.append(f"  Events shorter than ~{interval:.1f}s can fall between frames. "
                   "Absent from")
        out.append("  these frames is not absent from the video.")
    out.append("")
    out.append("FRAMES (read each as an image):")
    for t, pth in kept:
        out.append(f"  t={fmt_ts(t, ms=True)}  {pth}")
    out.append("")
    out.append(f"TRANSCRIPT  ({trans['source']})")
    out.append(text if text else "  (none)")
    out.append(BAR)
    print("\n".join(out))
    return 0


# --------------------------------------------------------------------- extract

# One moment per second of video, capped so a long clip does not produce a
# hundred sheets. Density is what makes the handoff useful; sheets are cheap.
DEFAULT_HANDOFF_FRAMES = 0          # 0 = derive from duration


def cmd_extract(args) -> int:
    """Build a handoff folder: a brief to paste, full-size frames to upload.

    The point of a contact sheet was to fit many moments into few tokens. When a
    person does the analysis by hand in a chat window that constraint
    disappears - full-size frames are far more legible than 256px tiles and cost
    the agent nothing. So this stage extracts and describes; it does not judge.
    """
    rc, meta, path = prepare(args.source, need_video=True)
    if path is None:
        raise VidwatchError("extract needs the video file; download failed")

    duration = float(meta.get("duration") or 0.0)
    trans = tx.build_transcript(
        rc, use_whisper=not args.no_whisper,
        model=args.whisper_model, language=args.language,
    )
    segments = trans.get("segments") or []

    transitions, cut_method = transitions_for(rc, path, duration)
    shots = td.shot_table(transitions, duration)
    pacing = td.pacing_summary(shots)
    gaps = td.annotate_audio(
        td.silence_gaps(segments, duration, min_gap=args.silence),
        media.detect_silence(path),
        has_audio=bool(meta.get("has_audio", True)),
    )
    density = td.speech_density(segments, duration)

    stem = Path(str(meta.get("source", "clip"))).stem[:60] or "clip"
    # Default to ~/Downloads rather than the working directory. cwd is whatever
    # the agent happened to be sitting in, which put handoff folders on the
    # Desktop; Downloads is where files to forward belong and where the owner
    # already looks for them.
    if args.out:
        out_dir = Path(args.out).expanduser()
    else:
        base = Path.home() / "Downloads"
        out_dir = (base if base.is_dir() else Path.cwd()) / f"{stem}-handoff"
    frame_dir = out_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    # Back off 0.25s from the end: seeking to the final frame frequently fails,
    # which silently returned 7 frames when 8 were asked for.
    wanted = args.frames or max(12, min(120, round(duration)))
    times = framesmod.uniform_times(0.0, max(0.1, duration - 0.25), wanted)
    # Deliberately NOT run through resolve_frame_size. That caps the long edge
    # because a provider would downscale it anyway - true for frames entering an
    # agent's context, irrelevant for files a person uploads by hand. Capping
    # here would just hand you a blurrier image for no saving.
    width = max(160, min(4096, args.width))
    got = framesmod.extract(path, times, rc.path("frames", f"pool{width}"),
                            width=width)

    named: list[tuple[float, str]] = []
    if args.layout == "frames":
        for i, (ts, src) in enumerate(got, 1):
            name = f"{i:02d}_{fmt_ts(ts).replace(':', 'm')}s.jpg"
            (frame_dir / name).write_bytes(src.read_bytes())
            named.append((ts, name))
    else:
        # A handful of large-tile sheets rather than a dozen separate uploads.
        # Chat interfaces handle many attachments badly - order gets confused and
        # attention spreads thin. A 2x2 grid is the compromise that matters: more
        # tiles per sheet shrinks each one, and legibility is the whole point of
        # sending full-size frames in the first place. At 540px a vertical tile
        # is 540x960, which keeps burned-in captions readable.
        if args.grid:
            cols, rows = args.grid
        else:
            cols, rows = framesmod.sheet_layout(
                meta.get("width") or 16, meta.get("height") or 9,
                tile_width=args.tile_width)
        per_sheet = cols * rows
        groups = [got[i:i + per_sheet] for i in range(0, len(got), per_sheet)]
        for gi, group in enumerate(groups, 1):
            labelled = framesmod.extract(
                path, [t for t, _ in group], rc.path("frames", f"lbl{args.tile_width}"),
                width=args.tile_width, label=True,
            )
            name = f"sheet{gi:02d}.jpg"
            framesmod.build_sheet(
                [p for _, p in labelled], frame_dir / name,
                cols=cols, rows=rows, tile_width=args.tile_width,
            )
            stamps = ", ".join(fmt_ts(t) for t, _ in labelled)
            named.append((group[0][0], f"{name}  [{stamps}]"))

    brief = td.build_brief(
        goal=args.goal or "",
        meta=meta, duration=duration, shots=shots, pacing=pacing, gaps=gaps,
        density=density, transcript=trans, cut_method=cut_method,
        frame_files=named,
    )
    (out_dir / "brief.md").write_text(brief, encoding="utf-8")

    if args.sheet:
        cols, rows = framesmod.grid_for(min(9, len(got)))
        sheet_src = framesmod.extract(
            path, even_sample(times, cols * rows), rc.path("frames", "sheetpool"),
            width=256, label=True,
        )
        framesmod.build_sheet(
            [p for _, p in sheet_src], out_dir / "sheet.jpg",
            cols=cols, rows=rows, tile_width=256,
        )

    if args.json:
        print(json.dumps({
            "out_dir": str(out_dir), "brief": str(out_dir / "brief.md"),
            "frames": [{"t": t, "file": n} for t, n in named],
            "shots": len(shots), "cut_method": cut_method,
            "transcript_source": trans.get("source"),
        }, indent=2, ensure_ascii=False))
        return 0

    print(BAR)
    print("MY-VIDWATCH EXTRACT")
    print(BAR)
    print(f"out        {out_dir}")
    print(f"brief      brief.md   ({len(brief.splitlines())} lines - paste this)")
    kind = "sheets" if args.layout == "sheets" else "frames"
    print(f"{kind:<10} frames/    ({len(named)} file(s) - upload these)")
    if args.sheet:
        print("sheet      sheet.jpg  (9-tile overview, optional)")
    print("")
    print(f"transcript {trans.get('source')}   shots {len(shots)} via {cut_method}")
    print("")
    print(BAR)
    print("REQUIRED NEXT STEP - do this before writing anything else")
    print(BAR)
    print("Attach these files to your reply so they can be downloaded:")
    print("")
    print(f"  {out_dir / 'brief.md'}")
    for _, name in named:
        fn = name.partition("  [")[0]
        print(f"  {frame_dir / fn}")
    print("")
    print("If this host cannot attach files, print each absolute path above on")
    print("its own line so they are one click from opening. Printing only the")
    print("folder is not enough.")
    print("")
    print("Attaching the files is the part that must not be skipped. Writing your")
    print("own read of the video afterwards is fine and often useful - just do it")
    print("in addition, never instead. Note that brief.md's findings are")
    print("provisional and each carries a Check: line, so anything you conclude")
    print("from the brief alone is drawn from less evidence than a reader looking")
    print("at the sheets will have. Say so if you offer a view.")
    print("")
    print("Tell the owner: paste brief.md, upload the sheets.")
    if not args.goal:
        print("")
        print("WARNING: --goal was not set, so brief.md does not say what this")
        print("teardown is for. Whoever reads it next will have to ask, which is")
        print("the round trip this stage exists to remove. Ask the owner what they")
        print("want and re-run with --goal \"...\".")
    print(BAR)
    return 0


# ---------------------------------------------------------------------- cache

def cmd_cache(args) -> int:
    if args.purge:
        n = cachemod.purge(args.purge)
        print(f"purged {n} cache entr{'y' if n == 1 else 'ies'}")
        return 0
    if args.trim:
        n = cachemod.trim(args.trim * 1024**3)
        print(f"trimmed {n} entr{'y' if n == 1 else 'ies'}")
        return 0
    entries = cachemod.list_entries()
    if not entries:
        print(f"cache empty ({cachemod.cache_root()})")
        return 0
    total = sum(e["bytes"] for e in entries)
    print(f"{cachemod.cache_root()}  —  {len(entries)} entries, "
          f"{total / 1024**3:.2f} GB")
    for e in entries:
        dur = fmt_ts(e["duration"]) if e["duration"] else "?"
        print(f"  {e['key']}  {e['bytes'] / 1024**2:8.1f} MB  {dur:>9}  "
              f"{e['source'][:70]}")
    return 0


# ------------------------------------------------------------------------ CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="my-vidwatch",
        description="Staged video reading for agents: probe -> scan -> read.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("source", help="URL (anything yt-dlp supports) or local file path")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    def budgeted(sp):
        sp.add_argument("--vendor", choices=vendors.CHOICES, default=None,
                        help="image token model for budgeting; defaults to "
                             f"${vendors.ENV_VENDOR} then 'generic'")

    pr = sub.add_parser("probe", help="metadata + transcript + motion profile (free)")
    common(pr)
    pr.add_argument("--no-cuts", dest="cuts", action="store_false", default=True,
                    help="skip scene-cut detection (skips the video download for URLs)")
    pr.add_argument("--no-whisper", action="store_true",
                    help="captions only; never transcribe locally")
    pr.add_argument("--whisper-model", default=tx.DEFAULT_MODEL,
                    help=f"ggml model name (default {tx.DEFAULT_MODEL}; "
                         f"options: {', '.join(tx.MODEL_SIZES)})")
    pr.add_argument("--language", default="auto", help="whisper language hint, e.g. en, zh")
    pr.add_argument("--sub-langs", default=None, help="yt-dlp --sub-langs override")
    pr.set_defaults(func=cmd_probe)

    df = sub.add_parser("defects", help="deterministic zero-token defect locator")
    common(df)
    df.set_defaults(func=cmd_defects)

    sc = sub.add_parser("scan", help="whole-video contact sheets (cheap overview)")
    common(sc)
    budgeted(sc)
    sc.add_argument("--start", default=None)
    sc.add_argument("--end", default=None)
    sc.add_argument("--tiles", type=int, default=None, help="force tile count")
    sc.add_argument("--tile-width", type=int, default=256)
    sc.add_argument("--grid", type=int, nargs=2, metavar=("COLS", "ROWS"), default=None)
    sc.add_argument("--mode", choices=("scene", "keyframe", "uniform"), default="scene")
    sc.add_argument("--max-tokens", type=int, default=DEFAULT_SCAN_BUDGET)
    sc.set_defaults(func=cmd_scan)

    rd = sub.add_parser("read", help="dense frames on a bounded window")
    common(rd)
    budgeted(rd)
    rd.add_argument("--start", default=None)
    rd.add_argument("--end", default=None)
    rd.add_argument("--width", type=int, default=None,
                    help=f"frame width in px; omitted = budget-managed from "
                         f"{DEFAULT_WIDTH}px down to {MANAGED_WIDTH_FLOOR}px; "
                         "an explicit value is honoured exactly")
    rd.add_argument("--fps", type=float, default=None,
                    help="force a sampling rate; bypasses the frame cap entirely")
    rd.add_argument("--max-tokens", type=int, default=DEFAULT_READ_BUDGET,
                    help=f"budget tripwire, warns rather than thinning "
                         f"(default {DEFAULT_READ_BUDGET})")
    rd.add_argument("--max-frames", type=int, default=None,
                    help=f"automatic sampling ceiling (default {framesmod.DEFAULT_MAX_FRAMES})")
    rd.add_argument("--mode", choices=("scene", "keyframe", "uniform"), default="scene")
    rd.add_argument("--timestamps", nargs="*", default=None,
                    help="always include these times (survive dedup)")
    rd.add_argument("--dedup", choices=("auto", "on", "off"), default="auto",
                    help="auto skips dedup when the clip's noise floor is as "
                         "loud as its real changes (default)")
    rd.add_argument("--no-dedup", action="store_true",
                    help="alias for --dedup off")
    rd.add_argument("--dedup-threshold", type=float,
                    default=dedupmod.DEFAULT_THRESHOLD,
                    help=f"max-tile delta, 0-255 (default {dedupmod.DEFAULT_THRESHOLD})")
    rd.add_argument("--force", action="store_true",
                    help="allow a window wider than the guard")
    rd.set_defaults(func=cmd_read)

    qk = sub.add_parser(
        "quick", help="single pass for short clips: transcript + dense frames")
    common(qk)
    budgeted(qk)
    qk.add_argument("--width", type=int, default=None,
                    help=f"omitted = budget-managed from {DEFAULT_WIDTH}px down to "
                         f"{MANAGED_WIDTH_FLOOR}px; explicit values are exact")
    qk.add_argument("--fps", type=float, default=None)
    qk.add_argument("--max-tokens", type=int, default=DEFAULT_READ_BUDGET)
    qk.add_argument("--max-frames", type=int, default=None)
    qk.add_argument("--mode", choices=("scene", "keyframe", "uniform"), default="scene")
    qk.add_argument("--max-duration", type=float, default=QUICK_MAX_SECONDS,
                    help=f"refuse clips longer than this (default {QUICK_MAX_SECONDS:.0f}s)")
    qk.add_argument("--dedup", choices=("auto", "on", "off"), default="auto",
                    help="auto skips dedup when the clip's noise floor is as "
                         "loud as its real changes (default)")
    qk.add_argument("--no-dedup", action="store_true",
                    help="alias for --dedup off")
    qk.add_argument("--dedup-threshold", type=float, default=dedupmod.DEFAULT_THRESHOLD)
    qk.add_argument("--no-whisper", action="store_true")
    qk.add_argument("--whisper-model", default=tx.DEFAULT_MODEL)
    qk.add_argument("--language", default="auto")
    qk.add_argument("--force", action="store_true", help="ignore the duration guard")
    qk.set_defaults(func=cmd_quick)

    ex = sub.add_parser(
        "extract",
        help="handoff folder: brief.md to paste + full-size frames to upload")
    common(ex)
    ex.add_argument("--goal", default=None,
                    help="what the owner wants from this teardown, in their own "
                         "words. Pass it every time - it is the one flag that "
                         "should always be set")
    ex.add_argument("--frames", type=int, default=DEFAULT_HANDOFF_FRAMES,
                    help="evenly spaced moments; default is one per second of "
                         "video (min 12, max 120)")
    ex.add_argument("--layout", choices=("sheets", "frames"), default="sheets",
                    help="sheets = a few large-tile grids (default, fewer uploads); "
                         "frames = one file per moment")
    ex.add_argument("--grid", type=int, nargs=2, metavar=("COLS", "ROWS"),
                    default=None,
                    help="tiles per sheet; default adapts to aspect ratio "
                         "(vertical 2x2, landscape up to 3x4)")
    ex.add_argument("--tile-width", type=int, default=540,
                    help="per-tile width in a sheet (default 540)")
    ex.add_argument("--width", type=int, default=1024,
                    help="frame width; 1024 keeps on-screen text legible")
    ex.add_argument("--out", default=None, help="output directory")
    ex.add_argument("--sheet", action="store_true",
                    help="also build a 9-tile overview sheet")
    ex.add_argument("--silence", type=float, default=td.DEFAULT_SILENCE_GAP)
    ex.add_argument("--no-whisper", action="store_true")
    ex.add_argument("--whisper-model", default=tx.DEFAULT_MODEL)
    ex.add_argument("--language", default="auto")
    ex.set_defaults(func=cmd_extract)

    ca = sub.add_parser("cache", help="inspect or clear the run cache")
    ca.add_argument("--purge", nargs="?", const="all", default=None,
                    metavar="KEY", help="delete one key, or all")
    ca.add_argument("--trim", type=int, default=None, metavar="GB",
                    help="LRU-trim down to GB")
    ca.add_argument("--json", action="store_true")
    ca.set_defaults(func=cmd_cache)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except VidwatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
