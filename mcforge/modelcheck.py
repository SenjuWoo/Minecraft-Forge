"""Find z-fighting in a model before texturing it.

Two cube faces flicker when they face the same way, lie on one plane and overlap.
This reads Blockbench projects (.bbmodel), GeckoLib/Bedrock geometry (.geo.json)
and Java block models (.json), compares cubes that share one rigid frame (the same
chain of rotations about the same pivots, so their boxes stay axis-aligned to each
other), and skips an overlap covered by a third cube that contains or touches it from
outside, where nobody sees it.
Cubes in different rotation frames are not compared; the result says how many
frames there were.
"""
from __future__ import annotations

import json
from pathlib import Path

from .shapes import read_bbmodel

# Face names in Blockbench/Java coordinates: +X east, +Y up, +Z south.
NAMES = {(0, 1): "east", (0, -1): "west", (1, 1): "up", (1, -1): "down", (2, 1): "south", (2, -1): "north"}
ALL_FACES = frozenset(NAMES.values())
MAX_FILE = 64 * 1024 * 1024


def _turned(rotation) -> bool:
    return any(abs(float(angle)) > 1e-9 for angle in (rotation or (0, 0, 0)))


def _frame(chain: tuple, pivot, rotation) -> tuple:
    if not _turned(rotation):
        return chain
    return chain + ((tuple(round(float(v), 4) for v in pivot or (0, 0, 0)), tuple(round(float(a), 4) for a in rotation)),)


def _box(name, bone, frame, low, high, inflate, faces) -> dict:
    low = [float(v) - inflate for v in low]
    high = [float(v) + inflate for v in high]
    return {"name": name, "bone": bone, "frame": frame, "min": low, "max": high, "faces": faces}


def _bbmodel_boxes(data: dict) -> list[dict]:
    project = read_bbmodel(data)
    boxes = []

    def faces_of(cube):
        faces = cube.get("faces")
        if not faces:
            return ALL_FACES
        # Texture index 0 is a real texture: test identity, since 0 == False in Python.
        return frozenset(name for name, face in faces.items()
                         if name in ALL_FACES and face.get("texture") is not None and face.get("texture") is not False)

    def add(cube, bone, chain):
        if cube.get("export") is False:
            return
        frame = _frame(chain, cube.get("origin"), cube.get("rotation"))
        low, high = cube["from"], cube["to"]
        boxes.append(_box(cube.get("name", "cube"), bone, frame, [min(a, b) for a, b in zip(low, high)],
                          [max(a, b) for a, b in zip(low, high)], float(cube.get("inflate", 0)), faces_of(cube)))

    def walk(nodes, bone, chain):
        for node in nodes:
            if "cube" in node:
                add(node["cube"], bone, chain)
            else:
                group = node["bone"]
                walk(node["children"], group.get("name", bone), _frame(chain, group.get("origin"), group.get("rotation")))

    walk(project["tree"], None, ())
    if not project["tree"]:
        # A project without an outliner: every cube sits at the root.
        for cube in project["cubes"]:
            add(cube, None, ())
    return boxes


def _geo_boxes(data: dict) -> list[dict]:
    geometries = data.get("minecraft:geometry")
    if not isinstance(geometries, list) or not geometries:
        raise ValueError("Not a Bedrock/GeckoLib geometry file: no minecraft:geometry list")
    bones = {bone["name"]: bone for bone in geometries[0].get("bones", [])}
    chains: dict[str, tuple] = {}

    def chain_of(name, seen=()):
        if name in chains:
            return chains[name]
        if name in seen:
            raise ValueError(f"Bone parent cycle at {name!r}")
        bone = bones[name]
        parent = bone.get("parent")
        base = chain_of(parent, seen + (name,)) if parent in bones else ()
        chains[name] = _frame(base, bone.get("pivot"), bone.get("rotation"))
        return chains[name]

    boxes = []
    for name, bone in bones.items():
        for index, cube in enumerate(bone.get("cubes", [])):
            # Bedrock stores x mirrored ([-x1, y0, z0]); flip it back so face names match Blockbench.
            origin, size = cube["origin"], cube["size"]
            low = [-(origin[0] + size[0]), origin[1], origin[2]]
            high = [-origin[0], origin[1] + size[1], origin[2] + size[2]]
            pivot = cube.get("pivot")
            rotation = cube.get("rotation")
            if pivot is not None:
                pivot = [-pivot[0], pivot[1], pivot[2]]
            if rotation is not None:
                rotation = [-rotation[0], -rotation[1], rotation[2]]
            uv = cube.get("uv")
            faces = frozenset(uv) & ALL_FACES if isinstance(uv, dict) else ALL_FACES
            boxes.append(_box(f"{name}#{index}", name, _frame(chain_of(name), pivot, rotation),
                              [min(a, b) for a, b in zip(low, high)], [max(a, b) for a, b in zip(low, high)],
                              float(cube.get("inflate", 0)), faces))
    return boxes


def _block_boxes(data: dict) -> list[dict]:
    boxes = []
    for index, element in enumerate(data.get("elements", [])):
        rotation = element.get("rotation")
        frame = ()
        if rotation and float(rotation.get("angle", 0)):
            frame = ((tuple(rotation.get("origin", (8, 8, 8))), (rotation.get("axis"), float(rotation["angle"]))),)
        low, high = element["from"], element["to"]
        boxes.append(_box(element.get("name", f"element#{index}"), None, frame, [min(a, b) for a, b in zip(low, high)],
                          [max(a, b) for a, b in zip(low, high)], 0.0, frozenset(element.get("faces", {})) & ALL_FACES))
    return boxes


def load_boxes(path: Path) -> tuple[str, list[dict]]:
    path = Path(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError("Model file exceeds 64 MiB")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Model file is not a JSON object")
    if "minecraft:geometry" in data:
        return "geo", _geo_boxes(data)
    if "outliner" in data or "meta" in data:
        return "bbmodel", _bbmodel_boxes(data)
    if "elements" in data:
        return "block", _block_boxes(data)
    raise ValueError("Unknown model format: expected .bbmodel, .geo.json or a block model with elements")


def _hidden(plane: float, axis: int, sign: int, rect: list[tuple[float, float]], others: list[dict], eps: float) -> bool:
    """True when another cube fills the space just outside the overlap rectangle (it contains or touches the face)."""
    sides = [b for b in range(3) if b != axis]
    for box in others:
        if sign > 0 and not (box["min"][axis] <= plane + eps and box["max"][axis] > plane + eps):
            continue
        if sign < 0 and not (box["max"][axis] >= plane - eps and box["min"][axis] < plane - eps):
            continue
        if all(box["min"][b] <= low + eps and high <= box["max"][b] + eps for b, (low, high) in zip(sides, rect)):
            return True
    return False


def check_model(path: Path, eps: float = 0.01) -> dict:
    """Report same-facing coplanar overlapping faces (z-fighting) in a model file."""
    if not 0 < eps <= 1:
        raise ValueError("--eps must be between 0 and 1 pixel")
    kind, boxes = load_boxes(path)
    frames: dict[tuple, list[dict]] = {}
    for box in boxes:
        frames.setdefault(box["frame"], []).append(box)
    findings = []
    for members in frames.values():
        for axis in range(3):
            sides = [b for b in range(3) if b != axis]
            for sign in (1, -1):
                face = NAMES[(axis, sign)]
                planes = sorted(((box["max"][axis] if sign > 0 else box["min"][axis]), index)
                                for index, box in enumerate(members) if face in box["faces"])
                for position, (plane, first) in enumerate(planes):
                    for other_plane, second in planes[position + 1:]:
                        if other_plane - plane > eps:
                            break
                        a, b = members[first], members[second]
                        rect = [(max(a["min"][s], b["min"][s]), min(a["max"][s], b["max"][s])) for s in sides]
                        if any(high - low <= 1e-3 for low, high in rect):
                            continue
                        rest = [box for index, box in enumerate(members) if index not in (first, second)]
                        if _hidden((plane + other_plane) / 2, axis, sign, rect, rest, eps):
                            continue
                        findings.append({"cubes": [a["name"], b["name"]], "bones": [a["bone"], b["bone"]], "face": face,
                                         "plane": round(plane, 4), "gap": round(other_plane - plane, 4),
                                         "overlap": [round(high - low, 4) for low, high in rect]})
    return {"file": str(path), "format": kind, "cubes": len(boxes), "frames": len(frames), "eps": eps,
            "z_fighting": findings, "status": "z_fighting" if findings else "clean",
            "note": "Cubes are compared within one rigid frame (same rotations about the same pivots) at the rest pose; "
                    "posed frames and cubes in different frames are not checked. Every cube counts as opaque, so an overlap "
                    "covered by another cube is skipped."}
