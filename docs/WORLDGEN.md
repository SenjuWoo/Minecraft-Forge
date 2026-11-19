# Where a mob lives: homes, structures, natural spawns (NeoForge 1.21.1)

How finished mods put a character into the world and proved it: a home block that forms the mob, structures generated from code, placement against natural lava in the Overworld and the Nether, and a real-worldgen check. Each rule below cost a session when it was missing.

```text
minecraft-forge kit PROJECT home --mob NAME                 # home block + block entity, fluid-anchored structure type, GameTests
python -I asset-pipeline/build_assets.py world --validate    # templates (.nbt), structure, structure set, biome tags (mob/world.py)
minecraft-forge verify PROJECT                               # GameTests: the home forms one resident; the fluid scanner
minecraft-forge verify PROJECT --client --world normal       # a normal world with structures ON: locate scenes
minecraft-forge devlog PROJECT                               # {"kind": "locate", "equals": {"found": "1"}, "field": "ms", "max": 5000}
```

## Pick the mechanism

| The mob | Use |
|---|---|
| Appears in biomes like an animal or monster | natural spawns: a `neoforge:add_spawns` biome modifier (data) and a spawn placement (`RegisterSpawnPlacementsEvent`) |
| Belongs to a place and should always be there | a **home block** inside a structure; the block entity forms the mob |
| Is unique per player or summoned | an item or event creates it; store ownership in synced data and `SavedData` |
| Lives in villages | find meeting points with `PoiManager`, record the village in `SavedData` (`guide entities`) |
| Grows or lives in certain biomes with something it needs (a plant, a nest, an ore) | vegetation: a placed feature added by a `neoforge:add_features` biome modifier on a biome tag, plus natural spawns; the mob places a few starting blocks in `finalizeSpawn`. No structure: in a pack with terrain mods (Tectonic, Lithostitched) structures are risk for no gain |

## The home block (do not store the mob in the template)

A template entity is created once, cannot come back after it dies or is discarded, and every `/place template` duplicates it. A home block is a block whose block entity:

- forms the mob on its first server tick at a free, dry, sturdy spot beside it (`create`, `moveTo`, `finalizeSpawn(level, difficulty, MobSpawnType.STRUCTURE, null)`, `setPersistenceRequired`, `addFreshEntityWithPassengers`);
- adopts a resident that already lives there instead of making a second one (the resident carries the home position in its persistent data);
- re-forms the resident after a delay when it is gone, and only decides "gone" where entities really tick (`isPositionEntityTicking`): an unloaded mob is not a missing one;
- saves the resident's UUID, the timer and the formed flag.

`kit PROJECT home --mob NAME` writes this (`<Name>HomeBlock`, `<Name>HomeBlockEntity`, self-registering) with a GameTest that places the block and expects exactly one resident. The mob reads its home with `BlockPos.of(getPersistentData().getLong(HOME_KEY))` for leashing, schedules and returning. A defeat that is not a death (the mob retreats, sinks, sleeps) calls `residentLeft(uuid, ticks)` for a shorter wait.

Keep "home" separate from every other anchor the mob has (a stay or guard position, a work station): one field per meaning, or a command overwrites the home.

## Structures from code

`mob/world.py` builds templates as `{(x, y, z): block}` dictionaries and `lib/worldgen.py` writes the NBT (`DataVersion` 3955 for 1.21.1) and the JSON. A structure only generates when **all four** exist, and a missing one fails silently:

| File | Purpose |
|---|---|
| `data/<mod>/structure/<name>.nbt` | the template (at most 48 blocks per side) |
| `data/<mod>/worldgen/structure/<name>.json` | type, biome tag, step, terrain adaptation |
| `data/<mod>/worldgen/structure_set/<set>.json` | which structures share a placement grid: `random_spread` `spacing`, `separation` (chunks), a unique `salt` |
| `data/<mod>/tags/worldgen/biome/has_structure/<name>.json` | the biomes it may start in |

Also useful: a structure tag (`tags/worldgen/structure/<set>.json`) for locator items, maps and advancements, and loot tables for containers (`<mod>:chests/<name>`). `world --validate` checks the four-file rule, template sizes and data versions.

- **On the surface:** `minecraft:jigsaw` with one `single_pool_element`, `project_start_to_heightmap: WORLD_SURFACE_WG`, `start_height` a few blocks below the surface, `terrain_adaptation: beard_thin`. No Java. Bring your own pool, crater or clearing rather than hoping for one.
- **Against natural lava or water:** lake features generate *after* structures and cannot be queried during placement. The chunk generator's base column (`ChunkGenerator.getBaseColumn`) already contains aquifer fluids and seas. The kit's structure type samples 16 columns of the candidate chunk, needs the fluid with open air above it inside a y band, and sets the template floor at the fluid surface. Cave lava: y -63..-1, step `underground_structures`. **Nether lava sea:** y 24..40, step `surface_structures`, biomes `nether_wastes`, `basalt_deltas`, `crimson_forest`. Measured: about 3 ms per base column, 34 ms per candidate chunk, roughly 8 % of cave candidates valid, so pair a rare anchored variant with a surface variant in one set (weights 3 and 2) if the mob must be findable.
- Spacing that worked: Overworld landmark 40 / 24 chunks; Nether 28 / 12 (distances there count eight times).
- Template placement settings: ignore structure blocks, `LiquidSettings.IGNORE_WATERLOGGING` (otherwise template blocks in an aquifer become waterlogged). Water from a nearby aquifer can still reach your lava and crust it to obsidian: cosmetic, note it.
- A custom `TemplateStructurePiece` must save what its constructor needs (rotation, pivot) in `addAdditionalSaveData` and read it back in the load constructor, or the piece reloads differently after a restart.
- Interiors: a ceiling the mob fits under plus headroom for its tallest clip; a doorway its hitbox passes; light.

## Proving worldgen

1. **Template looks right:** in the flat test world, `/place template <mod>:<name>` and photograph it (a devshots scene). The home block forms the mob there too.
2. **Placement logic:** GameTests against the real generator, no world needed: build a `RandomState` from the `WorldPresets.NORMAL` overworld stem and call the scanner on real columns, or `structure.findValidGenerationPoint(new Structure.GenerationContext(...))` over a grid of chunks and assert some succeed and each stays under a time budget.
3. **It generates and is found:** a **normal-terrain world created with structure generation on**. `verify PROJECT --client --world normal` creates one; a `locate` step in `DevScenes` searches within a bounded radius, logs `MCFORGE-TRACE locate ... found=1 ms=...`, flies there and takes screenshots. The first attempt at this in a finished mod ran 15 minutes and found nothing: the test world had been created with structures off, so the placement check passed while no start was ever generated. Flat test worlds usually have structures off (`new WorldOptions(seed, generateStructures, bonusChest)`).
4. **The resident is there:** after flying to the located start, load the piece's bounding box, find the home block and count residents near it.

Every search is bounded. `findNearestMapStructure(level, holders, origin, radius, false)` with a radius of 50 placement cells returns in milliseconds to a second; a locator item that searched 125 rings (about 5,000 chunks) could stall a server where nothing was near and was cut to 4 rings with a clear "nothing nearby" answer.

## Natural spawns

`data/<mod>/neoforge/biome_modifier/<name>.json` with `"type": "neoforge:add_spawns"`, a biome tag or id and a spawner list (`lib/worldgen.natural_spawns`). Use the `c:` biome tags (`#c:is_snowy`, ...) to cover modded biomes (read the biome mod's own tags from its jar with `jar PATH`), and check what a tag really contains (frozen_river is not in `#c:is_snowy`). Register a spawn placement (`ON_GROUND`, a heightmap, a predicate); a config weight can scale the predicate while the JSON weight stays fixed. `CREATURE` category mobs spawn at chunk generation and rarely afterwards; make rare unique mobs persistent and keep them apart with a distance check in the predicate.

Prove vegetation and spawns like structures: a `world` scene under `verify --client --world normal` scans a bounded area, traces `MCFORGE-TRACE world patches=N mobs=N ms=N`, flies to one of each and photographs it; a devlog gate requires at least one.

## World content that is data

Loot (global loot modifiers for vanilla chests, with a GameTest that the item appears in the intended chests and never elsewhere), advancements on one custom trigger with named events, recipes, jukebox songs and painting variants (`guide api`), structure loot tables. Keep them data so a pack can retune them.

A light a mob carries is a tracked `minecraft:light` block: place it only into air, remember the position, and remove it on every exit path (move, toggle, removal, unload, and on load after a crash).
