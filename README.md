<p align="center">
  <img src="assets/mark.svg" width="72" height="72" alt="Minecraft Forge · WIP">
</p>

<div align="center">

# Minecraft Forge · WIP

<p>
  <a href="https://github.com/SenjuWoo/Minecraft-Forge/actions/workflows/ci.yml"><img src="https://github.com/SenjuWoo/Minecraft-Forge/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/SenjuWoo/Minecraft-Forge/releases"><img src="https://img.shields.io/github/v/release/SenjuWoo/Minecraft-Forge?include_prereleases&label=release&color=4E7A3A&labelColor=0d1117" alt="latest release"></a>
</p>

</div>

**Early development — interfaces and supported targets may change.** This is an independent agent workbench, unaffiliated with Minecraft Forge, NeoForged or Mojang. The name describes the workbench; its initial loader provider is NeoForge.

A CLI workbench that gives AI agents a verified starting point for **NeoForge mod development**. Initial target: Minecraft **1.21.1**, NeoForge **21.1.265**, Java **21**. Windows is the primary development platform; CI also checks the Python CLI on Linux.

Point an agent at this folder and tell it to read **[AGENTS.md](AGENTS.md)**. It loads focused guides when needed. Nothing is registered globally, and no MCP stays running in unrelated chats.

## Use it

Clone the repository, then run in PowerShell:

```powershell
git clone https://github.com/SenjuWoo/Minecraft-Forge.git
cd Minecraft-Forge
.\Minecraft-Forge.ps1 doctor
.\Minecraft-Forge.ps1 instances
.\Minecraft-Forge.ps1 quickstart "D:\YourProjects\MyMod" --mod-id mymod --package dev.yourname.mymod --name "My Mod"
.\Minecraft-Forge.ps1 doctor --project "D:\YourProjects\MyMod"
.\Minecraft-Forge.ps1 gradle "D:\YourProjects\MyMod" build
```

`quickstart` is the fast path: it creates the pinned `--with-tests` project and dresses the scaffold's registered example block/item with free procedural textures, models and language entries. Use bare `init` when you want neither the optional tests nor the example art:

```powershell
.\Minecraft-Forge.ps1 init "D:\YourProjects\MyMod" --mod-id mymod --package dev.yourname.mymod --name "My Mod"
```

The new project's **parent directory must already exist**. Existing projects are never overwritten. A scaffold starts with the official example block/item/config; the agent replaces these with the requested feature. It retains its own target lock, agent instructions and progress note. Use the full path to the PowerShell script from elsewhere; relative arguments stay relative to your current directory.

Python equivalent from this toolkit root: `python -m mcforge ...`. Requires Python 3.11+; `UABS_PYTHON` can point to an existing interpreter. The PowerShell entrypoint probes installed Python runtimes. JDK21 with `javac` is required for builds; run `setup-java --plan` and `setup-java` if you need a local Windows x64 JDK.

## Testable starter

Add `--with-tests` when creating a project to include two GameTests and a recipe data provider. From the toolkit root:

```powershell
.\Minecraft-Forge.ps1 init "<new source directory>" --mod-id mymod --package dev.example.mymod --name "My Mod" --with-tests
.\Minecraft-Forge.ps1 verify "<new source directory>" --starter
.\Minecraft-Forge.ps1 verify "<new source directory>" --check
```

`verify` runs data generation in its own Gradle invocation, then tests/build, so the game loads the generated recipe. It requires a fresh nonempty passing GameTest report, inspects the final JAR and saves a receipt binding source/build inputs, generated data, output bytes and logs. `--starter` also checks this example's recipe/advancement and named tests. The tests cover block placement and crafting nine example items from one example block, including rejection of dirt.

`verify --check` rehashes the recorded evidence offline, without rebuilding. Source, target, generated data, JAR, report or log changes invalidate it. The receipt is at `PROJECT/build/mcforge/verification.json`, with per-run receipts/logs under `PROJECT/build/mcforge/verification/`. A failed or interrupted new run supersedes a previous success. See [testing guidance](docs/TESTING.md) for scope and limits.

Test code and its empty structure live in `src/gameTest`, under a separate development mod `<id>_tests` loaded for data generation and GameTests. They stay out of the production JAR; generated recipe and advancement JSON are included. With this option, the main mod ID can contain at most **58 characters** to leave room for `_tests`. Bare `init` stays unchanged and contains zero GameTests. See [testing guidance](docs/TESTING.md) before adapting the examples to a real feature.

## Free procedural assets

`asset` writes original 16 or 32 px RGBA textures, block/item models, blockstates, language entries and a block loot table using only the Python standard library. It downloads no art and calls no paid service. The same project, id, style and size always produce the same PNG bytes.

```powershell
# Dress the scaffold's registered example_block and example_item
.\Minecraft-Forge.ps1 asset "D:\YourProjects\MyMod"

# Add a gem block and item with 32x32 textures
.\Minecraft-Forge.ps1 asset "D:\YourProjects\MyMod" --id ruby_block:block --id ruby:item --style gem --size 32
```

Existing files are skipped unless `--force` is passed; `en_us.json` is merged. New IDs still need Java registration. See [free-asset guidance](docs/ASSETS.md) for the generated layout, styles and the free tools that fill the remaining gaps (Krita, GIMP, Blockbench, ImageMagick, FFmpeg, Audacity).

## Commands

| Command | Purpose |
|---|---|
| `doctor [--project PATH]` | Verify template/Java; optionally inspect actual target pins and lock drift offline |
| `updates PATH` | Read official version candidates explicitly; change no pins/files |
| `instances [--atlauncher PATH]` | List ATLauncher instances read-only |
| `inventory --instance PATH [--hash] [--output NEW_FILE]` | Inspect installed JARs, declared dependencies, duplicates and bounded crash summaries |
| `jar PATH [--hash]` | Inspect one JAR without extracting or executing it |
| `init PATH --mod-id ID --package PACKAGE --name NAME [--with-tests]` | Create a pinned project, optionally with a test/datagen starter |
| `quickstart PATH --mod-id ID --package PACKAGE --name NAME [--no-tests] [--style STYLE] [--size N]` | Create a pinned testable project and generate example assets |
| `asset PATH [--id ID:KIND]... [--style STYLE] [--size 16\|32] [--force]` | Generate free procedural textures, models, blockstates, lang and block loot tables |
| `install [--root PATH] [--force]` | Install/update the toolkit in a versionless local root |
| `gradle PATH TASK [TASK...] [--java-home PATH]` | Run wrapper tasks with Java21 and durable logs; exit status is Gradle's status |
| `verify PATH [--starter] [--java-home PATH]` | Run datagen/build and configured GameTests; save evidence tied to current inputs |
| `verify PATH --check` | Recheck a passing receipt's hashes offline |
| `sources PATH "literal text"` | Search Java source directory or source JAR; bounded JAR results |
| `sources --project PATH ["literal text"]` | Locate exact prepared project sources, optionally search them |
| `search "query" [--minecraft 1.21.1]` | Read Modrinth candidates filtered to the target and NeoForge |
| `guide workflow\|neoforge\|tools\|testing` | Read one focused agent guide |
| `setup-java --plan` / `setup-java` | Resolve / install an official checksum-verified Windows x64 JDK21 locally, if needed |
| `self-test` | Run offline diagnostic tests |

Global `--debug` before a command adds tracebacks to stderr. Metadata commands emit JSON; failures exit nonzero. `sources` uses exit 1 for no matches. Full inventory reports stay in files so agents can read selected records.

Gradle accepts `--stacktrace`, `--offline`, `--info`, `--all` and `--rerun-tasks`. Full output goes to a new log under `PROJECT/build/mcforge/logs/`; stderr reports its path, exit code and a bounded failure tail. `--log NEW_FILE` selects another new file without overwriting it. Execution-redirection switches and arbitrary Gradle arguments are rejected.

New projects lock Minecraft, NeoForge, Java, Gradle distribution/checksum, wrapper hash, ModDevGradle and Parchment mappings. Builds stop on drift or unresolved pins. Existing legacy locks remain usable with a warning about their unpinned fields; inspection never migrates them. `updates PATH` reports stable same-branch NeoForge candidates and build-tool/mapping candidates from official metadata. Candidates require separate validation; other loader lines are ports, not automatic upgrades.

## Included

- Python CLI, diagnostics and progressively loaded agent guides; no Python packages to install.
- Free deterministic procedural textures, block/item models, blockstates, language entries, block loot tables and an asset manifest; no paid service.
- One-command `quickstart` and a versionless local `install` with a launcher and timestamped update backup.
- Official MIT-licensed NeoForge MDK at an immutable commit, including the verified Gradle wrapper and a checksummed Gradle distribution pin. See [vendor/manifest.json](vendor/manifest.json).
- Java discovery and optional official local JDK provisioning. Compatible installed JDKs are reused.
- Read-only ATLauncher and mod metadata inspection, source lookup and optional Modrinth discovery.
- Optional development-only GameTests, recipe data generation and final-artifact verification.
- Project-aware target inspection, explicit update checks and freshness receipts with local diagnostic logs.

## Scope and limits

- **What it does:** scaffolds and verifies NeoForge **1.21.1** projects from a pinned official MDK; inspects installed packs, JARs and prepared sources read-only.
- **What it does not modify:** ATLauncher instances, installed mods, configs, worlds, saves, launcher profiles, global Java/Gradle settings or the active pack. `init` writes only to the new path you pass it and never overwrites existing data.
- **Verified in CI:** Python 3.11/3.14 on Windows and Linux, portable-package extraction, and a real NeoForge 1.21.1 datagen → two GameTests → build → receipt run on Windows. See the CI badge and the [v0.3.0 prerelease](https://github.com/SenjuWoo/Minecraft-Forge/releases/tag/v0.3.0).
- **Not claimed:** client rendering, dedicated-server play, save upgrades, arbitrary modpack compatibility, automatic crash repair, measured FPS gains, or Fabric/Forge support. Those require separate runtime checks.

Gradle downloads Minecraft, NeoForge, mappings and build dependencies on first use. They remain in `local/gradle/` for reuse; the first build can take several minutes and substantial disk space. Assets and source preparation can use multiple gigabytes. Ordinary builds start no permanent service. Game clients/servers run only when their Gradle tasks are explicitly invoked; Ctrl+C stops the owned build process group.

## Install locally

```powershell
.\Minecraft-Forge.ps1 install
```

This copies the portable product to `%LOCALAPPDATA%\Minecraft-Tools\Minecraft-Forge` and writes `Minecraft-Forge.cmd` there. `--force` updates an existing install and keeps a timestamped backup. It changes no PATH, registry, launcher or global Python settings. On other platforms the default is `~/.local/share/minecraft-forge`. Use `--root PATH` for a different location.

The toolkit does not bundle the user's modpack, worlds or Minecraft binaries. Asset editors and paid/authenticated APIs are task-specific integrations; see [docs/TOOLS.md](docs/TOOLS.md). Future Fabric/Forge support needs its own verified provider and tests.

## Validation and local context

The development workspace's `VALIDATION.md` records tested commands and remaining runtime gaps. Your private inventory and integration logs are kept in ignored `local/`; they are excluded from the portable toolkit. The current pack crash is a separate repair task. Mod projects should pass a clean development run before integration with that pack.

Version: **0.4.0 (WIP)**. There is no stable release yet. Download the source or a successful CI run's portable artifact. See [roadmap](docs/ROADMAP.md), [contribution guide](CONTRIBUTING.md), [code of conduct](CODE_OF_CONDUCT.md), [security policy](SECURITY.md) and [third-party notices](THIRD-PARTY.md).

## Development checks

```powershell
python -m mcforge self-test
python scripts/package.py
python scripts/verify_package.py
```

CI tests Python 3.11 and 3.14 on Windows/Linux and verifies an extracted package. Its Windows NeoForge workflow creates the optional starter and verifies fresh datagen, two GameTests, build/JAR evidence and the receipt. This covers the example slice; client rendering and compatibility with an arbitrary modpack require separate runtime checks. See [testing guidance](docs/TESTING.md).
