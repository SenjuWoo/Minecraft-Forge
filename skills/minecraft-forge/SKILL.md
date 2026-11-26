---
name: minecraft-forge
description: Use for Minecraft Java mod work with the local Minecraft Forge workbench - NeoForge, Fabric or Forge mods; blocks, items, tools, weapons, armor, furniture, mobs; Blockbench models; textures; popular libraries (GeckoLib, Curios, Architectury, JEI); resource, data and shader packs; launcher instances (ATLauncher, Prism, CurseForge, Modrinth); builds, tests and deploys. CLI first; no MCP or background service.
---

# Minecraft Forge

Find the toolkit root containing `Minecraft-Forge.ps1` and `mcforge/` (this skill's folder is not the toolkit). Run commands from that root, through the installed `Minecraft-Forge.cmd`, or with `python -m mcforge`. Read the toolkit's `AGENTS.md` and the mod project's `AGENTS.md`/`STATE.md`/`mcforge-project.json` before changes.

Bundled targets (official templates pinned by hash, built in CI): neoforge-1.21.1 (default), neoforge-26.3, fabric-1.20.1, fabric-1.21.1, fabric-26.3, forge-1.20.1, forge-26.3. Other versions: `--fetch` (not built by the release; say so). Quilt packs use Fabric mods.

1. `doctor`; `instances` (each instance's matching `init` options); `plan "<request>"` for the route.
2. `quickstart PATH --mod-id ID --package PKG --name "Name" --loader L --minecraft V` (add `--no-examples` for a mob-only or from-scratch mod).
3. `add PATH KIND NAME`: block, item, food, sword, pickaxe, axe, shovel, hoe, toolset, armor, furniture (`--shape chair|table|stool|bench|shelf|cabinet|lamp|pedestal`), mob (`--shape quadruped|biped|blob`, `--hostile`). Writes version-correct assets, data and, on the four kit targets (neoforge-1.21.1, fabric-1.21.1, fabric-1.20.1, forge-1.20.1), compiling Java.
4. Blockbench: furniture and mobs ship `blockbench/NAME.bbmodel`; after editing, `bbmodel PATH FILE --entity ID` or `--block ID`. `preview PATH FILE` renders without the game (`.geo.json` posed and lit like the game); `model-check FILE` lists z-fighting faces; `voxel SPEC.json --project PATH` builds GeckoLib voxel models from shapes; `ground` plants animation clips.
5. Character mobs (custom model, keyframed animation, springs; GeckoLib on NeoForge 1.21.1): `guide mobs`, then `pipeline PATH --mob NAME` (code-driven asset generators with validators), `kit PATH geomob --mob NAME` (entity, model, renderer, registration, spring solver), `devshots PATH`, `verify PATH --client [--scenes a,b]`, `devlog PATH` (gates the client log and `MCFORGE-TRACE` numbers). `guide api` lists verified signatures. A mob that lives somewhere: `kit PATH home --mob NAME` (home block that forms it, fluid-anchored structure type), the pipeline's `world` command (templates and worldgen data) and `verify PATH --client --world normal` (structures only generate in a world created with them on); `guide worldgen`.
6. Libraries: `libs --loader L --minecraft V`, `libs --add SLUG --project PATH` (exact Modrinth version id, right Gradle configuration per build system); declare it in mod metadata too.
7. Packs without Java: `pack PATH --kind resource|data|shader`.
8. `verify PATH` (NeoForge before 1.21.5, including 1.21.1: `tests PATH` first; NeoForge 26.3/Forge: `--load`). Client proof on NeoForge 1.21.1: `devshots PATH`, then `verify PATH --client`. Sounds: `audio-check PATH`. Receipt tiers: compile, package, server_load, client_load, gameplay. `verify PATH --check` rehashes offline.
9. On request only: `deploy PATH --instance DIR`, then `--apply` (backs up replaced JARs).

Guides: `guide workflow|neoforge|fabric|forge|content|entities|mobs|worldgen|api|backport|assets|audio|libraries|launchers|packs|tools|testing` - load one at a time; `guide list` also shows private guides kept on this machine. `capabilities` lists every command and option as JSON.

Verify exact APIs in prepared sources (`sources --project PATH "Symbol"`) or version-specific docs before writing Java. Preserve IDs, user edits, save formats and personal settings. Launcher instances, installed mods and saves are read-only apart from an explicit `deploy --apply`. Report only evidence tiers that ran; keep `STATE.md` current; publish only on explicit authorization.
