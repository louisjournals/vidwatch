"""Transcript acquisition. Captions first, local whisper.cpp second, never an API.

No network egress of audio and no API keys: whisper.cpp runs on the machine.
Model weights are the only download, fetched once into the cache.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import media
from cache import RunCache, models_dir
from util import VidwatchError, fmt_ts, run, warn, which

WHISPER_BINARIES = ("whisper-cli", "whisper-cpp", "whisper", "main")
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"

# Multilingual by default: the English-only builds silently mistranscribe
# anything else, and mixed-language content is common.
# large-v3-turbo, not small. Measured on a real ad: `small` produced ten
# transcription errors a reviewer had to correct off the frames, including the
# product name (X-Revision LD Procedure for XRAY VISION LASER PRO) and several
# place names. turbo is 1.6GB against small's 466MB and close to large in
# accuracy - a one-off download for output that stops being misleading.
DEFAULT_MODEL = "large-v3-turbo"
MODEL_SIZES = {
    "tiny": "75 MB", "base": "142 MB", "small": "466 MB",
    "medium": "1.5 GB", "large-v3": "2.9 GB", "large-v3-turbo": "1.6 GB",
}


# ------------------------------------------------------------------ VTT/SRT

_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


def _to_secs(h: str, m: str, s: str, frac: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(frac.ljust(3, "0")) / 1000.0


def parse_vtt(text: str) -> list[dict]:
    """Parse WebVTT or SRT into segments, collapsing YouTube's rolling repeats.

    Auto-generated YouTube captions restate the previous line in every cue, so
    a naive parse produces roughly double the tokens with no extra information.
    """
    segments: list[dict] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _TIME_RE.search(lines[i])
        if not m:
            i += 1
            continue
        start = _to_secs(*m.groups()[:4])
        end = _to_secs(*m.groups()[4:])
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip() and not _TIME_RE.search(lines[i]):
            body.append(_TAG_RE.sub("", lines[i]).strip())
            i += 1
        content = " ".join(b for b in body if b).strip()
        if content:
            segments.append({"start": round(start, 3), "end": round(end, 3), "text": content})

    # Drop cues whose text is fully contained in the tail of what we already have.
    cleaned: list[dict] = []
    for seg in segments:
        if cleaned:
            prev = cleaned[-1]
            if seg["text"] == prev["text"]:
                prev["end"] = seg["end"]
                continue
            if seg["text"].startswith(prev["text"]) and len(prev["text"]) > 8:
                prev["text"] = seg["text"]
                prev["end"] = seg["end"]
                continue
            if prev["text"].endswith(seg["text"]) and len(seg["text"]) > 8:
                prev["end"] = seg["end"]
                continue
        cleaned.append(seg)
    return cleaned


def fetch_captions(cache: RunCache, lang: str | None = None) -> list[dict] | None:
    """yt-dlp caption fetch, no video download. Returns None when unavailable."""
    if not cache.is_url:
        return None
    sub_dir = cache.path("subs")
    sub_dir.mkdir(exist_ok=True)
    langs = lang or "en.*,en,zh-Hans,zh-Hant,zh,ms"
    try:
        run([
            media.ytdlp_bin(), "--no-warnings", "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", langs, "--sub-format", "vtt/srt/best",
            "-o", str(sub_dir / "cap"), cache.source,
        ], timeout=300, check=False)
    except VidwatchError as exc:
        warn(f"caption fetch failed: {exc}")
        return None

    files = sorted(sub_dir.glob("cap*.vtt")) + sorted(sub_dir.glob("cap*.srt"))
    # Prefer human-authored tracks; yt-dlp does not flag them, but manual
    # tracks are almost always shorter and cleaner than auto ones.
    for f in files:
        segs = parse_vtt(f.read_text(encoding="utf-8", errors="replace"))
        if segs:
            return segs
    return None


# ------------------------------------------------------- embedded subtitles

def embedded_subtitle_streams(path: Path) -> list[dict]:
    """Subtitle streams in a local container: index, codec, language, title."""
    proc = run([
        media.ffprobe_bin(), "-v", "error", "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-print_format", "json", str(path),
    ], check=False, timeout=120)
    if proc.returncode != 0:
        return []
    try:
        data = json.loads((proc.stdout or b"{}").decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return []
    out = []
    for i, st in enumerate(data.get("streams", [])):
        tags = st.get("tags") or {}
        out.append({
            "order": i,                      # position among subtitle streams
            "index": st.get("index"),        # absolute stream index
            "codec": st.get("codec_name", "?"),
            "language": (tags.get("language") or "").lower(),
            "title": tags.get("title", ""),
        })
    return out


def pick_subtitle_stream(streams: list[dict], language: str = "auto") -> dict | None:
    """Prefer a track matching the requested language, else the first."""
    if not streams:
        return None
    # Bitmap subtitles carry no text; extracting them yields nothing useful.
    textual = [s for s in streams
               if s["codec"] not in ("dvd_subtitle", "hdmv_pgs_subtitle", "dvb_subtitle")]
    if not textual:
        return None
    lang = (language or "auto").lower()
    if lang not in ("", "auto"):
        for s in textual:
            if s["language"].startswith(lang[:2]):
                return s
    return textual[0]


def extract_embedded(path: Path, order: int, dest: Path) -> list[dict] | None:
    """Pull one subtitle track out to SRT and parse it.

    `-map 0:s:<order>` indexes among subtitle streams, which is what
    ffprobe's ordering gives us.
    """
    proc = run([
        media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(path), "-map", f"0:s:{order}", "-c:s", "srt", str(dest),
    ], check=False, timeout=600)
    if proc.returncode != 0 or not dest.exists() or dest.stat().st_size < 8:
        return None
    segs = parse_vtt(dest.read_text(encoding="utf-8", errors="replace"))
    return segs or None


# ---------------------------------------------------------------- whisper.cpp

def _identify_whisper(path: str) -> str | None:
    """Probe --help and return 'cpp', 'python', or None.

    Filename is not evidence. On macOS `brew install openai-whisper` puts a
    Python CLI at /opt/homebrew/bin/whisper — same name whisper.cpp sometimes
    uses. Accepting it by name made preflight report ready and then fail at
    runtime with "invalid choice" when whisper.cpp flags were passed to it.
    """
    proc = run([path, "--help"], check=False, timeout=60)
    blob = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace").lower()
    if not blob:
        return None
    # openai-whisper is argparse-generated: snake_case options.
    if "--output_format" in blob or "--model_dir" in blob or "--word_timestamps" in blob:
        return "python"
    # whisper.cpp: kebab-case, and its own distinctive flags.
    if "--output-json" in blob or "-oj," in blob or "whisper.cpp" in blob:
        return "cpp"
    if "-m fname" in blob or "--model fname" in blob:
        return "cpp"
    return None


def detect_whisper() -> tuple[str, str] | None:
    """First positively-identified local backend as (kind, path)."""
    for name in WHISPER_BINARIES:
        path = which(name)
        if not path:
            continue
        kind = _identify_whisper(path)
        if kind:
            return kind, path
    return None


def whisper_bin() -> str | None:
    """Back-compat: path only, or None."""
    found = detect_whisper()
    return found[1] if found else None


def ensure_model(name: str) -> Path:
    """Download ggml weights into the cache on first use."""
    dest = models_dir() / f"ggml-{name}.bin"
    if dest.exists() and dest.stat().st_size > 1024 * 1024:
        return dest
    url = MODEL_URL.format(model=name)
    size = MODEL_SIZES.get(name, "unknown size")
    print(f"[my-vidwatch] downloading whisper model {name} ({size}) -> {dest}")
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as out:
            while chunk := resp.read(1024 * 512):
                out.write(chunk)
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise VidwatchError(
            f"could not download whisper model {name}: {exc}\n"
            f"fetch it manually to {dest} from {url}"
        )
    tmp.replace(dest)
    return dest


def run_whisper_python(
    wav: Path, *, binary: str, model: str, language: str = "auto"
) -> list[dict]:
    """openai-whisper CLI. Local, no keys; downloads its own weights."""
    out_dir = wav.parent
    cmd = [binary, str(wav), "--model", model, "--output_format", "json",
           "--output_dir", str(out_dir), "--verbose", "False"]
    # openai-whisper auto-detects when --language is omitted; "auto" is invalid.
    if language and language.lower() not in ("auto", ""):
        cmd += ["--language", language]
    run(cmd, timeout=14400)
    js = out_dir / (wav.stem + ".json")
    if not js.exists():
        raise VidwatchError("openai-whisper produced no JSON output")
    data = json.loads(js.read_text(encoding="utf-8", errors="replace"))
    segments = []
    for item in data.get("segments", []):
        text = (item.get("text") or "").strip()
        if text:
            segments.append({
                "start": round(float(item.get("start", 0.0)), 3),
                "end": round(float(item.get("end", 0.0)), 3),
                "text": text,
            })
    return segments


def run_whisper(
    wav: Path,
    *,
    model: str = DEFAULT_MODEL,
    language: str = "auto",
    threads: int = 0,
) -> tuple[list[dict], str]:
    """Transcribe locally. Returns (segments, backend_label)."""
    found = detect_whisper()
    if not found:
        raise VidwatchError(
            "no local whisper backend found.\n"
            "  whisper.cpp:     brew install whisper-cpp\n"
            "  openai-whisper:  brew install openai-whisper\n"
            "Either works; both run locally with no API key.\n"
            "Or pass --no-whisper to run frames-only."
        )
    kind, binary = found
    if kind == "python":
        return run_whisper_python(
            wav, binary=binary, model=model, language=language
        ), f"openai-whisper:{model}"

    weights = ensure_model(model)
    out_prefix = wav.with_suffix("")
    cmd = [
        binary, "-m", str(weights), "-f", str(wav),
        "-l", language, "--output-json", "--no-prints",
        "-of", str(out_prefix),
    ]
    if threads:
        cmd += ["-t", str(threads)]
    run(cmd, timeout=14400)

    js = Path(str(out_prefix) + ".json")
    if not js.exists():
        raise VidwatchError("whisper.cpp produced no JSON output")
    data = json.loads(js.read_text(encoding="utf-8", errors="replace"))
    segments = []
    for item in data.get("transcription", []):
        offsets = item.get("offsets") or {}
        text = (item.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "start": round(offsets.get("from", 0) / 1000.0, 3),
            "end": round(offsets.get("to", 0) / 1000.0, 3),
            "text": text,
        })
    return segments, f"whisper.cpp:{model}"


# --------------------------------------------------------------- orchestration

def _params(use_whisper: bool, model: str, language: str, lang_pref: str | None) -> dict:
    """Everything that can change what a transcript acquisition returns."""
    return {
        "whisper": bool(use_whisper),
        "model": model,
        "language": language,
        "sub_langs": lang_pref,
    }


def _reusable(cached: dict | None, want: dict) -> bool:
    """Whether a cached transcript may be returned for these parameters.

    Two rules, both learned the hard way:

    1. An EMPTY result is never reusable. A single `--no-whisper` probe used to
       write {"source": "none", "segments": []}, and because the old check only
       asked whether `segments is not None`, that empty answer was returned
       forever after — permanently suppressing transcription for that video. An
       empty transcript is a cache miss, not a finding.
    2. A non-empty result is only reusable when the parameters that produced it
       still apply. Captions and embedded tracks do not depend on the whisper
       model or language flags, but they do depend on the requested subtitle
       language, so only that field is compared for them.
    """
    if not cached or not cached.get("segments"):
        return False
    had = cached.get("params")
    if had == want:
        return True
    if cached.get("source") in ("captions", "embedded"):
        return bool(had) and had.get("sub_langs") == want["sub_langs"]
    return False


def build_transcript(
    cache: RunCache,
    *,
    use_whisper: bool = True,
    model: str = DEFAULT_MODEL,
    language: str = "auto",
    lang_pref: str | None = None,
) -> dict:
    """Return {"source": ..., "segments": [...]}, cached after the first build."""
    want = _params(use_whisper, model, language, lang_pref)
    cached = cache.read_json("transcript.json")
    if _reusable(cached, want):
        return cached

    segs = fetch_captions(cache, lang_pref)
    if segs:
        payload = {"source": "captions", "segments": segs, "params": want}
        cache.write_json("transcript.json", payload)
        return payload

    # Local containers often carry a subtitle track already. Transcribing audio
    # to reproduce text that is sitting in the file is a model download and
    # minutes of compute to get a worse result than `-map 0:s:0` in one second.
    local = cache.local_media()
    if local is not None and local.exists():
        streams = embedded_subtitle_streams(local)
        chosen = pick_subtitle_stream(streams, language)
        if chosen is not None:
            segs = extract_embedded(local, chosen["order"], cache.path("embedded.srt"))
            if segs:
                payload = {
                    "params": want,
                    "source": "embedded",
                    "language": chosen["language"] or "unknown",
                    "codec": chosen["codec"],
                    "segments": segs,
                }
                cache.write_json("transcript.json", payload)
                return payload

    if not use_whisper:
        # Deliberately NOT cached: an empty result must stay retryable, or a
        # single --no-whisper run poisons the video forever.
        return {"source": "none", "segments": [], "params": want}

    src = cache.local_media()
    if src is not None and src.exists():
        # Screen recordings are routinely captured without audio. Asking ffmpeg
        # for a WAV from a video-only file fails with the opaque "Output file
        # does not contain any stream", which surfaced as a crash rather than
        # "this clip has no speech".
        if not media.probe_file(src).get("has_audio"):
            return {
                "source": "no audio track", "segments": [], "params": want,
            }
    else:
        src = media.download_audio(cache)
    wav = media.extract_wav(src, cache.path("audio.wav"))
    segs, backend = run_whisper(wav, model=model, language=language)
    payload = {"source": backend, "segments": segs, "params": want}
    cache.write_json("transcript.json", payload)
    return payload


def render(segments: list[dict], start: float = 0.0, end: float | None = None) -> str:
    """Timestamped plain text, optionally clipped to a window."""
    out = []
    for s in segments:
        if end is not None and s["start"] > end:
            continue
        if s["end"] < start:
            continue
        out.append(f"[{fmt_ts(s['start'])}] {s['text']}")
    return "\n".join(out)


def word_count(segments: list[dict]) -> int:
    return sum(len(s["text"].split()) for s in segments)
