# Asset pipeline

Rerunnable generators for the model, textures, animations, sounds wiring and generated Java constants of this mob
(scaffolded by `minecraft-forge pipeline`; the files are yours). Never hand-edit their output: change the generator
and rerun. Nothing in this folder ships in the mod JAR.

```
python -I asset-pipeline/build_assets.py check
python -I asset-pipeline/build_assets.py all --validate
python -I asset-pipeline/build_assets.py <rig|model|texture|anim|sheets|sprites|sounds> [--validate]
```

The first run creates `asset-pipeline/.venv` (numpy, pillow) with uv, or with venv + pip, and re-executes inside it.

| You edit | Command | Writes |
|---|---|---|
| `mob/rig.py` bones, procedural bones, swap groups, springs | `rig` | `gen/<Mob>Rig.java`, `build/rig_manifest.json` |
| `mob/model.py` implicit shapes and boxes per bone | `model` | `geo/entity/<mob>.geo.json`, `build/<mob>_faces.json` |
| `mob/paint.py` one function per material, `palette.json` | `texture` | `textures/entity/<mob>.png`, `_glowmask.png`, `_uvtest.png`, `media/<mob>.bbmodel` |
| `mob/clips.py` one function per clip | `anim` (`anim sheet` for contact sheets) | `animations/entity/<mob>.animation.json`, `gen/<Mob>Clips.java` |
| `mob/look.py` views and the look checklist | `sheets` | `media/look/*.png`, `media/look/CHECKLIST.md` |
| `mob/sprites.py` item, particle, block and GUI art drawn with `lib/pixel.py` | `sprites` | `textures/<path>.png`, item models |
| `mob/sounds.py` events; OGG files in `assets/<mod>/sounds/<mob>/` | `sounds` | `sounds.json`, subtitles, `gen/<Mob>Sounds.java` |
| `mob/world.py` structure templates, worldgen data, natural spawns (not part of `all`: opt in) | `world` | `data/<mod>/structure/*.nbt`, `worldgen/structure*`, biome and structure tags, biome modifier |
| layer textures (`<mob>_glowmask.png`, overlays) | `cubes` (in `all`) | `gen/<Mob>Cubes.java`: the cubes each selective pass redraws (kit `CubePasses`) |
| `audio/export/<voice\|sfx\|music>/` staged takes | `audio export [DIR]`, `audio --validate` | levelled mono OGGs in `assets/<mod>/sounds/<mob>/`; silent, clipping and copied variants fail |
| `mob/commands.py` (optional) | your own commands | `COMMANDS` adds modules from `mob/`; `ALL_ORDER` puts them into `all` |
| - | `springs [scene]` | `spring_gains.json` from the client trace (then `rig`) |
| `../docs/VALIDATION.md` | `release` | `../mod/<jar>`, `../mod/MANIFEST.json` from the verified receipt |
| `../PLAN.md` | `plan status ID STATE "evidence"`, `plan reprove [check]` | the plan's Status and Evidence cells |

`lib/` is the machinery (voxeliser, painter, renderer, animation toolkit, IK, pixel-art helpers, NBT writer); `mob/` is this mob.
For a second mob, copy `mob/` into another pipeline folder (`minecraft-forge pipeline PROJECT --mob NAME --dir DIR`).

## Order that avoids rework

1. Write `mob/look.py` CHECKLIST from the brief, in the owner's words, before modelling.
2. Rig and a blockout model with flat materials. `all --validate`, then prove orientation and scale in a client:
   `minecraft-forge kit PROJECT geomob --mob <mob>`, `minecraft-forge devshots PROJECT`, start the run with
   `-Dmcforge.uvtest=true` once and look at the `turntable` and `updown` shots.
3. The riskiest mechanic next (a chain, a transformation, a ranged attack): one working slice in a real client
   before final art.
4. Final shapes, then paint, then clips; `sheets` and `anim sheet` after every change, the client run per stage.
5. Springs: trace, `springs`, `rig`, rebuild, repeat until `springs --validate` passes.
6. Sounds last; `sounds --validate` runs the toolkit's `audio-check`.

## Conventions

Blockbench pixels, y up, front is -Z, +X is the model's own right side; `_l` bones at negative x. Geometry and
animation JSON are written in Bedrock layout (rotation `[-rx, -ry, rz]`, pivot and position `[-x, y, z]`, cube origin
`[-x1, y0, z0]`); GeckoLib undoes it at load time. Per-face UV direction lives in `lib/voxel.py` `FACE_AXES`.
`minecraft-forge guide entities` and `guide api` hold the measured facts behind these.
