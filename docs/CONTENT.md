# Content: `add`, `preview`, `bbmodel`

One command per piece of content. Each writes textures, models, blockstates, item definitions, loot tables, tags and language entries for the project's exact Minecraft version, and, where a Java kit exists, the registration code. Existing files are skipped unless `--force`; tags and `en_us.json` are merged. Everything is recorded with hashes in `mcforge-content.json`.

| Kind | Example | Writes |
|---|---|---|
| `block` | `add P block ruby_block --style gem` | cube block, item form, loot table, `mineable/<tool>` tag |
| `item` | `add P item ruby --shape gemstone` | handheld-free item sprite (`ingot`, `gemstone`, `orb`) |
| `food` | `add P food honey_bun` | edible item (nutrition 4, saturation 0.3) |
| `sword` `pickaxe` `axe` `shovel` `hoe` | `add P sword bone_sword --tier iron` | one tool, its tier class, item tag |
| `toolset` | `add P toolset ruby --tier diamond --repair mymod:ruby` | all five tools sharing one tier |
| `armor` | `add P armor ruby --tier iron --repair mymod:ruby` | four pieces, armor material, worn-armor layers, item icons, trim/slot tags |
| `furniture` | `add P furniture oak_chair --shape chair` | multi-part block model, facing blockstate, collision shapes, Blockbench project |
| `mob` | `add P mob cave_boar --shape quadruped [--hostile]` | entity class with AI goals and attributes, model, renderer, texture, spawn egg, Blockbench project |

Shapes: furniture `chair table stool bench shelf cabinet lamp pedestal`; mobs `quadruped biped blob`. Styles: `auto` (picked from words in the name) or `stone wood gem metal organic arcane ruby gold bone flesh leather`. Tool and armor numbers start from the vanilla tier you name (`wood stone iron diamond netherite`): durability, speed, damage, enchantability, defense, toughness. Edit the generated classes to tune them.

## Java kits

| Target | Kit |
|---|---|
| neoforge-1.21.1, fabric-1.21.1, fabric-1.20.1, forge-1.20.1 | yes: every kind above compiles and loads on a server (toolkit CI) |
| neoforge-26.3, fabric-26.3, forge-26.3, fetched targets | assets and data only; `java.status` is `not_generated` and the result says what to write |

Generated classes are standalone files under `<package>.content` (client code under `.content.client`, or `src/client` on Fabric). NeoForge and Forge find them by `@EventBusSubscriber`; Fabric through entry points the command appends to `fabric.mod.json`. They are yours to edit; the toolkit never rewrites one unless you pass `--force`.

What the mob kit leaves to you: natural spawning (biome modifiers / spawn placements; the spawn egg works immediately), sounds, loot (an empty loot table is written), and animations beyond walk and head-look. For keyframed animation, add GeckoLib (`libs --add geckolib --project P`) and follow its docs.

## Blockbench round trip

`add furniture` and `add mob` write `blockbench/<name>.bbmodel` with the texture embedded. Open it in [Blockbench](https://www.blockbench.net/) (free), edit, save, then:

```powershell
.\Minecraft-Forge.ps1 bbmodel P blockbench\cave_boar.bbmodel --entity cave_boar     # replaces the model class + texture
.\Minecraft-Forge.ps1 bbmodel P blockbench\oak_chair.bbmodel --block oak_chair      # replaces the block model + texture
.\Minecraft-Forge.ps1 bbmodel P my_new_mob.bbmodel --entity frost_bear             # a new mob from any Modded Entity project
```

Conversion uses Blockbench's own Java-export arithmetic (`modded_entity` codec: X mirrored, Y measured up from the ground at 24), and rig to `.bbmodel` to rig is tested to round-trip exactly. Rules: block models allow one rotation axis per cube; in entity models rotate bones, not cubes; embed the texture before saving. A model class you edited by hand is protected: `--force` replaces it. Bone names containing `head`, `leg`, `arm` or `foot` get head-look and walk animation.

## Previews without the game

`preview P FILE` renders a block model `.json`, a `.bbmodel` or a texture `.png` to `build/mcforge/previews/`. `add` renders furniture and mobs automatically. It is a small software ray caster: correct geometry, UV mapping and facing; no lighting engine, translucency, tint or animation. Use it to catch a wrong UV or a backwards model before a client run, not as proof of in-game rendering.

## The older `asset` command

`asset P --id name:block --id name:item` still writes cube blocks and flat items with the 0.4 generator, byte for byte. Prefer `add`, which also writes Java and version-correct data.
