"""Per-model image token estimates.

Why this is (vendor, model-family, detail) and not just "vendor"
---------------------------------------------------------------
One model per vendor cannot work, because OpenAI runs two different tokenizers
at the same time:

  * 4o / 4.1 / 4.5-class: fit a 2048 box, scale the SHORT side to 768, then
    count 512px tiles at 170 each plus an 85 base.
  * GPT-5.x and the mini/nano models: 32x32 patches,
    ceil(w/32) * ceil(h/32).

The same 1024x576 frame is 765 tokens under the first rule and 576 under the
second. Labelling either one "openai" misprices the other.

Anthropic likewise documents 28x28 visual patches, ceil(w/28) * ceil(h/28),
which gives 209 for 512x288 and 777 for 1024x576 — close to the older area/750
approximation but not identical, and the newer models raise the long-edge limit
from 1568 to 2576.

Gemini charges a flat 258 when BOTH sides are at most 384, and otherwise tiles
at 768 and charges 258 per tile.

Qwen estimates are provisional. The current model uses the Qwen3-VL processor's
16px patch size with 2x spatial merge, i.e. a /32 merged grid after processor
alignment. The video-sequence model then applies 2x temporal grouping. The
processor's shortest-edge floor is below every my-vidwatch width in normal use,
so this estimator does not impose an additional image-token floor. API-reported
usage must still calibrate these derived figures.

The uncapped case matters
-------------------------
GPT-5.x at detail `original`/`auto` applies no patch budget and no pixel cap, so
cost grows without bound with image size. That is why `max_edge` lives on the
model rather than on the vendor, and why the long-edge cap is framed as "this
saves you tokens" rather than "the provider would downscale anyway" — for that
combination, it would not.

These are documented estimates for planning, not billing. Providers revise
tokenizers between versions; check your host's own counter if exact cost
matters.
"""
from __future__ import annotations

import math
import os

ENV_VENDOR = "VIDWATCH_VENDOR"


class TokenModel:
    """A model's image cost rule plus the frame size worth sending it."""

    name = "generic"
    max_edge: int | None = 1536
    note = "conservative upper bound across vendors"
    uncapped = False          # True when the provider applies no size limit

    def tokens(self, width: int, height: int) -> int:
        raise NotImplementedError

    def frames_for_budget(self, budget: int, width: int, height: int) -> int:
        per = max(1, self.tokens(width, height))
        return max(1, budget // per)


def _patches(width: int, height: int, size: int) -> int:
    return max(1, math.ceil(width / size)) * max(1, math.ceil(height / size))


# ------------------------------------------------------------------ Anthropic

class Anthropic(TokenModel):
    """28x28 visual patches. 209 for 512x288, 777 for 1024x576."""

    name = "anthropic"
    max_edge = 1568
    note = "28x28 patches; long edge downscaled past 1568px"
    PATCH = 28

    def tokens(self, width: int, height: int) -> int:
        return _patches(width, height, self.PATCH)


class AnthropicHiRes(Anthropic):
    """Newer models raise the long edge to 2576 with a higher token ceiling."""

    name = "anthropic:hires"
    max_edge = 2576
    note = "28x28 patches, 2576px long edge tier"


# --------------------------------------------------------------------- OpenAI

class OpenAITile(TokenModel):
    """4o / 4.1 / 4.5-class: 85 base + 170 per 512px tile.

    Fit a 2048 box first, then scale the SHORT side to 768. Note the published
    procedure scales the short side TO 768; this implementation only scales it
    DOWN, which is why 512x288 comes out 255 rather than higher.
    """

    name = "openai:4o"
    max_edge = 1536
    note = "85 + 170/tile after a 2048 box and a 768px short side"
    BASE = 85
    PER_TILE = 170

    def tokens(self, width: int, height: int) -> int:
        w, h = float(width), float(height)
        if max(w, h) > 2048:
            scale = 2048 / max(w, h)
            w, h = w * scale, h * scale
        if min(w, h) > 768:
            scale = 768 / min(w, h)
            w, h = w * scale, h * scale
        return self.BASE + self.PER_TILE * _patches(round(w), round(h), 512)


class OpenAIPatch(TokenModel):
    """GPT-5.x and mini/nano: 32x32 patches.

    At detail `original`/`auto` there is no patch budget and no pixel cap, so
    cost rises linearly with area forever. The long-edge cap this tool applies
    is therefore a real saving here, not a no-op.
    """

    name = "openai:5"
    max_edge = 1536
    note = "32x32 patches; NO provider-side cap at original/auto detail"
    PATCH = 32
    uncapped = True

    def tokens(self, width: int, height: int) -> int:
        return _patches(width, height, self.PATCH)


class OpenAIPatchHigh(OpenAIPatch):
    """detail=high: same patches, but clamped to a patch budget."""

    name = "openai:5-high"
    max_edge = 2048
    note = "32x32 patches capped at a ~2500-patch budget (detail=high)"
    BUDGET = 2500
    uncapped = False

    def tokens(self, width: int, height: int) -> int:
        return min(self.BUDGET, _patches(width, height, self.PATCH))


# --------------------------------------------------------------------- Gemini

class Gemini(TokenModel):
    """258 flat when both sides <= 384, else 258 per 768x768 tile."""

    name = "gemini"
    max_edge = 1536
    note = "258 flat under 384px, else 258 per 768px tile"
    PER_TILE = 258
    SMALL = 384
    TILE = 768

    def tokens(self, width: int, height: int) -> int:
        if width <= self.SMALL and height <= self.SMALL:
            return self.PER_TILE
        return self.PER_TILE * _patches(width, height, self.TILE)


# ----------------------------------------------------------------------- Qwen

QWEN_FACTOR = 32


def _round_to_factor(value: int, factor: int) -> int:
    """Nearest positive factor multiple; Qwen's processor aligns dimensions."""
    return max(factor, int(math.floor(value / factor + 0.5)) * factor)


def _qwen_spatial_tokens(width: int, height: int) -> int:
    w = _round_to_factor(width, QWEN_FACTOR)
    h = _round_to_factor(height, QWEN_FACTOR)
    return max(1, (w // QWEN_FACTOR) * (h // QWEN_FACTOR))


class QwenImage(TokenModel):
    """Provisional Qwen image estimate on the processor's /32 merged grid."""

    name = "qwen"
    max_edge = None
    note = "provisional /32 image grid; no active min-pixel floor at my-vidwatch widths"

    def tokens(self, width: int, height: int) -> int:
        return _qwen_spatial_tokens(width, height)


class QwenVideo(TokenModel):
    """Provisional Qwen video-sequence average: /32 spatial grid, 2x temporal."""

    name = "qwen:video"
    max_edge = None
    note = "provisional /32 spatial grid + 2x temporal grouping; only for true video-sequence input"
    TEMPORAL = 2

    def tokens(self, width: int, height: int) -> int:
        return max(1, math.ceil(_qwen_spatial_tokens(width, height) / self.TEMPORAL))


# -------------------------------------------------------------------- generic

class Generic(TokenModel):
    """Highest estimate across every known model, with the tightest cap.

    A deliberate mismatch: cost is the MAX so a budget is never overspent,
    while max_edge is the MIN so frames are never larger than the strictest
    provider would keep. Verified as an upper bound at the sizes this tool
    produces; `--vendor` is still the accurate answer.
    """

    name = "generic"
    note = "highest estimate across vendors; set --vendor for accuracy"

    def __init__(self) -> None:
        self._models = [
            Anthropic(), AnthropicHiRes(), OpenAITile(),
            OpenAIPatch(), OpenAIPatchHigh(), Gemini(), QwenImage(), QwenVideo(),
        ]
        self.max_edge = min(m.max_edge for m in self._models if m.max_edge is not None)

    def tokens(self, width: int, height: int) -> int:
        return max(m.tokens(width, height) for m in self._models)


MODELS = {
    "generic": Generic,
    "anthropic": Anthropic,
    "claude": Anthropic,
    "anthropic:hires": AnthropicHiRes,
    "openai": OpenAITile,
    "gpt": OpenAITile,
    "openai:4o": OpenAITile,
    "openai:4.1": OpenAITile,
    "openai:5": OpenAIPatch,
    "openai:5-high": OpenAIPatchHigh,
    "gemini": Gemini,
    "google": Gemini,
    "qwen": QwenImage,
    "qwen3-vl": QwenImage,
    "qwen:video": QwenVideo,
}

CHOICES = (
    "generic", "anthropic", "anthropic:hires",
    "openai:4o", "openai:5", "openai:5-high", "gemini", "qwen", "qwen:video",
)


def resolve(name: str | None = None) -> TokenModel:
    key = (name or os.environ.get(ENV_VENDOR) or "generic").strip().lower()
    cls = MODELS.get(key)
    if cls is None:
        raise ValueError(
            f"unknown model {key!r}; choose from {', '.join(CHOICES)}"
        )
    return cls()


def fit_to_edge(width: int, height: int, max_edge: int | None) -> tuple[int, int]:
    """Scale down so the LONG edge is at most max_edge. Even dimensions.

    Capping width alone leaves portrait sources unbounded: a 1080x1920 clip
    asked for at width 1536 becomes 1536x2731.
    """
    if max_edge is None:
        return width, height
    long_edge = max(width, height)
    if long_edge <= max_edge:
        return width, height
    scale = max_edge / long_edge
    w = max(2, int(width * scale) // 2 * 2)
    h = max(2, int(height * scale) // 2 * 2)
    return w, h


def compare(width: int, height: int) -> list[tuple[str, int]]:
    """Per-model cost of one frame — used by the preflight report."""
    return [
        (m.name, m.tokens(width, height))
        for m in (Anthropic(), OpenAITile(), OpenAIPatch(), Gemini(), QwenImage(), QwenVideo())
    ]
