"""Content-addressed run cache.

The whole point of the three-stage loop is that `probe`, `scan` and `read` get
called several times against the same video. Without a cache each call would
re-download and re-detect scene cuts, which is the single biggest waste in a
naive frame-extraction pipeline. Everything expensive lands here once:

    ~/.cache/my-vidwatch/<key>/
        meta.json        source, duration, dimensions, fps
        source.<ext>     downloaded media (URL sources only)
        audio.wav        16 kHz mono, only if whisper had to run
        transcript.json  segments + provenance
        cuts.json        scene-cut timestamps for the whole video
        frames/          extracted JPEGs, named f<idx>_t<ms>.jpg
        sheets/          contact sheets
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from util import VidwatchError

ENV_ROOT = "VIDWATCH_CACHE"
DEFAULT_MAX_BYTES = 20 * 1024**3  # 20 GB, LRU-trimmed


def cache_root() -> Path:
    root = os.environ.get(ENV_ROOT)
    if root:
        return Path(root).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base).expanduser() / "my-vidwatch"


def models_dir() -> Path:
    d = cache_root() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "www."))


def _key_for(source: str) -> str:
    """Stable key. URLs hash the string; local files hash path+size+mtime.

    Hashing file *contents* would be correct but reads gigabytes to answer a
    question the stat fields already answer.
    """
    if is_url(source):
        payload = f"url:{source.strip()}"
    else:
        p = Path(source).expanduser().resolve()
        if not p.exists():
            raise VidwatchError(f"no such file: {source}")
        st = p.stat()
        payload = f"file:{p}:{st.st_size}:{st.st_mtime_ns}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class RunCache:
    def __init__(self, source: str):
        self.source = source
        self.is_url = is_url(source)
        self.key = _key_for(source)
        self.dir = cache_root() / self.key
        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        (self.dir / "sheets").mkdir(parents=True, exist_ok=True)
        self.touch()

    # ------------------------------------------------------------- plumbing
    def touch(self) -> None:
        (self.dir / ".used").write_text(str(int(time.time())))

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def read_json(self, name: str):
        p = self.dir / name
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return None

    def write_json(self, name: str, data) -> None:
        tmp = self.dir / (name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(self.dir / name)

    # ------------------------------------------------------------ media file
    def local_media(self) -> Path | None:
        """The playable file on disk, or None if a URL hasn't been fetched."""
        if not self.is_url:
            return Path(self.source).expanduser().resolve()
        hits = sorted(self.dir.glob("source.*"))
        return hits[0] if hits else None

    def size_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.dir.rglob("*") if f.is_file())


# ------------------------------------------------------------------ maintenance

def list_entries() -> list[dict]:
    root = cache_root()
    if not root.exists():
        return []
    out = []
    for d in root.iterdir():
        if not d.is_dir() or d.name == "models":
            continue
        meta = {}
        mp = d / "meta.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text())
            except json.JSONDecodeError:
                pass
        used = 0
        up = d / ".used"
        if up.exists():
            try:
                used = int(up.read_text().strip())
            except ValueError:
                pass
        out.append({
            "key": d.name,
            "source": meta.get("source", "?"),
            "duration": meta.get("duration"),
            "bytes": sum(f.stat().st_size for f in d.rglob("*") if f.is_file()),
            "last_used": used,
        })
    return sorted(out, key=lambda e: e["last_used"], reverse=True)


def purge(key: str | None = None) -> int:
    """Delete one entry, or every entry when key is None/'all'. Returns count."""
    root = cache_root()
    if not root.exists():
        return 0
    if key and key != "all":
        target = root / key
        if not target.is_dir():
            raise VidwatchError(f"no cache entry {key!r}")
        shutil.rmtree(target)
        return 1
    n = 0
    for d in root.iterdir():
        if d.is_dir() and d.name != "models":
            shutil.rmtree(d)
            n += 1
    return n


def trim(max_bytes: int = DEFAULT_MAX_BYTES) -> int:
    """Drop least-recently-used entries until under budget. Returns count."""
    entries = list_entries()
    total = sum(e["bytes"] for e in entries)
    removed = 0
    for e in reversed(entries):  # oldest first
        if total <= max_bytes:
            break
        shutil.rmtree(cache_root() / e["key"], ignore_errors=True)
        total -= e["bytes"]
        removed += 1
    return removed
