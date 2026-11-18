"""Small pixel-art toolkit for item, particle, block and GUI textures: canvases, value noise, ramp fills with an
optional ordered dither, shapes, outlines, inventory-style panels and slots. `sprites` (below) runs the drawing
functions listed in mob/sprites.py and writes them under assets/<mod>/textures/.

Conventions that read as Minecraft: 16x16 items with a 1 px darker outline, light from the top left, 3-5 colours
per material from palette.json; particles 8x8 with strong silhouettes; GUI panels 176 px wide with 18 px slots.
"""
from __future__ import annotations

import json

import numpy as np
from PIL import Image

from . import palette, paths

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 - 0.47


def canvas(w, h):
    return np.zeros((h, w, 4), np.uint8)


def ramp(name):
    return np.array([palette.rgb(h) for h in palette.load()["ramps"][name]], np.uint8)


def noise(w, h, scale=4.0, seed=0, octaves=2):
    """Smooth value noise in 0..1 (the same picture for the same seed)."""
    rng = np.random.default_rng(seed)
    out, amp, total = np.zeros((h, w)), 1.0, 0.0
    ys, xs = np.mgrid[0:h, 0:w]
    for o in range(octaves):
        s = scale / (2 ** o)
        g = rng.random((int(h / s) + 2, int(w / s) + 2))
        fx, fy = xs / s, ys / s
        x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = fx - x0, fy - y0
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        out += (g[y0, x0] * (1 - tx) * (1 - ty) + g[y0, x0 + 1] * tx * (1 - ty) + g[y0 + 1, x0] * (1 - tx) * ty + g[y0 + 1, x0 + 1] * tx * ty) * amp
        total += amp
        amp *= 0.5
    return out / total


def fill(img, mask, ramp_name, value, dither=0.0):
    """Colour the masked pixels from a ramp by `value` (0 dark .. 1 light); dither 0.3 adds an ordered pattern."""
    r = ramp(ramp_name)
    h, w = mask.shape
    ys, xs = np.mgrid[0:h, 0:w]
    d = BAYER4[ys % 4, xs % 4] * dither
    idx = np.clip(np.floor(np.clip(value, 0, 1) * (len(r) - 1) + 0.5 + d), 0, len(r) - 1).astype(int)
    img[mask, :3] = r[idx][mask]
    img[mask, 3] = 255
    return img


def disc(w, h, cx, cy, radius):
    ys, xs = np.mgrid[0:h, 0:w]
    return (xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2 <= radius * radius


def light(w, h, dx=-0.6, dy=-0.8):
    """A 0..1 top-left light ramp across a w x h sprite, for fill()."""
    ys, xs = np.mgrid[0:h, 0:w]
    v = (xs / max(1, w - 1) - 0.5) * dx + (ys / max(1, h - 1) - 0.5) * dy
    return np.clip(0.5 + v, 0, 1)


def outline(img, colour):
    """A 1 px outline around the opaque pixels (outside them)."""
    a = img[..., 3] > 0
    out = np.zeros_like(a)
    out[:-1, :] |= a[1:, :]
    out[1:, :] |= a[:-1, :]
    out[:, :-1] |= a[:, 1:]
    out[:, 1:] |= a[:, :-1]
    out &= ~a
    img[out, :3] = colour
    img[out, 3] = 255
    return img


def panel(w=176, h=166, face=(198, 198, 198), lightc=(255, 255, 255), dark=(85, 85, 85)):
    """A vanilla-style GUI panel: bevelled face with rounded corners."""
    img = canvas(256, 256)
    img[0:h, 0:w, :3] = face
    img[0:h, 0:w, 3] = 255
    img[0:2, 0:w - 2, :3] = lightc
    img[0:h - 2, 0:2, :3] = lightc
    img[h - 2:h, 2:w, :3] = dark
    img[2:h, w - 2:w, :3] = dark
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        img[y, x, 3] = 0
    return img


def slot(img, x, y, size=18, face=(139, 139, 139), lightc=(255, 255, 255), dark=(55, 55, 55)):
    """An inventory slot whose inside starts at (x + 1, y + 1)."""
    img[y:y + size, x:x + size, :3] = face
    img[y:y + size, x:x + size, 3] = 255
    img[y, x:x + size - 1, :3] = dark
    img[y:y + size - 1, x, :3] = dark
    img[y + size - 1, x + 1:x + size, :3] = lightc
    img[y + 1:y + size, x + size - 1, :3] = lightc
    return img


def save(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img, "RGBA").save(path)
    return path


def run(args) -> int:
    from mob import sprites as MS
    written = 0
    for relative, draw in MS.SPRITES.items():
        target = paths.ASSETS / "textures" / relative
        save(draw(), target)
        written += 1
        if relative.startswith("item/"):
            model = paths.ASSETS / "models/item" / (target.stem + ".json")
            if not model.exists():
                paths.write_text(model, json.dumps({"parent": "minecraft:item/generated",
                                                    "textures": {"layer0": f"{paths.MOD}:item/{target.stem}"}}, indent=2) + "\n")
    print(f"sprites: {written} texture(s)")
    return 0


def validate(args) -> int:
    from mob import sprites as MS
    errs = []
    for relative in MS.SPRITES:
        target = paths.ASSETS / "textures" / relative
        if not target.is_file():
            errs.append(f"{relative} was not written")
            continue
        w, h = Image.open(target).size
        if relative.startswith(("item/", "particle/")) and (w != h or w & (w - 1)):
            errs.append(f"{relative} is {w}x{h}; item and particle sprites are square powers of two")
    for e in errs:
        print("SPRITE ERROR:", e)
    print(f"sprites validate: {len(errs)} error(s)")
    return 1 if errs else 0
