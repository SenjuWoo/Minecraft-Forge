"""Texture painter: every texel is shaded from its rest-pose 3D position and the analytic normal of its shape, then
quantised to the palette ramps (palette.json). Vectorised per cube face; a per-texel Python loop is an order of
magnitude slower at about 1,000 cubes.

mob/paint.py supplies one function per material: it receives a Ctx (positions P, normals N, ambient occlusion,
light, the part and face) and returns rgb (h, w, 3 in 0..255) and optionally a glow layer (h, w, 4).

Outputs: textures/entity/<mob>.png, <mob>_glowmask.png (only when a material glows), <mob>_uvtest.png (the
orientation proof for the client: -Dmcforge.uvtest=true), and media/<mob>.bbmodel for inspection in Blockbench.

Style rules that held up next to vanilla blocks: hard light bands (3-5 steps per ramp, no gradients, no
anti-aliasing, no dithering), shadows shifted in hue instead of merely darker, one-texel highlights and creases
for small relief instead of extra cubes, and 2 texels per pixel so the model sits beside 16x and 32x packs.
"""
from __future__ import annotations

import base64
import io
import json
import uuid
from dataclasses import dataclass

import numpy as np
from PIL import Image

from . import modeltools, palette, paths, sdf
from .voxel import FACE_AXES, FACES, NORMALS, Cube, face_points

# Key, fill and rim directions the baked shading uses (model space). The game adds its own two entity lights on
# top, so the bake stays gentle: it shapes forms, it does not replace lighting.
LIGHT_KEY = np.array([0.35, 0.80, -0.50])
LIGHT_KEY /= np.linalg.norm(LIGHT_KEY)
LIGHT_FILL = np.array([-0.50, 0.30, -0.80])
LIGHT_FILL /= np.linalg.norm(LIGHT_FILL)
LIGHT_SKY = np.array([0.0, 1.0, 0.0])
UV_HUES = {"north": (230, 70, 60), "south": (60, 200, 90), "east": (70, 110, 240), "west": (240, 200, 60),
           "up": (230, 230, 230), "down": (150, 80, 190)}


@dataclass
class Ctx:
    part: modeltools.Part
    cube: Cube
    face: str
    P: np.ndarray        # (h, w, 3) rest-pose positions of the texel centres
    N: np.ndarray        # (h, w, 3) unit normals of the smooth surface
    ao: np.ndarray       # (h, w) 0.25..1 ambient occlusion from the neighbouring body
    light: np.ndarray    # (h, w) 0..1 baked light (key + fill + sky) times ao
    ramps: dict          # palette ramps as float arrays (steps, 3)

    def ramp(self, name, light=None, thresholds=None):
        """Quantise light to the steps of a ramp (hard bands). thresholds: ascending cut points in 0..1."""
        ramp = self.ramps[name]
        light = self.light if light is None else light
        steps = len(ramp)
        cuts = np.asarray(thresholds if thresholds is not None else [(i + 1) / steps for i in range(steps - 1)])
        return ramp[np.searchsorted(cuts, light)]

    def flat(self, name, step=-1):
        return np.broadcast_to(self.ramps[name][step], self.P.shape).copy()

    def noise(self, scale=1.0, seed=0):
        """Stable per-texel value noise in 0..1 from the 3D position (the same on every rebuild)."""
        q = np.floor(self.P * scale + 1e-3).astype(np.int64)
        h = (q[..., 0] * 73856093) ^ (q[..., 1] * 19349663) ^ (q[..., 2] * 83492791) ^ (seed * 2654435761)
        return ((h % 1024) / 1023.0).astype(np.float32)

    def specular(self, gloss=1.0):
        """Mask of the hard highlight (key light reflected toward the viewer side)."""
        return (self.N @ LIGHT_KEY) >= 0.985 - 0.03 * gloss


class Painter:
    def __init__(self, geo=""):
        self.parts = {p.name: p for p in modeltools.load_parts() if p.geo == geo}
        blobs = [p.shape for p in self.parts.values() if p.kind == "blob"]
        self.body = sdf.union(*blobs) if blobs else None
        pal = palette.load()
        self.ramps = {k: np.array([palette.rgb(h) for h in v], np.float32) for k, v in pal["ramps"].items()}

    def normals(self, part, face, P):
        if part.kind == "box":
            return np.broadcast_to(np.array(NORMALS[face], np.float32), P.shape).copy()
        shp = part.normal_shape or part.shape
        N = sdf.gradient(shp, P[..., 0], P[..., 1], P[..., 2])
        # one projection step onto the smooth surface: stepped voxel faces then read as one curved form
        Q = P - N * shp(P[..., 0], P[..., 1], P[..., 2])[..., None]
        N = sdf.gradient(shp, Q[..., 0], Q[..., 1], Q[..., 2])
        fn = np.array(NORMALS[face], np.float32)
        bad = (N @ fn) < -0.2    # keep the painted normal on the visible side of the face
        N[bad] = N[bad] * 0.3 + fn * 0.7
        return N / np.linalg.norm(N, axis=-1, keepdims=True)

    def ao(self, P, N):
        if self.body is None:
            return np.ones(P.shape[:-1], np.float32)
        acc = np.zeros(P.shape[:-1], np.float32)
        for k, dk in enumerate((0.8, 1.8, 3.2)):
            Q = P + N * dk
            dist = self.body(Q[..., 0], Q[..., 1], Q[..., 2])
            acc += np.clip((dk - np.maximum(dist, 0)) / dk, 0, 1) * (0.5 ** k)
        return np.clip(1.0 - acc * 0.42, 0.25, 1.0)

    def light(self, N, ao):
        # mostly sky (top lighter than sides, undersides darkest), a key from the front and a little fill: backs stay readable
        lam = 0.40 * np.clip(N @ LIGHT_KEY, 0, 1) + 0.15 * (0.5 + 0.5 * (N @ LIGHT_FILL)) + 0.45 * (0.5 + 0.5 * (N @ LIGHT_SKY))
        return np.clip((0.2 + 0.8 * lam) * ao, 0, 1)


def load_faces(geo=""):
    return json.loads((paths.BUILD / f"{modeltools.geo_name(geo)}_faces.json").read_text(encoding="utf-8"))


def paint(geo=""):
    """Paint one geometry. Returns (base RGBA, glow RGBA, faces json)."""
    from mob import paint as MP
    fj = load_faces(geo)
    W, H = fj["texture"]
    pt = Painter(geo)
    base = np.zeros((H, W, 4), np.uint8)
    glow = np.zeros((H, W, 4), np.uint8)
    for c in fj["cubes"]:
        cube = Cube(c["name"], c["blob"], c["bone"], tuple(c["lo"]), tuple(c["hi"]), list(c["uv"]), c["tpp"], c["mat"], c["uv"])
        part = pt.parts[cube.blob]
        fn = MP.MATERIALS.get(cube.material)
        if fn is None:
            raise ValueError(f"part {part.name}: no material {cube.material!r} in mob/paint.py MATERIALS")
        for face, (u, v, w, h) in c["uv"].items():
            P = face_points(cube, face, w, h)
            N = pt.normals(part, face, P)
            ao = pt.ao(P, N) if part.kind == "blob" else np.ones((h, w), np.float32)
            out = fn(Ctx(part, cube, face, P, N, ao, pt.light(N, ao), pt.ramps))
            rgb, gl = out if isinstance(out, tuple) else (out, None)
            if rgb.shape[-1] == 4:
                base[v:v + h, u:u + w] = np.clip(rgb, 0, 255).astype(np.uint8)
            else:
                base[v:v + h, u:u + w, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
                base[v:v + h, u:u + w, 3] = 255
            if gl is not None:
                glow[v:v + h, u:u + w] = np.clip(gl, 0, 255).astype(np.uint8)
    return base, glow, fj


def paint_uvtest(fj):
    """Orientation proof: a hue per face direction, dark to bright along u, a white band on the first rows of v.
    In a client screenshot every side face must read dark-left to bright-right with the band on top; the top face
    brightens toward the model's left (-X) with the band at its back edge (+Z), the bottom face brightens toward
    -X with the band at its front edge (-Z)."""
    W, H = fj["texture"]
    img = np.zeros((H, W, 4), np.uint8)
    for c in fj["cubes"]:
        for face, (u, v, w, h) in c["uv"].items():
            ramp = 0.25 + 0.75 * (np.arange(w) + 0.5) / w
            col = (np.array(UV_HUES[face], np.float32)[None, None, :] * ramp[None, :, None]).repeat(h, 0)
            if h > 1:
                col[:max(1, int(round(h * 0.18)))] = 255
            img[v:v + h, u:u + w, :3] = col.astype(np.uint8)
            img[v:v + h, u:u + w, 3] = 255
    return img


def bbmodel(name, fj, png: bytes) -> dict:
    """A Blockbench project (generic model, per-face UV) for looking at the result; the generator stays the source."""
    m = json.loads((paths.BUILD / "rig_manifest.json").read_text(encoding="utf-8"))
    W, H = fj["texture"]
    pivots = {b["name"]: b["pivot"] for b in m["bones"]}

    def uid(*parts):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "/".join((name,) + parts)))
    elements, groups = [], {}
    for c in fj["cubes"]:
        faces = {}
        for f in FACES:
            if f in c["uv"]:
                u, v, w, h = c["uv"][f]
                faces[f] = {"uv": [u, v, u + w, v + h], "texture": 0}
            else:
                faces[f] = {"uv": [0, 0, 0, 0], "texture": None}
        e = {"name": c["name"], "type": "cube", "uuid": uid(c["name"]), "box_uv": False, "from": list(c["lo"]), "to": list(c["hi"]),
             "origin": list(pivots[c["bone"]]), "rotation": [0, 0, 0], "autouv": 0, "color": 0, "faces": faces}
        elements.append(e)
        groups.setdefault(c["bone"], []).append(e["uuid"])

    def outline(parent):
        return [{"name": b["name"], "uuid": uid(b["name"], "group"), "origin": list(b["pivot"]), "rotation": [0, 0, 0], "isOpen": False,
                 "children": groups.get(b["name"], []) + outline(b["name"])} for b in m["bones"] if b["parent"] == parent]
    source = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return {"meta": {"format_version": "4.10", "model_format": "free", "box_uv": False}, "name": name,
            "resolution": {"width": W, "height": H}, "elements": elements, "outliner": outline(None),
            "textures": [{"name": f"{name}.png", "id": "0", "uuid": uid("texture"), "mode": "bitmap", "saved": False, "particle": False,
                          "visible": True, "width": W, "height": H, "uv_width": W, "uv_height": H, "source": source}]}


def _png(arr) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, "PNG")
    return buf.getvalue()


def run(args) -> int:
    paths.ensure(paths.TEX, paths.MEDIA)
    for geo in modeltools.geos():
        name = modeltools.geo_name(geo)
        base, glow, fj = paint(geo)
        png = _png(base)
        (paths.TEX / f"{name}.png").write_bytes(png)
        mask = paths.TEX / f"{name}_glowmask.png"
        if glow[..., 3].any():
            mask.write_bytes(_png(glow))
        elif mask.exists():
            mask.unlink()
        (paths.TEX / f"{name}_uvtest.png").write_bytes(_png(paint_uvtest(fj)))
        paths.write_json(paths.MEDIA / f"{name}.bbmodel", bbmodel(name, fj, png))
        cols = len(np.unique(base[base[..., 3] > 0][:, :3].reshape(-1, 3), axis=0))
        print(f"texture {name}: {base.shape[1]}x{base.shape[0]}, {cols} colours, glow {'yes' if glow[..., 3].any() else 'no'}")
    return 0


def validate(args) -> int:
    errs = []
    pal = palette.load()
    allowed = {palette.rgb(h) for ramp in pal["ramps"].values() for h in ramp}
    for geo in modeltools.geos():
        name = modeltools.geo_name(geo)
        fj = load_faces(geo)
        W, H = fj["texture"]
        occ = np.zeros((H, W), np.int32)
        for c in fj["cubes"]:
            for f, (u, v, w, h) in c["uv"].items():
                if u < 0 or v < 0 or u + w > W or v + h > H:
                    errs.append(f"{c['name']} {f}: UV outside {W}x{H}")
                else:
                    occ[v:v + h, u:u + w] += 1
        if (occ > 1).any():
            errs.append(f"{name}: {int((occ > 1).sum())} texels claimed by more than one face")
        img = np.asarray(Image.open(paths.TEX / f"{name}.png").convert("RGBA"))
        if img.shape[:2] != (H, W):
            errs.append(f"{name}.png is {img.shape[1]}x{img.shape[0]}, the model expects {W}x{H} (rerun texture after model)")
            continue
        used = {tuple(int(v) for v in c) for c in np.unique(img[(occ > 0) & (img[..., 3] > 0)][:, :3].reshape(-1, 3), axis=0)}
        stray = sorted(used - allowed)
        print(f"{name}: {len(used)} colours, {len(stray)} outside the palette")
        if stray and pal.get("strict", True):
            errs.append(f"{name}: {len(stray)} colours outside palette.json, e.g. {stray[:4]} (add a ramp or set \"strict\": false)")
        mask = paths.TEX / f"{name}_glowmask.png"
        if mask.exists():
            g = np.asarray(Image.open(mask).convert("RGBA"))
            if g.shape[:2] != (H, W):
                errs.append(f"{name}_glowmask.png size differs from the base texture (GeckoLib rejects it)")
            if not g[..., 3].any():
                errs.append(f"{name}_glowmask.png has no opaque texel (GeckoLib rejects it)")
    for n, ramp in pal["ramps"].items():
        if len(ramp) > 6:
            errs.append(f"ramp {n} has {len(ramp)} steps; hard pixel-art ramps use 3-5")
    for e in errs:
        print("TEXTURE ERROR:", e)
    print(f"texture validate: {len(errs)} error(s)")
    return 1 if errs else 0


__all__ = ["Ctx", "Painter", "paint", "paint_uvtest", "FACE_AXES"]
