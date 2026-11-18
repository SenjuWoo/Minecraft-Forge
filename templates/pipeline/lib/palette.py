"""Palette: palette.json holds the locked colour ramps every painter reads ({"ramps": {name: ["#rrggbb", ...]}},
dark to light). Lock the palette before painting: colours decided once stop drifting between sessions.

ramp_from_image() measures a ramp from a reference picture (k-means on sample boxes that show only that
material) and hue-shifts it the pixel-art way: shadows toward one hue, lights toward another.
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


def ramp_from_image(image_path, boxes, steps=4, shadow_shift=0.035, light_shift=-0.025, min_step=14, keep=None) -> list[str]:
    """A ramp of `steps` colours from pixel boxes (x0, y0, x1, y1) of a reference image.

    keep: optional function(pixels) -> pixels to drop neighbours and background inside the boxes.
    """
    from PIL import Image
    im = np.asarray(Image.open(image_path).convert("RGB")).astype(float)
    px = np.concatenate([im[y0:y1, x0:x1].reshape(-1, 3) for x0, y0, x1, y1 in boxes])
    if keep is not None:
        px = keep(px)
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
