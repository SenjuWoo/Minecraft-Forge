"""Palette: palette.json holds the locked colour ramps every painter reads ({"ramps": {name: ["#rrggbb", ...]}},
dark to light). Lock the palette before painting: colours decided once stop drifting between sessions.

ramp_from_image() measures a ramp from a reference picture and hue-shifts it the pixel-art way: shadows toward one
hue, lights toward another. The default method measures anchors (circular-mean hue, median saturation of the mid
tones, the 8th to 97th percentile of lightness) and spaces the steps evenly in lightness: k-means clusters of a
painted reference gave muddy, unevenly spaced ramps. hsv_filter() keeps only the material's own pixels inside a
generous box (no background, no neighbouring material).
"""
from __future__ import annotations

import colorsys
import json

import numpy as np

from . import paths

PALETTE_JSON = paths.PIPE / "palette.json"
LUMA = np.array([0.299, 0.587, 0.114])


def load() -> dict:
    return json.loads(PALETTE_JSON.read_text(encoding="utf-8"))


def rgb(hexstr: str) -> tuple[int, int, int]:
    return tuple(int(hexstr[i:i + 2], 16) for i in (1, 3, 5))


def to_hex(colour) -> str:
    return "#%02X%02X%02X" % tuple(int(round(max(0, min(255, v)))) for v in colour)


def kmeans(px: np.ndarray, k: int, iters: int = 30) -> np.ndarray:
    """Deterministic k-means: centres start on luminance quantiles so the clusters spread along the ramp."""
    order = np.argsort(px @ LUMA)
    c = px[order[np.linspace(0, len(px) - 1, k).astype(int)]].astype(float)
    for _ in range(iters):
        lab = ((px[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
        new = np.array([px[lab == i].mean(0) if np.any(lab == i) else c[i] for i in range(k)])
        if np.allclose(new, c, atol=0.1):
            break
        c = new
    return c


def hsv_filter(hmin=None, hmax=None, smin=0.0, smax=1.0, vmin=0.0, vmax=1.0):
    """A `keep` function for ramp_from_image: hue range in turns (wraps when hmin > hmax), saturation and value."""
    def keep(px):
        a = px / 255.0
        mx, mn = a.max(1), a.min(1)
        s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        d = np.maximum(mx - mn, 1e-6)
        r, g, b = a[:, 0], a[:, 1], a[:, 2]
        h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6.0
        m = (s >= smin) & (s <= smax) & (mx >= vmin) & (mx <= vmax)
        if hmin is not None:
            m &= ((h >= hmin) & (h <= hmax)) if hmin <= hmax else ((h >= hmin) | (h <= hmax))
        return px[m]
    return keep


def ramp_from_anchors(px, steps=4, shadow_shift=0.035, light_shift=-0.025, lo_pct=8, hi_pct=97, l_range=None,
                      sat_curve=(1.18, 0.82), min_span=0.34) -> list[str]:
    """Measured anchors -> a hard-band ramp: hue = circular mean, saturation = median of the mid tones (times
    sat_curve from shadow to light), lightness from the lo_pct to the hi_pct percentile (at least min_span apart, or
    l_range when a glossy highlight falls out of the filter), steps evenly spaced in lightness."""
    a = px / 255.0
    hls = np.array([colorsys.rgb_to_hls(*c) for c in a[:: max(1, len(a) // 20000)]])
    h, l, sat = hls[:, 0], hls[:, 1], hls[:, 2]
    hue = np.angle(np.mean(np.exp(2j * np.pi * h))) / (2 * np.pi) % 1.0
    lo, hi = (l_range if l_range is not None else (np.percentile(l, lo_pct), np.percentile(l, hi_pct)))
    if l_range is None and hi - lo < min_span:
        c = min(max((lo + hi) / 2, 0.12 + min_span / 2), 0.92 - min_span / 2)
        lo, hi = c - min_span / 2, c + min_span / 2
    mid = (l > np.percentile(l, 30)) & (l < np.percentile(l, 80))
    s_med = float(np.median(sat[mid])) if mid.any() else float(np.median(sat))
    out = []
    for i in range(steps):
        t = i / max(1, steps - 1)
        S = min(1.0, s_med * (sat_curve[0] + (sat_curve[1] - sat_curve[0]) * t))
        H = (hue + shadow_shift * (1 - t) + light_shift * t) % 1.0
        out.append(to_hex(np.array(colorsys.hls_to_rgb(H, lo + (hi - lo) * t, S)) * 255))
    return out


def ramp_from_image(image_path, boxes, steps=4, shadow_shift=0.035, light_shift=-0.025, min_step=14, keep=None,
                    method="anchors", **anchor_options) -> list[str]:
    """A ramp of `steps` colours from pixel boxes (x0, y0, x1, y1) of a reference image.

    keep: optional function(pixels) -> pixels to drop neighbours and background inside the boxes (hsv_filter).
    method: "anchors" (default, ramp_from_anchors) or "kmeans" (clusters sorted by luminance).
    """
    from PIL import Image
    im = np.asarray(Image.open(image_path).convert("RGB")).astype(float)
    px = np.concatenate([im[y0:y1, x0:x1].reshape(-1, 3) for x0, y0, x1, y1 in boxes])
    if keep is not None:
        px = keep(px)
    if len(px) < 30:
        raise ValueError(f"only {len(px)} pixels pass the filter in {image_path}: widen the boxes or the filter")
    if method == "anchors":
        return ramp_from_anchors(px, steps, shadow_shift, light_shift, **anchor_options)
    if len(px) > 60000:
        px = px[np.random.default_rng(1).choice(len(px), 60000, replace=False)]
    centres = kmeans(px, steps)
    cs = centres[np.argsort(centres @ LUMA)]
    out = []
    for i, c in enumerate(cs):
        h, l, s = colorsys.rgb_to_hls(*(c / 255.0))
        t = i / max(1, steps - 1)
        h = (h + shadow_shift * (1 - t) + light_shift * t) % 1.0
        out.append(np.array(colorsys.hls_to_rgb(h, l, s)) * 255)
    for i in range(1, len(out)):   # hard ramps need visibly separate steps
        li, lp = out[i] @ LUMA, out[i - 1] @ LUMA
        if li - lp < min_step:
            out[i] = np.clip(out[i] * ((lp + min_step) / max(li, 1)), 0, 255)
    return [to_hex(c) for c in out]


def swatch_sheet(out_path) -> None:
    from PIL import Image, ImageDraw
    ramps = load()["ramps"]
    cell, pad = 40, 6
    img = Image.new("RGB", (150 + 6 * (cell + 4), pad + len(ramps) * (cell + pad)), (24, 22, 36))
    d = ImageDraw.Draw(img)
    for r, (name, ramp) in enumerate(ramps.items()):
        y = pad + r * (cell + pad)
        d.text((8, y + 12), name, fill=(230, 230, 240))
        for i, hx in enumerate(ramp):
            d.rectangle([150 + i * (cell + 4), y, 150 + i * (cell + 4) + cell, y + cell], fill=hx)
    img.save(out_path)
