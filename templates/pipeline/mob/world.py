"""Where this mob lives: structure templates built from code, their worldgen data and natural spawns
(lib/worldgen.py writes them; `build_assets.py world --validate` checks the set is complete).

build() returns a short summary. Delete what the mob does not need: a mob that only spawns naturally keeps
natural_spawns(); a mob with a home keeps the template and one structure.

The example den holds the home block of `minecraft-forge kit PROJECT home --mob <mob>` (block id
`<mod>:<mob>_home`): its block entity forms the mob there. Until that kit is added, the block id does not exist
and the game replaces it with air when the template is placed.
"""
from lib import paths
from lib import worldgen as W

DEN = "sentinel_den"


def den():
    """A 9x6x9 stone den: floor, low walls with a doorway to the north, four corner pillars, a slab roof, a lantern."""
    blocks = {}
    for x in range(9):
        for z in range(9):
            blocks[(x, 0, z)] = "minecraft:mossy_cobblestone" if (x * 3 + z * 5) % 7 == 0 else "minecraft:cobblestone"
            edge = x in (0, 8) or z in (0, 8)
            door = z == 0 and 3 <= x <= 5
            for y in range(1, 5):
                if edge and not door:
                    corner = x in (0, 8) and z in (0, 8)
                    blocks[(x, y, z)] = "minecraft:stone_bricks" if corner or y < 3 else "minecraft:air"
                else:
                    blocks[(x, y, z)] = "minecraft:air"
            blocks[(x, 5, z)] = ("minecraft:stone_brick_slab", {"type": "bottom", "waterlogged": "false"})
    blocks[(4, 1, 6)] = f"{paths.MOD}:{paths.MOB}_home"
    blocks[(4, 4, 4)] = ("minecraft:lantern", {"hanging": "true", "waterlogged": "false"})
    return (9, 6, 9), blocks


def build() -> str:
    size, blocks = den()
    W.write_template(DEN, size, blocks)
    W.surface_structure(DEN, sink=1)
    W.biome_tag(DEN, ["#minecraft:is_forest", "#minecraft:is_taiga", "minecraft:plains", "minecraft:meadow"])
    W.structure_set(DEN + "s", [(DEN, 1)], spacing=34, separation=12)
    W.structures_tag(DEN + "s", [DEN])
    # A fluid-anchored home instead (needs kit home): cave lava with six open blocks over it, floor at the surface.
    # W.anchored_structure("sentinel_forge", "minecraft:lava", min_y=-63, max_y=-1)
    # W.biome_tag("sentinel_forge", ["#minecraft:is_overworld"])
    # In the Nether: W.anchored_structure("sentinel_shore", "minecraft:lava", 24, 40, step="surface_structures")
    #                W.biome_tag("sentinel_shore", ["minecraft:nether_wastes", "minecraft:basalt_deltas", "minecraft:crimson_forest"])
    # Natural spawns without a structure:
    # W.natural_spawns("sentinel_spawns", "#minecraft:is_forest", weight=4)
    return f"{DEN} {size[0]}x{size[1]}x{size[2]}, {len(blocks)} blocks, set {DEN}s"
