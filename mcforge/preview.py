"""Render block models and entity rigs to PNG without the game.

A small orthographic ray caster in pure Python: enough to check proportions,
texture mapping and facing before a client run. It is a preview, not the game's
renderer: no lighting engine, translucency or tinting. GeckoLib geometry can be
posed from an animation file, and `light="vanilla"` shades faces with the game's
entity diffuse lighting so previews match in-game screenshots.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .pixelart import Image, blank, png_bytes, put, read_png
from .shapes import walk_parts

Vector = tuple[float, float, float]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def _mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _apply(matrix, vector):
    return tuple(_dot(matrix[i], vector) for i in range(3))


def _transpose(matrix):
    return tuple(tuple(matrix[j][i] for j in range(3)) for i in range(3))


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
# Vanilla entity lighting (com.mojang.blaze3d.platform.Lighting, 1.21.1): two fixed directions,
# shade = min(1, 0.6 * (max(0, n.L0) + max(0, n.L1)) + 0.4).
VANILLA_LIGHT_0 = (0.2 / 1.2369317, 1.0 / 1.2369317, -0.7 / 1.2369317)
VANILLA_LIGHT_1 = (-0.2 / 1.2369317, 1.0 / 1.2369317, 0.7 / 1.2369317)


def vanilla_shade(normal) -> float:
    return min(1.0, 0.6 * (max(0.0, _dot(normal, VANILLA_LIGHT_0)) + max(0.0, _dot(normal, VANILLA_LIGHT_1))) + 0.4)


def _inverse(m):
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
           + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    if abs(det) < 1e-12:
        raise ValueError("A bone is scaled to zero; it cannot be rendered")
    return tuple(tuple(((m[(j + 1) % 3][(i + 1) % 3] * m[(j + 2) % 3][(i + 2) % 3]
                         - m[(j + 1) % 3][(i + 2) % 3] * m[(j + 2) % 3][(i + 1) % 3]) / det) for j in range(3)) for i in range(3))


def rotation(axis: str, radians: float):
    c, s = math.cos(radians), math.sin(radians)
    if axis == "x":
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if axis == "y":
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def _texel(texture: Image, u: float, v: float):
    height = len(texture)
    width = len(texture[0]) // 4
    x, y = int(math.floor(u)) % width, int(math.floor(v)) % height
    return tuple(texture[y][x * 4:x * 4 + 4])


def block_boxes(model: dict, textures: dict[str, Image]) -> list[dict]:
    """Ray-cast boxes for a block model's elements (single-axis element rotation supported)."""
    boxes = []
    names = model.get("textures", {})

    def resolve(reference: str) -> Image | None:
        seen = 0
        while reference.startswith("#") and seen < 8:
            reference = names.get(reference[1:], "")
            seen += 1
        return textures.get(reference)

    for element in model.get("elements", []):
        start, end = element["from"], element["to"]
        matrix, offset = IDENTITY, (0.0, 0.0, 0.0)
        turn = element.get("rotation")
        if turn:
            matrix = rotation(turn["axis"], math.radians(turn["angle"]))
            origin = turn.get("origin", [8, 8, 8])
            moved = _apply(matrix, origin)
            offset = (origin[0] - moved[0], origin[1] - moved[1], origin[2] - moved[2])
        faces = element.get("faces", {})

        def sample(face, point, start=start, end=end, faces=faces):
            spec = faces.get(face)
            if spec is None:
                return None
            texture = resolve(spec.get("texture", ""))
            if texture is None:
                return (255, 0, 255, 255)
            x, y, z = point
            size = len(texture[0]) // 4
            if "uv" in spec:
                u1, v1, u2, v2 = spec["uv"]
                fx, fy = {"north": ((end[0] - x) / max(end[0] - start[0], 1e-6), (end[1] - y) / max(end[1] - start[1], 1e-6)),
                          "south": ((x - start[0]) / max(end[0] - start[0], 1e-6), (end[1] - y) / max(end[1] - start[1], 1e-6)),
                          "west": ((z - start[2]) / max(end[2] - start[2], 1e-6), (end[1] - y) / max(end[1] - start[1], 1e-6)),
                          "east": ((end[2] - z) / max(end[2] - start[2], 1e-6), (end[1] - y) / max(end[1] - start[1], 1e-6)),
                          "up": ((x - start[0]) / max(end[0] - start[0], 1e-6), (z - start[2]) / max(end[2] - start[2], 1e-6)),
                          "down": ((x - start[0]) / max(end[0] - start[0], 1e-6), (end[2] - z) / max(end[2] - start[2], 1e-6))}[face]
                u, v = u1 + (u2 - u1) * fx, v1 + (v2 - v1) * fy
            else:
                u, v = {"north": (16 - x, 16 - y), "south": (x, 16 - y), "west": (z, 16 - y), "east": (16 - z, 16 - y),
                        "up": (x, z), "down": (x, 16 - z)}[face]
            return _texel(texture, u * size / 16 - 1e-4 if u == 16 else u * size / 16, v * size / 16 - 1e-4 if v == 16 else v * size / 16)

        boxes.append({"matrix": matrix, "offset": offset, "min": tuple(start), "max": tuple(end), "sample": sample,
                      "names": ("west", "east", "down", "up", "north", "south")})
    return boxes


def rig_boxes(rig: dict, texture: Image) -> list[dict]:
    """Ray-cast boxes for a rig in model space, with Minecraft's box-UV face mapping."""
    boxes = []

    def visit(part, matrix, offset):
        rx, ry, rz = part.get("rotation", (0, 0, 0))
        local = _mul(rotation("z", rz), _mul(rotation("y", ry), rotation("x", rx)))
        moved = _apply(matrix, part["pivot"])
        offset = (offset[0] + moved[0], offset[1] + moved[1], offset[2] + moved[2])
        matrix = _mul(matrix, local)
        for cube in part["cubes"]:
            x0, y0, z0 = cube["origin"]
            width, height, depth = cube["size"]
            u0, v0 = cube["uv"]

            def sample(face, point, x0=x0, y0=y0, z0=z0, width=width, height=height, depth=depth, u0=u0, v0=v0):
                x, y, z = point[0] - x0, point[1] - y0, point[2] - z0
                u, v = {"north": (u0 + depth + x, v0 + depth + y), "south": (u0 + 2 * depth + 2 * width - x, v0 + depth + y),
                        "west": (u0 + depth - z, v0 + depth + y), "east": (u0 + depth + width + z, v0 + depth + y),
                        "down": (u0 + depth + x, v0 + depth - z), "up": (u0 + depth + width + x, v0 + depth - z)}[face]
                return _texel(texture, min(u, len(texture[0]) // 4 - 1e-4), min(v, len(texture) - 1e-4))

            # In model space Y points down: the face at minimum Y is the visual top ("down" in ModelPart terms).
            boxes.append({"matrix": matrix, "offset": offset, "min": (x0, y0, z0), "max": (x0 + width, y0 + height, z0 + depth),
                          "sample": sample, "names": ("west", "east", "down", "up", "north", "south")})
        for child in part["children"]:
            visit(child, matrix, offset)

    for part in rig["parts"]:
        visit(part, IDENTITY, (0.0, 0.0, 0.0))
    return boxes


def render(boxes: list[dict], *, size: int = 256, direction: Vector = (-0.62, -0.5, 0.6), up: Vector = (0, 1, 0),
           background=(34, 36, 44), light: str = "soft") -> Image:
    """Orthographic render. ``direction`` is the way the camera looks; ``up`` is the scene's up axis.

    ``light``: "soft" (a key light from the camera side) or "vanilla" (the game's entity lighting, y-up scenes).
    """
    forward = _unit(direction)
    right = _unit(_cross(forward, up))
    upward = _cross(right, forward)
    corners = []
    for box in boxes:
        for x in (box["min"][0], box["max"][0]):
            for y in (box["min"][1], box["max"][1]):
                for z in (box["min"][2], box["max"][2]):
                    world = _apply(box["matrix"], (x, y, z))
                    corners.append((world[0] + box["offset"][0], world[1] + box["offset"][1], world[2] + box["offset"][2]))
    if not corners:
        raise ValueError("Nothing to render")
    horizontal = [_dot(corner, right) for corner in corners]
    vertical = [_dot(corner, upward) for corner in corners]
    depth = [_dot(corner, forward) for corner in corners]
    span = max(max(horizontal) - min(horizontal), max(vertical) - min(vertical)) * 1.12 or 1.0
    centre_x, centre_y = (max(horizontal) + min(horizontal)) / 2, (max(vertical) + min(vertical)) / 2
    near = min(depth) - 10.0
    prepared = []
    for box in boxes:
        inverse = box.get("inverse") or _transpose(box["matrix"])
        points = []
        for x in (box["min"][0], box["max"][0]):
            for y in (box["min"][1], box["max"][1]):
                for z in (box["min"][2], box["max"][2]):
                    world = _apply(box["matrix"], (x, y, z))
                    points.append((world[0] + box["offset"][0], world[1] + box["offset"][1], world[2] + box["offset"][2]))
        # Screen rectangle of the box: each pixel only tests the boxes that can cover it.
        rect = (min(_dot(p, right) for p in points), max(_dot(p, right) for p in points),
                min(_dot(p, upward) for p in points), max(_dot(p, upward) for p in points))
        prepared.append((box, inverse, _apply(inverse, forward), box["offset"], rect))
    light_direction = _unit((-forward[0] + upward[0] * 0.9 - right[0] * 0.35, -forward[1] + upward[1] * 0.9 - right[1] * 0.35,
                             -forward[2] + upward[2] * 0.9 - right[2] * 0.35))
    image = blank(size, size)
    for py in range(size):
        sy = centre_y + (0.5 - (py + 0.5) / size) * span
        row = [entry for entry in prepared if entry[4][2] <= sy <= entry[4][3]]
        for px in range(size):
            sx = centre_x + ((px + 0.5) / size - 0.5) * span
            origin = (right[0] * sx + upward[0] * sy + forward[0] * near, right[1] * sx + upward[1] * sy + forward[1] * near,
                      right[2] * sx + upward[2] * sy + forward[2] * near)
            best, colour = None, None
            for box, inverse, local_direction, offset, rect in row:
                if not rect[0] <= sx <= rect[1]:
                    continue
                local_origin = _apply(inverse, (origin[0] - offset[0], origin[1] - offset[1], origin[2] - offset[2]))
                t_near, t_far, hit_axis, hit_side = -1e30, 1e30, 0, 0
                for axis in range(3):
                    if abs(local_direction[axis]) < 1e-9:
                        if not box["min"][axis] <= local_origin[axis] <= box["max"][axis]:
                            t_near = 1e30
                            break
                        continue
                    first = (box["min"][axis] - local_origin[axis]) / local_direction[axis]
                    second = (box["max"][axis] - local_origin[axis]) / local_direction[axis]
                    side = 0
                    if first > second:
                        first, second, side = second, first, 1
                    if first > t_near:
                        t_near, hit_axis, hit_side = first, axis, side
                    t_far = min(t_far, second)
                if t_near > t_far or t_near >= 1e29 or (best is not None and t_near >= best):
                    continue
                point = tuple(local_origin[i] + local_direction[i] * t_near for i in range(3))
                pixel = box["sample"](box["names"][hit_axis * 2 + hit_side], point)
                if pixel is None or pixel[3] < 16:
                    continue
                normal = [0.0, 0.0, 0.0]
                normal[hit_axis] = 1.0 if hit_side else -1.0
                world_normal = _unit(_apply(box["matrix"], normal))
                if light == "vanilla":
                    shade = vanilla_shade(world_normal)
                else:
                    shade = 0.58 + 0.42 * max(0.0, _dot(world_normal, light_direction))
                best, colour = t_near, (pixel[0] * shade, pixel[1] * shade, pixel[2] * shade)
            put(image, px, py, colour if colour else background)
    return image


def _load_texture(project: Path, mod_id: str, reference: str) -> Image | None:
    namespace, _, path = reference.partition(":")
    if not path:
        namespace, path = "minecraft", namespace
    for root in ("src/main/resources", "src/client/resources", "src/generated/resources"):
        candidate = project / root / "assets" / namespace / "textures" / (path + ".png")
        if candidate.is_file():
            return read_png(candidate.read_bytes())
    return None


def preview_block_model(project: Path, mod_id: str, model_path: Path, output: Path, size: int = 256) -> dict:
    model = json.loads(model_path.read_text(encoding="utf-8-sig"))
    if "elements" not in model:
        parent = model.get("parent", "")
        if parent.endswith(("block/cube_all", "block/cube_column", "block/cube")):
            texture = next(iter(model.get("textures", {}).values()), "")
            model = {"textures": {"all": texture}, "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                     "faces": {face: {"texture": "#all"} for face in ("down", "up", "north", "south", "west", "east")}}]}
        else:
            raise ValueError(f"Model has no elements and parent {parent or '(none)'} is not a cube; preview the parent model instead")
    textures = {}
    missing = []
    for reference in set(model.get("textures", {}).values()):
        if reference.startswith("#"):
            continue
        loaded = _load_texture(project, mod_id, reference)
        if loaded is None:
            missing.append(reference)
        else:
            textures[reference] = loaded
    image = render(block_boxes(model, textures), size=size)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png_bytes(image))
    return {"preview": str(output), "elements": len(model["elements"]), "missing_textures": sorted(missing),
            "note": "Software preview: geometry and UV mapping only; magenta marks a texture the project does not contain."}


def _face_fraction(face: str, point, low, high):
    """(u, v) fractions across a face as seen from outside: u left to right, v top to bottom (Blockbench space)."""
    x, y, z = point
    w, h, d = (max(high[i] - low[i], 1e-6) for i in range(3))
    return {"north": ((high[0] - x) / w, (high[1] - y) / h), "south": ((x - low[0]) / w, (high[1] - y) / h),
            "west": ((z - low[2]) / d, (high[1] - y) / h), "east": ((high[2] - z) / d, (high[1] - y) / h),
            "up": ((x - low[0]) / w, (z - low[2]) / d), "down": ((x - low[0]) / w, (high[2] - z) / d)}[face]


def geo_boxes(geometry: dict, texture: Image, texture_size, matrices: dict) -> list[dict]:
    """Ray-cast boxes for GeckoLib geometry (geckopose.load_geometry) posed by bone matrices.

    A face missing from a per-face UV map is skipped, as GeckoLib builds no quad for it.
    """
    width, height = len(texture[0]) // 4, len(texture)
    scale_u, scale_v = width / texture_size[0], height / texture_size[1]
    boxes = []
    for name in geometry["order"]:
        bone_matrix = matrices[name]
        for cube in geometry["bones"][name]["cubes"]:
            m = [[sum(bone_matrix[i][k] * cube["matrix"][k][j] for k in range(4)) for j in range(4)] for i in range(4)]
            matrix = tuple(tuple(m[i][j] for j in range(3)) for i in range(3))
            low, high = cube["min"], cube["max"]
            sx, sy, sz = cube["size"]

            def sample(face, point, cube=cube, low=low, high=high, sx=sx, sy=sy, sz=sz):
                fx, fy = _face_fraction(face, point, low, high)
                if cube["faces"] is not None:
                    spec = cube["faces"].get(face)
                    if spec is None:
                        return None
                    u0, v0 = spec["uv"]
                    du, dv = spec.get("uv_size", [0, 0])
                else:
                    u, v = cube["box_uv"] or (0, 0)
                    du, dv = {"north": (sx, sy), "south": (sx, sy), "east": (sz, sy), "west": (sz, sy), "up": (sx, sz), "down": (sx, sz)}[face]
                    u0, v0 = {"east": (u, v + sz), "north": (u + sz, v + sz), "west": (u + sz + sx, v + sz),
                              "south": (u + 2 * sz + sx, v + sz), "up": (u + sz, v), "down": (u + sz + sx, v)}[face]
                tu = (u0 + du * fx) * scale_u
                tv = (v0 + dv * fy) * scale_v
                return _texel(texture, min(max(tu, 0), width - 1e-4), min(max(tv, 0), height - 1e-4))

            boxes.append({"matrix": matrix, "inverse": _inverse(matrix), "offset": (m[0][3], m[1][3], m[2][3]),
                          "min": low, "max": high, "sample": sample, "names": ("west", "east", "down", "up", "north", "south")})
    return boxes


def preview_geo(geo_path: Path, texture: Image, output: Path, size: int = 256, *, light: str = "vanilla",
                animation: Path | None = None, clip: str | None = None, time: float = 0.0,
                direction: Vector = (-0.55, -0.45, 0.7)) -> dict:
    """Render GeckoLib geometry (rest pose, or one frame of an animation clip)."""
    from . import geckopose
    data = json.loads(Path(geo_path).read_text(encoding="utf-8-sig"))
    description = data["minecraft:geometry"][0].get("description", {})
    texture_size = (description.get("texture_width") or len(texture[0]) // 4, description.get("texture_height") or len(texture))
    geometry = geckopose.load_geometry(geo_path)
    pose, clip_name = None, None
    if animation is not None:
        if not clip:
            raise ValueError("--clip names the animation to pose")
        clip_name, clip_data = geckopose.find_clip(geckopose.load_animations(animation), clip)
        pose = geckopose.pose_at(clip_data, time)
    boxes = geo_boxes(geometry, texture, texture_size, geckopose.bone_matrices(geometry, pose))
    # Blockbench space: y up, the model faces north (-Z); look at its front from above and to one side.
    image = render(boxes, size=size, direction=direction, up=(0, 1, 0), light=light)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png_bytes(image))
    uv = "box (Blockbench layout, approximate)" if any(c["box_uv"] is not None for b in geometry["bones"].values() for c in b["cubes"]) else "per-face"
    return {"preview": str(output), "bones": len(geometry["order"]), "cubes": len(boxes), "light": light, "uv": uv,
            "pose": {"clip": clip_name, "time": time} if clip_name else "rest",
            "note": "Software preview: no translucency, tint or glow layers; missing faces are skipped as GeckoLib skips them."}


def preview_rig(rig: dict, texture: Image, output: Path, size: int = 256) -> dict:
    # Model space has Y down and the front at -Z: look from in front, above and to one side.
    image = render(rig_boxes(rig, texture), size=size, direction=(0.55, 0.5, 0.67), up=(0, -1, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png_bytes(image))
    return {"preview": str(output), "bones": sum(1 for _ in walk_parts(rig["parts"])),
            "note": "Software preview of the rest pose; no animation, lighting engine or translucency."}
