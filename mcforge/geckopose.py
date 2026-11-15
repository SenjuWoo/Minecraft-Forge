"""Offline pose evaluator for GeckoLib geometry and animation JSON, plus foot grounding.

Everything is evaluated in Blockbench space (the space a modeller sees), which is
what GeckoLib reconstructs at load time:

- geometry: Bedrock writes x mirrored, so a cube origin [ox, oy, oz] with size
  [sx, sy, sz] spans x from -(ox + sx) to -ox; pivots are [-x, y, z]; rotations
  are [-rx, -ry, rz] (degrees).
- animation keyframes: rotation [-rx, -ry, rz] is added to the bone's rest
  rotation; position [-px, py, pz] is a translation in model pixels.
- bone transform: T(position) * T(pivot) * Rz * Ry * Rx * S * T(-pivot), parent
  first. The Z, Y, X order is GeckoLib's RenderUtil.rotateMatrixAroundBone.

`ground_animations` keys the root bone so the lowest point of the leg geometry
sits at y = 0 on every sampled frame, which keeps wide stances, squats, kneeling
and lunges planted without hand-tuned root offsets.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

MAX_FILE = 64 * 1024 * 1024


def _load(path: Path) -> dict:
    path = Path(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError(f"{path.name} exceeds 64 MiB")
    return json.loads(path.read_text(encoding="utf-8-sig"))


# ------------------------------------------------------------------ 4x4 matrices (row-major lists)
def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _translate(x, y, z):
    return [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]]


def _scale(x, y, z):
    return [[x, 0, 0, 0], [0, y, 0, 0], [0, 0, z, 0], [0, 0, 0, 1]]


def _rotate(rx, ry, rz):
    """Rz * Ry * Rx for angles in degrees."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    x = [[1, 0, 0, 0], [0, ca, -sa, 0], [0, sa, ca, 0], [0, 0, 0, 1]]
    y = [[cb, 0, sb, 0], [0, 1, 0, 0], [-sb, 0, cb, 0], [0, 0, 0, 1]]
    z = [[cc, -sc, 0, 0], [sc, cc, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    return _matmul(z, _matmul(y, x))


def _point(m, p):
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))


IDENTITY = _translate(0, 0, 0)


# ------------------------------------------------------------------ geometry
def load_geometry(path: Path) -> dict:
    """Bones in parent-first order, in Blockbench space."""
    data = _load(path)
    geometries = data.get("minecraft:geometry")
    if not isinstance(geometries, list) or not geometries:
        raise ValueError("Not a Bedrock/GeckoLib geometry file: no minecraft:geometry list")
    raw = geometries[0].get("bones", [])
    bones = {}
    for bone in raw:
        pivot = bone.get("pivot", [0, 0, 0])
        rotation = bone.get("rotation", [0, 0, 0])
        cubes = []
        for cube in bone.get("cubes", []):
            origin, size = cube["origin"], cube["size"]
            inflate = float(cube.get("inflate", 0))
            low = (-(origin[0] + size[0]) - inflate, origin[1] - inflate, origin[2] - inflate)
            high = (-origin[0] + inflate, origin[1] + size[1] + inflate, origin[2] + size[2] + inflate)
            turn = cube.get("rotation")
            local = IDENTITY
            if turn and any(turn):
                cp = cube.get("pivot", [0, 0, 0])
                cp = (-cp[0], cp[1], cp[2])
                local = _matmul(_translate(*cp), _matmul(_rotate(-turn[0], -turn[1], turn[2]), _translate(-cp[0], -cp[1], -cp[2])))
            uv = cube.get("uv")
            cubes.append({"min": low, "max": high, "matrix": local, "size": tuple(float(v) for v in size),
                          "faces": uv if isinstance(uv, dict) else None, "box_uv": uv if isinstance(uv, list) else None})
        bones[bone["name"]] = {"name": bone["name"], "parent": bone.get("parent"), "pivot": (-pivot[0], pivot[1], pivot[2]),
                               "rotation": (-rotation[0], -rotation[1], rotation[2]), "cubes": cubes}
    order, seen = [], set()

    def visit(name, stack=()):
        if name in seen:
            return
        if name in stack:
            raise ValueError(f"Bone parent cycle at {name!r}")
        parent = bones[name]["parent"]
        if parent is not None and parent not in bones:
            raise ValueError(f"Bone {name!r} has unknown parent {parent!r}")
        if parent is not None:
            visit(parent, stack + (name,))
        seen.add(name)
        order.append(name)

    for name in bones:
        visit(name)
    return {"bones": bones, "order": order}


def descendants(geometry: dict, roots) -> set[str]:
    roots = set(roots)
    missing = roots - set(geometry["bones"])
    if missing:
        raise ValueError(f"Unknown bones: {', '.join(sorted(missing))}")
    result = set()
    for name in geometry["order"]:
        bone = geometry["bones"][name]
        if name in roots or bone["parent"] in result:
            result.add(name)
    return result


# ------------------------------------------------------------------ animation channels
def _vector(value, name):
    if isinstance(value, dict):
        if "vector" in value:
            value = value["vector"]
        elif "post" in value:
            value = value["post"]
        elif "pre" in value:
            value = value["pre"]
    if isinstance(value, (int, float)):
        value = [value, value, value]
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"Unsupported keyframe value in {name}: {value!r}")
    out = []
    for item in value:
        if isinstance(item, str):
            try:
                item = float(item)
            except ValueError:
                raise ValueError(f"Molang expression in {name} ({item!r}) cannot be evaluated offline") from None
        out.append(float(item))
    return tuple(out)


def _pre(value, name):
    if isinstance(value, dict) and "pre" in value:
        return _vector(value["pre"], name)
    return _vector(value, name)


def channel_times(channel) -> list[float]:
    if isinstance(channel, dict) and not ({"vector", "pre", "post"} & set(channel)):
        return sorted(float(t) for t in channel)
    return []


def sample(channel, t: float, name: str = "channel"):
    """Value of a keyframe channel at time t (linear between keys; catmull-rom is approximated linearly)."""
    if channel is None:
        return None
    if not (isinstance(channel, dict) and not ({"vector", "pre", "post"} & set(channel))):
        return _vector(channel, name)
    keys = sorted((float(time), value) for time, value in channel.items())
    if t <= keys[0][0]:
        return _pre(keys[0][1], name)
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            a, b = _vector(v0, name), _pre(v1, name)
            if t1 - t0 < 1e-9:
                return b
            f = (t - t0) / (t1 - t0)
            return tuple(a[i] + (b[i] - a[i]) * f for i in range(3))
    return _vector(keys[-1][1], name)


def load_animations(path: Path) -> dict:
    data = _load(path)
    animations = data.get("animations")
    if not isinstance(animations, dict):
        raise ValueError("Not a Bedrock/GeckoLib animation file: no animations object")
    return data


def find_clip(data: dict, clip: str) -> tuple[str, dict]:
    animations = data["animations"]
    if clip in animations:
        return clip, animations[clip]
    matches = [name for name in animations if name.rsplit(".", 1)[-1] == clip]
    if len(matches) != 1:
        raise ValueError(f"Animation {clip!r} not found (have: {', '.join(sorted(animations))})")
    return matches[0], animations[matches[0]]


def pose_at(animation: dict, t: float) -> dict:
    """{bone: (rotation_add, position, scale)} in Blockbench space."""
    pose = {}
    for bone, channels in (animation.get("bones") or {}).items():
        rotation = sample(channels.get("rotation"), t, f"{bone}.rotation")
        position = sample(channels.get("position"), t, f"{bone}.position")
        scale = sample(channels.get("scale"), t, f"{bone}.scale")
        pose[bone] = ((-rotation[0], -rotation[1], rotation[2]) if rotation else (0.0, 0.0, 0.0),
                      (-position[0], position[1], position[2]) if position else (0.0, 0.0, 0.0),
                      scale if scale else (1.0, 1.0, 1.0))
    return pose


def bone_matrices(geometry: dict, pose: dict | None = None) -> dict:
    pose = pose or {}
    matrices = {}
    for name in geometry["order"]:
        bone = geometry["bones"][name]
        rotation, position, scale = pose.get(name, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))
        pivot = bone["pivot"]
        total = tuple(bone["rotation"][i] + rotation[i] for i in range(3))
        local = _matmul(_translate(*position), _matmul(_translate(*pivot), _matmul(_rotate(*total), _matmul(
            _scale(*scale), _translate(-pivot[0], -pivot[1], -pivot[2])))))
        matrices[name] = _matmul(matrices[bone["parent"]], local) if bone["parent"] else local
    return matrices


def corners(cube: dict):
    low, high = cube["min"], cube["max"]
    for x in (low[0], high[0]):
        for y in (low[1], high[1]):
            for z in (low[2], high[2]):
                yield _point(cube["matrix"], (x, y, z))


def lowest_point(geometry: dict, matrices: dict, bones) -> float:
    low = None
    for name in bones:
        for cube in geometry["bones"][name]["cubes"]:
            for corner in corners(cube):
                y = _point(matrices[name], corner)[1]
                low = y if low is None or y < low else low
    if low is None:
        raise ValueError("The leg bones have no cubes")
    return low


# ------------------------------------------------------------------ grounding
def _key(t: float) -> str:
    text = f"{t:.4f}".rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def ground_animations(geo_path: Path, animation_path: Path, legs, clips, *, root: str = "root", fps: float | None = None) -> tuple[dict, dict]:
    """Return (new animation data, report). Keys root position y so the lowest leg point is at y = 0."""
    geometry = load_geometry(geo_path)
    data = load_animations(animation_path)
    if root not in geometry["bones"]:
        raise ValueError(f"Root bone {root!r} is not in the geometry")
    leg_bones = descendants(geometry, legs)
    if root in leg_bones:
        raise ValueError("The root bone cannot be one of the leg bones")
    report = {"geometry": str(geo_path), "animations": str(animation_path), "root": root, "legs": sorted(set(legs)), "clips": {}}
    output = json.loads(json.dumps(data))
    for clip in clips:
        name, animation = find_clip(output, clip)
        length = float(animation.get("animation_length") or 0)
        times = set()
        for channels in (animation.get("bones") or {}).values():
            for channel in channels.values():
                times.update(channel_times(channel))
        if fps:
            steps = max(1, round(length * fps))
            times.update(length * i / steps for i in range(steps + 1))
        if not times:
            times = {0.0}
        times = sorted(t for t in times if t <= length + 1e-9 or not length)
        root_channels = animation.setdefault("bones", {}).setdefault(root, {})
        old_position = root_channels.get("position")
        keys, offsets = {}, []
        for t in times:
            pose = pose_at(animation, t)
            rotation, position, scale = pose.get(root, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))
            pose[root] = (rotation, (position[0], 0.0, position[2]), scale)
            low = lowest_point(geometry, bone_matrices(geometry, pose), leg_bones)
            json_position = sample(old_position, t) if old_position is not None else (0.0, 0.0, 0.0)
            keys[_key(t)] = [round(json_position[0], 4) + 0.0, round(-low, 4) + 0.0, round(json_position[2], 4) + 0.0]
            offsets.append(-low)
        root_channels["position"] = keys
        report["clips"][name] = {"frames": len(keys), "min_offset": round(min(offsets), 4), "max_offset": round(max(offsets), 4)}
    return output, report
