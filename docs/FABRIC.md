# Fabric targets

Bundled: **fabric-1.20.1** (Java 17), **fabric-1.21.1** (Java 21), **fabric-26.3** (Java 25), each from the official [fabric-example-mod](https://github.com/FabricMC/fabric-example-mod) branch at a pinned commit, with Fabric Loader 0.20.1 and **Loom 1.19.4** pinned exactly (the template's moving `-SNAPSHOT` is replaced). Quilt loads Fabric mods: build a Fabric mod for a Quilt pack.

```powershell
.\Minecraft-Forge.ps1 quickstart "D:\Mods\MyMod" --mod-id mymod --package dev.you.mymod --name "My Mod" --loader fabric --minecraft 1.21.1
.\Minecraft-Forge.ps1 verify "D:\Mods\MyMod"
```

## What the scaffold gives you

- `src/main` (common code) and `src/client` (client-only code) from Loom's `splitEnvironmentSourceSets()`. Client classes cannot be referenced from `src/main`; the compiler enforces the split.
- `fabric.mod.json` renamed to your mod. Its licence is set to `All-Rights-Reserved` because the template's CC0 notice covers the template, not your mod: set the licence you want.
- Official game-test wiring (`fabricApi { configureTests { ... } }`): a `gametest` source set holding a separate `<id>_tests` mod and `LoadSmokeTest`. `build` runs the headless game-test server, so every `verify` proves that the server loads your mod, its registries and its data. Test code never enters the mod JAR.
- Mojang's official names (`loom.officialMojangMappings()` on 1.20.1/1.21.1; 26.x is unobfuscated and needs no mappings).

## Gradle runs on Java 25

Loom 1.19 itself requires a Java 25 JVM, even when the mod compiles for Java 17 or 21 (Loom passes `--release`). The toolkit runs Gradle on JDK 25 for every Fabric target; `doctor` reports `gradle_java_major`. Install one with `setup-java --major 25` if missing.

## Entry points and registration

Fabric has no event bus annotations: code runs from entry points listed in `fabric.mod.json` (`main`, `client`, `fabric-datagen`, `fabric-gametest`, ...). `add` writes self-contained initializer classes and appends them to the right entry point list without touching anything else in the file.

Register content in `onInitialize()` with `Registry.register(BuiltInRegistries.X, id, value)`. Creative-tab entries use `ItemGroupEvents.modifyEntriesEvent(...)`, entity attributes `FabricDefaultAttributeRegistry`, renderers `EntityRendererRegistry` and model layers `EntityModelLayerRegistry` (client entry point). Read the exact signatures in the prepared sources (`gradle PROJECT genSources`, then `sources --project PROJECT "Symbol"`).

## Dependencies

Mods from Maven use `modImplementation` on remapped (1.20.1/1.21.1) targets and `implementation` on 26.x; `libs --add SLUG --project PROJECT` writes the right form. Declare the dependency in `fabric.mod.json` `depends` as well; the game-test server enforces those declarations at load (a wrong-version library fails `verify`, which is the point).

## Version notes

- 1.20.1: data folders are plural (`loot_tables`, `tags/blocks`, `recipes`); armor textures resolve in the `minecraft` namespace, so `add armor` names them `<modid>_<name>_layer_N.png` there.
- 1.21.x: singular data folders; 1.21.2+ moved armor textures to `equipment` assets and 1.21.4 added item definition files under `assets/<ns>/items/`. `add` follows the project's version from facts read out of the game (`mcforge/data/minecraft_versions.json`).
- 26.x: the plugin id is `net.fabricmc.fabric-loom` (no remap). The toolkit generates assets and data for 26.3 content but no Java yet (no kit; see `guide content`).

Sources: [Fabric documentation](https://docs.fabricmc.net/develop/), [Loom](https://docs.fabricmc.net/develop/loom/), [game tests](https://docs.fabricmc.net/develop/automatic-testing). Checked 2026-11-13.
