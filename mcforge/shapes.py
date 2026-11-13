"""Procedural geometry: furniture block models and simple mob rigs.

One description of each shape feeds every output: the block model JSON or Java
model class, the collision boxes, the texture layout, the Blockbench project and
the preview render. Mob rigs use Minecraft's model space (Y down, ground at 24).
"""
from __future__ import annotations

import base64
import math
import uuid

# Block-space boxes (0..16, Y up); the front of each piece faces north (-Z).
FURNITURE = {
    "chair": {"boxes": [("seat", (2, 6, 2), (14, 8, 14)), ("leg", (2, 0, 2), (4, 6, 4)), ("leg", (12, 0, 2), (14, 6, 4)),
                        ("leg", (2, 0, 12), (4, 6, 14)), ("leg", (12, 0, 12), (14, 6, 14)), ("back", (2, 8, 12), (14, 16, 14))]},
    "table": {"boxes": [("top", (0, 13, 0), (16, 16, 16)), ("leg", (1, 0, 1), (3, 13, 3)), ("leg", (13, 0, 1), (15, 13, 3)),
                        ("leg", (1, 0, 13), (3, 13, 15)), ("leg", (13, 0, 13), (15, 13, 15))]},
    "stool": {"boxes": [("seat", (3, 7, 3), (13, 9, 13)), ("leg", (4, 0, 4), (6, 7, 6)), ("leg", (10, 0, 4), (12, 7, 6)),
                        ("leg", (4, 0, 10), (6, 7, 12)), ("leg", (10, 0, 10), (12, 7, 12))]},
    "bench": {"boxes": [("seat", (0, 6, 3), (16, 8, 13)), ("support", (1, 0, 4), (3, 6, 12)), ("support", (13, 0, 4), (15, 6, 12))]},
    "shelf": {"boxes": [("back", (0, 0, 14), (16, 16, 16)), ("side", (0, 0, 7), (1, 16, 14)), ("side", (15, 0, 7), (16, 16, 14)),
                        ("board", (1, 3, 7), (15, 4, 14)), ("board", (1, 11, 7), (15, 12, 14))]},
    "cabinet": {"boxes": [("body", (1, 0, 2), (15, 13, 16)), ("top", (0, 13, 1), (16, 15, 16)), ("knob", (7, 7, 1), (9, 8, 2))]},
    "lamp": {"boxes": [("base", (5, 0, 5), (11, 1, 11)), ("pole", (7, 1, 7), (9, 10, 9)), ("shade", (4, 10, 4), (12, 15, 12))], "light": 14},
    "pedestal": {"boxes": [("base", (2, 0, 2), (14, 3, 14)), ("column", (4, 3, 4), (12, 13, 12)), ("cap", (2, 13, 2), (14, 16, 14))]},
}
FACES = ("down", "up", "north", "south", "west", "east")
FACINGS = ("north", "east", "south", "west")


def furniture_model(mod_id: str, asset_id: str, kind: str) -> dict:
    """Block model with position-derived UVs, so one tiling texture covers every face."""
    elements = [{"name": name, "from": list(start), "to": list(end),
                 "faces": {face: {"texture": "#all"} for face in FACES}} for name, start, end in FURNITURE[kind]["boxes"]]
    return {"parent": "minecraft:block/block", "textures": {"all": f"{mod_id}:block/{asset_id}", "particle": f"{mod_id}:block/{asset_id}"},
            "elements": elements}


def furniture_blockstate(mod_id: str, asset_id: str) -> dict:
    return {"variants": {f"facing={facing}": ({"model": f"{mod_id}:block/{asset_id}"} | ({"y": 90 * index} if index else {}))
                         for index, facing in enumerate(FACINGS)}}


def furniture_shapes(kind: str) -> dict[str, list[tuple[float, ...]]]:
    """Collision boxes per facing; each quarter turn maps (x, z) to (16 - z, x)."""
    shapes = {}
    boxes = [(*start, *end) for _, start, end in FURNITURE[kind]["boxes"]]
    for facing in FACINGS:
        shapes[facing] = boxes
        boxes = [(16 - z2, y1, x1, 16 - z1, y2, x2) for x1, y1, z1, x2, y2, z2 in boxes]
    return shapes


def default_uv(face: str, start, end) -> list[float]:
    """The UV rectangle Minecraft derives for a block-model face that declares none."""
    x1, y1, z1 = start
    x2, y2, z2 = end
    return {"down": [x1, 16 - z2, x2, 16 - z1], "up": [x1, z1, x2, z2], "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
            "south": [x1, 16 - y2, x2, 16 - y1], "west": [z1, 16 - y2, z2, 16 - y1], "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1]}[face]


# ---- mob rigs -------------------------------------------------------------

def _part(name, pivot, cubes, role=None, face=False):
    return {"name": name, "pivot": pivot, "cubes": [{"origin": origin, "size": size} for origin, size in cubes], "role": role, "face": face}


RIGS = {
    "quadruped": {"hitbox": (0.9, 1.0), "shadow": 0.6, "parts": [
        _part("head", (0, 10, -6), [((-4, -4, -8), (8, 8, 8)), ((-2, 0, -9), (4, 3, 1))], "head", True),
        _part("body", (0, 12, 2), [((-5, -4, -8), (10, 8, 16))]),
        _part("leg_front_right", (-3, 16, -5), [((-2, 0, -2), (4, 8, 4))], "leg_a"),
        _part("leg_front_left", (3, 16, -5), [((-2, 0, -2), (4, 8, 4))], "leg_b"),
        _part("leg_back_right", (-3, 16, 7), [((-2, 0, -2), (4, 8, 4))], "leg_b"),
        _part("leg_back_left", (3, 16, 7), [((-2, 0, -2), (4, 8, 4))], "leg_a")]},
    "biped": {"hitbox": (0.6, 1.95), "shadow": 0.5, "parts": [
        _part("head", (0, 0, 0), [((-4, -8, -4), (8, 8, 8))], "head", True),
        _part("body", (0, 0, 0), [((-4, 0, -2), (8, 12, 4))]),
        _part("right_arm", (-5, 2, 0), [((-3, -2, -2), (4, 12, 4))], "leg_b"),
        _part("left_arm", (5, 2, 0), [((-1, -2, -2), (4, 12, 4))], "leg_a"),
        _part("right_leg", (-2, 12, 0), [((-2, 0, -2), (4, 12, 4))], "leg_a"),
        _part("left_leg", (2, 12, 0), [((-2, 0, -2), (4, 12, 4))], "leg_b")]},
    "blob": {"hitbox": (0.7, 0.8), "shadow": 0.45, "parts": [
        _part("body", (0, 17, 0), [((-5, -5, -5), (10, 10, 10)), ((-2, -7, -1), (4, 2, 2))], "head", True),
        _part("foot_right", (-3, 22, 0), [((-2, 0, -2), (4, 2, 4))], "leg_a"),
        _part("foot_left", (3, 22, 0), [((-2, 0, -2), (4, 2, 4))], "leg_b")]},
}


def mob_rig(archetype: str) -> dict:
    """Return a rig with packed box-UV offsets and a power-of-two texture size."""
    source = RIGS[archetype]
    rig = {"archetype": archetype, "hitbox": source["hitbox"], "shadow": source["shadow"], "parts": []}
    x = y = shelf = 0
    for part in source["parts"]:
        cubes = []
        for cube in part["cubes"]:
            width, height, depth = cube["size"]
            footprint = (2 * (width + depth), depth + height)
            if x + footprint[0] > 64:
                x, y, shelf = 0, y + shelf, 0
            cubes.append({"origin": cube["origin"], "size": cube["size"], "uv": (x, y)})
            x += footprint[0]
            shelf = max(shelf, footprint[1])
        rig["parts"].append({"name": part["name"], "pivot": part["pivot"], "rotation": (0, 0, 0), "cubes": cubes,
                             "role": part["role"], "face": part["face"], "children": []})
    used = y + shelf
    rig["texture"] = (64, 32 if used <= 32 else 64 if used <= 64 else 128)
    return rig


# ---- Blockbench projects ----------------------------------------------------

def _uuid(*parts) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "mcforge:" + ":".join(str(part) for part in parts)))


def _texture_entry(name: str, png: bytes) -> dict:
    return {"name": name + ".png", "id": "0", "uuid": _uuid(name, "texture"), "particle": True,
            "source": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}


def furniture_bbmodel(asset_id: str, kind: str, png: bytes, size: int) -> dict:
    """Blockbench "Java Block/Item" project of a furniture model, texture embedded."""
    elements = []
    for index, (name, start, end) in enumerate(FURNITURE[kind]["boxes"]):
        elements.append({"name": name, "type": "cube", "uuid": _uuid(asset_id, index), "from": list(start), "to": list(end),
                         "origin": [8, 8, 8], "rotation": [0, 0, 0], "box_uv": False, "autouv": 0, "color": index % 8,
                         "faces": {face: {"uv": default_uv(face, start, end), "texture": 0} for face in FACES}})
    return {"meta": {"format_version": "4.10", "model_format": "java_block", "box_uv": False}, "name": asset_id,
            "resolution": {"width": 16, "height": 16}, "elements": elements, "outliner": [element["uuid"] for element in elements],
            "textures": [_texture_entry(asset_id, png)]}


def rig_bbmodel(asset_id: str, rig: dict, png: bytes) -> dict:
    """Blockbench "Modded Entity" project of a rig.

    Blockbench mirrors X and measures Y up from the ground, the inverse of its
    own Java export: origin = (-pivot.x, 24 - pivot.y, pivot.z).
    """
    elements, outliner = [], []
    for part in rig["parts"]:
        origin = [-part["pivot"][0], 24 - part["pivot"][1], part["pivot"][2]]
        children = []
        for index, cube in enumerate(part["cubes"]):
            x, y, z = cube["origin"]
            width, height, depth = cube["size"]
            high = [origin[0] - x, origin[1] - y, origin[2] + z + depth]
            low = [high[0] - width, high[1] - height, origin[2] + z]
            element = {"name": part["name"], "type": "cube", "uuid": _uuid(asset_id, part["name"], index), "from": low, "to": high,
                       "origin": origin, "rotation": [0, 0, 0], "box_uv": True, "uv_offset": list(cube["uv"]), "autouv": 0, "color": 0}
            elements.append(element)
            children.append(element["uuid"])
        outliner.append({"name": part["name"], "uuid": _uuid(asset_id, part["name"], "group"), "origin": origin,
                         "rotation": [0, 0, 0], "isOpen": True, "children": children})
    width, height = rig["texture"]
    return {"meta": {"format_version": "4.10", "model_format": "modded_entity", "box_uv": True}, "name": asset_id,
            "modded_entity_version": "1.17", "modded_entity_flip_y": True,
            "resolution": {"width": width, "height": height}, "elements": elements, "outliner": outliner,
            "textures": [_texture_entry(asset_id, png)]}


def read_bbmodel(model: dict) -> dict:
    """Normalise a Blockbench project: format, texture bytes, cubes by uuid and the bone tree.

    Accepts both project layouts: bones inline in the outliner (4.x) and bones
    stored in ``groups`` with the outliner holding only their uuids (5.x).
    """
    meta = model.get("meta") or {}
    cubes = {element["uuid"]: element for element in model.get("elements", []) if element.get("type", "cube") == "cube"}
    groups = {group["uuid"]: group for group in model.get("groups", []) if isinstance(group, dict) and "uuid" in group}

    def walk(nodes):
        result = []
        for node in nodes:
            if isinstance(node, str):
                if node in cubes:
                    result.append({"cube": cubes[node]})
                continue
            merged = groups.get(node.get("uuid"), {}) | node
            result.append({"bone": merged, "children": walk(node.get("children", []))})
        return result

    textures = []
    for texture in model.get("textures", []):
        source = texture.get("source", "")
        if source.startswith("data:image/png;base64,"):
            textures.append({"name": texture.get("name", "texture.png"), "png": base64.b64decode(source.split(",", 1)[1])})
    resolution = model.get("resolution") or {}
    return {"format": meta.get("model_format", "java_block"), "box_uv": bool(meta.get("box_uv")), "name": model.get("name", "model"),
            "resolution": (resolution.get("width", 16), resolution.get("height", 16)), "tree": walk(model.get("outliner", [])),
            "cubes": list(cubes.values()), "textures": textures}


def bbmodel_to_block_model(project: dict, texture_ref: str) -> dict:
    """Convert a "Java Block/Item" project to a block model (per-face UV, one texture)."""
    width, height = project["resolution"]
    elements = []
    for cube in project["cubes"]:
        if cube.get("export") is False:
            continue
        faces = {}
        for name, face in (cube.get("faces") or {}).items():
            if face.get("texture") is None or name not in FACES:
                continue
            u1, v1, u2, v2 = face.get("uv", [0, 0, 16, 16])
            entry = {"uv": [round(u1 * 16 / width, 4), round(v1 * 16 / height, 4), round(u2 * 16 / width, 4), round(v2 * 16 / height, 4)],
                     "texture": "#all"}
            if face.get("rotation"):
                entry["rotation"] = face["rotation"]
            faces[name] = entry
        element = {"from": [round(value, 4) for value in cube["from"]], "to": [round(value, 4) for value in cube["to"]], "faces": faces}
        turned = [(axis, angle) for axis, angle in zip("xyz", cube.get("rotation", [0, 0, 0])) if angle]
        if len(turned) > 1:
            raise ValueError(f"Cube {cube.get('name')!r} is rotated on two axes; block models allow one axis per element")
        if turned:
            element["rotation"] = {"angle": turned[0][1], "axis": turned[0][0], "origin": cube.get("origin", [8, 8, 8])}
        elements.append(element)
    if not elements:
        raise ValueError("The Blockbench project contains no exportable cubes")
    return {"parent": "minecraft:block/block", "textures": {"all": texture_ref, "particle": texture_ref}, "elements": elements}


def bbmodel_to_rig(project: dict) -> dict:
    """Convert a "Modded Entity" project to a rig, using Blockbench's own Java-export arithmetic."""
    def bone(node, parent_origin):
        data = node["bone"]
        origin = data.get("origin", [0, 0, 0])
        rotation = data.get("rotation", [0, 0, 0])
        pivot = [origin[0] - parent_origin[0], origin[1] - parent_origin[1], origin[2] - parent_origin[2]] if parent_origin else list(origin)
        pivot = (-pivot[0], -pivot[1] + (0 if parent_origin else 24), pivot[2])
        part = {"name": _java_name(data.get("name", "bone")), "pivot": pivot,
                "rotation": (math.radians(-rotation[0]), math.radians(-rotation[1]), math.radians(rotation[2])),
                "cubes": [], "role": None, "face": False, "children": []}
        for child in node["children"]:
            if "cube" in child:
                cube = child["cube"]
                if cube.get("export") is False:
                    continue
                if any(cube.get("rotation", [0, 0, 0])):
                    raise ValueError(f"Cube {cube.get('name')!r} is rotated; in Blockbench, move its rotation onto a bone")
                size = [cube["to"][index] - cube["from"][index] for index in range(3)]
                part["cubes"].append({"origin": (origin[0] - cube["to"][0], -cube["from"][1] - size[1] + origin[1], cube["from"][2] - origin[2]),
                                      "size": tuple(size), "uv": tuple(cube.get("uv_offset", [0, 0])), "inflate": cube.get("inflate", 0),
                                      "mirror": bool(cube.get("mirror_uv"))})
            else:
                part["children"].append(bone(child, origin))
        return part

    parts = [bone(node, None) for node in project["tree"] if "bone" in node]
    if not parts:
        raise ValueError("The Blockbench project has no bones; group its cubes in the outliner first")
    seen: dict[str, int] = {}

    def unique(part):
        count = seen.get(part["name"], 0)
        seen[part["name"]] = count + 1
        if count:
            part["name"] += f"_{count + 1}"
        for child in part["children"]:
            unique(child)
    for part in parts:
        unique(part)
    return {"archetype": "imported", "hitbox": (0.8, 1.0), "shadow": 0.5, "parts": parts, "texture": project["resolution"]}


def _java_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in name.strip().lower()).strip("_") or "bone"
    return ("part_" + cleaned) if cleaned[0].isdigit() else cleaned


def walk_parts(parts: list[dict]):
    for part in parts:
        yield part
        yield from walk_parts(part["children"])
