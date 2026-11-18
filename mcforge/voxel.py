"""Implicit shapes -> Minecraft-style voxel cubes for GeckoLib (geo.json + texture + Blockbench project).

Organic parts are written as implicit shapes (ellipsoids, superellipsoids, tapered
capsules, boxes, unions, smooth unions, subtractions), voxelized on an axis-aligned
grid and greedy-merged into a *partition* of boxes. Two boxes of a partition never
have overlapping same-facing coplanar faces, so a blob cannot z-fight with itself.
Each blob tries sub-pixel grid offsets (multiples of 0.03 px) until none of its
visible faces lies on a visible face of an earlier blob. Faces whose whole outside neighbour layer belongs to the
blob are left out of the per-face UV map: GeckoLib builds no quad for a missing
face (4.9.3, BakedModelFactory.buildQuad), so they cost neither draw time nor atlas
space. Coordinates are Blockbench model pixels (y up, the model faces north/-Z).

Spec (JSON):

    {"name": "bog_toad", "cell": 0.8, "texels_per_pixel": 2,
     "bones": [{"name": "root", "pivot": [0, 0, 0]},
               {"name": "body", "parent": "root", "pivot": [0, 6, 0]}],
     "blobs": [{"name": "belly", "bone": "body", "color": "#6f8f3a",
                "shape": {"smooth_union": {"k": 0.4, "of": [
                    {"ellipsoid": {"center": [0, 6, 0], "radii": [6, 4.5, 7]}},
                    {"capsule": {"a": [0, 8, -5], "b": [0, 10, -8], "ra": 3, "rb": 2.2}}]}}}]}

Shapes: ellipsoid {center, radii}, superellipsoid {center, radii, exponent},
capsule {a, b, ra, rb}, box {min, max}, torus {center, axis, major, minor},
halfspace {point, normal} (inside where (p - point) . normal < 0; only inside
intersect or subtract), union [shapes], smooth_union {k, of}, intersect [shapes],
subtract {from, remove}. A blob may set its own "cell", "texels_per_pixel" and
"order" (greedy axis order, default "yxz").
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import random
import re

from .modelcheck import check_model
from .pixelart import blank, png_bytes, put
from .shapes import _texture_entry, _uuid

FACES = ("north", "south", "east", "west", "up", "down")
MAX_CELLS = 2_000_000
MAX_ATLAS = 4096
# model-check flags same-facing planes closer than 0.01 px; blobs keep a slightly wider window between visible faces.
PLANE_WINDOW = 0.012
PLANE_BUCKET = 0.005
UNBOUNDED = 1.0e6
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")


# ------------------------------------------------------------------ implicit shapes
def _vec(value, name, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length or not all(isinstance(v, (int, float)) for v in value):
        raise ValueError(f"{name} must be a list of {length} numbers")
    return tuple(float(v) for v in value)


def _positive(value, name):
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def build_shape(spec) -> tuple:
    """Return (f(x, y, z) -> value < 0 inside, (low, high) bounds)."""
    if not isinstance(spec, dict) or len(spec) != 1:
        raise ValueError(f"A shape is an object with one key, got {spec!r}")
    kind, body = next(iter(spec.items()))
    if kind in ("ellipsoid", "superellipsoid"):
        c = _vec(body.get("center"), f"{kind}.center")
        r = tuple(_positive(v, f"{kind}.radii") for v in _vec(body.get("radii"), f"{kind}.radii"))
        n = _positive(body.get("exponent", 2.0 if kind == "ellipsoid" else 2.5), f"{kind}.exponent")
        if n == 2.0:
            def f(x, y, z):
                return ((x - c[0]) / r[0]) ** 2 + ((y - c[1]) / r[1]) ** 2 + ((z - c[2]) / r[2]) ** 2 - 1
        else:
            def f(x, y, z):
                return abs((x - c[0]) / r[0]) ** n + abs((y - c[1]) / r[1]) ** n + abs((z - c[2]) / r[2]) ** n - 1
        return f, (tuple(c[i] - r[i] for i in range(3)), tuple(c[i] + r[i] for i in range(3)))
    if kind == "capsule":
        a, b = _vec(body.get("a"), "capsule.a"), _vec(body.get("b"), "capsule.b")
        ra = _positive(body.get("ra"), "capsule.ra")
        rb = _positive(body.get("rb", ra), "capsule.rb")
        d = tuple(b[i] - a[i] for i in range(3))
        length2 = sum(v * v for v in d) or 1e-9

        def f(x, y, z):
            p = (x - a[0], y - a[1], z - a[2])
            t = min(1.0, max(0.0, (p[0] * d[0] + p[1] * d[1] + p[2] * d[2]) / length2))
            q = (p[0] - t * d[0], p[1] - t * d[1], p[2] - t * d[2])
            r = ra + (rb - ra) * t
            return (q[0] * q[0] + q[1] * q[1] + q[2] * q[2]) / (r * r) - 1
        big = max(ra, rb)
        return f, (tuple(min(a[i], b[i]) - big for i in range(3)), tuple(max(a[i], b[i]) + big for i in range(3)))
    if kind == "box":
        low, high = _vec(body.get("min"), "box.min"), _vec(body.get("max"), "box.max")
        if any(high[i] <= low[i] for i in range(3)):
            raise ValueError("box.max must exceed box.min on every axis")
        c = tuple((low[i] + high[i]) / 2 for i in range(3))
        h = tuple((high[i] - low[i]) / 2 for i in range(3))

        def f(x, y, z):
            return max(abs(x - c[0]) / h[0], abs(y - c[1]) / h[1], abs(z - c[2]) / h[2]) - 1
        return f, (low, high)
    if kind in ("union", "smooth_union"):
        items = body if kind == "union" else body.get("of")
        if not isinstance(items, list) or not items:
            raise ValueError(f"{kind} needs a non-empty list of shapes")
        parts = [build_shape(item) for item in items]
        functions = [part[0] for part in parts]
        low = tuple(min(part[1][0][i] for part in parts) for i in range(3))
        high = tuple(max(part[1][1][i] for part in parts) for i in range(3))
        if kind == "union":
            return (lambda x, y, z: min(g(x, y, z) for g in functions)), (low, high)
        k = _positive(body.get("k", 0.5), "smooth_union.k")

        def f(x, y, z):
            v = functions[0](x, y, z)
            for g in functions[1:]:
                w = g(x, y, z)
                h = min(1.0, max(0.0, 0.5 + 0.5 * (w - v) / k))
                v = w * (1 - h) + v * h - k * h * (1 - h)
            return v
        # The blend can swell past the parts; leave room for it.
        margin = tuple((high[i] - low[i]) * 0.15 for i in range(3))
        return f, (tuple(low[i] - margin[i] for i in range(3)), tuple(high[i] + margin[i] for i in range(3)))
    if kind == "subtract":
        keep, cut = build_shape(body.get("from")), build_shape(body.get("remove"))
        return (lambda x, y, z: max(keep[0](x, y, z), -cut[0](x, y, z))), keep[1]
    if kind == "intersect":
        if not isinstance(body, list) or len(body) < 2:
            raise ValueError("intersect needs a list of at least two shapes")
        parts = [build_shape(item) for item in body]
        functions = [part[0] for part in parts]
        low = tuple(max(part[1][0][i] for part in parts) for i in range(3))
        high = tuple(min(part[1][1][i] for part in parts) for i in range(3))
        if any(high[i] <= low[i] for i in range(3)):
            raise ValueError("intersect: the shapes' bounds do not overlap")
        if any(abs(v) >= UNBOUNDED for v in low + high):
            raise ValueError("intersect needs at least one bounded shape on every axis")
        return (lambda x, y, z: max(g(x, y, z) for g in functions)), (low, high)
    if kind == "halfspace":
        point, normal = _vec(body.get("point"), "halfspace.point"), _vec(body.get("normal"), "halfspace.normal")
        length = math.sqrt(sum(v * v for v in normal))
        if length < 1e-9:
            raise ValueError("halfspace.normal must not be zero")
        unit = tuple(v / length for v in normal)
        return ((lambda x, y, z: (x - point[0]) * unit[0] + (y - point[1]) * unit[1] + (z - point[2]) * unit[2]),
                ((-UNBOUNDED,) * 3, (UNBOUNDED,) * 3))
    if kind == "torus":
        c = _vec(body.get("center"), "torus.center")
        axis = body.get("axis", "y")
        if axis not in ("x", "y", "z"):
            raise ValueError("torus.axis must be x, y or z")
        major, minor = _positive(body.get("major"), "torus.major"), _positive(body.get("minor"), "torus.minor")
        a = "xyz".index(axis)
        b1, b2 = [i for i in range(3) if i != a]

        def f(x, y, z):
            p = (x - c[0], y - c[1], z - c[2])
            ring = math.sqrt(p[b1] * p[b1] + p[b2] * p[b2]) - major
            return (ring * ring + p[a] * p[a]) / (minor * minor) - 1
        reach = [major + minor] * 3
        reach[a] = minor
        return f, (tuple(c[i] - reach[i] for i in range(3)), tuple(c[i] + reach[i] for i in range(3)))
    raise ValueError(f"Unknown shape {kind!r}: use ellipsoid, superellipsoid, capsule, box, torus, halfspace, union, "
                     "smooth_union, intersect or subtract")


# ------------------------------------------------------------------ voxels and partition
def voxelize(f, bounds, cell: float, offset: float = 0.0):
    low, high = bounds
    n = tuple(max(1, math.ceil((high[i] - low[i]) / cell - 1e-6)) for i in range(3))
    if n[0] * n[1] * n[2] > MAX_CELLS:
        raise ValueError(f"Blob grid of {n[0]}x{n[1]}x{n[2]} cells is too large; raise the cell size")
    # Centre the grid on the bounds (symmetric shapes stay symmetric), then shift by the blob's offset.
    origin = tuple((low[i] + high[i]) / 2 - n[i] * cell / 2 + offset for i in range(3))
    occupied = bytearray(n[0] * n[1] * n[2])
    for i in range(n[0]):
        x = origin[0] + (i + 0.5) * cell
        for j in range(n[1]):
            y = origin[1] + (j + 0.5) * cell
            base = (i * n[1] + j) * n[2]
            for k in range(n[2]):
                if f(x, y, origin[2] + (k + 0.5) * cell) < 0:
                    occupied[base + k] = 1
    return occupied, n, origin


def partition(occupied: bytearray, n, order: str = "yxz") -> list[tuple[list[int], list[int]]]:
    """Greedy merge into disjoint boxes [lo, hi) covering every occupied cell exactly once."""
    if sorted(order) != ["x", "y", "z"]:
        raise ValueError("order must be a permutation of xyz")
    axes = ["xyz".index(ch) for ch in order]
    left = bytearray(occupied)

    def at(i, j, k):
        return left[(i * n[1] + j) * n[2] + k]

    def slab_full(lo, hi, axis, layer):
        ranges = [range(lo[a], hi[a]) for a in range(3)]
        ranges[axis] = range(layer, layer + 1)
        return all(at(i, j, k) for i in ranges[0] for j in ranges[1] for k in ranges[2])

    boxes = []
    for i in range(n[0]):
        for j in range(n[1]):
            for k in range(n[2]):
                if not at(i, j, k):
                    continue
                lo, hi = [i, j, k], [i + 1, j + 1, k + 1]
                for axis in axes:
                    while hi[axis] < n[axis] and slab_full(lo, hi, axis, hi[axis]):
                        hi[axis] += 1
                for a in range(lo[0], hi[0]):
                    for b in range(lo[1], hi[1]):
                        start = (a * n[1] + b) * n[2]
                        left[start + lo[2]:start + hi[2]] = bytes(hi[2] - lo[2])
                boxes.append((lo, hi))
    return boxes


def buried_faces(occupied: bytearray, n, lo, hi) -> set[str]:
    """Faces of box [lo, hi) whose whole outside neighbour layer is occupied by the same blob."""
    names = {(0, -1): "west", (0, 1): "east", (1, -1): "down", (1, 1): "up", (2, -1): "north", (2, 1): "south"}
    result = set()
    for axis in range(3):
        for side in (-1, 1):
            layer = lo[axis] - 1 if side < 0 else hi[axis]
            if layer < 0 or layer >= n[axis]:
                continue
            ranges = [range(lo[a], hi[a]) for a in range(3)]
            ranges[axis] = range(layer, layer + 1)
            if all(occupied[(i * n[1] + j) * n[2] + k] for i in ranges[0] for j in ranges[1] for k in ranges[2]):
                result.add(names[(axis, side)])
    return result


# ------------------------------------------------------------------ atlas
def _face_dims(face: str, size) -> tuple[float, float]:
    w, h, d = size
    return {"north": (w, h), "south": (w, h), "east": (d, h), "west": (d, h), "up": (w, d), "down": (w, d)}[face]


def pack(rects: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], int, int]:
    """Shelf-pack (w, h) rectangles; returns positions and a power-of-two atlas size."""
    area = sum(w * h for w, h in rects)
    width = 16
    while width * width < area * 1.25 or width < max((w for w, _ in rects), default=1):
        width *= 2
    while True:
        order = sorted(range(len(rects)), key=lambda index: (-rects[index][1], -rects[index][0]))
        positions = [None] * len(rects)
        x = y = shelf = 0
        for index in order:
            w, h = rects[index]
            if x + w > width:
                x, y, shelf = 0, y + shelf, 0
            positions[index] = (x, y)
            x += w
            shelf = max(shelf, h)
        height = 16
        while height < y + shelf:
            height *= 2
        if height <= width * 2 or width >= MAX_ATLAS:
            break
        width *= 2
    if width > MAX_ATLAS or height > MAX_ATLAS:
        raise ValueError(f"The texture atlas would be {width}x{height}; lower texels_per_pixel or raise the cell size")
    return positions, width, height


def _colour(value: str):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"color must be #rrggbb, got {value!r}")
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


# ------------------------------------------------------------------ build
def build_voxel_model(spec: dict) -> dict:
    """Return {"geo", "bbmodel", "texture", "uv_test", "report"} for a voxel spec."""
    name = spec.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("name must be a lowercase id ([a-z][a-z0-9_]*)")
    cell = _positive(spec.get("cell", 0.8), "cell")
    density = _positive(spec.get("texels_per_pixel", 2), "texels_per_pixel")
    bones = spec.get("bones") or [{"name": "root", "pivot": [0, 0, 0]}]
    bone_names = []
    for bone in bones:
        if not isinstance(bone, dict) or not isinstance(bone.get("name"), str) or bone["name"] in bone_names:
            raise ValueError("every bone needs a unique name")
        if bone.get("parent") is not None and bone["parent"] not in bone_names:
            raise ValueError(f"bone {bone['name']!r}: list the parent {bone.get('parent')!r} before its children")
        _vec(bone.get("pivot", [0, 0, 0]), f"bone {bone['name']}.pivot")
        bone_names.append(bone["name"])
    blobs = spec.get("blobs")
    if not isinstance(blobs, list) or not blobs:
        raise ValueError("blobs must be a non-empty list")
    cubes, faces_total, seen, warnings = [], 0, set(), []
    step = 0.03
    placed: dict[tuple, list] = {}

    def faces_of(low, high, kept):
        for face in kept:
            axis, sign = {"west": (0, -1), "east": (0, 1), "down": (1, -1), "up": (1, 1), "north": (2, -1), "south": (2, 1)}[face]
            plane = high[axis] if sign > 0 else low[axis]
            rect = tuple((low[b], high[b]) for b in range(3) if b != axis)
            yield axis, sign, plane, rect

    def conflicts(candidate):
        count = 0
        for low, high, kept in candidate:
            for axis, sign, plane, rect in faces_of(low, high, kept):
                bucket = round(plane / PLANE_BUCKET)
                span = math.ceil(PLANE_WINDOW / PLANE_BUCKET) + 1
                for key in ((axis, sign, bucket + d) for d in range(-span, span + 1)):
                    for other_plane, other in placed.get(key, ()):
                        if abs(other_plane - plane) <= PLANE_WINDOW and all(
                                min(a[1], b[1]) - max(a[0], b[0]) > 1e-3 for a, b in zip(rect, other)):
                            count += 1
        return count

    for index, blob in enumerate(blobs):
        blob_name = blob.get("name")
        if not isinstance(blob_name, str) or not NAME.fullmatch(blob_name) or blob_name in seen:
            raise ValueError("every blob needs a unique lowercase name")
        seen.add(blob_name)
        if blob.get("bone") not in bone_names:
            raise ValueError(f"blob {blob_name!r}: unknown bone {blob.get('bone')!r}")
        blob_cell = _positive(blob.get("cell", cell), f"blob {blob_name}.cell")
        f, bounds = build_shape(blob.get("shape"))
        if any(abs(v) >= UNBOUNDED for v in bounds[0] + bounds[1]):
            raise ValueError(f"blob {blob_name!r}: a halfspace alone is unbounded; put it inside intersect or subtract")
        blob_density = _positive(blob.get("texels_per_pixel", density), f"blob {blob_name}.texels_per_pixel")
        colour = _colour(blob.get("color", "#9a9a9a"))
        best = None
        # Try sub-pixel grid offsets until no visible face lies on a visible face of an earlier blob.
        for attempt in range(max(1, int(blob_cell / step))):
            offset = step * attempt
            occupied, n, origin = voxelize(f, bounds, blob_cell, offset)
            if not any(occupied):
                raise ValueError(f"blob {blob_name!r} is empty at cell {blob_cell}")
            candidate = []
            for lo, hi in partition(occupied, n, blob.get("order", "yxz")):
                low = tuple(round(origin[a] + lo[a] * blob_cell, 4) for a in range(3))
                high = tuple(round(origin[a] + hi[a] * blob_cell, 4) for a in range(3))
                buried = buried_faces(occupied, n, lo, hi)
                candidate.append((low, high, [face for face in FACES if face not in buried]))
            clashes = conflicts(candidate)
            if best is None or clashes < best[0]:
                best = (clashes, offset, candidate)
            if not clashes:
                break
        clashes, offset, candidate = best
        if clashes:
            warnings.append(f"blob {blob_name!r}: {clashes} face(s) still share a plane with an earlier blob; see model_check")
        for number, (low, high, kept) in enumerate(candidate):
            faces_total += 6
            cubes.append({"name": f"{blob_name}_{number}", "blob": blob_name, "bone": blob["bone"], "min": low, "max": high,
                          "faces": kept, "colour": colour, "offset": offset,
                          "density": blob_density})
            for axis, sign, plane, rect in faces_of(low, high, kept):
                placed.setdefault((axis, sign, round(plane / PLANE_BUCKET)), []).append((plane, rect))
    # Texture rectangles: one per kept face, sized to the face at the chosen texel density.
    rects, owners = [], []
    for cube in cubes:
        size = tuple(cube["max"][a] - cube["min"][a] for a in range(3))
        for face in cube["faces"]:
            fw, fh = _face_dims(face, size)
            rects.append((max(1, round(fw * cube["density"])), max(1, round(fh * cube["density"]))))
            owners.append((cube, face))
    positions, width, height = pack(rects)
    texture, uv_test = blank(width, height), blank(width, height)
    rng = random.Random(name)
    hues = {"north": (230, 70, 60), "south": (60, 200, 90), "east": (70, 110, 240), "west": (240, 200, 60),
            "up": (230, 230, 230), "down": (120, 60, 160)}
    for (cube, face), (x, y), (w, h) in zip(owners, positions, rects):
        cube.setdefault("uv", {})[face] = (x, y, w, h)
        for ty in range(h):
            for tx in range(w):
                jitter = 1.0 + (rng.random() - 0.5) * 0.12
                put(texture, x + tx, y + ty, tuple(min(255, int(c * jitter)) for c in cube["colour"]))
                # UV test: dark to bright along u, a hue per face direction, and a white band on the first rows of v,
                # so a flipped u or v shows from any side (see guide entities for where each face's u and v run).
                ramp = 0.25 + 0.75 * (tx + 0.5) / w
                top = ty < max(1, round(h * 0.18)) and h > 1
                put(uv_test, x + tx, y + ty, (255, 255, 255) if top else tuple(int(c * ramp) for c in hues[face]))
    # GeckoLib geometry (Bedrock layout: x mirrored).
    bounds_low = tuple(min(c["min"][a] for c in cubes) for a in range(3))
    bounds_high = tuple(max(c["max"][a] for c in cubes) for a in range(3))
    geo_bones = []
    for bone in bones:
        pivot = _vec(bone.get("pivot", [0, 0, 0]), "pivot")
        entry = {"name": bone["name"], "pivot": [round(-pivot[0], 4) + 0.0, pivot[1], pivot[2]]}
        if bone.get("parent"):
            entry["parent"] = bone["parent"]
        own = [c for c in cubes if c["bone"] == bone["name"]]
        if own:
            entry["cubes"] = [{"origin": [round(-c["max"][0], 4) + 0.0, c["min"][1], c["min"][2]],
                               "size": [round(c["max"][a] - c["min"][a], 4) for a in range(3)],
                               "uv": {face: {"uv": [u, v], "uv_size": [w, h]} for face, (u, v, w, h) in c["uv"].items()}}
                              for c in own]
        geo_bones.append(entry)
    extent = max(abs(bounds_low[0]), abs(bounds_high[0]), abs(bounds_low[2]), abs(bounds_high[2]))
    geo = {"format_version": "1.12.0", "minecraft:geometry": [{
        "description": {"identifier": f"geometry.{name}", "texture_width": width, "texture_height": height,
                        "visible_bounds_width": math.ceil(extent * 2 / 16) + 1, "visible_bounds_height": math.ceil(bounds_high[1] / 16) + 1,
                        "visible_bounds_offset": [0, round(bounds_high[1] / 32, 3), 0]},
        "bones": geo_bones}]}
    # Blockbench "Generic Model" project with per-face UV; buried faces carry no texture.
    elements, groups = [], {}
    for cube in cubes:
        bone = next(b for b in bones if b["name"] == cube["bone"])
        pivot = list(_vec(bone.get("pivot", [0, 0, 0]), "pivot"))
        faces = {}
        for face in FACES:
            if face in cube["uv"]:
                u, v, w, h = cube["uv"][face]
                faces[face] = {"uv": [u, v, u + w, v + h], "texture": 0}
            else:
                faces[face] = {"uv": [0, 0, 0, 0], "texture": None}
        element = {"name": cube["name"], "type": "cube", "uuid": _uuid(name, cube["name"]), "box_uv": False,
                   "from": list(cube["min"]), "to": list(cube["max"]), "origin": pivot, "rotation": [0, 0, 0],
                   "autouv": 0, "color": 0, "faces": faces}
        elements.append(element)
        groups.setdefault(cube["bone"], []).append(element["uuid"])

    def outline(parent):
        nodes = []
        for bone in bones:
            if bone.get("parent") == parent:
                nodes.append({"name": bone["name"], "uuid": _uuid(name, bone["name"], "group"),
                              "origin": list(_vec(bone.get("pivot", [0, 0, 0]), "pivot")), "rotation": [0, 0, 0],
                              "isOpen": True, "children": groups.get(bone["name"], []) + outline(bone["name"])})
        return nodes
    texture_png = png_bytes(texture)
    bbmodel = {"meta": {"format_version": "4.10", "model_format": "free", "box_uv": False}, "name": name,
               "resolution": {"width": width, "height": height}, "elements": elements, "outliner": outline(None),
               "textures": [_texture_entry(name, texture_png) | {"width": width, "height": height, "uv_width": width, "uv_height": height}]}
    kept = sum(len(c["faces"]) for c in cubes)
    report = {"name": name, "blobs": len(blobs), "cubes": len(cubes), "faces": faces_total, "faces_kept": kept,
              "faces_omitted": faces_total - kept, "texture": [width, height], "bounds": [list(bounds_low), list(bounds_high)],
              "warnings": warnings}
    return {"geo": geo, "bbmodel": bbmodel, "texture": texture_png, "uv_test": png_bytes(uv_test), "report": report}


def write_voxel_model(spec_path: Path, *, project: Path | None = None, out: Path | None = None, force: bool = False) -> dict:
    from .workbench import guard_output
    spec_path = Path(spec_path)
    if project is not None:
        guard_output(Path(project).resolve())
    if spec_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Voxel spec exceeds 4 MiB")
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    built = build_voxel_model(spec)
    name = built["report"]["name"]
    if (project is None) == (out is None):
        raise ValueError("Pass exactly one of --project PATH or --out DIR")
    if project is not None:
        project = Path(project).resolve()
        mod_id = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8-sig"))["mod_id"]
        assets = project / "src/main/resources/assets" / mod_id
        targets = {"geo": assets / "geo/entity" / f"{name}.geo.json", "texture": assets / "textures/entity" / f"{name}.png",
                   "bbmodel": project / "blockbench" / f"{name}.bbmodel", "uv_test": project / "blockbench" / f"{name}_uvtest.png"}
    else:
        out = Path(out).resolve()
        targets = {"geo": out / f"{name}.geo.json", "texture": out / f"{name}.png", "bbmodel": out / f"{name}.bbmodel",
                   "uv_test": out / f"{name}_uvtest.png"}
    for path in targets.values():
        guard_output(path)
        if path.exists() and not force:
            raise ValueError(f"{path} exists; pass --force to replace the generated files")
    for key, path in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        data = built[key]
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(json.dumps(data, indent=1 if key == "bbmodel" else None, separators=None if key == "bbmodel" else (",", ":")) + "\n",
                            encoding="utf-8", newline="\n")
    check = check_model(targets["geo"])
    return built["report"] | {"files": {key: str(path) for key, path in targets.items()},
                              "model_check": {"status": check["status"], "z_fighting": check["z_fighting"][:20], "frames": check["frames"]},
                              "next": "preview PROJECT FILE.geo.json --vanilla-light; register the geo with a GeoModel (guide entities)"}
