"""ffprobe / ffmpeg / yt-dlp wrappers."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from cache import RunCache
from util import VidwatchError, run, which


def ffmpeg_bin() -> str:
    b = which("ffmpeg")
    if not b:
        raise VidwatchError("ffmpeg not found. macOS: brew install ffmpeg")
    return b


def ffprobe_bin() -> str:
    b = which("ffprobe")
    if not b:
        raise VidwatchError("ffprobe not found. macOS: brew install ffmpeg")
    return b


def ytdlp_bin() -> str:
    b = which("yt-dlp")
    if not b:
        raise VidwatchError("yt-dlp not found. macOS: brew install yt-dlp")
    return b


# --------------------------------------------------------------------- probe

def probe_file(path: Path) -> dict:
    """Container + first video stream facts."""
    proc = run([
        ffprobe_bin(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    data = json.loads(proc.stdout.decode("utf-8", "replace"))
    vs = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if vs is None:
        raise VidwatchError(f"no video stream in {path.name}")
    audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))

    duration = 0.0
    for candidate in (data.get("format", {}).get("duration"), vs.get("duration")):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue

    fps = 0.0
    rate = vs.get("avg_frame_rate") or vs.get("r_frame_rate") or "0/1"
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            fps = float(num) / float(den) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0

    return {
        "duration": round(duration, 3),
        "width": int(vs.get("width") or 0),
        "height": int(vs.get("height") or 0),
        "fps": round(fps, 3),
        "codec": vs.get("codec_name", "?"),
        "has_audio": audio,
        "size_bytes": int(data.get("format", {}).get("size") or 0),
    }


def ytdlp_metadata(url: str) -> dict:
    """Title/duration/subtitle availability without downloading the video."""
    proc = run([
        ytdlp_bin(), "--no-warnings", "--skip-download",
        "--dump-single-json", url,
    ], timeout=180)
    info = json.loads(proc.stdout.decode("utf-8", "replace"))
    subs = sorted((info.get("subtitles") or {}).keys())
    autos = sorted((info.get("automatic_captions") or {}).keys())
    return {
        "title": info.get("title") or "",
        "duration": float(info.get("duration") or 0.0),
        "uploader": info.get("uploader") or "",
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
        "manual_subs": subs,
        "auto_subs": autos,
    }


# ------------------------------------------------------------------ download

def download_video(cache: RunCache, *, max_height: int = 1080) -> Path:
    """Fetch the video once into the cache. No-op if already there."""
    existing = cache.local_media()
    if existing and existing.exists():
        return existing
    out_tmpl = str(cache.path("source.%(ext)s"))
    fmt = (
        f"bestvideo[height<={max_height}][vcodec!*=av01]+bestaudio/"
        f"best[height<={max_height}]/best"
    )
    run([
        ytdlp_bin(), "--no-warnings", "--no-playlist",
        "-f", fmt, "--merge-output-format", "mp4",
        "-o", out_tmpl, cache.source,
    ], timeout=3600)
    got = cache.local_media()
    if not got:
        raise VidwatchError("download produced no file")
    return got


def download_audio(cache: RunCache) -> Path:
    """Audio-only fetch for the whisper path — far smaller than the video."""
    target = cache.path("audio_src.m4a")
    if target.exists():
        return target
    run([
        ytdlp_bin(), "--no-warnings", "--no-playlist",
        "-f", "bestaudio/best", "-o", str(target), cache.source,
    ], timeout=1800)
    if not target.exists():
        hits = sorted(cache.dir.glob("audio_src.*"))
        if not hits:
            raise VidwatchError("audio download produced no file")
        return hits[0]
    return target


def extract_wav(src: Path, dest: Path) -> Path:
    """16 kHz mono PCM — the only format whisper.cpp accepts."""
    if dest.exists() and dest.stat().st_size > 1024:
        return dest
    run([
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(dest),
    ], timeout=1800)
    if not dest.exists():
        raise VidwatchError("audio extraction failed")
    return dest


# --------------------------------------------------------------- scene cuts

_PTS_RE = re.compile(rb"pts_time:([0-9.]+)")

# 0.15, not the more common 0.30. Measured: a hard cut between two similarly
# lit slides scored between 0.10 and 0.20 and was missed at both 0.20 and 0.30,
# while heavy grain (alls=22 at CRF 30) over a held frame produced zero false
# positives down to 0.15.
#
# The asymmetry justifies biasing sensitive. A false-positive cut is nearly
# free: it becomes one more candidate, then gets thinned by the frame cap and
# collapsed by dedup if it looks like its neighbour. A false-negative cut is
# permanent — the frame is never extracted and nothing downstream can recover
# it. So err toward detecting too much.
DEFAULT_SCENE_THRESHOLD = 0.15

# Prescale before the scene filter. Platform-dependent, and the two
# measurements disagree:
#
#   macOS 15 / ffmpeg 7.1.1 (2 independent audits) .. prescale 0.49-0.50x the
#                                                     time, i.e. ~2x FASTER
#   Ubuntu / ffmpeg 6.1.1 (this project's sandbox) .. prescale 15.6s vs 12.7s,
#                                                     i.e. ~1.2x SLOWER
#
# Cut lists were byte-identical at every threshold on both, so accuracy is not
# at stake — only speed. Default is on, because the deployment target is macOS
# with ffmpeg 7 where it wins clearly. Override with VIDWATCH_SCENE_PRESCALE=0
# if your platform behaves like the sandbox. An earlier version hardcoded this
# off based on the sandbox figure alone, which made detection twice as slow on
# the machine that actually runs it.
SCENE_PRESCALE_WIDTH = 160


def scene_prescale() -> int:
    """Prescale width, or 0 to disable."""
    raw = os.environ.get("VIDWATCH_SCENE_PRESCALE")
    if raw is None:
        return SCENE_PRESCALE_WIDTH
    raw = raw.strip().lower()
    if raw in ("0", "", "off", "false", "no"):
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return SCENE_PRESCALE_WIDTH


def detect_cuts(
    media_path: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> list[float]:
    """Absolute scene-cut timestamps inside [start, end].

    Windowed on purpose. Detection requires a full decode of whatever range it
    is given, so scanning an entire long video to answer a question about one
    minute of it is the single most wasteful thing this tool could do.
    `-copyts` keeps reported timestamps absolute; without it they come back
    relative to the seek point.
    """
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostats", "-threads", "0"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-t", f"{max(0.1, end - start):.3f}"]
    pre = scene_prescale()
    vf = f"select='gt(scene,{threshold})',showinfo"
    if pre:
        vf = f"scale={pre}:-2,{vf}"
    cmd += [
        "-copyts", "-i", str(media_path), "-an", "-sn",
        "-vf", vf, "-fps_mode", "vfr", "-f", "null", "-",
    ]
    proc = run(cmd, timeout=7200)
    cuts = [float(m.group(1)) for m in _PTS_RE.finditer(proc.stderr or b"")]
    lo, hi = start, (end if end is not None else float("inf"))
    return sorted({round(c, 3) for c in cuts if lo <= c <= hi})


def get_cuts(
    cache: RunCache,
    media_path: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> list[float]:
    """Cached windowed detection. Reuses a wider cached window when one exists."""
    store = cache.read_json("cuts.json") or {"windows": []}
    for w in store["windows"]:
        if (
            abs(w["threshold"] - threshold) < 1e-9
            and w["start"] <= start + 0.01
            and (w["end"] is None or (end is not None and w["end"] >= end - 0.01))
        ):
            hi = end if end is not None else float("inf")
            return [c for c in w["cuts"] if start <= c <= hi]

    cuts = detect_cuts(media_path, start=start, end=end, threshold=threshold)
    store["windows"].append(
        {"start": start, "end": end, "threshold": threshold, "cuts": cuts}
    )
    cache.write_json("cuts.json", store)
    return cuts


CUT_CLUSTER_WINDOW = 0.5


def cluster_cuts(cuts: list[float], window: float = CUT_CLUSTER_WINDOW) -> list[float]:
    """Collapse detections within `window` seconds into one transition.

    A flash, glitch or cross-fade fires the scene filter several times for what
    a viewer reads as one cut. Measured on real short-form footage: 6 detections
    inside 0.17s at one transition and 4 inside 0.47s at another, inflating a
    31/min rate to roughly 19/min of real transitions. Rate is what the motion
    profile classifies on, so the raw count misreports the pacing.
    """
    out: list[float] = []
    for c in sorted(cuts):
        if not out or (c - out[-1]) > window:
            out.append(c)
    return out


def estimate_cut_density(
    media_path: Path,
    duration: float,
    *,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
    samples: int = 6,
    probe_seconds: float = 20.0,
) -> dict:
    """Cuts per minute from sampled probes instead of a full decode.

    The motion profile only needs a rate, not an exhaustive list. Six 20-second
    probes cost two minutes of decode regardless of whether the source is three
    minutes or three hours, which keeps `probe` genuinely cheap.
    """
    if duration <= samples * probe_seconds:
        raw = detect_cuts(media_path, threshold=threshold)
        cuts = cluster_cuts(raw)
        per_min = len(cuts) / (duration / 60.0) if duration else 0.0
        return {
            "cuts_per_min": round(per_min, 2), "exact": True,
            "sampled_seconds": round(duration, 1), "total_cuts": len(cuts),
            "raw_cuts": len(raw),
        }

    usable = max(0.0, duration - probe_seconds)
    starts = [usable * i / max(1, samples - 1) for i in range(samples)]
    found = 0
    raw_total = 0
    for st in starts:
        raw = detect_cuts(
            media_path, start=st, end=st + probe_seconds, threshold=threshold
        )
        raw_total += len(raw)
        found += len(cluster_cuts(raw))
    scanned = samples * probe_seconds
    return {
        "cuts_per_min": round(found / (scanned / 60.0), 2), "exact": False,
        "sampled_seconds": round(scanned, 1), "total_cuts": found,
        "raw_cuts": raw_total,
    }


def keyframe_times(media: Path, start: float = 0.0, end: float | None = None) -> list[float]:
    """Keyframe timestamps via the packet index. Near-instant, no full decode."""
    cmd = [
        ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
        "-skip_frame", "nokey", "-show_entries", "frame=best_effort_timestamp_time",
        "-print_format", "csv=p=0",
    ]
    if start:
        cmd += ["-read_intervals", f"{start}%{end}" if end else f"{start}%"]
    cmd += [str(media)]
    proc = run(cmd, timeout=1800)
    times = []
    for line in (proc.stdout or b"").decode("utf-8", "replace").splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("N/A",):
            continue
        try:
            times.append(round(float(line), 3))
        except ValueError:
            continue
    return sorted(set(times))


# ------------------------------------------------------------ audio silence

_SIL_START = re.compile(rb"silence_start:\s*(-?[0-9.]+)")
_SIL_END = re.compile(rb"silence_end:\s*(-?[0-9.]+)")


def detect_silence(
    media_path: Path,
    *,
    noise_db: float = -30.0,
    min_duration: float = 1.0,
) -> list[tuple[float, float]]:
    """Genuinely silent spans, measured from the audio track.

    Necessary because a gap in the TRANSCRIPT only means nobody is speaking.
    Measured on a real ad: all four transcript gaps had music playing under
    them and ffmpeg found no silence at all. Reporting those as "silence" was
    simply wrong, and a disclaimer under a wrong label does not fix it.

    Returns [] when there is no audio stream, which is the correct answer for
    a screen recording.
    """
    if not probe_file(media_path).get("has_audio"):
        return []
    proc = run([
        ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(media_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-",
    ], timeout=1800)
    err = proc.stderr or b""
    starts = [float(m.group(1)) for m in _SIL_START.finditer(err)]
    ends = [float(m.group(1)) for m in _SIL_END.finditer(err)]
    spans = []
    for i, st in enumerate(starts):
        en = ends[i] if i < len(ends) else None
        if en is not None and en > st:
            spans.append((round(st, 3), round(en, 3)))
    return spans
