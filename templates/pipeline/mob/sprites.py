"""Item, particle, block and GUI textures of this mob, drawn in code (lib/pixel.py). Each entry maps a path under
assets/<mod>/textures/ to a function that returns an RGBA array. `build_assets.py sprites` writes them and, for
item/ paths, a generated item model when none exists.

Register the item, particle or screen in Java yourself; this file only keeps the art rerunnable and on palette.
"""
import numpy as np

from lib import pixel as px


def hide_scrap():
    """A drop: a rounded scrap of the mob's hide, lit from the top left, with a dark outline."""
    img = px.canvas(16, 16)
    body = px.disc(16, 16, 8, 8.5, 5.2) & ~px.disc(16, 16, 12.5, 4.0, 2.4)
    px.fill(img, body, "hide", px.light(16, 16) * 0.8 + px.noise(16, 16, 3.0, seed=4) * 0.25)
    return px.outline(img, px.ramp("hide")[0] // 2)


def spark():
    """An 8x8 particle: a small plus-shaped glint in the eye glow colour."""
    img = px.canvas(8, 8)
    mask = np.zeros((8, 8), bool)
    mask[3:5, 1:7] = True
    mask[1:7, 3:5] = True
    img[mask, :3] = px.ramp("eye")[2]
    img[mask, 3] = 255
    return img


SPRITES = {
    "item/sentinel_hide_scrap.png": hide_scrap,
    "particle/sentinel_spark.png": spark,
}
