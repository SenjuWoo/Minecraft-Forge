# Minecraft Forge · WIP

[![CI](https://github.com/SenjuWoo/Minecraft-Forge/actions/workflows/ci.yml/badge.svg)](https://github.com/SenjuWoo/Minecraft-Forge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

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
.\Minecraft-Forge.ps1 init "D:\YourProjects\MyMod" --mod-id mymod --package dev.yourname.mymod --name "My Mod"
.\Minecraft-Forge.ps1 gradle "D:\YourProjects\MyMod" build
```

The new project's **parent directory must already exist**. Existing projects are never overwritten. A scaffold starts with the official example block/item/config; the agent replaces these with the requested feature. It retains its own target lock, agent instructions and progress note. Use the full path to the PowerShell script from elsewhere; relative arguments stay relative to your current directory.

Python equivalent from this toolkit root: `python -m mcforge ...`. Requires Python 3.11+; `UABS_PYTHON` can point to an existing interpreter. The PowerShell entrypoint probes installed Python runtimes. JDK21 with `javac` is required for builds; run `setup-java --plan` and `setup-java` if you need a local Windows x64 JDK.

## Testable starter

Add `--with-tests` when creating a project to include two GameTests and a recipe data provider. From the toolkit root:

```powershell
.\Minecraft-Forge.ps1 init "<new source directory>" --mod-id mymod --package dev.example.mymod --name "My Mod" --with-tests
.\Minecraft-Forge.ps1 gradle "<new source directory>" runData
.\Minecraft-Forge.ps1 gradle "<new source directory>" runGameTestServer build
python scripts/verify_starter.py "<new source directory>"
```

Run data generation in its own Gradle invocation first so the next run loads the generated recipe. The tests verify block registration/placement and crafting nine example items from one example block, including rejection of dirt as an input. The verifier checks the generated recipe/advancement, actual XML test cases, and the final JAR.

Test code and its empty structure live in `src/gameTest`, under a separate development mod `<id>_tests` loaded for data generation and GameTests. They stay out of the production JAR; generated recipe and advancement JSON are included. With this option, the main mod ID can contain at most **58 characters** to leave room for `_tests`. Bare `init` stays unchanged and contains zero GameTests. See [testing guidance](docs/TESTING.md) before adapting the examples to a real feature.

## Commands

| Command | Purpose |
|---|---|
| `doctor` | Verify template integrity and discover compatible Java/tool paths |
| `instances [--atlauncher PATH]` | List ATLauncher instances read-only |
| `inventory --instance PATH [--hash] [--output NEW_FILE]` | Inspect installed JARs, declared dependencies, duplicates and bounded crash summaries |
| `jar PATH [--hash]` | Inspect one JAR without extracting or executing it |
| `init PATH --mod-id ID --package PACKAGE --name NAME [--with-tests]` | Create a pinned project, optionally with a test/datagen starter |
| `gradle PATH TASK [TASK...] [--java-home PATH]` | Run wrapper tasks with Java21; exit status is Gradle's status |
| `sources PATH "literal text"` | Search Java source directory or source JAR; bounded JAR results |
| `search "query" [--minecraft 1.21.1]` | Read Modrinth candidates filtered to the target and NeoForge |
| `guide workflow\|neoforge\|tools\|testing` | Read one focused agent guide |
| `setup-java --plan` / `setup-java` | Resolve / install an official checksum-verified Windows x64 JDK21 locally, if needed |
| `self-test` | Run offline diagnostic tests |

Global `--debug` before a command adds tracebacks to stderr. Metadata commands emit JSON; failures exit nonzero. `sources` uses exit 1 for no matches. Full inventory reports stay in files so agents can read selected records.

## Included

- Python CLI, diagnostics and progressively loaded agent guides; no Python packages to install.
- Official MIT-licensed NeoForge MDK at an immutable commit, including the verified Gradle wrapper and a checksummed Gradle distribution pin. See [vendor/manifest.json](vendor/manifest.json).
- Java discovery and optional official local JDK provisioning. Compatible installed JDKs are reused.
- Read-only ATLauncher and mod metadata inspection, source lookup and optional Modrinth discovery.
- Optional development-only GameTests, recipe data generation and final-artifact verification.

Gradle downloads Minecraft, NeoForge, mappings and build dependencies on first use. They remain in `local/gradle/` for reuse; the first build can take several minutes and substantial disk space. Assets and source preparation can use multiple gigabytes. Ordinary builds start no permanent service. Game clients/servers run only when their Gradle tasks are explicitly invoked; Ctrl+C stops an interactive run.

The toolkit does not bundle the user's modpack, worlds or Minecraft binaries. Asset editors and paid/authenticated APIs are task-specific integrations; see [docs/TOOLS.md](docs/TOOLS.md). Future Fabric/Forge support needs its own verified provider and tests.

## Validation and local context

The development workspace's `VALIDATION.md` records tested commands and remaining runtime gaps. Your private inventory and integration logs are kept in ignored `local/`; they are excluded from the portable toolkit. The current pack crash is a separate repair task. Mod projects should pass a clean development run before integration with that pack.

Version: **0.2.0 (WIP)**. There is no stable release yet. Download the source or a successful CI run's portable artifact. See [roadmap](docs/ROADMAP.md), [contribution guide](CONTRIBUTING.md), [security policy](SECURITY.md) and [third-party notices](THIRD-PARTY.md).

## Development checks

```powershell
python -m mcforge self-test
python scripts/package.py
python scripts/verify_package.py
```

CI tests Python 3.11 and 3.14 on Windows/Linux and verifies an extracted package. Its Windows NeoForge workflow creates the optional starter, runs data generation, executes the two GameTests, builds the mod, and verifies its JSON, XML report and JAR contents. This covers the example slice; client rendering and compatibility with an arbitrary modpack require separate runtime checks. See [testing guidance](docs/TESTING.md).
