#!/usr/bin/env python3
"""Preflight. Reports what is missing and exactly how to install it.

Deliberately does not run installers itself. A skill that silently shells out
to a package manager on first use is a skill that can change the machine in
ways the person did not ask for and cannot see.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cache as cachemod
import transcript as tx
import vendors
from util import which

INSTALL = {
    "Darwin": {
        "ffmpeg": "brew install ffmpeg",
        "ffprobe": "brew install ffmpeg",
        "yt-dlp": "brew install yt-dlp",
        "whisper": "brew install whisper-cpp",
    },
    "Linux": {
        "ffmpeg": "sudo apt install ffmpeg   # or: dnf install ffmpeg",
        "ffprobe": "sudo apt install ffmpeg",
        "yt-dlp": "pipx install yt-dlp   # or: sudo apt install yt-dlp",
        "whisper": "build from source: github.com/ggml-org/whisper.cpp",
    },
    "Windows": {
        "ffmpeg": "winget install Gyan.FFmpeg",
        "ffprobe": "winget install Gyan.FFmpeg",
        "yt-dlp": "winget install yt-dlp.yt-dlp   # or: pip install yt-dlp",
        "whisper": "build from source: github.com/ggml-org/whisper.cpp",
    },
}


def check() -> dict:
    system = platform.system()
    hints = INSTALL.get(system, INSTALL["Linux"])
    rows = []

    for name, required, note in (
        ("ffmpeg", True, "frame extraction, audio, scene detection"),
        ("ffprobe", True, "metadata and keyframe index"),
        ("yt-dlp", False, "URL sources and captions (local files work without it)"),
    ):
        rows.append({
            "name": name, "path": which(name), "required": required,
            "note": note, "install": hints.get(name, ""),
        })

    found = tx.detect_whisper()
    kind = found[0] if found else None
    label = {"cpp": "whisper.cpp", "python": "openai-whisper"}.get(kind, "whisper")
    rows.append({
        "name": label, "path": found[1] if found else None, "required": False,
        "note": ("local transcription, backend identified by probing --help"
                 if found else
                 "local transcription when a video has no captions"),
        "install": hints.get("whisper", ""),
        "backend": kind,
    })

    models = sorted(cachemod.models_dir().glob("ggml-*.bin"))
    active = vendors.resolve()
    return {
        "system": system,
        "rows": rows,
        "models": [m.name for m in models],
        "cache": str(cachemod.cache_root()),
        "vendor": active.name,
        "vendor_note": active.note,
        "vendor_explicit": bool(os.environ.get(vendors.ENV_VENDOR)),
        "compare": vendors.compare(512, 288),
        "ok": all(r["path"] for r in rows if r["required"]),
    }


EXIT_OK = 0
EXIT_MISSING_REQUIRED = 2
EXIT_MISSING_OPTIONAL = 3


def exit_code(r: dict) -> int:
    """0 ready, 2 required tooling missing, 3 only optional missing."""
    if not r["ok"]:
        return EXIT_MISSING_REQUIRED
    if any(not row["path"] for row in r["rows"] if not row["required"]):
        return EXIT_MISSING_OPTIONAL
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """--check is silent and returns only an exit code; --json is structured."""
    args = sys.argv[1:] if argv is None else argv
    r = check()

    if "--json" in args:
        print(json.dumps({
            "system": r["system"], "cache": r["cache"], "ready": r["ok"],
            "token_model": r["vendor"], "token_model_note": r["vendor_note"],
            "token_model_explicit": r["vendor_explicit"],
            "whisper_models": r["models"],
            "tools": [
                {"name": row["name"], "path": row["path"],
                 "required": row["required"], "install": row["install"],
                 "backend": row.get("backend")}
                for row in r["rows"]
            ],
            "exit_code": exit_code(r),
        }, indent=2))
        return exit_code(r)

    if "--check" in args:
        return exit_code(r)

    return _report(r)


def _report(r: dict) -> int:
    print(f"my-vidwatch preflight  ({r['system']})")
    print(f"cache: {r['cache']}")
    print()
    for row in r["rows"]:
        mark = "ok  " if row["path"] else ("MISSING" if row["required"] else "absent ")
        print(f"  [{mark}] {row['name']:12} {row['note']}")
        if row["path"]:
            print(f"            {row['path']}")
        else:
            print(f"            install: {row['install']}")
    print()
    wrow = next((x for x in r["rows"] if x.get("backend")), None)
    if wrow:
        print(f"  transcription backend: {wrow['backend']} at {wrow['path']}")
    print()
    if r["models"]:
        print(f"  whisper models cached: {', '.join(r['models'])}")
    else:
        print(f"  whisper models cached: none "
              f"(the default '{tx.DEFAULT_MODEL}' downloads on first use, "
              f"{tx.MODEL_SIZES.get(tx.DEFAULT_MODEL, '?')})")
    print()
    print(f"  token model: {r['vendor']}  ({r['vendor_note']})")
    if not r["vendor_explicit"]:
        per = ", ".join(f"{n} {t}" for n, t in r["compare"])
        print(f"    a 512x288 frame costs: {per}")
        print(f"    set {vendors.ENV_VENDOR}=anthropic|openai|gemini so "
              "--max-tokens budgets match your host")
    print()
    if not r["ok"]:
        print("Required tooling missing — install the items marked MISSING above.")
        return 1
    print("Ready. Nothing leaves this machine: captions come from the source, "
          "transcription runs locally, no API keys are used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
