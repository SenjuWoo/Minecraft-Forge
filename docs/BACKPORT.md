# Backport: newer Minecraft content into an older pack

Bringing blocks, items, mobs and worldgen from a newer Minecraft release into an older pack as one mod. The rules below come from moving 26.3 content into a 1.21.1 NeoForge pack (Java 21); the method holds for any pair of versions, the API table is specific to that pair.

The newer version is a **behaviour reference**. Every signature you write comes from the older version's prepared sources. Nothing the newer game writes is copied by hand: converters produce assets and data, and each converter is checked against the older jar's own files.

## 1. Target and scope

| Step | How |
|---|---|
| Target | `instances` -> the pack's Minecraft, loader, loader build and Java. The mod targets exactly that (`quickstart --loader neoforge --minecraft 1.21.1 --no-examples`). Do not move the pack. |
| Scope inventory | Run the vanilla data generator on each version's server jar (main class `net.minecraft.data.Main`, `--reports --server`) and diff the two report trees: `registries.json` (blocks, items, entity types, particle types, sound events, features), `blocks.json` (states and properties), the data folders (recipes, loot tables, tags, worldgen, biomes) and the `en_us` keys. The diff is the scope; a changelog is not. |
| Decide every id | One table: id, in or out, owning module, reason. Per-wood boat entities and split potion entities show up as entity types; most are items or already exist under another name. |
| Existing backports | Check whether a maintained backport mod for the same content exists and whether the pack already runs one. Two mods registering the same ids cannot be installed together. |

## 2. Reference sources

| Version | Sources |
|---|---|
| Older (the pack's) | The mod project itself: `gradle PROJECT createMinecraftArtifacts` (NeoForge), then `sources --project PROJECT "Symbol"`. |
| Newer | A throwaway project of the newer target: `setup-java --major 25` (26.x is unobfuscated and needs JDK 25), `quickstart REF --minecraft 26.3 --no-examples`, `createMinecraftArtifacts` there. Its sources jar is decompiled with the loader's patches applied. Keep it outside the mod; it is never built or shipped. |

Read both before porting a class: the same name often has a different signature, argument order or call site (section 7).

## 3. Namespace decision

Registering the content as `minecraft:<id>` (the newer game's own ids) means assets, recipes, loot tables and tags port without rewriting references, and a world opened later in the newer version keeps the blocks. Check before choosing it:

| Check | Why |
|---|---|
| The loader accepts the namespace | NeoForge 1.21.1 `DeferredRegister` takes any namespace without a warning (grep the registries package of the prepared sources; the old Forge "dangerous prefix" check is gone). A GameTest asserts the registered id. |
| No installed mod ships those ids | `inventory --instance` plus a grep of every jar's registries; two owners of `minecraft:x` is a load failure or a silent override. |
| Server and client both carry the mod | Removing the mod turns those blocks into air in saved worlds. |
| Files the game merges vs files it replaces | Never write a file at a path the older jar already has, except files the game merges across packs: `lang/*.json` (per key), `sounds.json` (per event; write only new events), tags with `"replace": false`, `atlases/*.json` sources, NeoForge data maps and global loot modifiers. Fail the converter on any other collision. |

Ids the newer version does not have (mod-owned block entity types, menu types, sensor types the port invents) stay in the mod's namespace. NeoForge enum extensions must use it too: `enumextensions.json` names are validated as `<modid>:...` (boat types), so their textures move to the mod's namespace.

## 4. Modules and parallel builds

| Rule | Detail |
|---|---|
| One module per content family | `content/<module>.txt` lists its ids (one per line); its Java lives in its own package with its own registers. The only shared edits are one `register` call and one creative-tab include. |
| Each id has one owner | A module that needs another module's block, particle or sound looks it up at runtime (`BuiltInRegistries.BLOCK.getOptional(...)`) and does nothing when absent. Never register it twice. |
| Parallel work | One git worktree and branch per module. Gradle builds only inside its own worktree. |
| Shared generated files | Tags, the language files, `sounds.json`, data-map and loot-modifier lists and converter manifests are generated from the **union** of every `content/*.txt`. Merge the content lists, rerun the converters; never hand-merge generated files. |
| Converters are idempotent | Write only when bytes change; a second run reports no changes. Keep a manifest per converter so files that are no longer produced are deleted. |
| Reference closure | A ported recipe, loot table or advancement may reference only ids the older game or a content list provides; otherwise skip it and print the missing ids. It appears by itself when the owning module lists them. |

## 5. Converters with an oracle

Every conversion is a whitelist; anything else raises "unsupported" and the file is skipped with that reason. The oracle: convert every newer file that **also exists in the older jar** and diff it against the older jar's own copy. Residue is either a vanilla content change (renamed group, new tag member, changed count) or a converter bug; read samples of each kind before extending a rule. Extend a whitelist only with that oracle green.

## 6. Format rules, 26.3 -> 1.21.1

### Data

| File | 26.3 | 1.21.1 |
|---|---|---|
| Recipe ingredients | `"minecraft:x"`, `"#minecraft:t"`, list of those | `{"item": ...}`, `{"tag": ...}`, list of objects |
| Recipe `category` | omitted for misc (codec default MISC) | written as `"misc"` |
| Recipe result `count` | omitted when 1 | written for crafting, stonecutting, smithing (cooking results stay without) |
| `smithing_trim` | explicit `pattern` | dropped (derived from the template) |
| No 1.21.1 form | `crafting_transmute`, `crafting_dye`, `crafting_imbue`, component results | skip, or write the behaviour in code |
| Loot functions | `modifier` (one or list), function `type` | `functions` list, key `function` |
| Loot conditions | `condition` (object or a string reference to `predicate/*.json`), key `type` | `conditions` list with the predicate inlined, key `condition` |
| Block predicate | `match_block {blocks, state}` | `block_state_property {block, properties}` (several blocks -> `any_of`) |
| Tag entries in loot | `items: "#t"` | `name: "t"` + `expand` |
| Damage predicates | tag ids with `#` | without `#` |
| Entity predicates | `minecraft:flags`, `minecraft:entity_type` | `flags`, `type` |
| `copy_components` | includes components 1.21.1 lacks | drop those, with a note |
| Advancements | `recipe_unlocked.recipes`, `enter_block.blocks` | `recipe`, `block` (one block) |
| Tags | same format; many new data-driven tags replace hard-coded checks | write a new tag only when something 1.21.1 reads points at it; never add existing ids to vanilla tags (that is a vanilla behaviour change) |
| Components as data | `cooking_fuel`, `compostable`, `repairable`, `provides_trim_material` | NeoForge data maps (`furnace_fuels`, `compostables`), tags, or the 1.21.1 registry file; numbers mapped through an oracle over the older game's own data maps |
| Loot additions | a new pool added to an existing table | NeoForge `neoforge:add_table` global loot modifier conditioned on `neoforge:loot_table_id`; entries inserted into an existing weighted pool are skipped (a modifier cannot insert without changing the odds) |

### Assets

| File | 26.3 | 1.21.1 |
|---|---|---|
| Element rotation | Euler `x`/`y`/`z` | one `axis` + `angle` (keep the largest component, report the rest) |
| Element angle | any | -45..45 in 22.5 steps; clamp and report. An element that needs 90 or 180 degrees has to be rotated geometrically |
| `shade_direction_override` | `"up"` | `shade: false`; other directions dropped (default shading) |
| `light_emission` | element field | NeoForge element `neoforge_data.block_light` |
| Texture references | objects `{sprite, force_translucent}` | the sprite string |
| Item definitions | `items/<id>.json` (`model`, `select`, `condition`, `range_dispatch`, `special`, `composite`, `tints`) | `models/item/<id>.json`: a plain model becomes a parent wrapper; `select` on display context -> `neoforge:separate_transforms` (with `gui_light` at the root); `select` on trim material -> `overrides` on `trim_type`; `composite` -> `neoforge:composite`; `special` -> `parent: builtin/entity` + a BEWLR; `tints` -> `ItemColor` code |
| Texture `.mcmeta` | `mipmap_strategy`, `alpha_cutoff_bias`, `palette` | remove those keys |
| Equipment textures | `textures/entity/equipment/<layer>/<material>.png` | `humanoid` -> `models/armor/<m>_layer_1`, `humanoid_leggings` -> `<m>_layer_2`, `horse_body` -> `entity/horse/armor/horse_armor_<m>`; other layers are read by your renderer at their 26.3 path |
| Signs and hanging signs | block models per wood, packed 32x32 `block/<wood>_sign.png` | particle-only block model (as vanilla `oak_sign`) + block entity renderer reading `entity/signs[/hanging]/<wood>.png`, regenerated from the packed texture; join the vanilla sign block entity types with `BlockEntityTypeAddBlocksEvent`; `Sheets.addWoodType` in client setup |
| Boats | one entity type per wood | `Boat.Type` extended through NeoForge `enumextensions.json` (mod-namespaced names); saved boats carry that name |
| Trim palettes | `textures/palettes/trim/` | `textures/trims/color_palettes/`; worn sprites need a `paletted_permutations` atlas source |
| Sounds | same `sounds.json`; files come from the asset index, not the client jar | check existence against the older asset index |

### Worldgen

| Feature | 26.3 | 1.21.1 |
|---|---|---|
| Folder | `worldgen/feature`, flat `{"type", ...fields}` | `worldgen/configured_feature`, `{"type", "config": {...}}` |
| Block states | `"id"` or `{"id", "properties"}` | `{"Name", "Properties"}` with every property written (defaults from `blocks.json`) |
| State providers | bare state, `weighted` | `simple_state_provider`, `weighted_state_provider` |
| Random patches | `count` + `offset` (trapezoid, plateau 0) + filters as placement | folded back into `random_patch {tries, xz_spread, y_spread, feature}`: the draws are identical |
| Tree soil | `below_trunk_provider: soil_beneath_tree` | `dirt_provider` dirt + `force_dirt: false` |
| Tree decorators and placers | new types (registered by your Java) | pass through with the 26.3 fields only when a module registers the type; fail closed on any unknown trunk/foliage placer type |
| Biome placement | biome files list features | `neoforge:add_features` with exact vanilla biome ids (no tags: modded biomes stay untouched); a feature the newer version changed in place gets a mod-namespaced copy and a modifier that swaps the holder at the same index |
| Natural spawns | biome attribute (spawn data) | `neoforge:add_spawns` biome modifiers, exact biome lists per weight group |
| New feature types | e.g. fallen trees | not portable as data; drop the entry and report it |

### Entities and items in code

| 26.3 | 1.21.1 |
|---|---|
| Mob variant registries (data-driven) | entity data: an enum synced as INT, saved under the 26.3 NBT key and id strings |
| Brain AI with memory types and sensors 1.21.1 lacks | goals with the same numbers, or the brain ported with new sensor types in the mod namespace; register a `minecraft:` AI entry (a memory type) only when saved entities must keep the newer key |
| `equippable`, `consumable`, `use_cooldown` components | written in code on the item or entity (`isBodyArmorItem`, `mobInteract`, `finishUsingItem`) |
| `EquipmentSlot.SADDLE` | a one-slot container (saddleable flag, NBT key) or the BODY slot |
| Mount screen packet (horses only in 1.21.1) | a mod menu type |
| Textured spawn eggs | `DeferredSpawnEggItem` with white for both colours: NeoForge tints every spawn egg |
| Environment attributes (day/night windows) | `dayTime % 24000` in the same window, in natural dimensions without fixed time |
| Data-driven enchantment effects 1.21.1 cannot parse | keep the definition as data, apply the effect in code after the trigger |

## 7. API differences, 26.x -> 1.21.1

| Area | 26.3 | 1.21.1 |
|---|---|---|
| `Mth.clampedLerp` | `(factor, min, max)` | `(start, end, delta)`: same name, the factor moved to the end |
| Block removal | `affectNeighborsAfterRemoval` / `preRemoveSideEffects` run only when the block goes away | `onRemove(state, level, pos, newState, moved)` runs on every state change: guard drops and block-entity cleanup with `!state.is(newState.getBlock())` (oxidation and waxing keep the block entity) |
| Spawn finalisation | `finalizeSpawn` then the jockey rules | NeoForge fires `FinalizeSpawnEvent` **before** `finalizeSpawn`; to act after it, a lowest-priority listener runs `finalizeSpawn` itself, cancels the event and applies the rule |
| Equipment attributes | visible at once | applied on the entity's next tick (`LivingEntity.detectEquipmentUpdates`): assert armor values a tick or two later |
| Gamerules | `spawnMobs` and `spawnMonsters` | `doMobSpawning` only |
| Comparator output | direction-aware | `getAnalogOutputSignal` has no direction |
| `isRandomlyTicking` from data maps | read at runtime | cached per state at registry bake, before data maps load: decide from the block's own state |
| Random ticks of a vanilla block | data | no NeoForge random-tick event: a mixin on that block, acting only for that exact block |
| `canBeCollidedWith(other)` | has the other entity | no argument |
| Display context `ON_SHELF` | exists | does not; use `NONE` (+ a turn for 3D models) |
| Quad leash, `isFlyingVehicle`, camera-distance attribute | exist | do not: distances in code, `isNoGravity` for the floating-vehicle kick, `CalculateDetachedCameraDistanceEvent` |

## 8. GameTests for a backport

| Pitfall | Fix |
|---|---|
| Global state (day time, `doMobSpawning`, weather) | its own batch with `@BeforeBatch` / `@AfterBatch` that set and restore it; the test server turns mob spawning off |
| Mobs that react to any survival player in range (freeze while watched, target the nearest) | their own batch: mock players of other tests in the same batch are in range |
| Armor and other equipment attributes | assert after `runAfterDelay(2, ...)` |
| Numbers | compare durability, stack size, enchantability, rarity and attribute modifiers against the newer version's item components report, not against memory |
| Vanilla ids | one test asserts each registered block and item has its `minecraft:` id |
| Log gate | after `verify`, scan the server log for WARN/ERROR lines naming your ids, recipes, loot tables, tags or models; recipe and advancement counts should equal the older jar's plus the ported ones |

## 9. In the pack

`deploy PROJECT --instance INSTANCE --apply` after `verify`, then `links --instance INSTANCE` (references between mods, classes too new for the pack's Java). Client checks: the pack showcase in `guide testing` (place every block and entity on a grid, screenshot, count `Unable to load model` lines). A resource pack in the pack that ships models in the newer format for the backported blocks shows them as the missing model: `packcompat PACK.zip --minecraft 1.21.1 --instance INSTANCE [--mod-jar MOD.jar]` plans an overlay pack, `--apply` writes it (`guide packs`).

## Out of scope, and why

| Item | Why |
|---|---|
| Vanilla bug fixes | there is no list a mod can apply; each fix is a code change somewhere else. Port one only where a backported feature needs the fixed behaviour |
| Data-driven item components as components | 1.21.1 has no reader; the behaviour moves into code per item (section 6) |
| Renames (`chain` -> `iron_chain`) | the older game already has the content under the old id; map the id in recipes instead |
| Vanilla behaviour changes to existing content | new tag members, changed trades, re-categorised recipes, new entries in existing weighted loot pools: changing them means shadowing vanilla files |
| Experimental-only content in the older version | the base item may be unobtainable without the experiment (dyed bundles need the bundle) |
| Developer and server-management additions | test blocks, test instances, management registries |
