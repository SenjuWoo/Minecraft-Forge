"""Voxelisation, greedy box partition, buried-face culling, cross-blob z-fight avoidance and atlas packing.

A blob's occupied cells are greedy-merged into a partition of boxes (no two same-facing coplanar faces of one
blob overlap). Each blob then tries sub-pixel grid offsets (multiples of 0.03 px) until none of its visible
faces lies within 0.012 px of a visible same-facing face of an earlier blob (the toolkit's model-check flags
0.01 px). Faces whose outside neighbour layer belongs to the same blob get no UV: GeckoLib builds no quad for
them, so they cost neither draw time nor atlas space.

FACE_AXES is the single source of truth for per-face UV direction (model space, seen from outside): the
direction in which u and v grow. It is GeckoLib 4.9.3's mapping, read from its quad builder and proven with a
UV test texture in a client (guide api). face_points() and the preview renderer both derive from it, so a
painter works in 3D and never thinks about UV orientation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FACES = ("north", "south", "east", "west", "up", "down")
NORMALS = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}
FACE_AXES = {
    "north": ((-1, 0, 0), (0, -1, 0)),
    "south": ((1, 0, 0), (0, -1, 0)),
    "east": ((0, 0, -1), (0, -1, 0)),
    "west": ((0, 0, 1), (0, -1, 0)),
    "up": ((-1, 0, 0), (0, 0, -1)),
    "down": ((-1, 0, 0), (0, 0, 1)),
}
STEP = 0.03
PLANE_WINDOW = 0.012
BUCKET = 0.005


@dataclass
class Cube:
    name: str
    blob: str
    bone: str
    lo: tuple
    hi: tuple
    faces: list
    tpp: float
    material: str = ""
    uv: dict = field(default_factory=dict)

    def size(self):
        return tuple(self.hi[i] - self.lo[i] for i in range(3))


def voxelize(shape, cell: float, offset: float = 0.0):
    lo, hi = np.asarray(shape.bounds[0]), np.asarray(shape.bounds[1])
    n = np.maximum(1, np.ceil((hi - lo) / cell - 1e-6).astype(int))
    if int(np.prod(n)) > 4_000_000:
        raise ValueError(f"grid {n} too large; raise the cell size")
    origin = (lo + hi) / 2 - n * cell / 2 + offset
    xs = origin[0] + (np.arange(n[0]) + 0.5) * cell
    ys = origin[1] + (np.arange(n[1]) + 0.5) * cell
    zs = origin[2] + (np.arange(n[2]) + 0.5) * cell
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return shape(X, Y, Z) < 0, origin


def partition(occ: np.ndarray, order: str = "yxz"):
    axes = ["xyz".index(ch) for ch in order]
    left = occ.copy()
    n = occ.shape
    boxes = []
    for i, j, k in np.argwhere(occ):
        if not left[i, j, k]:
            continue
        lo, hi = [i, j, k], [i + 1, j + 1, k + 1]
        for ax in axes:
            while hi[ax] < n[ax]:
                sl = [slice(lo[0], hi[0]), slice(lo[1], hi[1]), slice(lo[2], hi[2])]
                sl[ax] = slice(hi[ax], hi[ax] + 1)
                if left[tuple(sl)].all():
                    hi[ax] += 1
                else:
                    break
        left[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = False
        boxes.append((lo, hi))
    return boxes


def buried(occ: np.ndarray, lo, hi) -> set:
    names = {(0, -1): "west", (0, 1): "east", (1, -1): "down", (1, 1): "up", (2, -1): "north", (2, 1): "south"}
    out = set()
    n = occ.shape
    for ax in range(3):
        for side in (-1, 1):
            layer = lo[ax] - 1 if side < 0 else hi[ax]
            if layer < 0 or layer >= n[ax]:
                continue
            sl = [slice(lo[0], hi[0]), slice(lo[1], hi[1]), slice(lo[2], hi[2])]
            sl[ax] = slice(layer, layer + 1)
            if occ[tuple(sl)].all():
                out.add(names[(ax, side)])
    return out


def _face_planes(lo, hi, faces):
    for f in faces:
        ax = {"west": 0, "east": 0, "down": 1, "up": 1, "north": 2, "south": 2}[f]
        sign = 1 if f in ("east", "up", "south") else -1
        plane = hi[ax] if sign > 0 else lo[ax]
        rect = tuple((lo[b], hi[b]) for b in range(3) if b != ax)
        yield ax, sign, plane, rect


class Placer:
    """Tracks visible faces of placed blobs to pick a clash-free sub-pixel offset for each new blob."""

    def __init__(self):
        self.placed = {}

    def conflicts(self, cand) -> int:
        count = 0
        span = int(np.ceil(PLANE_WINDOW / BUCKET)) + 1
        for lo, hi, faces in cand:
            for ax, sign, plane, rect in _face_planes(lo, hi, faces):
                b = round(plane / BUCKET)
                for key in ((ax, sign, b + d) for d in range(-span, span + 1)):
                    for op, orect in self.placed.get(key, ()):
                        if abs(op - plane) <= PLANE_WINDOW and all(min(a[1], c[1]) - max(a[0], c[0]) > 1e-3 for a, c in zip(rect, orect)):
                            count += 1
        return count

    def add(self, cand):
        for lo, hi, faces in cand:
            for ax, sign, plane, rect in _face_planes(lo, hi, faces):
                self.placed.setdefault((ax, sign, round(plane / BUCKET)), []).append((plane, rect))


def voxel_blob(placer: Placer, name, shape, cell, bone, tpp, material="", orders=("yxz", "xyz", "zyx"), hide_faces=()):
    """Voxelise one blob; returns (cubes, clashes, offset). Tries three greedy orders and keeps the fewest boxes."""
    best = None
    # fine cells search finer offsets (still wider than PLANE_WINDOW), or a small part runs out of clash-free shifts
    step = max(PLANE_WINDOW * 1.1, min(STEP, cell / 12))
    for attempt in range(max(1, int(cell / step))):
        off = step * attempt
        occ, origin = voxelize(shape, cell, off)
        if not occ.any():
            raise ValueError(f"blob {name} is empty at cell {cell}")
        bestp = None
        for order in orders:
            parts = partition(occ, order)
            if bestp is None or len(parts) < len(bestp):
                bestp = parts
        cand = []
        for lo, hi in bestp:
            low = tuple(round(float(origin[a] + lo[a] * cell), 4) for a in range(3))
            high = tuple(round(float(origin[a] + hi[a] * cell), 4) for a in range(3))
            b = buried(occ, lo, hi) | set(hide_faces)
            cand.append((low, high, [f for f in FACES if f not in b]))
        clashes = placer.conflicts(cand)
        if best is None or clashes < best[0]:
            best = (clashes, off, cand)
        if clashes == 0:
            break
    clashes, off, cand = best
    placer.add(cand)
    cubes = [Cube(f"{name}_{i}", name, bone, lo, hi, faces, tpp, material) for i, (lo, hi, faces) in enumerate(cand) if faces]
    return cubes, clashes, off


def box_part(placer: Placer, name, lo, hi, bone, tpp, material="", faces=FACES):
    """One hand-placed box (plates, eyes, buckles). Returns (cubes, clashes)."""
    cand = [(tuple(map(float, lo)), tuple(map(float, hi)), list(faces))]
    clashes = placer.conflicts(cand)
    placer.add(cand)
    return [Cube(name, name, bone, cand[0][0], cand[0][1], list(faces), tpp, material)], clashes


def face_dims(face, size):
    w, h, d = size
    return {"north": (w, h), "south": (w, h), "east": (d, h), "west": (d, h), "up": (w, d), "down": (w, d)}[face]


def face_corners(lo, hi, face):
    """The four corners of a face as (point, (s, t)) for (0,0), (1,0), (1,1), (0,1): s along u, t along v."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    n = np.asarray(NORMALS[face], float)
    u, v = (np.asarray(d, float) for d in FACE_AXES[face])
    origin = np.where(n > 0, hi, lo).astype(float)
    for d in (u, v):
        ax = int(np.argmax(np.abs(d)))
        origin[ax] = lo[ax] if d[ax] > 0 else hi[ax]
    su = float(np.abs(u) @ (hi - lo))
    sv = float(np.abs(v) @ (hi - lo))
    return [(tuple(origin + u * su * s + v * sv * t), (s, t)) for s, t in ((0, 0), (1, 0), (1, 1), (0, 1))]


def face_points(cube: Cube, face: str, w: int, h: int):
    """Rest-pose 3D positions (h, w, 3) of the texel centres of one face."""
    lo, hi = np.asarray(cube.lo, float), np.asarray(cube.hi, float)
    n = np.asarray(NORMALS[face], float)
    u, v = (np.asarray(d, float) for d in FACE_AXES[face])
    origin = np.where(n > 0, hi, lo).astype(float)
    for d in (u, v):
        ax = int(np.argmax(np.abs(d)))
        origin[ax] = lo[ax] if d[ax] > 0 else hi[ax]
    su = float(np.abs(u) @ (hi - lo))
    sv = float(np.abs(v) @ (hi - lo))
    S, T = np.meshgrid((np.arange(w) + 0.5) / w, (np.arange(h) + 0.5) / h)
    return origin + S[..., None] * (u * su) + T[..., None] * (v * sv)


def pack(rects, max_size=4096):
    """Shelf-pack (w, h) rectangles into a power-of-two square-ish atlas."""
    area = sum(w * h for w, h in rects)
    width = 64
    while width * width < area * 1.18 or width < max((w for w, _ in rects), default=1):
        width *= 2
    while True:
        order = sorted(range(len(rects)), key=lambda i: (-rects[i][1], -rects[i][0]))
        pos = [None] * len(rects)
        x = y = shelf = 0
        for i in order:
            w, h = rects[i]
            if x + w > width:
                x, y, shelf = 0, y + shelf, 0
            pos[i] = (x, y)
            x += w
            shelf = max(shelf, h)
        height = 64
        while height < y + shelf:
            height *= 2
        if height <= width:
            break
        width *= 2
        if width > max_size:
            raise ValueError("atlas overflow: lower texels per pixel or raise the cell size")
    return pos, width, height


def assign_uv(cubes):
    rects, owners = [], []
    for c in cubes:
        for f in c.faces:
            fw, fh = face_dims(f, c.size())
            rects.append((max(1, round(fw * c.tpp)), max(1, round(fh * c.tpp))))
            owners.append((c, f))
    pos, W, H = pack(rects)
    for (c, f), (x, y), (w, h) in zip(owners, pos, rects):
        c.uv[f] = (x, y, w, h)
    return W, H
