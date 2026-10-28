# Agent workflow

Read this first. Load the other guides only for the current phase. Work in an owned source project; installed launcher files and supplied mods are references.

## Start with evidence

1. Read the project's `AGENTS.md`, `WORKSPACE_OWNERSHIP.md`, `STATE.md`, build files and existing tests. Preserve the current target and gameplay intent.
2. Run `python -m mcforge doctor`. On this machine prefer `Minecraft-Forge.ps1` if the Windows `python` alias is broken.
3. For pack integration, run `python -m mcforge inventory --instance "<instance directory>"`. Add `--hash` when recording a reproducible pack baseline. Inspect one relevant mod with `python -m mcforge jar "<mod.jar>"`.
4. Record Minecraft, loader, loader version, JDK, Gradle wrapper, ModDevGradle, mappings, physical side and required libraries in the project. A mod filename alone does not establish any of these.

The initial target is Minecraft **1.21.1**, NeoForge **21.1.265**, Java **21**. This matches the inspected pack, rather than following a moving newest release. A new game version is a port with separate validation.

## Choose the least machinery

| Desired change | First approach |
|---|---|
| Recipes, tags, loot or other data-only behavior | Check whether a data pack suffices before adding Java |
| New content or gameplay logic | NeoForge events and registry APIs in the target version |
| Integration with another mod | Its exact release API/source and declared optional/required dependency |
| Private or missing hook | Check access transformers and available events before a narrowly targeted mixin |
| Client visual asset | Existing resource format and tools; add asset tooling only for that asset |

Do not install a second loader, multiloader framework, editor bridge or MCP server for a task the CLI already handles. They can be introduced when a concrete requirement justifies them.

## New mod

From the toolkit directory:

```powershell
.\Minecraft-Forge.ps1 init "<new source directory>" --mod-id examplemod --package dev.example.examplemod --name "Example Mod"
.\Minecraft-Forge.ps1 gradle "<new source directory>" tasks
.\Minecraft-Forge.ps1 gradle "<new source directory>" build
```

Creation uses the bundled, pinned official MDK. Inspect the generated manifest and build files before editing. Keep third-party notices and select an intentional license for your own mod. First dependency resolution requires network access and can be much slower than incremental builds.

Add `--with-tests` to `init` when a working test/datagen example helps. The main mod ID must then be at most 58 characters. This option creates a separate `<id>_tests` development mod in `src/gameTest`, with a recipe provider and two tests for block placement and positive/negative crafting inputs. Bare `init` stays unchanged.

For that starter, run `gradle "<project>" runData` in its own invocation, followed by `gradle "<project>" runGameTestServer build`, then `python scripts/verify_starter.py "<project>"` from the toolkit root. The verifier checks generated recipe/advancement JSON, actual cases in `build/reports/gametest/results.xml`, and the final JAR. The JAR includes generated data and excludes the test mod's classes/structure. Read [TESTING.md](TESTING.md) for the evidence and runtime limits.

## Implement one usable slice

Find a target-version example or source signature before coding. Use `sources "<source tree>" "<symbol>"` and ordinary `rg`; inspect bytecode signatures with JDK `javap` when source is unavailable. Avoid dumping all decompiled sources into model context.

Build the smallest player-visible feature, then add the tests its behavior needs. Read [NEOFORGE.md](NEOFORGE.md) for the applicable API route and [TESTING.md](TESTING.md) for evidence gates. Reuse the same Gradle caches and dependency pins; avoid repeated clean builds.

## Handoff

Keep `STATE.md` current: goal, exact versions, completed changes, next step, commands/results, log locations and runtime gaps. Record a checksum for the final mod JAR. A useful report says which commands passed, what behavior was observed and which combinations remain untested. Keep development ledgers, logs, saves and caches out of a mod release.

Current pack failures are a separate baseline problem. Demonstrate the new mod in a clean development run before testing it with the pack in a separate disposable instance. Never silently deploy into the user's active instance.
