"""Deterministic, zero-token defect candidate locator.

This module does not decide whether an edit is bad. It finds timestamps worth a
high-resolution `read`: black flashes, freezes, real audio silence, luma spikes,
PTS discontinuities, and a shot that visually repeats an earlier non-adjacent
shot. Everything is local ffmpeg/ffprobe plus my-vidwatch's existing tile-wise
visual comparison.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

import dedup
import media
from util import VidwatchError, run

# Calibrated on the synthetic fixtures in tests/test_vidwatch.py. These are
# deliberately module constants so a threshold change is a reviewable code
# change rather than an undocumented CLI tweak.
BLACK_MIN_SECONDS = 0.03
BLACK_PIXEL_THRESHOLD = 0.10
BLACK_FLASH_MAX_SECONDS = 0.25
FREEZE_NOISE_DB = -50.0
FREEZE_MIN_SECONDS = 0.50
SILENCE_NOISE_DB = -35.0
SILENCE_MIN_SECONDS = 0.50
LUMA_SPIKE_DELTA = 40.0
LUMA_RETURN_DELTA = 12.0
PTS_GAP_FACTOR = 3.0
PTS_GAP_MIN_SECONDS = 0.10
DUPLICATE_SHOT_THRESHOLD = 2.0
DUPLICATE_CUT_SAMPLE_SECONDS = 0.25
MERGE_WINDOW_SECONDS = 0.25

_BLACK_RE = re.compile(
    rb"black_start:(-?[0-9.]+)\s+black_end:(-?[0-9.]+)\s+black_duration:([0-9.]+)"
)
_FREEZE_START_RE = re.compile(rb"freeze_start:\s*(-?[0-9.]+)")
_FREEZE_END_RE = re.compile(rb"freeze_end:\s*(-?[0-9.]+)\s*\|\s*freeze_duration:\s*([0-9.]+)")
_FRAME_RE = re.compile(r"^frame:\d+\s+pts:\S+\s+pts_time:([-0-9.]+)")
_YAVG_RE = re.compile(r"^lavfi\.signalstats\.YAVG=([-0-9.]+)")


def _candidate(t: float, kind: str, severity: str, evidence: dict) -> dict:
    return {
        "t": round(max(0.0, float(t)), 3),
        "kind": kind,
        "severity": severity,
        "evidence": evidence,
    }


def detect_black(media_path: Path) -> list[dict]:
    proc = run([
        media.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(media_path),
        "-vf", f"blackdetect=d={BLACK_MIN_SECONDS}:pix_th={BLACK_PIXEL_THRESHOLD}",
        "-an", "-sn", "-f", "null", "-",
    ], check=False, timeout=3600)
    if proc.returncode != 0:
        raise VidwatchError("blackdetect failed; refusing to report 'no black frames'")
    out = []
    for m in _BLACK_RE.finditer(proc.stderr or b""):
        st, en, dur = map(float, m.groups())
        severity = "high" if dur <= BLACK_FLASH_MAX_SECONDS else "medium"
        out.append(_candidate(st, "black", severity, {
            "start": round(st, 3), "end": round(en, 3),
            "duration": round(dur, 3), "pix_th": BLACK_PIXEL_THRESHOLD,
        }))
    return out


def detect_freeze(media_path: Path, duration: float) -> list[dict]:
    proc = run([
        media.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(media_path),
        "-vf", f"freezedetect=n={FREEZE_NOISE_DB}dB:d={FREEZE_MIN_SECONDS}",
        "-an", "-sn", "-f", "null", "-",
    ], check=False, timeout=3600)
    if proc.returncode != 0:
        raise VidwatchError("freezedetect failed; refusing to report 'no freezes'")
    err = proc.stderr or b""
    starts = [float(m.group(1)) for m in _FREEZE_START_RE.finditer(err)]
    endings = [(float(m.group(1)), float(m.group(2))) for m in _FREEZE_END_RE.finditer(err)]
    out = []
    for i, st in enumerate(starts):
        if i < len(endings):
            en, dur = endings[i]
        else:
            en = duration
            dur = max(0.0, en - st)
        if dur + 1e-6 < FREEZE_MIN_SECONDS:
            continue
        severity = "high" if dur >= 2.0 else "medium"
        out.append(_candidate(st, "freeze", severity, {
            "start": round(st, 3), "end": round(en, 3),
            "duration": round(dur, 3), "noise_db": FREEZE_NOISE_DB,
        }))
    return out


def detect_silence(media_path: Path, *, has_audio: bool) -> list[dict]:
    if not has_audio:
        return []
    spans = media.detect_silence(
        media_path, noise_db=SILENCE_NOISE_DB, min_duration=SILENCE_MIN_SECONDS,
    )
    out = []
    for st, en in spans:
        dur = en - st
        out.append(_candidate(st, "silence", "medium" if dur >= 1.0 else "low", {
            "start": st, "end": en, "duration": round(dur, 3),
            "noise_db": SILENCE_NOISE_DB,
        }))
    return out


def _luma_series(media_path: Path) -> list[tuple[float, float]]:
    proc = run([
        media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", str(media_path),
        "-vf", "signalstats,metadata=print:file=-", "-an", "-sn", "-f", "null", "-",
    ], check=False, timeout=3600)
    if proc.returncode != 0:
        raise VidwatchError("signalstats failed; refusing to report 'no luma spikes'")
    rows: list[tuple[float, float]] = []
    current_t: float | None = None
    for line in (proc.stdout or b"").decode("utf-8", "replace").splitlines():
        fm = _FRAME_RE.match(line)
        if fm:
            current_t = float(fm.group(1))
            continue
        ym = _YAVG_RE.match(line)
        if ym and current_t is not None:
            rows.append((current_t, float(ym.group(1))))
            current_t = None
    return rows


def detect_luma_spikes(media_path: Path) -> list[dict]:
    rows = _luma_series(media_path)
    out = []
    for i in range(1, len(rows)):
        t, y = rows[i]
        prev_t, prev_y = rows[i - 1]
        edge = abs(y - prev_y)
        if edge >= LUMA_SPIKE_DELTA:
            out.append(_candidate(t, "luma-spike", "high", {
                "yavg_before": round(prev_y, 2), "yavg_after": round(y, 2),
                "delta": round(edge, 2), "from": round(prev_t, 3),
            }))
            continue

        # Also catch a true one-frame spike whose immediate transitions are each
        # smaller than the edge threshold but whose value leaves and returns to
        # the same local baseline.
        if i < len(rows) - 1:
            next_y = rows[i + 1][1]
            baseline = (prev_y + next_y) / 2.0
            delta = abs(y - baseline)
            returned = abs(prev_y - next_y)
            if delta >= LUMA_SPIKE_DELTA and returned <= LUMA_RETURN_DELTA:
                out.append(_candidate(t, "luma-spike", "high", {
                    "yavg": round(y, 2),
                    "neighbor_yavg": [round(prev_y, 2), round(next_y, 2)],
                    "delta": round(delta, 2), "return_delta": round(returned, 2),
                }))
    return out


def _packet_timestamps(media_path: Path) -> list[float]:
    proc = run([
        media.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "packet=pts_time", "-of", "json", str(media_path),
    ], check=False, timeout=1800)
    if proc.returncode != 0:
        raise VidwatchError("ffprobe PTS scan failed; refusing to report 'no PTS gaps'")
    try:
        data = json.loads((proc.stdout or b"{}").decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise VidwatchError(f"ffprobe returned invalid PTS JSON: {exc}") from exc
    out = []
    for pkt in data.get("packets", []):
        try:
            out.append(float(pkt["pts_time"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(set(out))


def detect_pts_gaps(media_path: Path) -> list[dict]:
    pts = _packet_timestamps(media_path)
    deltas = [b - a for a, b in zip(pts, pts[1:]) if b > a]
    if len(deltas) < 3:
        return []
    expected = statistics.median(deltas)
    threshold = max(PTS_GAP_MIN_SECONDS, expected * PTS_GAP_FACTOR)
    out = []
    for a, b in zip(pts, pts[1:]):
        gap = b - a
        if gap > threshold:
            out.append(_candidate(a, "pts-gap", "high", {
                "from": round(a, 3), "to": round(b, 3), "gap": round(gap, 3),
                "expected": round(expected, 4), "threshold": round(threshold, 4),
            }))
    return out


def _grab_thumb(media_path: Path, ts: float) -> bytes | None:
    proc = run([
        media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, ts):.3f}", "-i", str(media_path), "-frames:v", "1",
        "-vf", f"scale={dedup.THUMB}:{dedup.THUMB},format=gray",
        "-f", "rawvideo", "-",
    ], check=False, timeout=120)
    if proc.returncode != 0:
        return None
    raw = proc.stdout or b""
    return raw[:dedup.FRAME_BYTES] if len(raw) >= dedup.FRAME_BYTES else None


def detect_duplicate_shots(media_path: Path, duration: float) -> list[dict]:
    if duration <= 0:
        return []
    raw_cuts = dedup.content_changes(
        media_path, duration, interval=DUPLICATE_CUT_SAMPLE_SECONDS,
    )
    cuts = dedup.confirm_transitions(media_path, raw_cuts)
    marks = [0.0] + [t for t in cuts if 0 < t < duration] + [duration]
    shots = [(marks[i], marks[i + 1]) for i in range(len(marks) - 1)
             if marks[i + 1] - marks[i] >= 0.15]
    if len(shots) < 3:
        return []

    reps: list[tuple[float, bytes | None]] = []
    for st, en in shots:
        mid = st + (en - st) * 0.5
        reps.append((mid, _grab_thumb(media_path, mid)))

    out = []
    for i in range(2, len(reps)):
        t, thumb = reps[i]
        if thumb is None:
            continue
        best: tuple[float, int] | None = None
        for j in range(0, i - 1):  # non-adjacent only: A -> B -> A
            prior = reps[j][1]
            if prior is None:
                continue
            tile_max, _ = dedup.score(thumb, prior)
            if best is None or tile_max < best[0]:
                best = (tile_max, j)
        if best and best[0] <= DUPLICATE_SHOT_THRESHOLD:
            score, j = best
            out.append(_candidate(shots[i][0], "duplicate-shot", "medium", {
                "shot_start": round(shots[i][0], 3),
                "shot_end": round(shots[i][1], 3),
                "matched_shot_start": round(shots[j][0], 3),
                "tile_delta": round(score, 3),
                "threshold": DUPLICATE_SHOT_THRESHOLD,
            }))
    return out


_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def merge_candidates(candidates: list[dict], *, window: float = MERGE_WINDOW_SECONDS) -> list[dict]:
    """Collapse detector hits from one physical event into one burst candidate.

    Clusters are anchored to the first hit, so a chain of nearby hits cannot grow
    beyond the merge window and accidentally fuse separate events.
    """
    ordered = sorted(candidates, key=lambda c: (c["t"], c["kind"]))
    if not ordered:
        return []

    clusters: list[list[dict]] = []
    current = [ordered[0]]
    anchor = float(ordered[0]["t"])
    for hit in ordered[1:]:
        if float(hit["t"]) - anchor <= window + 1e-9:
            current.append(hit)
        else:
            clusters.append(current)
            current = [hit]
            anchor = float(hit["t"])
    clusters.append(current)

    merged: list[dict] = []
    for hits in clusters:
        if len(hits) == 1:
            merged.append(hits[0])
            continue
        kinds = sorted({str(h["kind"]) for h in hits})
        severity = max(
            (str(h.get("severity", "low")) for h in hits),
            key=lambda s: _SEVERITY_RANK.get(s, -1),
        )
        merged.append(_candidate(
            min(float(h["t"]) for h in hits),
            "+".join(kinds),
            severity,
            {
                "merge_window": window,
                "hits": [
                    {
                        "t": h["t"], "kind": h["kind"],
                        "severity": h["severity"], "evidence": h["evidence"],
                    }
                    for h in hits
                ],
            },
        ))
    return merged


def locate(media_path: Path, meta: dict) -> list[dict]:
    """Run every deterministic detector and return merged event candidates."""
    duration = float(meta.get("duration") or 0.0)
    candidates = []
    candidates.extend(detect_black(media_path))
    candidates.extend(detect_freeze(media_path, duration))
    candidates.extend(detect_silence(media_path, has_audio=bool(meta.get("has_audio"))))
    candidates.extend(detect_luma_spikes(media_path))
    candidates.extend(detect_pts_gaps(media_path))
    candidates.extend(detect_duplicate_shots(media_path, duration))
    return merge_candidates(candidates)
