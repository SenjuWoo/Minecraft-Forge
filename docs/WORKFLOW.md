# Agent workflow

Read this first. Load the other guides only for the current phase. Work in an owned source project; installed launcher files and supplied mods are references.

## Start with evidence

1. Read the project's `AGENTS.md`, `WORKSPACE_OWNERSHIP.md`, `STATE.md`, build files and existing tests. Preserve the current target and gameplay intent.
2. Run `python -m mcforge doctor --project "<project>"` to inspect actual pins and lock drift offline; use plain `doctor` before creating a project. Prefer `Minecraft-Forge.ps1` if the Windows `python` alias is broken.
3. For pack integration, run `python -m mcforge inventory --instance "<instance directory>"`. Add `--hash` when recording a reproducible pack baseline. Inspect one relevant mod with `python -m mcforge jar "<mod.jar>"`.
4. Record Minecraft, loader, loader version, JDK, Gradle wrapper, ModDevGradle, mappings, physical side and required libraries in the project. A mod filename alone does not establish any of these.

Seven targets are bundled and built in CI (`targets` lists them): NeoForge 1.21.1 (default) and 26.3, Fabric 1.20.1, 1.21.1 and 26.3, Forge 1.20.1 and 26.3. Match the pack you build for: `instances` prints the `init` options for each installed instance. `--fetch` resolves the official template for any other version; such a target was not built by this release, so its own build and tests are the only evidence. A new game version is a port with separate validation.

`plan "<request>"` routes a plain-language request to the commands, the one guide to read and the pitfalls, without writing anything. `capabilities` lists every command and option of this version.

New projects lock the complete target: game, loader, Java, Gradle distribution/checksum, wrapper hash, ModDevGradle and Parchment. Builds reject drift and unresolved pins. Legacy locks retain their existing fields and warn about unpinned components; no automatic migration occurs. When currency matters, `updates "<project>"` explicitly reads official metadata without changing files. Its candidates require validation and do not authorize a port.

## Choose the least machinery

| Desired change | First approach |
|---|---|
| Recipes, tags, loot or other data-only behavior | Check whether a data pack suffices before adding Java |
| New content or gameplay logic | NeoForge events and registry APIs in the target version |
| Integration with another mod | Its exact release API/source and declared optional/required dependency |
| Private or missing hook | Check access transformers and available events before a narrowly targeted mixin |
| Client visual asset | `add` / `asset` for free placeholder textures/models, then an editor for final art |
| Blocks, items, tools, armor, furniture, mobs | `add PROJECT KIND NAME` (guide content) |
| Resource, data or shader pack | `pack` (guide packs); no compiled mod |
| A popular library (GeckoLib, Curios, Architectury, ...) | `libs` (guide libraries) |

Do not install a second loader, multiloader framework, editor bridge or MCP server for a task the CLI already handles. They can be introduced when a concrete requirement justifies them.

## New mod

From the toolkit directory:

```powershell
# Fast path: pinned testable project + free example textures/models/lang/loot
.\Minecraft-Forge.ps1 quickstart "<new source directory>" --mod-id examplemod --package dev.example.examplemod --name "Example Mod"

# Or a bare scaffold, then add assets explicitly
.\Minecraft-Forge.ps1 init "<new source directory>" --mod-id examplemod --package dev.example.examplemod --name "Example Mod"
.\Minecraft-Forge.ps1 asset "<new source directory>" --id ruby_block:block --id ruby:item --style gem --size 32
.\Minecraft-Forge.ps1 gradle "<new source directory>" tasks
.\Minecraft-Forge.ps1 gradle "<new source directory>" build
```

`quickstart` is `init --with-tests` plus the default `asset` pass. `asset` writes only resources/data: new IDs must also be registered in Java. Existing generated files are skipped unless `--force`; `en_us.json` is merged. See [ASSETS.md](ASSETS.md).

Creation uses the bundled, pinned official MDK. Inspect the generated manifest and build files before editing. Keep third-party notices and select an intentional license for your own mod. First dependency resolution requires network access and can be much slower than incremental builds.

Add `--with-tests` to `init` when a working test/datagen example helps. The main mod ID must then be at most 58 characters. This option creates a separate `<id>_tests` development mod in `src/gameTest`, with a recipe provider and two tests for block placement and positive/negative crafting inputs. Bare `init` stays unchanged.

For that starter, run `verify "<project>" --starter`. It runs datagen separately, then GameTests/build, requires fresh actual cases in `build/reports/gametest/results.xml`, checks example JSON/JAR contents and records hashes in `build/mcforge/verification.json`. Run `verify "<project>" --check` to rehash the receipt offline. Once replacing the example behavior, use `verify "<project>"` and adapt the tests. The older `scripts/verify_starter.py` inspects existing outputs only. Read [TESTING.md](TESTING.md) for evidence and runtime limits.

## Implement one usable slice

Find a target-version example or source signature before coding. `sources --project "<project>"` locates the exact prepared source JAR; add `"<symbol>"` to search it. If sources are absent, run `gradle "<project>" createMinecraftArtifacts` once. Explicit `sources "<source tree or JAR>" "<symbol>"`, ordinary `rg` and JDK `javap` remain available. Avoid dumping all decompiled sources into model context.

Build the smallest player-visible feature, then add the tests its behavior needs. Read [NEOFORGE.md](NEOFORGE.md) for the applicable API route and [TESTING.md](TESTING.md) for evidence gates. Reuse the same Gradle caches and dependency pins; avoid repeated clean builds.

For diagnosis, Gradle accepts `--stacktrace`, `--offline`, `--info`, `--all` and `--rerun-tasks`. It saves full output to a unique log under `build/mcforge/logs/` and prints its path, exit code and a bounded failure tail. `--log NEW_FILE` chooses a new path without overwriting. Read the relevant log section before retrying.

## Larger content mods (custom models, animation, sound)

- Match the pack before writing code: read the instance's loader, Minecraft and library builds (`instances`, `inventory --instance PATH`) and pin exactly those (for example the GeckoLib build the pack ships). The user's pack is the target, not the newest release.
- Generate art from scripts, not by hand: a model generator (Blender headless or plain Python) that writes `.bbmodel` and `.geo.json`, an animation generator, a texture painter and a sound generator, all rerunnable. A fix then becomes "edit a constant, rerun, rebuild" instead of re-describing the asset. Keep these in an `asset-pipeline/` folder beside the mod source; they never ship.
- Build validators into the generators (coplanar overlaps, bone names the Java code references, UV inside the texture, sound events in `sounds.json` match the registry) so a broken asset fails before the game starts.
- Iterate with evidence in this order: GameTests for behaviour (`guide testing`), a client screenshot run for looks and animation, then a deploy for the user to play. Each loop costs minutes, not a user round trip.
- Guides: `guide entities` (GeckoLib conventions, head look, actions, secondary motion, custom AI), `guide audio` (sounds.json, synthesis, voice).
- Deliverable layout that survives a later edit or share: `mod/` (the built JAR), `source/` (the Gradle project), `asset-pipeline/` (generators and raw takes), `media/` (screenshots, `.bbmodel`), plus a `MANIFEST.json` with JAR name, SHA-256, Minecraft/loader/Java versions, required mods with version ranges, test status and untested items. Large generator installs (TTS models, Python venvs with model weights) are tools, not project files: keep them out.

## Handoff

Keep `STATE.md` current: goal, exact versions, completed changes, next step, commands/results, receipt/log locations and runtime gaps. Record a checksum for the final mod JAR. A useful report says which commands passed, what behavior was observed and which combinations remain untested. Keep development ledgers, receipts, logs, saves and caches out of a mod release. Generated asset provenance is in `mcforge-assets.json`; replace placeholder art before a public art pass.

Current pack failures are a separate baseline problem. Demonstrate the new mod in a clean development run before testing it with the pack in a separate disposable instance. Never silently deploy into the user's active instance.
