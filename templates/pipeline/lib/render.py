"""Offline preview renderer for the GeckoLib model: orthographic numpy rasteriser with the game's entity lighting.

- Geometry in Blockbench space (geo x un-mirrored), bone transforms M = T(pos) T(pivot) Rz Ry Rx S T(-pivot),
  parent first (GeckoLib's order). Poses are {bone: (rot deg, pos px, scale)} offsets from rest, as the animation
  toolkit produces them; visibility is a set of hidden bones (children follow).
- Per-face UV orientation comes from voxel.FACE_AXES; nearest sampling, alpha cutout at 0.5.
- Lighting: shade = min(1, 0.6 (max(0, n.L0) + max(0, n.L1)) + 0.4), L0 = (0.2, 1, -0.7), L1 = (-0.2, 1, 0.7)
  (com.mojang.blaze3d.platform.Lighting), times a light-level factor; glowmask texels stay unlit. Physically based
  lights make backs black and voxel steps noisy, which misleads tuning; this matches in-game screenshots.
- The model is turned by `yaw` (degrees; 0 = its front faces the camera, 180 = its back) and the camera is tilted
  by `pitch` (positive looks down on it).
"""
from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image, ImageDraw

from .voxel import NORMALS, face_corners

L0 = np.array([0.2, 1.0, -0.7])
L0 /= np.linalg.norm(L0)
L1 = np.array([-0.2, 1.0, 0.7])
L1 /= np.linalg.norm(L1)


def T(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def S(x, y, z):
    return np.diag([x, y, z, 1.0])


def R(rx, ry, rz):
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    X = np.array([[1, 0, 0, 0], [0, math.cos(a), -math.sin(a), 0], [0, math.sin(a), math.cos(a), 0], [0, 0, 0, 1]])
    Y = np.array([[math.cos(b), 0, math.sin(b), 0], [0, 1, 0, 0], [-math.sin(b), 0, math.cos(b), 0], [0, 0, 0, 1]])
    Z = np.array([[math.cos(c), -math.sin(c), 0, 0], [math.sin(c), math.cos(c), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    return Z @ Y @ X


class Model:
    def __init__(self, geo_path, texture_path=None, glow_path=None):
        geo = json.loads(open(geo_path, encoding="utf-8").read())["minecraft:geometry"][0]
        self.W = geo["description"]["texture_width"]
        self.H = geo["description"]["texture_height"]
        self.bones = {}
        self.order = []
        for b in geo["bones"]:
            piv = (-b["pivot"][0], b["pivot"][1], b["pivot"][2])
            rot = b.get("rotation", [0, 0, 0])
            cubes = []
            for c in b.get("cubes", []):
                o, s = c["origin"], c["size"]
                lo = (-o[0] - s[0], o[1], o[2])
                hi = (-o[0], o[1] + s[1], o[2] + s[2])
                cubes.append((lo, hi, {f: (uv["uv"][0], uv["uv"][1], uv["uv_size"][0], uv["uv_size"][1]) for f, uv in c["uv"].items()}))
            self.bones[b["name"]] = {"parent": b.get("parent"), "pivot": piv, "rest": (-rot[0], -rot[1], rot[2]), "cubes": cubes}
            self.order.append(b["name"])
        self.tex = self.glow = None
        if texture_path:
            self.tex = np.asarray(Image.open(texture_path).convert("RGBA")).astype(np.float32) / 255.0
        if glow_path:
            self.glow = np.asarray(Image.open(glow_path).convert("RGBA")).astype(np.float32) / 255.0

    def matrices(self, pose=None):
        pose = pose or {}
        mats = {}
        for name in self.order:
            b = self.bones[name]
            rot, pos, scl = pose.get(name, ((0, 0, 0), (0, 0, 0), (1, 1, 1)))
            r = tuple(b["rest"][i] + rot[i] for i in range(3))
            piv = b["pivot"]
            m = T(*pos) @ T(*piv) @ R(*r) @ S(*scl) @ T(-piv[0], -piv[1], -piv[2])
            mats[name] = (mats[b["parent"]] @ m) if b["parent"] else m
        return mats

    def chain(self, bone):
        out = []
        while bone:
            out.append(bone)
            bone = self.bones[bone]["parent"]
        return out[::-1]

    def bone_matrix(self, pose, bone):
        """Model-space matrix of one bone under a pose (only its parent chain is evaluated)."""
        M = np.eye(4)
        for name in self.chain(bone):
            b = self.bones[name]
            rot, pos, scl = (pose or {}).get(name, ((0, 0, 0), (0, 0, 0), (1, 1, 1)))
            r = tuple(b["rest"][i] + rot[i] for i in range(3))
            piv = b["pivot"]
            M = M @ (T(*pos) @ T(*piv) @ R(*r) @ S(*scl) @ T(-piv[0], -piv[1], -piv[2]))
        return M

    def hidden_closure(self, hidden):
        out = set(hidden)
        for name in self.order:
            if self.bones[name]["parent"] in out:
                out.add(name)
        return out

    def descendants(self, roots):
        """The named bones and every bone below them."""
        out = set(roots)
        for name in self.order:
            if self.bones[name]["parent"] in out:
                out.add(name)
        return out

    def lowest_point(self, pose, bones=None, hidden=()):
        """Lowest y (px) of the posed cube corners of `bones` and their children (all bones when None)."""
        mats = self.matrices(pose)
        hid = self.hidden_closure(hidden)
        keep = self.descendants(bones) if bones else set(self.order)
        low = 1e9
        for name in self.order:
            if name in hid or name not in keep:
                continue
            M = mats[name]
            for lo, hi, _ in self.bones[name]["cubes"]:
                for x in (lo[0], hi[0]):
                    for y in (lo[1], hi[1]):
                        for z in (lo[2], hi[2]):
                            low = min(low, M[1, 0] * x + M[1, 1] * y + M[1, 2] * z + M[1, 3])
        return low


def render(model: Model, yaw=0.0, pitch=10.0, scale=8.0, size=None, pose=None, hidden=(), light=1.0,
           bg=(40, 36, 58), glow=True, center=None, tex=None):
    """Return an RGB uint8 image. scale = screen px per model px."""
    mats = model.matrices(pose)
    hid = model.hidden_closure(hidden)
    tex = model.tex if tex is None else tex
    ya, pa = math.radians(yaw), math.radians(pitch)
    Rw = np.array([[math.cos(ya), 0, math.sin(ya)], [0, 1, 0], [-math.sin(ya), 0, math.cos(ya)]])
    # camera at -Z looking +Z, tilted down by pitch: screen right = -X, screen up = +Y
    cp, sp = math.cos(pa), math.sin(pa)
    right = np.array([-1.0, 0.0, 0.0])
    up = np.array([0.0, cp, sp])
    fwd = np.array([0.0, -sp, cp])
    quads = []
    for name in model.order:
        if name in hid:
            continue
        M = mats[name]
        for lo, hi, uvs in model.bones[name]["cubes"]:
            for f, (u, v, w, h) in uvs.items():
                corners = face_corners(lo, hi, f)
                P = np.array([M @ np.array([*c, 1.0]) for c, _ in corners])[:, :3] @ Rw.T
                n = M[:3, :3] @ np.array(NORMALS[f], float)
                n = Rw @ (n / (np.linalg.norm(n) or 1))
                if n @ fwd > 1e-6:   # back face
                    continue
                st = np.array([s for _, s in corners], float)
                UV = np.stack([u + st[:, 0] * w, v + st[:, 1] * h], -1)
                shade = min(1.0, 0.6 * (max(0, n @ L0) + max(0, n @ L1)) + 0.4)
                quads.append((P, UV, shade))
    if not quads:
        return np.zeros((8, 8, 3), np.uint8)
    allP = np.concatenate([q[0] for q in quads])
    sx, sy = allP @ right, allP @ up
    if center is None:
        center = ((sx.min() + sx.max()) / 2, (sy.min() + sy.max()) / 2)
    if size is None:
        size = (int((sx.max() - sx.min()) * scale) + 24, int((sy.max() - sy.min()) * scale) + 24)
    Wi, Hi = size
    img = np.empty((Hi, Wi, 3), np.float32)
    img[:] = np.array(bg, np.float32) / 255
    zb = np.full((Hi, Wi), np.inf, np.float32)
    TH, TW = tex.shape[:2]
    for P, UV, shade in quads:
        X = (P @ right - center[0]) * scale + Wi / 2
        Y = Hi / 2 - (P @ up - center[1]) * scale
        D = P @ fwd
        for tri in ((0, 1, 2), (0, 2, 3)):
            x, y, d, uv = X[list(tri)], Y[list(tri)], D[list(tri)], UV[list(tri)]
            x0, x1 = int(max(0, math.floor(x.min()))), int(min(Wi - 1, math.ceil(x.max())))
            y0, y1 = int(max(0, math.floor(y.min()))), int(min(Hi - 1, math.ceil(y.max())))
            if x1 < x0 or y1 < y0:
                continue
            den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
            if abs(den) < 1e-9:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
            b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
            c = 1 - a - b
            m = (a >= -1e-4) & (b >= -1e-4) & (c >= -1e-4)
            if not m.any():
                continue
            dd = a * d[0] + b * d[1] + c * d[2]
            sub = zb[y0:y1 + 1, x0:x1 + 1]
            m &= dd < sub
            if not m.any():
                continue
            U = a * uv[0, 0] + b * uv[1, 0] + c * uv[2, 0]
            V = a * uv[0, 1] + b * uv[1, 1] + c * uv[2, 1]
            ui = np.clip(np.floor(U).astype(int), 0, TW - 1)
            vi = np.clip(np.floor(V).astype(int), 0, TH - 1)
            texel = tex[vi, ui]
            m &= texel[..., 3] >= 0.5
            if not m.any():
                continue
            col = texel[..., :3] * (shade * light)
            if glow and model.glow is not None:
                g = model.glow[vi, ui]
                gm = g[..., 3:4]
                col = col * (1 - gm) + np.maximum(col, g[..., :3]) * gm
            reg = img[y0:y1 + 1, x0:x1 + 1]
            reg[m] = col[m]
            sub[m] = dd[m]
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def sheet(images, labels=None, cols=4, pad=6, bg=(24, 22, 36)):
    """Tile images into a contact sheet with optional labels."""
    ims = [Image.fromarray(i) if isinstance(i, np.ndarray) else i for i in images]
    cw = max(i.width for i in ims)
    ch = max(i.height for i in ims) + 16
    rows = math.ceil(len(ims) / cols)
    out = Image.new("RGB", (cols * (cw + pad) + pad, rows * (ch + pad) + pad), bg)
    d = ImageDraw.Draw(out)
    for k, im in enumerate(ims):
        r, c = divmod(k, cols)
        x, y = pad + c * (cw + pad), pad + r * (ch + pad)
        out.paste(im, (x + (cw - im.width) // 2, y + 16))
        if labels:
            d.text((x + 2, y + 2), labels[k], fill=(230, 230, 240))
    return out
