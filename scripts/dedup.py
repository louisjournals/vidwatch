"""Near-duplicate frame removal, tile-wise.

Why not a whole-frame mean difference
-------------------------------------
The obvious approach — downscale to a thumbnail, take the mean absolute
difference over the whole image, drop anything under a threshold — has a
failure mode that matters precisely when frame reading matters most. A change
confined to a small region barely moves a whole-frame average. A subtitle
swapping out, a counter ticking over, one edited line in a terminal, a price
updating on a dashboard: each occupies a few percent of the pixels, so the
global mean shifts by a fraction of a level and the frame gets discarded as a
duplicate. The reader then never sees the only thing that changed.

What this does instead
----------------------
Downscale to a 128x128 grayscale thumbnail, split it into a 16x16 grid of 8x8
tiles, and score the frame by the *loudest* tile rather than the average of all
of them. A change inside one tile is measured against that tile alone, so its
signal is not divided down by the untouched rest of the frame. Two tiles out of
256 is a 128x sensitivity gain over a whole-frame average for a localised
change, and the thumbnail is kept large enough that thin text strokes survive
the downscale — at 32x32 they average into the background and disappear before
any comparison happens.

Comparison is against the last frame that was KEPT, not the immediately
previous candidate. Slow fades and gradual pans never trip a
frame-to-frame test because each step is tiny; measuring drift from the last
kept reference accumulates it.
"""
from __future__ import annotations

from pathlib import Path

from media import ffmpeg_bin
from util import run

GRID = 16         # 16x16 = 256 tiles
TILE = 8          # each tile 8x8 px -> 128x128 thumbnail
THUMB = GRID * TILE
FRAME_BYTES = THUMB * THUMB

# Threshold picked from measurement, not taste. Against a 720p source, the
# 0-255 max-tile score came out:
#
#     held slide, clean encode ............  0.39   drop
#     held slide, heavy grain + CRF 30 ....  0.97   drop
#     two digits change in a 26px font ....  4.27   keep   <- weakest real signal
#     small caption line appears .......... 31.02   keep
#     hard cut to a different slide ....... 106.89  keep
#
# 2.0 sits above a punishing noise floor and 2x below the faintest real change.
# The margin there is only ~4x, so on very grainy footage this is a knob worth
# turning (--dedup-threshold), and --no-dedup exists for when correctness beats
# token cost. For contrast, a whole-frame mean on the same pairs scored the
# two-digit change at 0.02 and the caption at 0.36 — indistinguishable from
# the 0.01 held slide, which is the whole reason for going tile-wise.
DEFAULT_THRESHOLD = 2.0


def thumbnails(paths: list[Path]) -> list[bytes]:
    """One ffmpeg call for all frames -> concatenated 32x32 grayscale bytes.

    Spawning a process per frame would dominate runtime on a 200-frame read,
    so the image2 demuxer streams the whole sorted set through a single filter
    graph. Pure stdlib from here on: no PIL, no numpy.
    """
    if not paths:
        return []
    blob = b"".join(p.read_bytes() for p in paths)
    proc = run([
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-f", "image2pipe", "-c:v", "mjpeg", "-i", "-",
        "-vf", f"scale={THUMB}:{THUMB},format=gray",
        "-f", "rawvideo", "-",
    ], stdin_bytes=blob, timeout=600)
    raw = proc.stdout
    return [raw[i:i + FRAME_BYTES] for i in range(0, len(raw), FRAME_BYTES)]


_TILE_AREA = TILE * TILE


def tile_deltas(a: bytes, b: bytes) -> list[float]:
    """Mean absolute difference per tile.

    Slice-and-zip rather than index arithmetic: roughly 3x faster in CPython
    and keeps the whole thing stdlib-only. ~0.25s for 200 frame comparisons.
    """
    out = []
    for ty in range(GRID):
        base = ty * TILE * THUMB
        for tx in range(GRID):
            total = 0
            off = base + tx * TILE
            for y in range(TILE):
                r = off + y * THUMB
                total += sum(
                    abs(x - z) for x, z in zip(a[r:r + TILE], b[r:r + TILE])
                )
            out.append(total / _TILE_AREA)
    return out


def score(a: bytes, b: bytes) -> tuple[float, float]:
    """(loudest tile delta, whole-frame delta) between two thumbnails.

    The second value is only for reporting — deciding on it is the bug this
    module exists to avoid.
    """
    deltas = tile_deltas(a, b)
    return max(deltas), sum(deltas) / len(deltas)


def estimate_floor(deltas: list[float]) -> float:
    """Quiet-end estimate of a clip's own noise floor.

    Uses the 25th percentile of adjacent-frame tile scores. The quarter of pairs
    that changed least are the closest thing to "nothing happened" this clip
    contains, so their score is what grain and compression cost per frame here.
    """
    if not deltas:
        return 0.0
    ordered = sorted(deltas)
    idx = max(0, min(len(ordered) - 1, int(round(0.25 * (len(ordered) - 1)))))
    return ordered[idx]


def dedup(
    paths: list[Path],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    protect: set[int] | None = None,
    gate: bool = True,
) -> tuple[list[Path], dict]:
    """Return (kept paths, stats).

    `protect` holds indices that must survive regardless of similarity — used
    for frames the caller asked for by explicit timestamp. First and last are
    always kept so the reported time span is honest.
    """
    if len(paths) <= 2:
        return list(paths), {
            "candidates": len(paths), "kept": len(paths), "dropped": 0,
            "threshold": threshold, "max_dropped_delta": 0.0,
        }

    protect = protect or set()
    thumbs = thumbnails(paths)
    if len(thumbs) != len(paths):
        # Decoder disagreed with the file list; keeping everything is the safe
        # failure, since dropping the wrong frame loses information silently.
        return list(paths), {
            "candidates": len(paths), "kept": len(paths), "dropped": 0,
            "threshold": threshold, "error": "thumbnail count mismatch",
            "max_dropped_delta": 0.0,
        }

    # Gate before dropping anything. On clean sources the quiet floor sits near
    # zero and the threshold separates cleanly. On compressed short-form the
    # floor MEETS OR EXCEEDS the weakest real change, measured on real footage:
    #
    #   screen recording ..... floor ~0.14, real change ~4.9   -> separable
    #   vertical, compressed . floor ~1.8-7.8, real change ~4.9 -> NOT separable
    #
    # When the ranges overlap no threshold works: raise it and genuine caption
    # changes vanish, keep it low and grain reads as content. Dropping a real
    # change is silent and unrecoverable, while keeping a duplicate costs one
    # frame — and on that footage dedup only removed ~2% of pairs anyway. So the
    # honest move is to stop deduping and say so, not to guess a threshold.
    adjacent = [score(thumbs[i], thumbs[i - 1])[0] for i in range(1, len(thumbs))]
    floor = estimate_floor(adjacent)
    if gate and floor >= threshold:
        return list(paths), {
            "candidates": len(paths), "kept": len(paths), "dropped": 0,
            "threshold": threshold, "max_dropped_delta": 0.0,
            "gated": True, "floor": round(floor, 2),
            "reason": (
                f"noise floor {floor:.2f} >= threshold {threshold:.2f}; this "
                "clip's grain is as loud as its real changes, so nothing was "
                "dropped. Use --dedup on to force it."
            ),
        }

    kept = [0]
    ref = thumbs[0]
    dropped_deltas: list[float] = []
    for i in range(1, len(paths)):
        last = i == len(paths) - 1
        if last or i in protect:
            kept.append(i)
            ref = thumbs[i]
            continue
        tile_max, _ = score(thumbs[i], ref)
        if tile_max > threshold:
            kept.append(i)
            ref = thumbs[i]
        else:
            dropped_deltas.append(tile_max)

    return [paths[i] for i in kept], {
        "candidates": len(paths),
        "kept": len(kept),
        "dropped": len(paths) - len(kept),
        "threshold": threshold,
        "max_dropped_delta": round(max(dropped_deltas), 2) if dropped_deltas else 0.0,
        "gated": False,
        "floor": round(floor, 2),
    }


# --------------------------------------------------- content-change sampling

# Sampled tile deltas on real material, 0-255:
#   held frame, no change ............   0.0
#   burned-in caption swaps ..........  19.6 - 22.6
#   slide changes / hard scene cut ...  82.1 - 110.9
# 40 sits between the last two, so a caption edit is not mistaken for a cut.
CONTENT_CHANGE_THRESHOLD = 40.0


def content_changes(
    media_path,
    duration: float,
    *,
    interval: float = 1.0,
    threshold: float = CONTENT_CHANGE_THRESHOLD,
    max_samples: int = 600,
) -> list[float]:
    """Transition timestamps found by comparing SAMPLED frames, not adjacent ones.

    ffmpeg's scene filter measures frame-to-frame difference, so a cross-fade or
    a slide transition never trips it: the change is real but spread across a
    second of video, and no single pair of neighbouring frames differs much.
    Measured on a 40-second clip containing four visually distinct slides, scene
    detection returned ZERO cuts.

    Sampling once per interval and comparing those samples sees the change
    regardless of how gradually it happened. That makes screencasts, slide decks
    and cross-faded edits legible to the pacing analysis, which otherwise
    reports them as one continuous shot.
    """
    from media import ffmpeg_bin  # local import: media must not depend on this

    if duration <= 0:
        return []
    if duration / interval > max_samples:
        interval = duration / max_samples

    proc = run([
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", str(media_path),
        "-vf", f"fps=1/{interval},scale={THUMB}:{THUMB},format=gray",
        "-an", "-sn", "-f", "rawvideo", "-",
    ], check=False, timeout=3600)

    raw = proc.stdout or b""
    frames = [
        raw[i:i + FRAME_BYTES] for i in range(0, len(raw), FRAME_BYTES)
    ]
    frames = [f for f in frames if len(f) == FRAME_BYTES]

    changes: list[float] = []
    for i in range(1, len(frames)):
        tile_max, _ = score(frames[i], frames[i - 1])
        if tile_max > threshold:
            changes.append(round(i * interval, 3))
    return changes


def confirm_transitions(
    media_path,
    candidates: list[float],
    *,
    window: float = 0.35,
    threshold: float = CONTENT_CHANGE_THRESHOLD,
) -> list[float]:
    """Keep only candidates where the frames either side genuinely differ.

    ffmpeg's scene filter is a sensitivity dial, and at the 0.15 needed to catch
    low-contrast cuts it also fires on camera shake, flashes and fast motion
    INSIDE one continuous setup. On a real vertical ad that inflated the count
    to 26 shots at 19.7/min, with boundaries a human reviewer judged to be
    motion rather than edits.

    Sampling 0.35s either side and requiring a real tile-wise difference keeps
    the sensitive detector for FINDING candidates while applying a stricter test
    for KEEPING them.
    """
    import subprocess

    from media import ffmpeg_bin

    if not candidates:
        return []

    def grab(ts: float) -> bytes | None:
        proc = subprocess.run([
            ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-ss", f"{max(0.0, ts):.3f}", "-i", str(media_path), "-frames:v", "1",
            "-vf", f"scale={THUMB}:{THUMB},format=gray", "-f", "rawvideo", "-",
        ], capture_output=True, timeout=120, check=False)
        out = proc.stdout or b""
        return out[:FRAME_BYTES] if len(out) >= FRAME_BYTES else None

    kept: list[float] = []
    for ts in candidates:
        before, after = grab(ts - window), grab(ts + window)
        if before is None or after is None:
            kept.append(ts)          # cannot judge - keep rather than lose a cut
            continue
        if score(after, before)[0] > threshold:
            kept.append(ts)
    return kept
