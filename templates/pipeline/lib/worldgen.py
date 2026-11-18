"""World: mob/world.py -> structure templates (.nbt), structure, structure-set, template-pool and tag JSON, and a
biome modifier for natural spawns. Everything is data, so a pack can retune it with a datapack.

Two ways to place a structure:
- "surface": a `minecraft:jigsaw` single piece projected to the surface heightmap. No Java. For things that stand
  on the ground and may bring their own pool or crater.
- "anchored": the `<mod>:<mob>_home` structure type of `minecraft-forge kit PROJECT home` against a natural fluid
  surface (cave lava, the Nether lava sea, water). Lake features generate after structures and cannot be queried
  during placement; the generator's base column can.

Rules that cost a session each when they were missing:
- Do not store the mob in the template. Put the home block (kit home) there: its block entity forms the mob,
  adopts an existing one and re-forms it. A template entity exists once and every /place duplicates it.
- A structure needs all of: the template, `worldgen/structure`, a `worldgen/structure_set` that lists it, and a
  biome tag `tags/worldgen/biome/has_structure/<name>` it names in "biomes". Missing any one fails silently.
- Test worlds must be created with structure generation on (flat test worlds usually have it off): with it off,
  the placement check passes and no start is ever generated, and a locate search runs for minutes and finds
  nothing. `minecraft-forge verify PROJECT --client --world normal` creates such a world.
- Every search for a structure is bounded (rings, radius): an unbounded locate stalls the server where none is near.
- Keep each template at most 48x48x48 (one structure block load) and give interiors a ceiling the mob fits under.
- Template blocks next to aquifers get waterlogged or crusted; the kit's piece ignores waterlogging, and water
  meeting your lava is cosmetic but worth a line in the validation notes.
"""
from __future__ import annotations

import zlib

from . import nbt, paths

DATA = paths.DATA
STRUCTURE = DATA / "structure"
WORLDGEN = DATA / "worldgen"


def salt(name: str) -> int:
    """A stable placement salt per structure set (the same world seed must not line different sets up)."""
    return zlib.crc32(f"{paths.MOD}:{name}".encode()) & 0x7FFFFFFF


def write_template(name: str, size, blocks, entities=()) -> None:
    if any(s > 48 for s in size):
        raise ValueError(f"template {name} is {size}; keep each side at most 48 blocks")
    path = STRUCTURE / f"{name}.nbt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(nbt.dumps(nbt.structure(size, blocks, entities)))


def surface_structure(name: str, sink: int = 0, adaptation: str = "beard_thin") -> None:
    """A jigsaw single piece on the surface: `sink` blocks below the heightmap, terrain shaped around it."""
    paths.write_json(WORLDGEN / "template_pool" / f"{name}.json", {"fallback": "minecraft:empty", "elements": [{"weight": 1, "element": {
        "element_type": "minecraft:single_pool_element", "location": f"{paths.MOD}:{name}", "processors": "minecraft:empty",
        "projection": "rigid"}}]})
    paths.write_json(WORLDGEN / "structure" / f"{name}.json", {
        "type": "minecraft:jigsaw", "biomes": f"#{paths.MOD}:has_structure/{name}", "step": "surface_structures", "spawn_overrides": {},
        "terrain_adaptation": adaptation, "start_pool": f"{paths.MOD}:{name}", "size": 1, "start_height": {"absolute": -sink},
        "project_start_to_heightmap": "WORLD_SURFACE_WG", "max_distance_from_center": 80, "use_expansion_hack": False})


def anchored_structure(name: str, fluid: str, min_y: int, max_y: int, air_above: int = 6, floor_offset: int = -1,
                       step: str = "underground_structures") -> None:
    """The kit's fluid-anchored type. Cave lava: y -63..-1. Nether lava sea: y 24..40, step surface_structures."""
    paths.write_json(WORLDGEN / "structure" / f"{name}.json", {
        "type": f"{paths.MOD}:{paths.MOB}_home", "biomes": f"#{paths.MOD}:has_structure/{name}", "step": step, "spawn_overrides": {},
        "terrain_adaptation": "none", "template": f"{paths.MOD}:{name}", "fluid": fluid, "min_y": min_y, "max_y": max_y,
        "air_above": air_above, "floor_offset": floor_offset})


def biome_tag(name: str, biomes) -> None:
    paths.write_json(DATA / "tags/worldgen/biome/has_structure" / f"{name}.json", {"replace": False, "values": list(biomes)})


def structure_set(name: str, members, spacing: int, separation: int) -> None:
    """members: [(structure name, weight)]. spacing/separation in chunks: one try per spacing x spacing cell, at
    least `separation` apart. Rare landmarks 32-48 / 16-24; Nether 24-32 / 8-12 (it is eight times smaller)."""
    if separation >= spacing:
        raise ValueError("separation must be smaller than spacing")
    paths.write_json(WORLDGEN / "structure_set" / f"{name}.json", {
        "structures": [{"structure": f"{paths.MOD}:{n}", "weight": w} for n, w in members],
        "placement": {"type": "minecraft:random_spread", "spacing": spacing, "separation": separation, "salt": salt(name)}})


def structures_tag(name: str, structures) -> None:
    """A structure tag for locating items, maps and advancements (`#<mod>:<name>`)."""
    paths.write_json(DATA / "tags/worldgen/structure" / f"{name}.json", {"replace": False, "values": [f"{paths.MOD}:{s}" for s in structures]})


def natural_spawns(name: str, biomes: str, weight: int, min_count: int = 1, max_count: int = 1) -> None:
    """A NeoForge biome modifier adding the mob to biomes (a tag such as "#c:is_snowy" or a biome id)."""
    paths.write_json(DATA / "neoforge/biome_modifier" / f"{name}.json", {
        "type": "neoforge:add_spawns", "biomes": biomes,
        "spawners": [{"type": f"{paths.MOD}:{paths.MOB}", "weight": weight, "minCount": min_count, "maxCount": max_count}]})


def run(args) -> int:
    from mob import world as MW
    made = MW.build()
    print(f"world: {made}")
    return 0


def validate(args) -> int:
    import json
    errs = []
    names = {p.stem for p in (WORLDGEN / "structure").glob("*.json")} if (WORLDGEN / "structure").is_dir() else set()
    in_sets = set()
    if (WORLDGEN / "structure_set").is_dir():
        for path in (WORLDGEN / "structure_set").glob("*.json"):
            for member in json.loads(path.read_text(encoding="utf-8"))["structures"]:
                in_sets.add(member["structure"].split(":", 1)[1])
    for name in sorted(names):
        data = json.loads((WORLDGEN / "structure" / f"{name}.json").read_text(encoding="utf-8"))
        template = data.get("template") or f"{paths.MOD}:{name}"
        if not (STRUCTURE / f"{template.split(':', 1)[1]}.nbt").is_file():
            errs.append(f"{name}: template {template} has no .nbt file")
        tag = data["biomes"].lstrip("#").split(":", 1)[1]
        if data["biomes"].startswith("#") and not (DATA / "tags/worldgen/biome" / f"{tag}.json").is_file():
            errs.append(f"{name}: biome tag {data['biomes']} does not exist")
        if name not in in_sets:
            errs.append(f"{name}: not listed in any structure set, so it never generates")
        if data["type"] == "minecraft:jigsaw" and not (WORLDGEN / "template_pool" / f"{data['start_pool'].split(':', 1)[1]}.json").is_file():
            errs.append(f"{name}: start pool {data['start_pool']} does not exist")
    for path in sorted(STRUCTURE.glob("*.nbt")) if STRUCTURE.is_dir() else []:
        root = nbt.loads(path.read_bytes())
        size = [v.v for v in root.v["size"].v]
        blocks = {p.v["Name"].v for p in root.v["palette"].v}
        if root.v["DataVersion"].v != nbt.DATA_VERSION:
            errs.append(f"{path.name}: DataVersion {root.v['DataVersion'].v}, expected {nbt.DATA_VERSION}")
        print(f"template {path.stem}: {size[0]}x{size[1]}x{size[2]}, {len(root.v['blocks'].v)} blocks, {len(blocks)} block kinds")
    for e in errs:
        print("WORLD ERROR:", e)
    print(f"world validate: {len(names)} structure(s), {len(errs)} error(s)")
    return 1 if errs else 0
