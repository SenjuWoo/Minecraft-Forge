# Changelog

## 1.1.0 - 2026-11-13

- New `guide entities`: GeckoLib entity work measured on NeoForge 1.21.1 / GeckoLib 4.9.3: the JSON sign conventions for scripted `.geo.json` and animation files (rotation `[-x,-y,z]`, pivot `[-x,y,z]`, additive animation rotation, unchanged face keys), head look from `EntityModelData`, controllers and triggered actions, prop swaps, translucent render type, z-fighting checks, spring-based secondary motion, villager-brain goals, village spawning at meeting points.
- New `guide audio`: `sounds.json` and `SoundEvent` wiring, mono OGG Vorbis encoding without shell quoting traps, synthesis recipes for original effects, and voice generation practice (non-verbal tags, one reference voice, scored takes).
- `init --with-tests` / `quickstart` also write an `arena` GameTest structure (15x7x15, smooth-stone floor) so mobs are not boxed in by the 3x3x3 `empty` template; `verify` and `scripts/verify_starter.py` reject it in the mod JAR.
- `guide testing`: entity/AI GameTest pitfalls (far-from-origin plots break pathing and line of sight; zombies burn in daylight) and a client screenshot automation run. `guide workflow`: larger content mods, asset generators and deliverable layout.
- `plan` routes animation and sound requests to the new guides.

## 1.0.2 - 2026-11-13

- `setup-java` installs JDKs into one per-user folder (`%LOCALAPPDATA%\Minecraft-Tools\jdks`, `~/.local/share/minecraft-forge-jdks`, or `MCFORGE_JDK_ROOT`) that every copy of the toolkit reads, so a clone and an installed copy share them. JDKs in an older copy's `local/tools/` are still found by that copy.
- `install --force` keeps the previous install's `local/` folder (Gradle cache, fetched templates) instead of leaving it in the backup.

## 1.0.1 - 2026-11-13

- Release checksum files (`.zip.sha256`) are written with LF line endings on every platform, so `sha256sum -c` works on Linux and macOS. `verify_package.py` now rejects a CRLF checksum file and one that does not match the ZIP. The 1.0.0 release's checksum asset was replaced with an LF copy of the same hash; its ZIP is unchanged.

## 1.0.0 - 2026-11-13

First stable release: one workbench for NeoForge, Fabric and Forge.

- **Loaders and versions.** Seven bundled targets from pinned official templates (NeoForge 1.21.1/26.3, Fabric 1.20.1/1.21.1/26.3, Forge 1.20.1/26.3) via `init`/`quickstart --loader --minecraft` or `--target`; `targets` lists them; `--fetch` resolves any other official template on demand. Fabric Loom and ForgeGradle version ranges/snapshots are replaced by exact releases. Project locks, drift detection and `updates` cover all three build systems.
- **Content.** `add` writes blocks, items, food, swords, pickaxes, axes, shovels, hoes, toolsets, armor sets, furniture (8 shapes, facing, collision) and mobs (3 rigs, AI goals, model, renderer, spawn egg) with assets and data for the project's exact version, and compiling Java on NeoForge 1.21.1, Fabric 1.21.1/1.20.1 and Forge 1.20.1.
- **Blockbench and previews.** Furniture and mobs ship `.bbmodel` projects; `bbmodel` imports block and entity projects back (exact round trip, Blockbench's own export arithmetic); `preview` renders models and textures without the game.
- **Libraries.** `libs`: catalog of ~60 popular libraries read from Modrinth; `--resolve` and `--add` write an exact Modrinth version id with the right Gradle configuration per build system.
- **Packs.** `pack` creates resource packs (with procedural retextures), data packs and Iris/OptiFine shader packs; pack formats, folder names and recipe JSON shape are read from each release's client JAR (1.14 to 26.3).
- **Launchers.** `instances` reads ATLauncher, Prism/MultiMC, CurseForge, Modrinth App and the official launcher; `deploy` copies a verified JAR into an instance with a backup, only with `--apply`.
- **Evidence.** Receipts record compile, package, server load, client load and gameplay as separate tiers. Fabric projects get Fabric's official game-test wiring and a load test; `tests` adds one to NeoForge 1.21.1; `verify --load` boots the game-test server elsewhere. A server that did not start can no longer pass.
- **Tooling.** `plan` routes a request before any file is written; `capabilities` is generated from the parser. JDK discovery covers common vendors, CI and Linux/macOS layouts; `setup-java --major 8|17|21|25` on Windows, Linux and macOS. Every local JDK is offered to Gradle as a toolchain.

## 0.4.1 WIP — 2026-11-12

- Fix `Minecraft-Forge.ps1` under Windows PowerShell 5.1. Every command failed with `NameError: name 'mcforge' is not defined`, because that shell removes the double quotes inside an argument passed to a native program and the launcher carried its Python start-up code in one. The launcher now runs the package with `python -m`.
- Add a launcher regression test that starts the script through `powershell.exe -File` from a folder whose name has a space, `!` and parentheses, and checks the exit code and that arguments arrive unchanged.

## 0.4.0 WIP — 2026-10-31

- Add `asset`: deterministic, standard-library-only 16/32 px textures, block/item models, blockstates, language entries, block loot tables and an asset manifest. No paid service or downloaded art.
- Add `quickstart`: create a pinned `--with-tests` project and dress its example block/item in one command.
- Add `install`: copy the portable product into a versionless local root with a launcher and a timestamped backup on update. No PATH or global settings changes.
- Report optional free asset tools (`magick`, `ffmpeg`, `blockbench`, `krita`, `gimp`, `audacity`) from `doctor`.
- Add asset, install and CLI regression tests plus the free-asset guide.

## 0.3.2 WIP — 2026-10-31

- Replace the generic Contributor Covenant with the project's own code of conduct: any content is allowed except backdoors, sexual content involving minors, malware and hidden destructive behavior.

## 0.3.1 WIP — 2026-10-31

- Add a Contributor Covenant 2.1 code of conduct and a short credits index pointing at the existing third-party notices.
- Add a release-hygiene gate that rejects tracked build artifacts, local paths, stale legacy-account links, unexpanded manifest versions and credential-shaped strings; run it in CI.
- Document the workbench's scope and explicit non-claims in the README.

## 0.3.0 WIP — 2026-10-29

- Add project-aware diagnostics and complete target locks for new projects, including Gradle distribution, wrapper, ModDevGradle and mappings. Legacy locks remain readable with an explicit warning.
- Add explicit, read-only upstream update checks with same-branch NeoForge candidates and separately reported port targets.
- Add `verify` to run datagen, configured GameTests and build, then bind source, generated files, actual XML cases, JAR and logs into a verification receipt. `verify --check` rejects changed evidence; failed or interrupted runs invalidate prior success.
- Resolve prepared Java sources from the exact project's NeoForge version. Preserve direct source-path searches.
- Allow a small set of native Gradle diagnostic flags; retain complete per-run logs and stop owned workers on interruption.
- Exercise new commands, stale evidence and failure handling in offline tests, portable package checks and real NeoForge CI.

## 0.2.0 WIP — 2026-10-27

- Add opt-in `init --with-tests`: isolated development mod, two GameTests, a working recipe data provider and XML test reporting. Bare scaffolds retain their existing behavior.
- Generate nine example items from one example block; test registration, placement, successful crafting and rejection of unrelated input.
- Add starter verification for actual generated JSON, nonempty passing XML results, final JAR contents and exclusion of development classes/structures.
- Exercise the full datagen → GameTest → build → artifact-inspection path in CI; include and verify the templates in portable packages.
- Preserve custom Java packages containing the MDK's example mod ID; allow 0.x production versions in the development test-mod dependency.
- Handle proven transient Windows sharing locks during final project publication with a bounded retry, retaining no-overwrite and persistent-error behavior.

## 0.1.0 — 2026-10-27

- Public WIP repository preparation: Windows/Linux CI, real NeoForge build check, package proof, contribution/security policies and roadmap. No stable release declared.

- Initial NeoForge 1.21.1 CLI workbench, pinned official ModDevGradle MDK and target lock.
- Read-only ATLauncher/JAR inventory; source search, library discovery, runtime diagnostics and foreground Gradle workflows.
- Focused agent instructions, test/evidence guidance, optional verified local Java provisioning and portable packaging.
- No standing MCP, global settings changes, launcher deployment or public publication.
