"""The materials of this mob. Each function paints one cube face: it gets a lib.painter.Ctx (rest positions P,
smooth normals N, ambient occlusion, baked light, the part, the face) and returns rgb (h, w, 3), or
(rgb, glow) where glow is (h, w, 4): its alpha marks emissive texels for the glowmask.

Work in 3D, not in UV space: a stripe is `P[..., 1] > 14`, a spot is a distance to a point, a marking on the
left side is `P[..., 0] < 0`. Features then land in the right place on every face of every cube, whatever the
voxel layout does. Colours come from palette.json ramps through ctx.ramp() so shading stays in hard bands.
"""
import numpy as np


def hide(ctx):
    """Body: banded shading, a darker belly-to-back gradient by height, sparse speckles."""
    rgb = ctx.ramp("hide", thresholds=(0.34, 0.52, 0.70))
    speck = (ctx.noise(1.0, seed=3) > 0.975) & (ctx.light > 0.45)
    rgb[speck] = ctx.ramps["hide"][1]
    return rgb


def plate(ctx):
    """Harder, lighter material (snout, belly plate, ears, feet) with a one-texel specular chip."""
    rgb = ctx.ramp("plate", thresholds=(0.38, 0.62))
    rgb[ctx.specular(1.2)] = ctx.ramps["plate"][-1]
    return rgb


def eyes_open(ctx):
    """Pixel-art plate painted by position: two eyes with a glowing pupil; the rest of the plate is transparent."""
    x, y = ctx.P[..., 0], ctx.P[..., 1]
    rgba = np.zeros(ctx.P.shape[:2] + (4,), np.float32)
    glow = np.zeros_like(rgba)
    for cx in (-1.75, 1.75):
        white = (np.abs(x - cx) < 0.95) & (np.abs(y - 25.4) < 0.75)
        pupil = (np.abs(x - cx) < 0.4) & (np.abs(y - 25.4) < 0.55)
        rgba[white] = (*ctx.ramps["eye"][1], 255)
        rgba[pupil] = (*ctx.ramps["eye"][0], 255)
        glow[pupil] = (*ctx.ramps["eye"][2], 255)
    return rgba, glow


def eyes_closed(ctx):
    x, y = ctx.P[..., 0], ctx.P[..., 1]
    rgba = np.zeros(ctx.P.shape[:2] + (4,), np.float32)
    for cx in (-1.75, 1.75):
        lid = (np.abs(x - cx) < 0.95) & (np.abs(y - 25.2) < 0.2)
        rgba[lid] = (*ctx.ramps["hide"][0], 255)
    return rgba


MATERIALS = {"hide": hide, "plate": plate, "eyes_open": eyes_open, "eyes_closed": eyes_closed}
