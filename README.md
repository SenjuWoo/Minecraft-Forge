<p align="center">
  <img src="assets/mark.svg" width="72" height="72" alt="Minecraft Forge">
</p>

<div align="center">

# Minecraft Forge

<p>
  <a href="https://github.com/SenjuWoo/Minecraft-Forge/actions/workflows/ci.yml"><img src="https://github.com/SenjuWoo/Minecraft-Forge/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/SenjuWoo/Minecraft-Forge/releases/latest"><img src="https://img.shields.io/github/v/release/SenjuWoo/Minecraft-Forge?label=release&color=4E7A3A&labelColor=0d1117" alt="latest release"></a>
</p>

</div>

A command-line workbench for making Minecraft Java mods with **NeoForge, Fabric and Forge**, built so an AI agent (or a person) can go from an idea to a verified, tested mod JAR: pinned official templates, one-command content generation (blocks, items, food, tools, weapons, armor, furniture, mobs), Blockbench import and export, free procedural art, popular libraries, resource/data/shader packs, launcher-aware deploys and evidence receipts for every build.

It is an independent project, unaffiliated with the Minecraft Forge project, NeoForged, FabricMC or Mojang; the name describes a workbench. Made with ATLauncher in mind and works with Prism, MultiMC, CurseForge, the Modrinth App and the official launcher.

Point an agent at this folder and tell it to read **[AGENTS.md](AGENTS.md)**. Nothing is registered globally and no server keeps running.

## Bundled targets

Every target is an official template pinned by hash, built and server-loaded in this repository's CI.

| Target | Loader | Minecraft | Java | Build system | Content kit (`add` writes Java) |
|---|---|---|---|---|---|
| `neoforge-1.21.1` (default) | NeoForge 21.1.265 | 1.21.1 | 21 | ModDevGradle 2.0.148 | yes |
| `neoforge-26.3` | NeoForge 26.3.0.103 | 26.3 | 25 | ModDevGradle 2.0.148 | assets + data |
| `fabric-1.20.1` | Fabric Loader 0.20.1 | 1.20.1 | 17 | Loom 1.19.4 | yes |
| `fabric-1.21.1` | Fabric Loader 0.20.1 | 1.21.1 | 21 | Loom 1.19.4 | yes |
| `fabric-26.3` | Fabric Loader 0.20.1 | 26.3 | 25 | Loom 1.19.4 | assets + data |
| `forge-1.20.1` | Forge 47.4.28 | 1.20.1 | 17 | ForgeGradle 6.0.54 | yes |
| `forge-26.3` | Forge 66.1.8 | 26.3 | 25 | ForgeGradle 7.0.40 | assets + data |

Any other version: `init ... --loader fabric --minecraft 1.19.2 --fetch` resolves that official template on demand (pinned by hash, clearly marked as not built by this release). Quilt packs load Fabric mods.

## Use it

Requires Python 3.11+ (no packages) and a JDK (the toolkit finds installed ones and can install a verified Temurin with `setup-java --major 17|21|25`).

```powershell
git clone https://github.com/SenjuWoo/Minecraft-Forge.git
cd Minecraft-Forge
.\Minecraft-Forge.ps1 doctor
.\Minecraft-Forge.ps1 instances                     # your launcher instances + the init options that match each
.\Minecraft-Forge.ps1 quickstart "D:\Mods\Ruby" --mod-id ruby --package dev.you.ruby --name "Ruby" --loader fabric --minecraft 1.21.1
.\Minecraft-Forge.ps1 add "D:\Mods\Ruby" toolset ruby --tier diamond
.\Minecraft-Forge.ps1 add "D:\Mods\Ruby" armor ruby --tier diamond
.\Minecraft-Forge.ps1 add "D:\Mods\Ruby" mob cave_boar --shape quadruped
.\Minecraft-Forge.ps1 add "D:\Mods\Ruby" furniture oak_chair
.\Minecraft-Forge.ps1 verify "D:\Mods\Ruby"         # build + headless game-test server + receipt
.\Minecraft-Forge.ps1 deploy "D:\Mods\Ruby" --instance "<instance folder>" --apply
```

On Linux/macOS use `python -m mcforge ...` from this folder. `install` copies the toolkit to `%LOCALAPPDATA%\Minecraft-Tools\Minecraft-Forge` (or `~/.local/share/minecraft-forge`) with a launcher; updates keep a backup.

## What you can make

| Want | Command | Guide |
|---|---|---|
| A mod for a loader and version | `quickstart` / `init --loader L --minecraft V` | `guide neoforge`, `guide fabric`, `guide forge` |
| Blocks, items, food | `add P block NAME`, `add P item NAME`, `add P food NAME` | `guide content` |
| Tools and weapons | `add P sword NAME`, `add P toolset NAME --tier diamond` | `guide content` |
| Armor sets (icons + worn layers) | `add P armor NAME --tier iron --repair ITEM` | `guide content` |
| Furniture (shaped, facing, collision) | `add P furniture NAME --shape chair\|table\|stool\|bench\|shelf\|cabinet\|lamp\|pedestal` | `guide content` |
| Mobs (entity, AI, model, renderer, spawn egg) | `add P mob NAME --shape quadruped\|biped\|blob [--hostile]` | `guide content` |
| Animated GeckoLib entities, secondary motion, custom AI | `libs --add geckolib --project P` | `guide entities` |
| Sounds, original SFX and voice lines | `sounds.json`, OGG pipeline | `guide audio` |
| Blockbench models in and out | `bbmodel P FILE --block ID` / `--entity ID`; furniture and mobs ship a `.bbmodel` | `guide content` |
| See a model without launching | `preview P FILE` (block model, `.bbmodel`, texture) | `guide content` |
| Popular libraries (GeckoLib, Curios, Architectury, JEI, Cloth Config, ~60) | `libs`, `libs --add SLUG --project P` | `guide libraries` |
| Resource, data and shader packs | `pack PATH --kind resource\|data\|shader` | `guide packs` |
| Match and deploy to a launcher instance | `instances`, `inventory`, `deploy` | `guide launchers` |
| Route a request before writing anything | `plan "a fabric 1.20.1 mod with a boar mob"` | |

Generated art is original and procedural (standard-library PNG writer): no downloads, accounts or paid services. Replace it with your own when the feature is final; the Blockbench projects make that a round trip.

## Evidence, not claims

`verify` hashes the project's inputs, runs datagen/tests/build, inspects the JAR and writes a receipt (`build/mcforge/verification.json`) with separate tiers: **compile, package, server load, client load, gameplay**. The first three run headlessly; the last two are recorded as `not_run` until someone observes them. `verify --check` rehashes the receipt offline. Fabric projects ship Fabric's official game-test wiring and a load test; NeoForge before 1.21.5 (including 1.21.1) gets one with `tests P`; the other targets use `verify --load`.

Project targets are locked (game, loader, Java, Gradle distribution and checksum, wrapper hash, plugin, mappings). Builds refuse drift; `updates P` reports official candidates without changing anything.

## Commands

`doctor` `targets` `instances` `inventory` `jar` `init` `quickstart` `add` `asset` `bbmodel` `preview` `tests` `libs` `pack` `plan` `capabilities` `gradle` `verify` `deploy` `sources` `search` `updates` `setup-java` `install` `self-test` `guide`. `capabilities` prints all of them with every option as JSON; every metadata command emits JSON and a stable exit code. Gradle output goes to a log under `PROJECT/build/mcforge/logs/` with a bounded failure tail on stderr.

## Scope and limits

- **Never modifies** launcher instances, installed mods, configs, worlds or launcher settings, except `deploy --apply`, which copies one verified JAR and backs up what it replaces. No global Java, PATH or registry changes.
- **Verified in CI:** Python 3.11/3.14 on Windows and Linux; all seven targets scaffold, build and boot a headless server; every content kind compiles and loads on the four kit targets; the portable package is rebuilt and exercised.
- **Not claimed:** client rendering, multiplayer, save upgrades, arbitrary modpack compatibility or automatic crash repair. Shader packs are not compiled by the toolkit. Content Java for 26.x targets is not generated yet (assets and data are).

First builds download Minecraft, the loader and libraries into `local/gradle/` and can take several minutes and gigabytes; later builds reuse them.

See [CHANGELOG](CHANGELOG.md), [roadmap](docs/ROADMAP.md), [contributing](CONTRIBUTING.md), [code of conduct](CODE_OF_CONDUCT.md), [security](SECURITY.md) and [third-party notices](THIRD-PARTY.md).

## Development checks

```powershell
python -m mcforge self-test
python scripts/package.py
python scripts/verify_package.py
```
