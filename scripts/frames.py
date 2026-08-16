"""Candidate selection, extraction, and contact-sheet assembly."""
from __future__ import annotations

import hashlib
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cache import RunCache
from media import ffmpeg_bin, get_cuts, keyframe_times, probe_file
from util import VidwatchError, fmt_ts, run, warn

# my-vidwatch adaptive sampling.
#
# The planner stays continuous: there are no duration buckets that suddenly
# drop density at a boundary. Two independent curves contribute a target:
#   1. the 1.4 sqrt(duration) curve, retained so longer-video coverage never
#      regresses from 1.4; and
#   2. a continuous coverage floor fitted above the pre-1.4 behaviour, so the
#      15s-3min range does not lose the dense coverage it used to have.
# The higher target wins. Explicit --fps remains an exact uncapped override.
DEFAULT_MAX_FRAMES = 100
WIDE_AUTO_RATE_LIMIT = 3.0
FOCUS_AUTO_RATE_LIMIT = 4.0
MIN_WIDE_FRAMES = 12
MIN_FOCUS_FRAMES = 18
DEFAULT_BURST_FPS = 10.0
DEFAULT_BURST_RADIUS = 0.5

# Piecewise-linear lower envelopes. These are deliberately *not* sampling
# buckets: interpolation makes the underlying target continuous at every point.
# The knots are chosen so the curve is never below the pre-1.4 default coverage,
# including immediately after the old step boundaries.
_WIDE_FLOOR_POINTS = (
    (0.0, 0.0),
    (6.0, 12.0),
    (12.0, 12.0),
    (30.0, 40.0),
    (60.0, 60.0),
    (180.0, 80.0),
    (600.0, 100.0),
)
_FOCUS_FLOOR_POINTS = (
    (0.0, 0.0),
    (30.0, 60.0),
    (40.0, 80.0),
    (60.0, 100.0),
)


def _desired_interval_v14(duration: float, *, focused: bool) -> float:
    """The 1.4 continuous interval curve, retained as a lower bound."""
    if duration <= 0:
        return 1.0
    wide = max(0.5, min(4.0, (duration ** 0.5) / 3.0))
    return max(0.25, wide / 1.75) if focused else wide


def _interpolated_floor(duration: float, *, focused: bool) -> float:
    """Continuous frame-count floor for automatic sampling."""
    points = _FOCUS_FLOOR_POINTS if focused else _WIDE_FLOOR_POINTS
    if duration <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if duration <= x1:
            ratio = (duration - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return points[-1][1]


def adaptive_sampling(
    duration: float,
    *,
    focused: bool,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> tuple[float, int]:
    """Plan an automatic sampling rate with continuous duration scaling."""
    if duration <= 0:
        return 1.0, 1

    interval = _desired_interval_v14(duration, focused=focused)
    minimum = MIN_FOCUS_FRAMES if focused else MIN_WIDE_FRAMES
    ceiling_fps = FOCUS_AUTO_RATE_LIMIT if focused else WIDE_AUTO_RATE_LIMIT

    v14_target = math.ceil(duration / interval)
    coverage_floor = math.ceil(_interpolated_floor(duration, focused=focused))
    wanted = max(minimum, v14_target, coverage_floor)
    fps_limited = max(1, math.ceil(duration * ceiling_fps))
    target = min(max_frames, wanted, fps_limited)
    target = max(1, target)
    return target / duration, target


def explicit_sampling(fps: float, duration: float) -> tuple[float, int]:
    """Honour a user-stated rate exactly; auto caps do not apply."""
    return fps, max(1, int(round(fps * max(0.0, duration))))


def sampling_plan(
    duration: float,
    *,
    focused: bool,
    fps_override: float | None = None,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> tuple[float, int, str]:
    """Resolve (fps, frame_target, strategy_label)."""
    if fps_override:
        fps, target = explicit_sampling(fps_override, duration)
        return fps, target, f"explicit {fps:g}fps"
    fps, target = adaptive_sampling(duration, focused=focused, max_frames=max_frames)
    return fps, target, "adaptive-focus" if focused else "adaptive-wide"


def burst_times(
    candidates: list[float],
    *,
    start: float,
    end: float,
    fps: float = DEFAULT_BURST_FPS,
    radius: float = DEFAULT_BURST_RADIUS,
) -> list[float]:
    """Dense local evidence samples around already-detected timestamps.

    This is evidence collection, not detection. Baseline sampling is planned
    separately and these timestamps are merged on top of it, so adding a burst
    never steals frames from the rest of the window.
    """
    if fps <= 0:
        raise VidwatchError("burst fps must be > 0")
    if radius < 0:
        raise VidwatchError("burst radius must be >= 0")
    step = 1.0 / fps
    out: set[float] = set()
    for candidate in candidates:
        if candidate < start or candidate > end:
            continue
        lo = max(start, candidate - radius)
        hi = min(end, candidate + radius)
        n = max(0, int(math.floor((hi - lo) / step + 1e-9)))
        for i in range(n + 1):
            out.add(round(min(hi, lo + i * step), 3))
        out.add(round(candidate, 3))
    return sorted(out)


FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def find_font() -> str | None:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


# ----------------------------------------------------------------- selection

def uniform_times(start: float, end: float, n: int) -> list[float]:
    if n <= 1:
        return [start]
    step = (end - start) / (n - 1)
    return [round(start + i * step, 3) for i in range(n)]


def select_candidates(
    cache: RunCache,
    media_path: Path,
    *,
    mode: str,
    start: float,
    end: float,
    target: int,
) -> tuple[list[float], str]:
    """Candidate timestamps inside [start, end] plus the strategy actually used.

    Scene and keyframe modes fall back to uniform top-up when the source is too
    static to produce enough candidates, so a 40-minute screencast with four
    cuts still yields even coverage instead of four frames.
    """
    if mode == "uniform":
        return uniform_times(start, end, target), "uniform"

    if mode == "keyframe":
        pool = [t for t in keyframe_times(media_path, start, end) if start <= t <= end]
        label = "keyframe"
    else:
        pool = get_cuts(cache, media_path, start=start, end=end)
        label = "scene"

    if len(pool) < max(3, target // 3):
        merged = sorted(set(pool) | set(uniform_times(start, end, target)))
        return merged, f"{label}+uniform"

    if start not in pool:
        pool = [start] + pool
    if end - 0.5 > pool[-1]:
        pool = pool + [max(start, end - 0.05)]
    return sorted(set(pool)), label


# ---------------------------------------------------------------- extraction

def _extract_one(
    media_path: Path,
    ts: float,
    dest: Path,
    width: int,
    label: str | None,
    font: str | None,
) -> Path | None:
    """Seek-then-decode a single frame. Fast seek keeps this ~50-100 ms.

    Labels go through `textfile=`, never `text=`. A timestamp contains colons,
    and ffmpeg's filtergraph parser treats a colon as an option separator:
    `text='00:00'` parses on ffmpeg 6 and dies on ffmpeg 7 with "No option name
    near '00:x=8...'", taking every labelled extraction with it. Quoting and
    backslash-escaping both differ across majors; reading the string from a file
    has no escaping semantics at all, so it behaves the same everywhere.
    """
    vf = [f"scale={width}:-2:flags=bicubic"]
    label_file: Path | None = None
    if label and font:
        # Sits beside the frame, so the path is cache-owned and space-free.
        label_file = dest.with_suffix(".label.txt")
        label_file.write_text(label, encoding="utf-8")
        box = (
            f"drawtext=fontfile='{font}':textfile='{label_file}':"
            f"x=8:y=8:fontsize={max(14, width // 28)}:fontcolor=white:"
            f"box=1:boxcolor=black@0.65:boxborderw=6"
        )
        vf.append(box)
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{ts:.3f}", "-i", str(media_path),
        "-frames:v", "1", "-vf", ",".join(vf),
        "-q:v", "3", str(dest),
    ]
    proc = run(cmd, check=False, timeout=180)
    if label_file is not None:
        label_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not dest.exists() or dest.stat().st_size < 512:
        return None
    return dest


def frame_name(ts: float, width: int, *, label: bool) -> str:
    """Content-addressed filename: same moment + same size = same file.

    Keyed on (timestamp, width, labelled) rather than a per-run index, so a
    second read of the same window reuses what is already on disk instead of
    re-running ffmpeg and overwriting identical bytes. That is what makes the
    "follow-up questions are instant" claim actually true.
    """
    tag = "lbl" if label else "raw"
    return f"w{width}_{tag}_t{round(ts * 1000):09d}.jpg"


def extract(
    media_path: Path,
    times: list[float],
    out_dir: Path,
    *,
    width: int = 512,
    label: bool = False,
    workers: int = 6,
    reuse: bool = True,
) -> list[tuple[float, Path]]:
    """Extract frames in parallel. Returns [(timestamp, path)] in time order.

    Frames already on disk at the requested size are reused untouched.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    font = find_font() if label else None
    if label and not font:
        warn("no usable font found; contact-sheet tiles will be unlabelled "
             "(a text legend is printed instead)")

    labelled = bool(label and font)

    jobs = []
    ready: list[tuple[float, Path]] = []
    for ts in times:
        dest = out_dir / frame_name(ts, width, label=labelled)
        if reuse and dest.exists() and dest.stat().st_size > 512:
            ready.append((ts, dest))
            continue
        jobs.append((ts, dest, fmt_ts(ts) if label else None))

    results: list[tuple[float, Path]] = list(ready)
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_extract_one, media_path, ts, dest, width, lab, font): ts
                for ts, dest, lab in jobs
            }
            for fut, ts in futures.items():
                got = fut.result()
                if got:
                    results.append((ts, got))
    if not results:
        raise VidwatchError("no frames could be extracted")
    return sorted(results, key=lambda r: r[0])


def frame_dims(path: Path) -> tuple[int, int]:
    info = probe_file(path)
    return info["width"], info["height"]


# -------------------------------------------------------------- contact sheet

def build_sheet(
    frame_paths: list[Path],
    dest: Path,
    *,
    cols: int,
    rows: int,
    tile_width: int,
) -> Path:
    """Tile frames into one image via image2pipe, preserving order."""
    n = len(frame_paths)
    slots = cols * rows
    if n > slots:
        raise VidwatchError(f"{n} frames will not fit a {cols}x{rows} sheet")
    blob = b"".join(p.read_bytes() for p in frame_paths)

    tile = f"tile={cols}x{rows}:padding=2:color=0x1b1b1b"
    if n < slots:
        tile = f"tile={cols}x{rows}:nb_frames={n}:padding=2:color=0x1b1b1b"

    # `-c:v mjpeg` is load-bearing, not decoration. Reading concatenated JPEGs
    # from a non-seekable pipe, ffmpeg cannot probe the stream, the filter graph
    # produces nothing, and the image2 muxer fails with the misleading "output
    # file does not contain any stream". Naming the decoder skips the probe.
    run([
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "image2pipe", "-c:v", "mjpeg", "-i", "-",
        "-vf", (
            f"scale={tile_width}:-2:flags=bicubic,"
            f"pad=iw+4:ih+4:2:2:color=0x1b1b1b,{tile}"
        ),
        "-frames:v", "1", "-update", "1", "-q:v", "4", str(dest),
    ], stdin_bytes=blob, timeout=600)
    if not dest.exists():
        raise VidwatchError("contact sheet assembly failed")
    return dest


def grid_for(n: int, max_cols: int = 5) -> tuple[int, int]:
    """Near-square grid for n tiles."""
    cols = min(max_cols, max(1, int(n ** 0.5 + 0.999)))
    rows = (n + cols - 1) // cols
    return cols, rows


def run_id(**params) -> str:
    payload = "|".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha256(payload.encode()).hexdigest()[:10]


def sheet_layout(src_w: int, src_h: int, tile_width: int = 540,
                 display_edge: int = 1568, min_readable: int = 380) -> tuple[int, int]:
    """Largest grid whose tiles stay readable after a chat client downscales it.

    Chat interfaces fit an image to roughly 1568px on the long edge, so the
    usable size of one tile is tile_width * (1568 / sheet_long_edge). That makes
    the ceiling depend entirely on aspect ratio, which is not obvious:

        vertical 9:16  -> 2x2 keeps 439px per tile; 2x4 collapses to 219px
        landscape 16:9 -> 3x4 still keeps 518px per tile

    A vertical sheet grows tall as tiles are added and the downscale punishes it;
    a landscape sheet stays wide and barely suffers. Hard-coding 2x2 wasted most
    of the budget on landscape, and hard-coding anything larger made vertical
    captions unreadable. 380px is the floor where burned-in captions were still
    legible in testing.
    """
    tile_h = max(1, round(tile_width * max(1, src_h) / max(1, src_w)))
    best = (2, 2)
    for cols in (2, 3):
        for rows in range(2, 7):
            sheet_w = (tile_width + 4) * cols
            sheet_h = (tile_h + 4) * rows
            scale = min(1.0, display_edge / max(sheet_w, sheet_h))
            if tile_width * scale >= min_readable and cols * rows > best[0] * best[1]:
                best = (cols, rows)
    return best
