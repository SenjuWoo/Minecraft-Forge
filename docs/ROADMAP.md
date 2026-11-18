# Roadmap and status

## Available in 1.0.0

- Seven bundled targets from pinned official templates: NeoForge 1.21.1 and 26.3, Fabric 1.20.1, 1.21.1 and 26.3, Forge 1.20.1 and 26.3. On-demand `--fetch` for any other official template.
- `add` for blocks, items, food, tools, toolsets, armor, furniture and mobs, with Java on NeoForge 1.21.1, Fabric 1.21.1/1.20.1 and Forge 1.20.1, and version-correct assets/data everywhere.
- Blockbench import/export (`bbmodel`, generated `.bbmodel` projects), software previews, procedural pixel art.
- Library catalog (~60 projects) with exact Modrinth resolution and `build.gradle` integration.
- Resource, data and shader pack scaffolds with pack formats read from the game.
- Launcher discovery (ATLauncher, Prism/MultiMC, CurseForge, Modrinth App, official) and a backed-up `deploy`.
- Verification receipts with separate evidence tiers; headless server-load proof on every bundled target.
- JDK 8/17/21/25 discovery and verified provisioning on Windows, Linux and macOS.

## Added in 1.1.0

- `guide entities`: GeckoLib geometry/animation coordinate conventions for scripted assets, head look, triggered actions, prop swaps, translucent rendering, spring-based secondary motion, villager-brain goals and village spawning.
- `guide audio`: `sounds.json` and registry wiring, OGG encoding, synthesized original effects, voice generation practice.
- `--with-tests` ships a 15x7x15 `arena` GameTest structure; `guide testing` covers entity/AI GameTests and a client screenshot automation run.

## Added in 1.2.0

- `ArenaTests` with the arena's correct stand height and a regression test; `--no-examples` for projects that start from scratch; `model-check` for z-fighting; `run-*` game directories excluded from receipts; PowerShell 5.1 launcher and BOM fixes; client-run and GeckoLib lessons in `guide testing` and `guide entities`.

## Added in 1.3.0

- `voxel` (implicit shapes to z-fighting-free GeckoLib voxel models), `ground` (planted animations), `preview` for `.geo.json` with game lighting and poses, `audio-check`, and a generated client screenshot run recorded by `verify --client`.

## Fixed in 1.3.1

- Installed launcher keeps the caller's folder; one JSON error contract with documented exit codes; `search --loader`; `pack --zip` naming; Fabric loader versions in `targets`; stale verification locks; deploy never overwrites; write guards on every content command; every template hash-checked when packaging.

## Added in 1.4.0

- `pipeline` (a code-driven asset pipeline scaffold for GeckoLib mobs), `kit` (Java kits: bone math, spring solver, shared-bone layer, trace, a GeckoLib mob skeleton), a scripted `devshots` engine with scene filters, `devlog` (a rules gate over the client log), `guide mobs` and `guide api`, private local guides, more voxel shapes; the top and bottom face UV direction corrected.

## Next

- Java kits for the 26.x targets (registration, item properties and equipment assets changed in 26.1+).
- Natural mob spawning, sounds and loot presets; ranged weapons; block entities with GUIs.
- `devshots` for Fabric and Forge targets, and a headless client run for CI.
- More furniture shapes and mob archetypes; animated textures.

Roadmap items have no promised dates. The project does not claim universal modpack compatibility or automatic crash repair.
