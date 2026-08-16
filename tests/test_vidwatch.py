"""Tests. No network: clips are synthesised with ffmpeg.

The dedup tests are the important ones. They encode the specific regression
this tool exists to avoid: a change confined to a small region of the frame
must survive deduplication, because that is usually the change you cared about.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path
from pathlib import Path as pathlib_Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dedup
import defects
import frames as framesmod
import media
import transcript as tx
import teardown as td
import util
import vendors

FONT = framesmod.find_font()
pytestmark = pytest.mark.skipif(
    not util.which("ffmpeg"), reason="ffmpeg required"
)


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="session")
def workdir(tmp_path_factory):
    return tmp_path_factory.mktemp("my-vidwatch")


@pytest.fixture(scope="session")
def slides_clip(workdir):
    """15s clip with four visually distinct states:

    0-5s    dark slide, heading only
    5-10s   same slide plus a small caption line     (small-region change)
    10-12s  same, two digits of the caption differ   (tiny-region change)
    12-15s  hard cut to a differently coloured slide (obvious change)
    """
    out = workdir / "slides.mp4"
    if out.exists():
        return out
    if not FONT:
        pytest.skip("no font available for drawtext")
    vf = (
        f"drawtext=fontfile={FONT}:text='QUARTERLY REVIEW':x=(w-tw)/2:y=200:"
        "fontsize=64:fontcolor=white,"
        f"drawtext=fontfile={FONT}:text='revenue 41.2':x=60:y=640:fontsize=28:"
        "fontcolor=0x9fd0ff:enable='between(t,5,10)',"
        f"drawtext=fontfile={FONT}:text='revenue 47.9':x=60:y=640:fontsize=28:"
        "fontcolor=0x9fd0ff:enable='gt(t,10)',"
        "drawbox=x=0:y=0:w=1280:h=720:color=0x7a1020:t=fill:enable='gt(t,12)',"
        f"drawtext=fontfile={FONT}:text='APPENDIX':x=(w-tw)/2:y=300:fontsize=72:"
        "fontcolor=white:enable='gt(t,12)'"
    )
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x102840:s=1280x720:d=15:r=10",
        "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "25", str(out),
    ], check=True)
    return out


@pytest.fixture(scope="session")
def vertical_clip(workdir):
    """1080x1920 portrait, 20s, burned-in caption that changes at 4s and 10s."""
    out = workdir / "vertical.mp4"
    if out.exists():
        return out
    if not FONT:
        pytest.skip("no font available for drawtext")
    vf = (
        f"drawtext=fontfile={FONT}:text='HEADING':x=(w-tw)/2:y=500:fontsize=90:"
        "fontcolor=white,"
        f"drawtext=fontfile={FONT}:text='size M in stock':x=80:y=1650:fontsize=44:"
        "fontcolor=0xffd9a0:enable='between(t,4,10)',"
        f"drawtext=fontfile={FONT}:text='size L in stock':x=80:y=1650:fontsize=44:"
        "fontcolor=0xffd9a0:enable='gt(t,10)'"
    )
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x141c2b:s=1080x1920:d=20:r=12",
        "-vf", vf, "-c:v", "libx264", "-crf", "26", "-pix_fmt", "yuv420p", str(out),
    ], check=True)
    return out


@pytest.fixture(scope="session")
def noisy_clip(workdir):
    """Held frame under heavy grain, with one small caption appearing at 8s."""
    out = workdir / "noisy.mp4"
    if out.exists():
        return out
    if not FONT:
        pytest.skip("no font available for drawtext")
    vf = (
        f"drawtext=fontfile={FONT}:text='NOISY SOURCE':x=(w-tw)/2:y=180:"
        "fontsize=60:fontcolor=white,"
        f"drawtext=fontfile={FONT}:text='total 1284':x=70:y=630:fontsize=26:"
        "fontcolor=0xffe0a0:enable='gt(t,8)',"
        "noise=alls=22:allf=t+u"
    )
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x203040:s=1280x720:d=12:r=10",
        "-vf", vf, "-c:v", "libx264", "-crf", "30", "-pix_fmt", "yuv420p", str(out),
    ], check=True)
    return out




@pytest.fixture(scope="session")
def silent_clip(workdir):
    """Video with no audio stream at all — how screen recordings usually are."""
    out = workdir / "silent.mp4"
    if out.exists():
        return out
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x203040:s=640x480:d=8:r=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ], check=True)
    return out


@pytest.fixture(scope="session")
def slides_deck(workdir):
    """Four visually distinct slides. Scene detection scores ZERO cuts here."""
    out = workdir / "deck.mp4"
    if out.exists():
        return out
    if not FONT:
        pytest.skip("no font available for drawtext")
    parts = []
    for i, (label, colour, lo) in enumerate(
            [("ONE", "white", 0), ("TWO", "0xffd9a0", 10),
             ("THREE", "0x9fd0ff", 20), ("FOUR", "0xffa0a0", 30)]):
        cond = f"gt(t,{lo})" if i == 3 else f"between(t,{lo},{lo + 10})"
        parts.append(
            f"drawtext=fontfile={FONT}:text='SLIDE {label}':x=(w-tw)/2:y=200:"
            f"fontsize=54:fontcolor={colour}:enable='{cond}'")
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x0d1b2a:s=854x480:d=40:r=10",
        "-vf", ",".join(parts), "-c:v", "libx264", "-crf", "24",
        "-pix_fmt", "yuv420p", str(out),
    ], check=True)
    return out

def grab(clip: Path, ts: float, out_dir: Path, width: int = 512) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"t{int(ts * 1000):08d}.jpg"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(ts), "-i", str(clip), "-frames:v", "1",
        "-vf", f"scale={width}:-2", "-q:v", "3", str(dest),
    ], check=True)
    return dest


# --------------------------------------------------------------- unit: util

def test_parse_ts_forms():
    assert util.parse_ts("45") == 45
    assert util.parse_ts("1:30") == 90
    assert util.parse_ts("1:02:03") == 3723
    assert util.parse_ts("0:01.5") == 1.5
    assert util.parse_ts(None) is None


def test_parse_ts_rejects_junk():
    with pytest.raises(util.VidwatchError):
        util.parse_ts("banana")
    with pytest.raises(util.VidwatchError):
        util.parse_ts("1:2:3:4")


def test_fmt_ts_roundtrip():
    assert util.fmt_ts(90) == "01:30"
    assert util.fmt_ts(3723) == "1:02:03"
    assert util.fmt_ts(1.5, ms=True) == "00:01.500"


def test_image_tokens_follow_the_selected_vendor():
    anthropic = vendors.resolve("anthropic")
    # B8 replaced the area/750 approximation with Anthropic's documented 28x28
    # patch rule, so the expected value moves from 197 to 209.
    assert util.image_tokens(512, 288, anthropic) == 209
    per = util.image_tokens(512, 288, anthropic)
    assert util.frames_for_budget(20_000, 512, 288, anthropic) == 20_000 // per
    assert util.image_tokens(512, 288, vendors.resolve("openai:5")) == 144


def test_vendor_models_disagree():
    """The whole reason the model is pluggable: they are not interchangeable."""
    costs = dict(vendors.compare(1024, 576))
    assert len(set(costs.values())) >= 3, costs
    assert costs["gemini"] < costs["anthropic"], costs
    assert costs["openai:4o"] != costs["openai:5"], costs


def test_openai_tile_model_shape():
    m = vendors.resolve("openai:4o")
    # 1024x576 -> no downscale, 2x2 tiles -> 85 + 4*170
    assert m.tokens(1024, 576) == 85 + 4 * 170
    # oversized input is fitted before tiling, so cost stops growing
    assert m.tokens(4096, 2304) <= m.tokens(2048, 1152) * 2


def test_gemini_small_image_is_flat():
    m = vendors.resolve("gemini")
    assert m.tokens(300, 200) == 258
    assert m.tokens(384, 384) == 258
    assert m.tokens(800, 400) == 2 * 258


def test_generic_never_underestimates():
    g = vendors.resolve("generic")
    for w, h in ((320, 180), (512, 288), (1024, 576), (1536, 864)):
        assert g.tokens(w, h) == max(t for _, t in vendors.compare(w, h))


def test_vendor_aliases_and_bad_name():
    assert vendors.resolve("claude").name == "anthropic"
    assert vendors.resolve("gpt").name == "openai:4o"
    assert vendors.resolve(None).name == "generic"
    with pytest.raises(ValueError):
        vendors.resolve("nonesuch")


def test_vendor_env_var(monkeypatch):
    monkeypatch.setenv(vendors.ENV_VENDOR, "gemini")
    assert vendors.resolve().name == "gemini"


def test_even_sample_keeps_ends():
    items = list(range(100))
    got = util.even_sample(items, 10)
    assert got[0] == 0 and got[-1] == 99
    assert len(got) <= 10
    assert util.even_sample(items, 500) == items


# ------------------------------------------------- unit: dedup (the point)

def test_dedup_drops_a_held_frame(slides_clip, workdir):
    d = workdir / "held"
    paths = [grab(slides_clip, t, d) for t in (1.0, 2.0, 3.0, 4.0)]
    kept, stats = dedup.dedup(paths)
    # First and last are always kept; the two identical middles must go.
    assert stats["dropped"] == 2
    assert len(kept) == 2


def test_dedup_keeps_small_region_change(slides_clip, workdir):
    """A caption appearing in ~2% of the frame must survive."""
    d = workdir / "small"
    paths = [grab(slides_clip, t, d) for t in (4.0, 5.0, 6.0)]
    thumbs = dedup.thumbnails(paths)
    tile_max, whole_frame = dedup.score(thumbs[2], thumbs[0])
    assert tile_max > dedup.DEFAULT_THRESHOLD, (
        f"caption change scored {tile_max}, under threshold"
    )
    # The regression guard: a whole-frame average cannot see this at all.
    assert whole_frame < 2.0, (
        "whole-frame delta unexpectedly large; this test no longer proves "
        "that tile-wise scoring is what saves the frame"
    )


def test_dedup_keeps_two_digit_change(slides_clip, workdir):
    """The hardest real case: two glyphs change inside a 26px caption."""
    d = workdir / "digits"
    paths = [grab(slides_clip, t, d) for t in (6.0, 11.0)]
    thumbs = dedup.thumbnails(paths)
    tile_max, whole_frame = dedup.score(thumbs[1], thumbs[0])
    assert tile_max > dedup.DEFAULT_THRESHOLD
    assert whole_frame < 1.0


def test_dedup_survives_grain(noisy_clip, workdir):
    """Grain must not read as change, and a real change must still register."""
    d = workdir / "grain"
    same = [grab(noisy_clip, t, d) for t in (2.0, 5.0)]
    thumbs = dedup.thumbnails(same)
    noise_floor, _ = dedup.score(thumbs[1], thumbs[0])
    assert noise_floor < dedup.DEFAULT_THRESHOLD, (
        f"grain scored {noise_floor}; threshold is too tight"
    )

    changed = [grab(noisy_clip, t, d) for t in (5.0, 10.0)]
    thumbs = dedup.thumbnails(changed)
    signal, _ = dedup.score(thumbs[1], thumbs[0])
    assert signal > dedup.DEFAULT_THRESHOLD
    assert signal > noise_floor * 2, "insufficient margin over the noise floor"


def test_dedup_honours_protect(slides_clip, workdir):
    d = workdir / "protect"
    paths = [grab(slides_clip, t, d) for t in (1.0, 2.0, 3.0, 4.0)]
    kept, stats = dedup.dedup(paths, protect={1})
    assert paths[1] in kept
    assert stats["dropped"] == 1


def test_dedup_short_input_is_passthrough(slides_clip, workdir):
    d = workdir / "short"
    paths = [grab(slides_clip, 1.0, d)]
    kept, stats = dedup.dedup(paths)
    assert kept == paths and stats["dropped"] == 0


# --------------------------------------------------------- unit: scene cuts

def test_detect_cuts_finds_low_contrast_cut(slides_clip):
    cuts = media.detect_cuts(slides_clip)
    assert cuts, "the cut at ~12s was not detected"
    assert any(11.5 <= c <= 12.6 for c in cuts)


def test_detect_cuts_timestamps_are_absolute(slides_clip):
    """Windowed detection must not report seek-relative times."""
    cuts = media.detect_cuts(slides_clip, start=10.0, end=15.0)
    assert cuts and all(c >= 10.0 for c in cuts)


def test_detect_cuts_quiet_on_grain(noisy_clip):
    assert media.detect_cuts(noisy_clip) == []


def test_cut_density_shape(slides_clip):
    d = media.estimate_cut_density(slides_clip, 15.0)
    assert d["exact"] is True
    assert d["cuts_per_min"] > 0


# ----------------------------------------------------------- unit: frames

def test_uniform_times_spans_window():
    ts = framesmod.uniform_times(10.0, 20.0, 5)
    assert ts[0] == 10.0 and ts[-1] == 20.0 and len(ts) == 5


def test_extract_returns_time_ordered(slides_clip, workdir):
    got = framesmod.extract(
        slides_clip, [6.0, 1.0, 13.0], workdir / "order", width=320
    )
    assert [t for t, _ in got] == [1.0, 6.0, 13.0]
    assert all(p.exists() for _, p in got)


def test_build_sheet_tiles(slides_clip, workdir):
    d = workdir / "sheet"
    got = framesmod.extract(slides_clip, [1.0, 6.0, 13.0, 14.0], d, width=256)
    dest = d / "sheet.jpg"
    framesmod.build_sheet([p for _, p in got], dest, cols=2, rows=2, tile_width=256)
    w, h = framesmod.frame_dims(dest)
    assert w > 256 and h > 100


# -------------------------------------------------------- unit: transcript

def test_vtt_parse_basic():
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\nfirst line\n\n"
        "00:00:03.000 --> 00:00:05.000\nsecond line\n"
    )
    segs = tx.parse_vtt(vtt)
    assert [s["text"] for s in segs] == ["first line", "second line"]
    assert segs[0]["start"] == 1.0


def test_vtt_collapses_rolling_repeats():
    """YouTube auto-captions restate the previous cue; that must not double up."""
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\nthe quick brown\n\n"
        "00:00:03.000 --> 00:00:05.000\nthe quick brown fox jumps\n\n"
        "00:00:05.000 --> 00:00:07.000\nsomething different\n"
    )
    segs = tx.parse_vtt(vtt)
    assert len(segs) == 2
    assert segs[0]["text"] == "the quick brown fox jumps"


def test_vtt_strips_inline_tags():
    vtt = (
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
        "<c.colorE5E5E5>hello</c> <00:00:01.500>world\n"
    )
    segs = tx.parse_vtt(vtt)
    assert "hello" in segs[0]["text"] and "<c" not in segs[0]["text"]


def test_srt_comma_timestamps():
    srt = "1\n00:00:02,500 --> 00:00:04,000\nsubtitle body\n"
    segs = tx.parse_vtt(srt)
    assert segs[0]["start"] == 2.5


def test_render_clips_to_window():
    segs = [
        {"start": 1.0, "end": 2.0, "text": "a"},
        {"start": 50.0, "end": 51.0, "text": "b"},
    ]
    assert "a" in tx.render(segs, 0, 10) and "b" not in tx.render(segs, 0, 10)


# ----------------------------------------------- long edge cap (portrait bug)

def test_fit_to_edge_leaves_small_images_alone():
    assert vendors.fit_to_edge(512, 288, 1568) == (512, 288)


def test_fit_to_edge_caps_height_on_portrait():
    """The regression: capping width alone leaves portrait height unbounded."""
    w, h = vendors.fit_to_edge(1536, 2731, 1568)
    assert max(w, h) <= 1568
    assert w % 2 == 0 and h % 2 == 0
    assert abs((w / h) - (1536 / 2731)) < 0.01, "aspect ratio not preserved"


def test_fit_to_edge_caps_width_on_landscape():
    w, h = vendors.fit_to_edge(3840, 2160, 1568)
    assert max(w, h) <= 1568
    assert w > h


def test_every_model_exposes_max_edge_not_max_width():
    for name in ("anthropic", "openai", "gemini", "generic"):
        m = vendors.resolve(name)
        assert isinstance(m.max_edge, int) and m.max_edge > 0
        assert not hasattr(m, "max_width"), f"{name} still has the buggy attribute"


def test_explicit_portrait_width_is_not_provider_capped(vertical_clip, workdir):
    """Explicit --width is a caller instruction even when portrait height exceeds a provider edge."""
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "quick", str(vertical_clip),
        "--no-whisper", "--width", "1536", "--vendor", "anthropic", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    w, h = data["frame_size"]
    assert w == 1536
    assert h > vendors.resolve("anthropic").max_edge
    assert data["resolution_mode"] == "explicit"


# --------------------------------------------------------------- quick path

def test_quick_covers_a_short_clip_in_one_pass(vertical_clip, workdir):
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "quick", str(vertical_clip),
        "--no-whisper", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    times = [f["t"] for f in data["frames"]]
    # caption absent, "size M", then "size L" -> at least three distinct states
    assert len(times) >= 3, f"quick collapsed too far: {times}"
    assert any(t < 4.0 for t in times)
    assert any(4.0 <= t < 10.5 for t in times)
    assert any(t >= 10.0 for t in times)


def test_quick_refuses_a_long_clip(workdir):
    long_clip = workdir / "long_quick.mp4"
    if not long_clip.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:d=240:r=5",
            "-c:v", "libx264", "-crf", "35", "-pix_fmt", "yuv420p", str(long_clip),
        ], check=True)
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "quick", str(long_clip),
        "--no-whisper",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 1
    assert "quick limit" in rc.stderr
    assert "probe" in rc.stderr, "should redirect to the staged path"


# ------------------------------------------ B8: per-model token rules

def test_anthropic_uses_28px_patches():
    m = vendors.resolve("anthropic")
    assert m.tokens(512, 288) == 209
    assert m.tokens(1024, 576) == 777


def test_openai_runs_two_tokenizers():
    """The reason one model per vendor cannot work."""
    tile = vendors.resolve("openai:4o")
    patch = vendors.resolve("openai:5")
    assert tile.tokens(1024, 576) == 765
    assert patch.tokens(1024, 576) == 576
    assert tile.tokens(1024, 576) != patch.tokens(1024, 576)


def test_gpt5_is_flagged_uncapped():
    """At original/auto detail there is no provider-side size limit, so the
    long-edge cap is a real saving rather than a no-op."""
    assert vendors.resolve("openai:5").uncapped is True
    assert vendors.resolve("openai:5-high").uncapped is False
    assert vendors.resolve("anthropic").uncapped is False


def test_gpt5_high_detail_is_budget_capped():
    m = vendors.resolve("openai:5-high")
    assert m.tokens(8000, 8000) == m.BUDGET


def test_gemini_flat_rate_only_under_384():
    m = vendors.resolve("gemini")
    assert m.tokens(384, 384) == 258
    assert m.tokens(800, 400) == 2 * 258


def test_qwen_models_use_provisional_32_grid_without_active_floor():
    image = vendors.resolve("qwen")
    video = vendors.resolve("qwen:video")
    # Qwen3-VL processor: patch_size 16 x merge_size 2 => /32 merged grid.
    assert vendors._qwen_spatial_tokens(512, 288) == 144
    assert image.tokens(512, 288) == 144
    assert video.tokens(512, 288) == 72
    assert image.tokens(1024, 576) == 576
    assert video.tokens(1024, 576) == 288
    assert vendors.resolve("qwen3-vl").tokens(512, 288) == 144


def test_qwen_rounds_to_nearest_32_before_counting():
    assert vendors._round_to_factor(512, 32) == 512
    assert vendors._round_to_factor(288, 32) == 288
    assert vendors._round_to_factor(1000, 32) == 992


def test_qwen_video_is_opt_in_and_cheaper_than_image_path():
    assert vendors.resolve("qwen").name == "qwen"
    assert vendors.resolve("qwen:video").name == "qwen:video"
    assert vendors.resolve("qwen:video").tokens(512, 288) < vendors.resolve("qwen").tokens(512, 288)


def test_anthropic_hires_tier_has_a_larger_edge():
    assert vendors.resolve("anthropic:hires").max_edge == 2576
    assert vendors.resolve("anthropic").max_edge == 1568


def test_generic_upper_bounds_every_model():
    g = vendors.resolve("generic")
    for w, h in ((320, 180), (512, 288), (1024, 576), (1536, 864),
                 (880, 1568), (1536, 2731)):
        for name in vendors.CHOICES:
            if name == "generic":
                continue
            assert g.tokens(w, h) >= vendors.resolve(name).tokens(w, h), (
                f"generic under-bounds {name} at {w}x{h}")


def test_generic_uses_the_tightest_cap():
    g = vendors.resolve("generic")
    caps = [vendors.resolve(n).max_edge for n in vendors.CHOICES if n != "generic"]
    assert g.max_edge == min(c for c in caps if c is not None)


def test_frames_are_content_addressed():
    """B10: same moment + same size = same filename, so reads reuse."""
    a = framesmod.frame_name(1.5, 512, label=False)
    assert a == framesmod.frame_name(1.5, 512, label=False)
    assert a != framesmod.frame_name(1.5, 1024, label=False)
    assert a != framesmod.frame_name(1.5, 512, label=True)
    assert a != framesmod.frame_name(2.0, 512, label=False)


# ------------------------------------------- A1: drawtext label escaping

def test_extract_with_label_succeeds(slides_clip, workdir):
    """Regression: a timestamp label contains colons. Interpolating it into
    drawtext's `text=` parses on ffmpeg 6 and dies on ffmpeg 7, which took every
    labelled extraction with it and broke `scan` entirely."""
    got = framesmod.extract(
        slides_clip, [1.0, 6.0], workdir / "labelled", width=256, label=True
    )
    assert len(got) == 2, "labelled extraction produced no frames"
    for _, pth in got:
        assert pth.exists() and pth.stat().st_size > 512


def test_label_temp_files_are_cleaned_up(slides_clip, workdir):
    d = workdir / "labelclean"
    framesmod.extract(slides_clip, [2.0], d, width=256, label=True)
    assert not list(d.glob("*.label.txt")), "label temp files left behind"


def test_scan_end_to_end(slides_clip, workdir):
    """The stage that shipped broken. Must produce a readable sheet."""
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "scan", str(slides_clip),
        "--tiles", "6", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    assert data["sheets"], "scan produced no sheets"
    for sheet in data["sheets"]:
        assert Path(sheet["path"]).exists()
        assert sheet["tiles"], "sheet has no timestamp legend"


# --------------------------------------- A3: whisper backend identification

def _fake_binary(tmp: Path, name: str, help_text: str) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    p = tmp / name
    p.write_text(f"#!/bin/sh\ncat <<'H'\n{help_text}\nH\n")
    p.chmod(0o755)
    return p


def test_identify_openai_whisper(workdir):
    b = _fake_binary(workdir / "fb1", "whisper",
                     "usage: whisper [--model MODEL] [--model_dir DIR] "
                     "[--output_format {txt,json}] audio")
    assert tx._identify_whisper(str(b)) == "python"


def test_identify_whisper_cpp(workdir):
    b = _fake_binary(workdir / "fb2", "whisper-cli",
                     "usage: whisper-cli [options] file0\n"
                     "  -m FNAME, --model FNAME  model path\n"
                     "  -oj,       --output-json  output JSON")
    assert tx._identify_whisper(str(b)) == "cpp"


def test_identify_rejects_unrelated_binary(workdir):
    b = _fake_binary(workdir / "fb3", "whisper", "I am not a transcriber")
    assert tx._identify_whisper(str(b)) is None


# ------------------------------------------- A4: embedded subtitle tracks

@pytest.fixture(scope="session")
def mkv_with_subs(workdir):
    out = workdir / "subbed.mkv"
    if out.exists():
        return out
    srt = workdir / "embedded_src.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nembedded track line one\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nsecond line here\n"
    )
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x203040:s=640x360:d=10:r=10",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=10",
        "-i", str(srt), "-map", "0:v", "-map", "1:a", "-map", "2:s",
        "-c:v", "libx264", "-c:a", "aac", "-c:s", "srt",
        "-metadata:s:s:0", "language=eng", "-shortest", str(out),
    ], check=True)
    return out


def test_embedded_streams_detected(mkv_with_subs):
    streams = tx.embedded_subtitle_streams(mkv_with_subs)
    assert streams and streams[0]["codec"] == "subrip"
    assert streams[0]["language"] == "eng"


def test_embedded_preferred_over_whisper(mkv_with_subs, workdir):
    """A local container with a text track must never reach Whisper."""
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "probe",
        str(mkv_with_subs), "--no-cuts", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_emb")})
    assert rc.returncode == 0, rc.stderr
    t = json.loads(rc.stdout)["transcript"]
    assert t["source"] == "embedded", f"fell through to {t['source']}"
    assert "embedded track line one" in t["segments"][0]["text"]


def test_pick_subtitle_skips_bitmap_tracks():
    assert tx.pick_subtitle_stream(
        [{"order": 0, "codec": "hdmv_pgs_subtitle", "language": "eng"}]) is None
    got = tx.pick_subtitle_stream([
        {"order": 0, "codec": "subrip", "language": "eng"},
        {"order": 1, "codec": "subrip", "language": "zho"},
    ], language="zh")
    assert got["language"] == "zho"


# ---------------------------------------------- A5: rate control model

def test_explicit_fps_holds_interval_across_durations():
    """A stated rate must not thin out on longer video."""
    fps_a, n_a = framesmod.explicit_sampling(1.0, 30.0)
    fps_b, n_b = framesmod.explicit_sampling(1.0, 300.0)
    assert fps_a == fps_b == 1.0
    assert n_a == 30 and n_b == 300, "explicit fps was capped"
    assert (30.0 / n_a) == pytest.approx(300.0 / n_b), "interval drifted"


def test_adaptive_sampling_preserves_pre14_anchor_minimums():
    """The continuous curve may exceed old coverage, but never undercut it."""
    wide_minimums = {15.0: 15, 30.0: 30, 45.0: 40, 60.0: 40,
                     120.0: 60, 180.0: 60}
    focus_minimums = {15.0: 30, 30.0: 60, 45.0: 80, 60.0: 80,
                      120.0: 100, 180.0: 100}
    for duration, minimum in wide_minimums.items():
        assert framesmod.adaptive_sampling(duration, focused=False)[1] >= minimum
    for duration, minimum in focus_minimums.items():
        assert framesmod.adaptive_sampling(duration, focused=True)[1] >= minimum

    # Boundary-adjacent samples catch the old bucket jumps without reintroducing
    # bucketed production logic. The new curve must already be above the next
    # old plateau before crossing each boundary.
    for duration, minimum in ((30.001, 40), (60.001, 60), (180.001, 80)):
        assert framesmod.adaptive_sampling(duration, focused=False)[1] >= minimum
    assert framesmod.adaptive_sampling(60.001, focused=True)[1] >= 100

    # Keep 1.4's sqrt-curve coverage above three minutes whenever it is denser.
    for duration in (181.0, 240.0, 300.0, 450.0, 600.0, 900.0):
        interval = max(0.5, min(4.0, duration ** 0.5 / 3.0))
        v14_wide = min(framesmod.DEFAULT_MAX_FRAMES, math.ceil(duration / interval))
        v14_focus = min(
            framesmod.DEFAULT_MAX_FRAMES,
            math.ceil(duration / max(0.25, interval / 1.75)),
        )
        assert framesmod.adaptive_sampling(duration, focused=False)[1] >= v14_wide
        assert framesmod.adaptive_sampling(duration, focused=True)[1] >= v14_focus


def test_ten_minute_window_never_collapses_to_thirty_second_count():
    """Regression for the 1.3 blocker: long windows must receive more samples."""
    for focused in (False, True):
        short = framesmod.adaptive_sampling(30.0, focused=focused)[1]
        long = framesmod.adaptive_sampling(600.0, focused=focused)[1]
        assert long > short, (focused, short, long)


def test_sampling_plan_labels_and_explicit_override():
    fps, _, label = framesmod.sampling_plan(60.0, focused=False)
    assert label == "adaptive-wide" and fps <= framesmod.WIDE_AUTO_RATE_LIMIT
    _, _, label = framesmod.sampling_plan(20.0, focused=True)
    assert label == "adaptive-focus"
    fps, n, label = framesmod.sampling_plan(10.0, focused=False, fps_override=8.0)
    assert fps == 8.0 and n == 80, "explicit override must ignore auto caps"
    assert "explicit" in label


def test_budget_guard_warns_without_thinning(slides_clip, workdir, capsys):
    """At the managed floor the budget is still only a tripwire, never a density dial."""
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--fps", "2", "--max-tokens", "500",
        "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_guard")})
    assert rc.returncode == 0, rc.stderr
    assert "over the 500 budget" in rc.stderr, rc.stderr
    data = json.loads(rc.stdout)
    assert data["rate"]["fps"] == 2.0
    assert data["rate"]["target"] == 30, "budget must not reduce frame count"
    assert data["frame_size"][0] == 384
    assert data["resolution_mode"] == "managed-floor"


def test_default_width_spends_resolution_to_keep_frame_count(slides_clip, workdir):
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--fps", "2", "--vendor", "anthropic",
        "--max-tokens", "5000", "--no-dedup", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_managed_width")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    assert data["rate"]["target"] == 30
    assert 384 <= data["frame_size"][0] < 512
    assert data["resolution_mode"] == "managed"
    assert data["est_image_tokens"] <= 5000


def test_explicit_width_is_exact_even_when_over_budget(slides_clip, workdir):
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--fps", "2", "--width", "1024",
        "--vendor", "anthropic", "--max-tokens", "500", "--no-dedup", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_explicit_width")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    assert data["frame_size"][0] == 1024, "explicit --width was silently changed"
    assert data["resolution_mode"] == "explicit"
    assert data["rate"]["target"] == 30, "budget must not reduce frame count"
    assert "over the 500 budget" in rc.stderr


# ------------------------------------------- B3/A: noise-floor gating

def test_estimate_floor_uses_quiet_quartile():
    assert dedup.estimate_floor([]) == 0.0
    assert dedup.estimate_floor([5.0]) == 5.0
    assert dedup.estimate_floor([float(i) for i in range(101)]) == pytest.approx(25.0)


def test_gate_trips_when_floor_meets_threshold(noisy_clip, workdir):
    """Grain as loud as real change means no threshold separates them, so
    nothing must be dropped."""
    d = workdir / "gate_trip"
    paths = [grab(noisy_clip, t, d) for t in (1.0, 2.0, 3.0, 5.0, 6.0, 7.0)]
    kept, stats = dedup.dedup(paths, threshold=0.3)
    assert stats["gated"] is True, stats
    assert stats["dropped"] == 0
    assert len(kept) == len(paths)
    assert "noise floor" in stats["reason"]


def test_gate_stays_open_on_clean_source(slides_clip, workdir):
    d = workdir / "gate_open"
    paths = [grab(slides_clip, t, d) for t in (1.0, 2.0, 3.0, 4.0)]
    _, stats = dedup.dedup(paths)
    assert stats["gated"] is False, stats
    assert stats["dropped"] > 0, "clean source should still dedup"


def test_gate_can_be_forced_off(noisy_clip, workdir):
    """gate=False must run the comparison rather than short-circuiting."""
    d = workdir / "gate_force"
    paths = [grab(noisy_clip, t, d) for t in (1.0, 2.0, 3.0, 5.0, 6.0, 7.0)]
    _, stats = dedup.dedup(paths, threshold=0.3, gate=False)
    assert stats["gated"] is False
    assert "reason" not in stats, "short-circuited despite gate=False"
    assert stats["floor"] > 0.3


# --------------------------------------- B4: transcript cache poisoning

def test_empty_transcript_is_not_cached(slides_clip, workdir):
    """A --no-whisper probe must not permanently suppress transcription."""
    import json
    env = {**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_poison")}
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "probe", str(slides_clip),
        "--no-cuts", "--no-whisper", "--json",
    ], capture_output=True, text=True, check=False, env=env)
    assert rc.returncode == 0, rc.stderr
    first = json.loads(rc.stdout)
    assert first["transcript"]["source"] == "none"
    cache_dir = Path(first["cache_dir"])
    assert not (cache_dir / "transcript.json").exists(), (
        "empty transcript was cached and will poison later runs")


def test_reusable_rejects_empty_and_stale_params():
    want = tx._params(True, "small", "auto", None)
    assert tx._reusable(None, want) is False
    assert tx._reusable({"source": "none", "segments": [], "params": want}, want) is False
    good = {"source": "whisper.cpp:small",
            "segments": [{"start": 0, "end": 1, "text": "x"}], "params": want}
    assert tx._reusable(good, want) is True
    other = tx._params(True, "medium", "auto", None)
    assert tx._reusable(good, other) is False


def test_captions_reused_across_whisper_params():
    p1 = tx._params(True, "small", "auto", "en")
    p2 = tx._params(False, "medium", "zh", "en")
    cached = {"source": "captions",
              "segments": [{"start": 0, "end": 1, "text": "x"}], "params": p1}
    assert tx._reusable(cached, p2) is True
    p3 = tx._params(True, "small", "auto", "zh")
    assert tx._reusable(cached, p3) is False


def test_embedded_cache_identity_includes_requested_language(workdir):
    import json
    clip = workdir / "dual_subs.mkv"
    if not clip.exists():
        en = workdir / "dual_en.srt"
        zh = workdir / "dual_zh.srt"
        en.write_text("1\n00:00:00,500 --> 00:00:02,500\nenglish line\n", encoding="utf-8")
        zh.write_text("1\n00:00:00,500 --> 00:00:02,500\n中文行\n", encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=gray:s=320x180:r=10:d=3",
            "-i", str(en), "-i", str(zh), "-map", "0:v", "-map", "1:s", "-map", "2:s",
            "-c:v", "libx264", "-c:s", "srt",
            "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=zho",
            str(clip),
        ], check=True)
    env = {**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_dual_subs")}
    def probe(lang):
        rc = subprocess.run([
            sys.executable, str(SCRIPTS / "vidwatch.py"), "probe", str(clip),
            "--no-cuts", "--no-whisper", "--language", lang, "--json",
        ], capture_output=True, text=True, check=False, env=env)
        assert rc.returncode == 0, rc.stderr
        return json.loads(rc.stdout)["transcript"]
    first, second = probe("en"), probe("zh")
    assert first["language"] == "eng" and "english line" in first["segments"][0]["text"]
    assert second["language"] == "zho" and "中文行" in second["segments"][0]["text"]


def test_local_cache_key_uses_nanosecond_mtime(workdir):
    import cache as cachemod
    p = workdir / "mtime_identity.bin"
    p.write_bytes(b"a" * 4096)
    sec = 1_700_000_000
    os.utime(p, ns=(sec * 1_000_000_000 + 100_000_000, sec * 1_000_000_000 + 100_000_000))
    first = cachemod._key_for(str(p))
    p.write_bytes(b"b" * 4096)
    os.utime(p, ns=(sec * 1_000_000_000 + 900_000_000, sec * 1_000_000_000 + 900_000_000))
    second = cachemod._key_for(str(p))
    assert first != second


def test_fmt_ts_rounds_total_milliseconds_before_split():
    assert util.fmt_ts(1.9995, ms=True) == "00:02.000"
    assert util.fmt_ts(59.9996, ms=True) == "01:00.000"


def test_extract_out_manifest_removes_only_prior_generated_files(slides_clip, workdir):
    out = workdir / "extract_reuse"
    out.mkdir(exist_ok=True)
    sentinel = out / "keep-me.txt"
    sentinel.write_text("user file")
    env = {**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_extract_reuse")}
    base = [
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract", str(slides_clip),
        "--layout", "frames", "--out", str(out), "--goal", "test",
        "--no-whisper",
    ]
    first = subprocess.run(base + ["--frames", "6"], capture_output=True, text=True, check=False, env=env)
    assert first.returncode == 0, first.stderr
    assert len(list((out / "frames").glob("*.jpg"))) == 6
    second = subprocess.run(base + ["--frames", "3"], capture_output=True, text=True, check=False, env=env)
    assert second.returncode == 0, second.stderr
    assert len(list((out / "frames").glob("*.jpg"))) == 3
    assert sentinel.read_text() == "user file"
    assert (out / ".my-vidwatch-manifest.json").exists()


# ------------------------------------------------ B9: cut-burst clustering

def test_cluster_collapses_transition_bursts():
    """Real measurement: 6 detections inside 0.17s at one transition."""
    burst = [9.142, 9.175, 9.208, 9.242, 9.275, 9.309, 61.161, 61.294, 61.628]
    assert media.cluster_cuts(burst) == [9.142, 61.161]


def test_cluster_keeps_genuinely_separate_cuts():
    cuts = [1.0, 2.0, 3.5, 10.0]
    assert media.cluster_cuts(cuts) == cuts


def test_cluster_is_order_independent_and_idempotent():
    once = media.cluster_cuts([5.0, 1.0, 1.2, 9.0])
    assert once == [1.0, 5.0, 9.0]
    assert media.cluster_cuts(once) == once


def test_density_reports_raw_and_clustered(slides_clip):
    d = media.estimate_cut_density(slides_clip, 15.0)
    assert "raw_cuts" in d
    assert d["raw_cuts"] >= d["total_cuts"]


# ----------------------------------------------------- teardown (timeline)

# Ground truth from a human+agent review of a real 79.3s vertical ad. The
# reviewer saw zero frames and still identified the pacing and dead-air
# problems; these numbers are that analysis, and teardown must reproduce them.
AD_DURATION = 79.3
AD_TRANSITIONS = [9.14, 18.52]
AD_SEGMENTS = [
    {"start": 0.0, "end": 5.4, "text": "hook line"},
    {"start": 9.8, "end": 17.4, "text": "product claim"},
    {"start": 24.7, "end": 31.0, "text": "problem list"},
]


def test_shot_table_matches_manual_analysis():
    shots = td.shot_table(AD_TRANSITIONS, AD_DURATION)
    assert [s["seconds"] for s in shots] == pytest.approx([9.14, 9.38, 60.78], abs=0.01)
    assert shots[0]["start"] == 0.0


def test_pacing_flags_the_long_hold():
    pacing = td.pacing_summary(td.shot_table(AD_TRANSITIONS, AD_DURATION))
    assert pacing["count"] == 3
    assert pacing["longest"] == pytest.approx(60.78, abs=0.01)
    assert pacing["longest_at"] == pytest.approx(18.52, abs=0.01)


def test_silence_finds_the_dead_gap_after_the_product_name():
    """The 7.3s gap the reviewer called a drop-off cliff."""
    gaps = td.silence_gaps(AD_SEGMENTS, AD_DURATION)
    lengths = [g["seconds"] for g in gaps]
    assert pytest.approx(4.4, abs=0.05) in lengths
    assert pytest.approx(7.3, abs=0.05) in lengths
    seven = next(g for g in gaps if abs(g["seconds"] - 7.3) < 0.05)
    assert seven["start"] == pytest.approx(17.4, abs=0.05)


def test_silence_labels_opening_and_ending():
    gaps = td.silence_gaps([{"start": 5.0, "end": 8.0, "text": "x"}], 20.0)
    where = {g["where"] for g in gaps}
    assert "opening" in where and "ending" in where


def test_silence_handles_no_speech_at_all():
    gaps = td.silence_gaps([], 30.0)
    assert len(gaps) == 1 and gaps[0]["where"] == "whole clip"


def test_speech_density_merges_overlaps():
    overlapping = [
        {"start": 0.0, "end": 5.0, "text": "a"},
        {"start": 3.0, "end": 8.0, "text": "b"},
    ]
    assert td.speech_density(overlapping, 16.0) == pytest.approx(0.5)


def test_hook_window_is_the_first_seconds():
    assert "hook line" in td.hook_window(AD_SEGMENTS)
    assert "product claim" not in td.hook_window(AD_SEGMENTS)


def test_shot_table_ignores_transitions_outside_the_clip():
    shots = td.shot_table([-5.0, 3.0, 999.0], 10.0)
    assert [s["seconds"] for s in shots] == pytest.approx([3.0, 7.0])


@pytest.fixture(scope="session")
def music_clip(workdir):
    """Tone throughout except a genuinely silent 12-18s stretch."""
    out = workdir / "music.mp4"
    if out.exists():
        return out
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x142033:s=640x480:d=20:r=10",
        "-f", "lavfi", "-i", "sine=frequency=200:duration=20",
        "-filter_complex", "[1:a]volume=enable='between(t,12,18)':volume=0[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p", str(out),
    ], check=True)
    return out


def test_detect_silence_finds_the_quiet_stretch(music_clip):
    spans = media.detect_silence(music_clip)
    assert spans, "no silence found in a clip with a silent stretch"
    st, en = spans[0]
    assert 11.5 < st < 12.5 and 17.5 < en < 18.5, spans


def test_detect_silence_empty_without_audio(silent_clip):
    assert media.detect_silence(silent_clip) == []


def test_gap_with_music_is_not_called_silent():
    """The factual error this fixes: four transcript gaps on a real ad were
    labelled SILENCE while music played under every one of them."""
    gaps = td.silence_gaps([{"start": 0.0, "end": 4.0, "text": "x"}], 20.0)
    annotated = td.annotate_audio(gaps, [])
    assert annotated[0]["audio"] == "audio playing"
    assert annotated[0]["silent_fraction"] == 0.0


def test_gap_that_is_really_silent_is_flagged():
    gaps = td.silence_gaps([{"start": 0.0, "end": 5.0, "text": "x"}], 15.0)
    assert td.annotate_audio(gaps, [(5.0, 15.0)])[0]["audio"] == "silent"


def test_partly_silent_is_distinguished():
    gaps = td.silence_gaps([{"start": 0.0, "end": 4.0, "text": "x"}], 20.0)
    assert td.annotate_audio(gaps, [(12.0, 18.0)])[0]["audio"] == "partly silent"


def test_no_audio_track_is_not_called_audio_playing():
    """Same class of error as calling music 'silence', in the other direction."""
    gaps = td.silence_gaps([{"start": 0.0, "end": 4.0, "text": "x"}], 20.0)
    out = td.annotate_audio(gaps, [], has_audio=False)
    assert out[0]["audio"] == "no audio track"


def test_findings_wording_follows_the_audio_state():
    base = dict(duration=79.3, shots=[], pacing={"count": 0}, density=0.9,
                transcript={"source": "captions"}, cut_method="scene")
    gap = [{"start": 10.0, "end": 17.0, "seconds": 7.0, "where": "mid",
            "audio": "no audio track"}]
    note = td.findings(gaps=gap, **base)[0]["note"]
    assert "no audio track" in note
    assert "audio track continues" not in note


# ------------------------- transition confirmation (motion false positives)

def test_confirm_rejects_a_boundary_with_no_visual_change(slides_deck):
    assert dedup.confirm_transitions(slides_deck, [5.0]) == []


def test_confirm_keeps_a_real_change(slides_deck):
    assert dedup.confirm_transitions(slides_deck, [20.0]) == [20.0]


def test_confirm_keeps_everything_when_it_cannot_judge(slides_deck):
    """Past the end there is nothing to compare, so keep rather than lose a cut."""
    assert dedup.confirm_transitions(slides_deck, [999.0]) == [999.0]


def test_confirm_handles_empty_input(slides_deck):
    assert dedup.confirm_transitions(slides_deck, []) == []


# ------------------------------------------------- extract (handoff folder)

def test_extract_frames_layout_gives_one_file_per_moment(vertical_clip, workdir,
                                                         tmp_path):
    """--layout frames: exactly as many files as moments asked for."""
    import json
    out = tmp_path / "handoff_frames"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "8",
        "--layout", "frames", "--out", str(out), "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_ex")})
    assert rc.returncode == 0, rc.stderr
    d = json.loads(rc.stdout)
    assert (out / "brief.md").exists()
    # regression: the last sample used to sit on the final frame and fail
    assert len(d["frames"]) == 8, d["frames"]
    assert len(list((out / "frames").glob("*.jpg"))) == 8


def test_extract_packs_moments_into_sheets(vertical_clip, workdir, tmp_path):
    """Chat interfaces handle many attachments badly, so moments are packed into
    grids. The count follows the adaptive layout, not a fixed 2x2."""
    import json
    out = tmp_path / "handoff_sheets"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "12",
        "--out", str(out), "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_sh")})
    assert rc.returncode == 0, rc.stderr
    files = sorted((out / "frames").glob("*.jpg"))
    assert all(f.name.startswith("sheet") for f in files)
    # 12 moments must fit in far fewer files than 12
    assert 1 <= len(files) <= 6, [f.name for f in files]
    assert len(json.loads(rc.stdout)["frames"]) == len(files)


def test_density_defaults_to_one_moment_per_second(vertical_clip, workdir,
                                                   tmp_path):
    """12 moments over a 79s ad was one every 6.6s, which skips whole beats."""
    import json
    out = tmp_path / "handoff_dense"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--out", str(out), "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_dense")})
    assert rc.returncode == 0, rc.stderr
    d = json.loads(rc.stdout)
    sheets = sorted((out / "frames").glob("*.jpg"))
    # the vertical fixture is 20s, so expect roughly 20 moments, not 12
    total_tiles = sum(len(f[1].partition("[")[2].split(",")) for f in
                      [(0, n["file"]) for n in d["frames"]])
    assert total_tiles >= 18, f"only {total_tiles} moments sampled"
    assert len(sheets) >= 3


def test_sheet_layout_adapts_to_aspect_ratio():
    """Vertical sheets grow tall and the chat downscale punishes them; landscape
    sheets stay wide and barely suffer. One fixed grid cannot serve both."""
    tall = framesmod.sheet_layout(1080, 1920)
    wide = framesmod.sheet_layout(1920, 1080)
    assert wide[0] * wide[1] > tall[0] * tall[1], (tall, wide)


def test_every_layout_keeps_tiles_readable():
    """380px is the floor where burned-in captions stayed legible."""
    for w, h in ((1080, 1920), (1920, 1080), (1080, 1080), (720, 1280)):
        cols, rows = framesmod.sheet_layout(w, h, tile_width=540)
        tile_h = round(540 * h / w)
        sheet_long = max((540 + 4) * cols, (tile_h + 4) * rows)
        effective = 540 * min(1.0, 1568 / sheet_long)
        assert effective >= 380, f"{w}x{h} -> {cols}x{rows} gives {effective:.0f}px"


def test_sheet_tiles_stay_large_enough_to_read(vertical_clip, workdir, tmp_path):
    """540px per tile is the point of 2x2. A 3x3 grid would shrink each tile
    below the ~512px where burned-in captions stop being legible."""
    out = tmp_path / "handoff_size"
    subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "4", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_sz")})
    sheet = sorted((out / "frames").glob("*.jpg"))[0]
    w, h = framesmod.frame_dims(sheet)
    assert w >= 2 * 540, f"sheet only {w}px wide; tiles would be too small"
    assert h > w, "a 2x2 grid of vertical tiles should be taller than wide"


def test_grid_option_changes_sheet_count(vertical_clip, workdir, tmp_path):
    out = tmp_path / "handoff_grid"
    subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "12",
        "--grid", "2", "3", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_grid")})
    # 12 moments at 6 tiles per sheet == 2 sheets
    assert len(list((out / "frames").glob("*.jpg"))) == 2


def test_extract_output_lists_every_file_for_attaching(vertical_clip, workdir,
                                                       tmp_path):
    """Two real runs showed an agent reading brief.md and writing its own
    teardown instead of handing the files over. The instruction lives in the
    command output because that is the one thing an agent always reads."""
    out = tmp_path / "handoff_required"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "8", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_req")})
    assert rc.returncode == 0, rc.stderr
    txt = rc.stdout
    assert "REQUIRED NEXT STEP" in txt
    assert str(out / "brief.md") in txt, "brief path not printed in full"
    for sheet in sorted((out / "frames").glob("*.jpg")):
        assert str(sheet) in txt, f"{sheet.name} path not printed"
    assert "must not be skipped" in txt
    assert "in addition, never instead" in txt


def test_extract_defaults_into_downloads(vertical_clip, workdir, monkeypatch,
                                         tmp_path):
    """cwd is wherever the agent happened to be, which scattered handoff
    folders onto the Desktop. Files meant to be forwarded belong in Downloads."""
    import importlib
    fake_home = tmp_path / "home"
    (fake_home / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(pathlib_Path, "home", classmethod(lambda cls: fake_home))
    import vidwatch
    importlib.reload(vidwatch)
    monkeypatch.setenv("VIDWATCH_CACHE", str(workdir / "cache_dl"))
    rc = vidwatch.main([
        "extract", str(vertical_clip), "--no-whisper", "--frames", "4", "--json",
    ])
    assert rc == 0
    made = list((fake_home / "Downloads").glob("*-handoff"))
    assert made, "handoff folder did not land in Downloads"
    assert (made[0] / "brief.md").exists()


def test_goal_lands_at_the_top_of_the_brief(vertical_clip, workdir, tmp_path):
    """The owner states their goal once, to whoever runs the extraction. It has
    to travel with the files or the next reader asks again."""
    out = tmp_path / "handoff_goal"
    goal = "recut to 30s for Reels, no reshoot, give me an edit list"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "4",
        "--goal", goal, "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_goal")})
    assert rc.returncode == 0, rc.stderr
    brief = (out / "brief.md").read_text()
    assert "## What the owner asked for" in brief
    assert goal in brief, "goal was paraphrased or dropped"
    # it must precede the reading instructions, not be buried
    assert brief.index("What the owner asked for") < brief.index("How to read this")
    assert "hands the work" in brief, "no instruction against closing questions"


def test_missing_goal_warns_and_says_so_in_the_brief(vertical_clip, workdir,
                                                    tmp_path):
    out = tmp_path / "handoff_nogoal"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "4", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_nogoal")})
    assert rc.returncode == 0, rc.stderr
    assert "--goal was not set" in rc.stdout
    assert "## No goal was supplied" in (out / "brief.md").read_text()


def test_multiline_goal_survives_markdown_quoting():
    brief = td.build_brief(
        goal="line one\nline two", meta={"source": "x.mp4"}, duration=10.0,
        shots=[], pacing={"count": 0}, gaps=[], density=0.5,
        transcript={"source": "captions", "segments": []},
        cut_method="scene", frame_files=[],
    )
    assert "> line one" in brief and "> line two" in brief


def test_brief_lists_sheet_timestamps(vertical_clip, workdir, tmp_path):
    """Tiles carry burned-in timestamps, and the brief must map them so a
    reader quotes a time rather than a tile position."""
    out = tmp_path / "handoff_stamps"
    subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "8", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_stamps")})
    brief = (out / "brief.md").read_text()
    assert "## Attached images" in brief
    assert "sheet01.jpg" in brief
    assert "row-major" in brief
    assert "quote the timestamp" in brief


def test_extract_frames_are_not_capped_by_the_vendor_edge(vertical_clip, workdir,
                                                          tmp_path):
    """Frames a person uploads are not entering an agent's context, so the
    long-edge cap must not blur them."""
    out = tmp_path / "handoff_big"
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "3",
        "--layout", "frames", "--width", "1024", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_ex2")})
    assert rc.returncode == 0, rc.stderr
    first = sorted((out / "frames").glob("*.jpg"))[0]
    w, _ = framesmod.frame_dims(first)
    assert w == 1024, f"frame was capped to {w}px"


def test_brief_marks_findings_as_checkable(vertical_clip, workdir, tmp_path):
    out = tmp_path / "handoff_brief"
    subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "extract",
        str(vertical_clip), "--no-whisper", "--frames", "4", "--out", str(out),
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_ex3")})
    brief = (out / "brief.md").read_text()
    assert "starting points, not conclusions" in brief
    assert "*Check:*" in brief
    assert "## Attached images" in brief and "## Transcript" in brief
    # the cross-check guidance that a real run showed was missing
    assert "Cross-check the frames against the timeline" in brief


def test_slow_open_finding_ignores_a_whole_clip_shot():
    """A single shot spanning everything is not a slow open."""
    shots = td.shot_table([], 60.0)
    notes = [f["note"] for f in td.findings(
        duration=60.0, shots=shots, pacing=td.pacing_summary(shots), gaps=[],
        density=0.9, transcript={"source": "captions"}, cut_method="scene")]
    assert not any("slow" in n.lower() or "is only 1 shot" in n for n in notes), notes


# ------------------------------------------------------------- end to end

def test_read_end_to_end_finds_every_state(slides_clip, workdir, monkeypatch):
    """The whole point, in one test: 100+ candidates over a mostly-static clip
    must collapse to exactly the visually distinct moments, including the
    two-digit caption change."""
    monkeypatch.setenv("VIDWATCH_CACHE", str(workdir / "cache"))
    import importlib

    import cache as cachemod
    importlib.reload(cachemod)
    import vidwatch
    importlib.reload(vidwatch)

    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--mode", "uniform", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 0, rc.stderr
    import json
    data = json.loads(rc.stdout)
    times = [f["t"] for f in data["frames"]]
    # --start/--end names a focused window, so adaptive sampling tightens
    # coverage compared with the same duration in wide mode.
    assert data["rate"]["mode"] == "adaptive-focus", data["rate"]
    assert data["rate"]["fps"] > 1.0
    assert data["dedup"]["candidates"] >= 18, data["dedup"]
    assert 4 <= len(times) <= 8, f"expected the distinct states, got {times}"
    # One frame per visually distinct span. Tolerance is one frame interval
    # (0.1s at 10fps) because a reported timestamp is the requested seek
    # position and the decoder returns the first frame at or after it.
    tol = 0.11
    assert any(t < 5.0 + tol for t in times)
    assert any(5.0 - tol <= t < 10.0 + tol for t in times)
    assert any(10.0 - tol <= t < 12.0 + tol for t in times)
    assert any(t >= 12.0 - tol for t in times)


def test_vendor_changes_cost_not_frame_count(slides_clip, workdir):
    """Frame count comes from adaptive sampling, so it must NOT vary by vendor.
    What varies is the reported cost and whether the budget guard trips — the
    budget is a tripwire, not a density dial."""
    import json
    seen = {}
    for vendor in ("anthropic", "gemini"):
        rc = subprocess.run([
            sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
            "--start", "0", "--end", "15", "--mode", "uniform",
            "--width", "1024", "--vendor", vendor, "--json",
        ], capture_output=True, text=True, check=False,
            env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
        assert rc.returncode == 0, rc.stderr
        data = json.loads(rc.stdout)
        assert data["vendor"] == vendor
        seen[vendor] = (data["rate"]["target"], data["est_image_tokens"])
    assert seen["anthropic"][0] == seen["gemini"][0], (
        f"frame target must be vendor-independent now; got {seen}")
    assert seen["gemini"][1] < seen["anthropic"][1], (
        f"gemini is cheaper per frame at 1024px; got {seen}")


def test_read_refuses_wide_window_without_force(slides_clip, workdir):
    long_clip = workdir / "long.mp4"
    if not long_clip.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:d=700:r=5",
            "-c:v", "libx264", "-crf", "35", "-pix_fmt", "yuv420p", str(long_clip),
        ], check=True)
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(long_clip),
        "--start", "0", "--end", "700",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 1
    assert "guard" in rc.stderr.lower()


def test_probe_runs_without_captions(slides_clip, workdir):
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "probe", str(slides_clip),
        "--no-whisper", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache")})
    assert rc.returncode == 0, rc.stderr
    import json
    data = json.loads(rc.stdout)
    assert data["meta"]["duration"] == pytest.approx(15.0, abs=0.5)
    assert data["transcript"]["source"] == "none"


# ------------------------------------------------ Phase 5: deterministic defects

@pytest.fixture(scope="session")
def black_flash_clip(workdir):
    out = workdir / "black_flash.mp4"
    if not out.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=white:s=320x180:r=30:d=2",
            "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,0.9,1.05)'",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ], check=True)
    return out


@pytest.fixture(scope="session")
def freeze_clip(workdir):
    out = workdir / "freeze.mp4"
    if not out.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1.5",
            "-vf", "tpad=stop_mode=clone:stop_duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ], check=True)
    return out


@pytest.fixture(scope="session")
def silence_clip(workdir):
    out = workdir / "silence.mp4"
    if not out.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=gray:s=320x180:r=30:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-filter_complex", "[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(out),
        ], check=True)
    return out


@pytest.fixture(scope="session")
def duplicate_shot_clip(workdir):
    out = workdir / "duplicate_shot.mp4"
    if not out.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=red:s=320x180:r=30:d=1",
            "-f", "lavfi", "-i", "color=blue:s=320x180:r=30:d=1",
            "-f", "lavfi", "-i", "color=red:s=320x180:r=30:d=1",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ], check=True)
    return out


@pytest.fixture(scope="session")
def pts_gap_clip(workdir):
    out = workdir / "pts_gap.mp4"
    if not out.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2",
            "-vf", "setpts='PTS+if(gte(N,30),0.5/TB,0)'", "-fps_mode", "vfr",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ], check=True)
    return out


@pytest.fixture(scope="session")
def clean_defect_clip(workdir):
    """Continuously moving picture + continuous tone, with no planted defect."""
    out = workdir / "clean_defects.mp4"
    if not out.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(out),
        ], check=True)
    return out


def test_defects_merges_one_planted_flash_into_one_event_candidate(black_flash_clip):
    meta = media.probe_file(black_flash_clip)
    found = defects.locate(black_flash_clip, meta)
    events = [c for c in found if 0.85 <= c["t"] <= 1.1]
    assert len(events) == 1, events
    event = events[0]
    assert "hits" in event["evidence"], event
    kinds = {h["kind"] for h in event["evidence"]["hits"]}
    assert {"black", "luma-spike"} <= kinds


def test_defects_detects_planted_freeze(freeze_clip):
    found = defects.detect_freeze(freeze_clip, media.probe_file(freeze_clip)["duration"])
    assert found and found[0]["kind"] == "freeze"
    assert found[0]["evidence"]["duration"] >= defects.FREEZE_MIN_SECONDS


def test_defects_detects_planted_silence(silence_clip):
    found = defects.detect_silence(silence_clip, has_audio=True)
    assert found and found[0]["kind"] == "silence"
    assert 0.8 <= found[0]["t"] <= 1.2
    assert found[0]["evidence"]["duration"] >= 0.8


def test_defects_detects_non_adjacent_duplicate_shot(duplicate_shot_clip):
    meta = media.probe_file(duplicate_shot_clip)
    found = defects.detect_duplicate_shots(duplicate_shot_clip, meta["duration"])
    assert found and found[0]["kind"] == "duplicate-shot"
    assert 1.8 <= found[0]["t"] <= 2.2
    assert found[0]["evidence"]["matched_shot_start"] == pytest.approx(0.0, abs=0.3)


def test_defects_detects_planted_pts_gap(pts_gap_clip):
    found = defects.detect_pts_gaps(pts_gap_clip)
    assert found and found[0]["kind"] == "pts-gap"
    assert found[0]["evidence"]["gap"] >= 0.5
    assert found[0]["evidence"]["expected"] == pytest.approx(1 / 30, abs=0.002)


def test_defects_clean_footage_returns_zero_candidates(clean_defect_clip):
    meta = media.probe_file(clean_defect_clip)
    assert defects.locate(clean_defect_clip, meta) == []


def test_structural_suppression_removes_luma_at_confirmed_cut_only():
    hits = [
        {"t": 5.0, "kind": "luma-spike", "severity": "high", "evidence": {}},
        {"t": 8.0, "kind": "luma-spike", "severity": "high", "evidence": {}},
    ]
    kept, suppressed = defects.suppress_structural(hits, scene_cuts=[5.1])
    assert [h["t"] for h in kept] == [8.0]
    assert len(suppressed) == 1
    assert suppressed[0]["suppression"] == "confirmed-scene-cut"


def test_structural_suppression_distinguishes_pause_from_dropout():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "before"},
        {"start": 4.0, "end": 6.0, "text": "after"},
    ]
    hits = [
        {"t": 2.2, "kind": "silence", "severity": "medium",
         "evidence": {"start": 2.2, "end": 3.8}},
        {"t": 4.5, "kind": "silence", "severity": "medium",
         "evidence": {"start": 4.5, "end": 5.0}},
    ]
    kept, suppressed = defects.suppress_structural(hits, transcript_segments=segments)
    assert [h["t"] for h in kept] == [4.5], "silence inside speech must stay as dropout"
    assert len(suppressed) == 1
    assert suppressed[0]["suppression"] == "between-transcript-segments"


def _install_failing_tool(workdir, monkeypatch, name):
    bad_dir = workdir / f"bad_{name}"
    bad_dir.mkdir(exist_ok=True)
    bad = bad_dir / name
    bad.write_text("#!/bin/sh\necho synthetic-detector-failure >&2\nexit 7\n")
    bad.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bad_dir}:{os.environ.get('PATH', '')}")


def _assert_loud_failure(call):
    with pytest.raises(util.VidwatchError) as exc:
        call()
    assert "synthetic-detector-failure" in str(exc.value)
    assert "exit 7" in str(exc.value)


def test_ffmpeg_detectors_fail_loudly(black_flash_clip, silence_clip, workdir, monkeypatch):
    _install_failing_tool(workdir, monkeypatch, "ffmpeg")
    monkeypatch.setattr(media, "probe_file", lambda _: {"has_audio": True})
    calls = [
        lambda: media.detect_cuts(black_flash_clip),
        lambda: media.detect_silence(silence_clip, noise_db=-35.0, min_duration=0.5),
        lambda: dedup.content_changes(black_flash_clip, 2.0),
        lambda: defects.detect_black(black_flash_clip),
        lambda: defects.detect_freeze(black_flash_clip, 2.0),
        lambda: defects.detect_luma_spikes(black_flash_clip),
        lambda: defects.detect_duplicate_shots(black_flash_clip, 2.0),
    ]
    for call in calls:
        _assert_loud_failure(call)


def test_ffprobe_detectors_fail_loudly(black_flash_clip, workdir, monkeypatch):
    _install_failing_tool(workdir, monkeypatch, "ffprobe")
    _assert_loud_failure(lambda: media.keyframe_times(black_flash_clip))
    _assert_loud_failure(lambda: defects.detect_pts_gaps(black_flash_clip))


def test_read_empty_extraction_fails_with_vidwatcherror(slides_clip, workdir, monkeypatch):
    import vidwatch
    monkeypatch.setenv("VIDWATCH_CACHE", str(workdir / "cache_empty_read"))
    monkeypatch.setattr(framesmod, "extract", lambda *a, **k: [])
    args = vidwatch.build_parser().parse_args([
        "read", str(slides_clip), "--start", "0", "--end", "2",
        "--mode", "uniform", "--no-dedup",
    ])
    with pytest.raises(util.VidwatchError, match="no usable frames"):
        args.func(args)


def test_defects_cli_json_records_are_stable_shape(black_flash_clip, workdir):
    import json
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "defects", str(black_flash_clip),
        "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_defects")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    assert data
    assert all(set(c) == {"t", "kind", "severity", "evidence"} for c in data)
    assert any("black" in c["kind"].split("+") for c in data)


def test_scan_custom_grid_respects_token_budget(workdir):
    import json
    clip = workdir / "scan_budget_8s.mp4"
    if not clip.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:r=10:d=8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
        ], check=True)
    rc = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "scan", str(clip),
        "--grid", "10", "10", "--max-tokens", "3000", "--json",
    ], capture_output=True, text=True, check=False,
        env={**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_scan_grid_budget")})
    assert rc.returncode == 0, rc.stderr
    data = json.loads(rc.stdout)
    assert data["est_image_tokens"] <= 3000, data
    assert all(s["cols"] == 10 and s["rows"] == 10 for s in data["sheets"])


# ------------------------------------------------ Phase 6: burst evidence + Qwen

def test_burst_sampling_adds_local_evidence_without_reducing_baseline(slides_clip, workdir):
    import json
    env = {**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_burst")}
    base = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--mode", "uniform", "--max-frames", "12",
        "--no-dedup", "--json",
    ], capture_output=True, text=True, check=False, env=env)
    burst = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--mode", "uniform", "--max-frames", "12",
        "--candidates", "7.5", "--burst-fps", "10", "--burst-radius", "0.5",
        "--no-dedup", "--json",
    ], capture_output=True, text=True, check=False, env=env)
    assert base.returncode == 0, base.stderr
    assert burst.returncode == 0, burst.stderr
    a, b = json.loads(base.stdout), json.loads(burst.stdout)
    assert a["rate"]["target"] == b["rate"]["target"] == 12
    assert len(b["frames"]) > len(a["frames"]), "burst must add evidence, not replace baseline"
    assert b["burst"]["candidates"] == [7.5]
    assert b["burst"]["frames"] >= 10
    assert any(abs(f["t"] - 7.5) < 0.001 for f in b["frames"])


def test_read_json_frames_include_timeline_context(slides_clip, workdir):
    import cache as cachemod
    import json
    env = {**os.environ, "VIDWATCH_CACHE": str(workdir / "cache_frame_context")}
    monkey = os.environ.get("VIDWATCH_CACHE")
    os.environ["VIDWATCH_CACHE"] = env["VIDWATCH_CACHE"]
    try:
        rc_obj = cachemod.RunCache(str(slides_clip))
        rc_obj.write_json("transcript.json", {
            "source": "fixture",
            "segments": [{"start": 0.0, "end": 5.0, "text": "first line"},
                         {"start": 5.0, "end": 15.0, "text": "second line"}],
        })
    finally:
        if monkey is None:
            os.environ.pop("VIDWATCH_CACHE", None)
        else:
            os.environ["VIDWATCH_CACHE"] = monkey
    run = subprocess.run([
        sys.executable, str(SCRIPTS / "vidwatch.py"), "read", str(slides_clip),
        "--start", "0", "--end", "15", "--mode", "uniform", "--max-frames", "6",
        "--no-dedup", "--json",
    ], capture_output=True, text=True, check=False, env=env)
    assert run.returncode == 0, run.stderr
    frames = json.loads(run.stdout)["frames"]
    assert frames
    assert all({"t", "ts", "path", "scene_id", "change_score", "transcript_line"} <= set(f)
               for f in frames)
    assert any(f["change_score"] is not None for f in frames[1:])
    assert any(f["transcript_line"] and f["transcript_line"]["text"] == "second line"
               for f in frames)
