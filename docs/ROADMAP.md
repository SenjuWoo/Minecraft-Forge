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

## Next

- Java kits for the 26.x targets (registration, item properties and equipment assets changed in 26.1+).
- Natural mob spawning, sounds and loot presets; ranged weapons; block entities with GUIs.
- A generated client screenshot run (`guide testing` documents the pattern) so `client_load` can be recorded automatically.
- More furniture shapes and mob archetypes; animated textures.

Roadmap items have no promised dates. The project does not claim universal modpack compatibility or automatic crash repair.
