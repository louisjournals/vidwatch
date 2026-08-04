"""Shared helpers. Pure stdlib."""
from __future__ import annotations

import shutil
import subprocess
import sys

import vendors


class VidwatchError(RuntimeError):
    """User-facing failure. Printed without a traceback."""


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def which(*names: str) -> str | None:
    """First binary on PATH from an ordered candidate list."""
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def run(
    cmd: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    timeout: int | None = None,
    stdin_bytes: bytes | None = None,
) -> subprocess.CompletedProcess:
    """Run a command. Raises VidwatchError with stderr tail on failure."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=capture,
            input=stdin_bytes,
            timeout=timeout,
            check=False,  # handled below so the error carries an stderr tail
        )
    except FileNotFoundError:
        raise VidwatchError(f"{cmd[0]} not found on PATH")
    except subprocess.TimeoutExpired:
        raise VidwatchError(f"{cmd[0]} timed out after {timeout}s")
    if check and proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        detail = "\n".join(tail[-6:]) if tail else "(no stderr)"
        raise VidwatchError(f"{cmd[0]} failed (exit {proc.returncode}):\n{detail}")
    return proc


# ---------------------------------------------------------------- timestamps

def parse_ts(value: str | float | None) -> float | None:
    """Accept SS, MM:SS, HH:MM:SS, with optional .fraction. Returns seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    neg = text.startswith("-")
    if neg:
        text = text[1:]
    parts = text.split(":")
    if len(parts) > 3:
        raise VidwatchError(f"bad timestamp: {value!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise VidwatchError(f"bad timestamp: {value!r}")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return -total if neg else total


def fmt_ts(seconds: float, *, ms: bool = False) -> str:
    """Seconds -> MM:SS or HH:MM:SS (with .mmm when ms=True)."""
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    frac = seconds - whole
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    base = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if ms:
        base += f".{round(frac * 1000):03d}"
    return base


def fmt_dur(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return fmt_ts(seconds)


# ------------------------------------------------------------------- tokens

def image_tokens(
    width: int, height: int, model: vendors.TokenModel | None = None
) -> int:
    """Estimated image tokens for one frame under the selected vendor model."""
    return (model or vendors.resolve()).tokens(width, height)


def frames_for_budget(
    budget: int,
    width: int,
    height: int,
    model: vendors.TokenModel | None = None,
) -> int:
    """How many frames of this size fit inside a token budget."""
    return (model or vendors.resolve()).frames_for_budget(budget, width, height)


def even_sample(items: list, cap: int) -> list:
    """Evenly thin a list to `cap`, always keeping the first and last item."""
    n = len(items)
    if cap >= n or n == 0:
        return list(items)
    if cap == 1:
        return [items[0]]
    step = (n - 1) / (cap - 1)
    idx = sorted({min(n - 1, round(i * step)) for i in range(cap)})
    return [items[i] for i in idx]
