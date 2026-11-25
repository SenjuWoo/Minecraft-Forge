# Changelog

## 1.5.3 - 2026-11-25

Pack lessons from a 1.21.1 NeoForge performance audit and a crash after a mod update. No command or option was removed.

- New `links --instance PATH` (or `--mods-dir DIR`, `--json`; also `inventory --links`): reads the class files of every installed mod, including jar-in-jar, and reports calls from one mod into another that the installed version no longer has: missing methods, fields and classes, and abstract interface methods an implementing class lacks. These are the `NoSuchMethodError`, `NoClassDefFoundError` and `AbstractMethodError` crashes that appear after an update even though every declared version range is satisfied. References that a mixin may add at runtime, or that leave the scanned jars, are counted as unresolved rather than reported. Exit 1 when it finds a broken reference. A 221-mod pack scans in about 9 seconds. On a real pack it flagged a Sodium beta that renamed `VertexBufferWriter.push`, which three installed mods still called.
- `plan` routes crash text with those errors, and "mod update", to the link check.
- `guide libraries`: the performance section is rewritten from moving-camera measurements. It covers measuring in motion; Sodium betas with closed-source mods built against the Sodium API; measured results for DLSS and FSR upscalers; where far terrain starts with Distant Horizons under a shader pack (the pack's own DH program decides, not `DistantHorizons.toml`); Distant Horizons generation threads; Physics Mod vine and ocean costs; and why Rust rewrites are not an option for a modded pack. Replaces the 1.5.1 advice to keep `overdrawPrevention` at 0.5.

## 1.5.2 - 2026-11-24

Lessons from six more mod builds and a pack audit (NeoForge 1.21.1, GeckoLib 4.9.3 and 4.9.4). No command or option was removed.

- Several mobs in one pipeline: `pipeline PROJECT --mob NAME --add` puts another mob in `mobs/NAME/` beside `mob/` with one shared `lib/`. Every command runs once per mob in its own process (`--mob a,b` selects); per-mob `build/` and `media/` folders, optional per-mob `palette.json` and spring gains; plan and release run once. Single-mob pipelines are unchanged.
- Fixed: `lib/rigtools` imported `mob/rig.py` at import time, so a mob module that imported `lib.animtools` met a half-initialised module; the rig is now read on first use.
- Fixed: kit `springs` peaks rose with the frame rate. Frames shorter than the 4 ms sub-step dropped their force; the force is now averaged over every frame since the last sub-step (same scene: 0.81 at low fps, 1.9-2.3 at high fps before).
- `lib/ik.two_bone` returns the Euler representative nearest the rest pose, and `two_bone_blend` the one nearest its start, so blends and additive offsets take the short way round (an arm reach swung through the body before). New `animtools.nearest_euler`.
- `lib/voxel`: fine cells search finer sub-pixel offsets, so small parts no longer run out of clash-free shifts.
- `mob/sounds.py` patterns may name another mob's folder (`"other_mob/step_*"`): a shared sound bank with a pitch offset.
- Devshots: the screenshot world is NORMAL difficulty (peaceful deleted hostile subjects and actors mid-scene) and the script clears world-generation mobs before the first summon.
- `deploy` checks the JAR's required dependencies against the instance (missing or outside the declared range is a mismatch), refuses `--apply` while a game runs from the instance (`--allow-running` overrides) and records each deploy in `mcforge-deployed.json`.
- `inventory` reports `dependency_problems` for the whole pack, `deployed_missing` (deployed mods a launcher reinstall or pack update dropped) and `fml` for libraries FML loads through their manifest or a loader service; such a multi-loader library with only `fabric.mod.json` is no longer listed as Fabric-only.
- Guides: GeckoLib 4.9.4 compatibility (signatures and glow-mask builder compared with 4.9.3), `GeoObjectRenderer` re-render offset, holding entities by riding, synced attachments, replacing any mob's look at render time, a layer on every renderer, bosses, titans, block-textured creatures, block sound types, shared sound banks, interrupted audio jobs, scene hygiene.

## 1.5.1 - 2026-11-24

Library catalog and guide notes from a 221-mod NeoForge 1.21.1 pack audit. No command changed.

- `libs` catalog: new `performance` category with Lithium, ModernFix, FerriteCore, ImmediatelyFast, EntityCulling, Sodium Extra, BadOptimizations and Structure Layout Optimizer; rendering entries for Distant Horizons and Physics Mod; `probejs` for KubeJS and `resourceful-config`. Titles, licences and Minecraft ranges are read from Modrinth; 71 entries (was 59).
- `docs/LIBRARIES.md`: performance-stack and rendering-boundary rules measured on the pack - Lithium/ModernFix duplicate mixins, only one render-scale/frame-generation mod (DLSS measured at 51.9% of the render thread and 178 -> 84 fps under shaders), Distant Horizons `CHUNKS_ONLY` with custom worldgen, cave culling and overdraw/fade settings for the vanilla border, Physics Mod ocean off under shaders, orphaned-library check, spark profiling.

## 1.5.0 - 2026-11-18

Lessons from two more GeckoLib mob builds (NeoForge 1.21.1, GeckoLib 4.9.3), turned into pipeline steps, a kit and guide notes. No command or option was removed.

- New pipeline step `cubes` (part of `all`): `gen/<Mob>Cubes.java` lists, for every layer texture (glowmask, overlays), the cubes that carry its texels. New kit `passes` (`CubePasses`, also part of `geomob`): a glow layer and an overlay redraw that draw only those cubes; the geomob renderer implements the cube filter. Measured in the builds: glow 1.55 -> 1.03 ms per instance, three overlays 3.45 -> 1.17 ms.
- New pipeline step `audio`: `audio export [STAGING]` writes a staged sound set into the mod (35 Hz high-pass, silence trim, RMS levelling per class, soft limiter, mono Vorbis, only changed files); `audio --validate` fails on silent, clipping, very short or non-mono files and on variants that are copies.
- `audio-check` reports variants of one event that are the same audio (same bytes, or the same decoded samples with FFmpeg).
- Pipeline rig: an optional rest rotation per bone (`(name, parent, pivot, (rx, ry, rz))`, mirrored for `_L` bones) written to the geometry and the Blockbench export; parts marked `local=True` stay out of ambient occlusion and the body union.
- Fixed: `lib/ik.two_bone` turned the middle joint away from the pole for the default negative flex range. The joint now points toward the pole for either sign; projects that mirrored the pole to compensate should un-mirror it.
- Fixed: glow rendered dark. GeckoLib 4.9.3 takes a glowing texel's colour from the base texture and only its alpha from the glowmask; the painter now copies the glow colour into the base texture (found by a client night shot of the selective glow pass).
- Animation export unwraps key rotations to the nearest equivalent Euler triple, so IK output no longer makes GeckoLib's controller transitions spin.
- Project commands without patching `lib/`: an optional `mob/commands.py` (`COMMANDS`, `ALL_ORDER`). The sprites step calls `mob/sprites.py` `write_particles()` when present.
- `mob/sounds.py` PLANNED: events still being made are reported, never an error and never in `sounds.json` (fixes `sounds --validate` failing on listed events without files).
- `lib/palette.py`: `ramp_from_image` measures anchors by default (circular-mean hue, median mid-tone saturation, percentile lightness, evenly spaced steps) with `hsv_filter` for material pixels; k-means stays available as `method="kmeans"`.
- `devshots`: an opt-in `audio` scene plays every sound event of the mod (`verify --client --scenes audio`, then `devlog`); `DevShots.named(scene)` for scenes a plain run skips.
- Guides: body types by region mapping, angled crisp parts, palette review of dark bands, dense sampling of contact clips, block-to-prop hand-offs from one definition, sequences as server tick tables with one abort path, POI lookups, no float world positions, overlays on game time (`mobs`); emissive pass order and glow keyed to the real texture (`entities`); pitch ceilings and the shift limit, staging, copies, levels (`audio`); scene cleanup and window focus (`testing`); vegetation instead of structures and proving it (`worldgen`).

## 1.4.1 - 2026-11-17

- `verify PROJECT --client` turns NeoForge's early loading window off in the screenshot run's game directory (`run-devshots/config/fml.toml`, `earlyWindowControl = false`). With the GPU busy, the early window could fail to hand over to the game window and show an error dialog; the unattended run then hung until it was killed. Only that line of the file is changed.

## 1.4.0 - 2026-11-17

The reusable parts of seven finished GeckoLib mob projects (NeoForge 1.21.1, GeckoLib 4.9.3), turned into commands. Each of those projects rebuilt the same asset scripts, physics classes, screenshot driver and log checker; they now ship with the toolkit.

- New `pipeline PROJECT --mob NAME`: scaffolds `asset-pipeline/` beside the project, a code-driven generator set the project owns. `lib/`: vectorised implicit shapes, the voxeliser (partition per blob, sub-pixel placement, buried faces dropped), a 3D texture painter with palette ramps, glow masks and a UV test texture, a preview renderer with the game's entity lighting, an animation toolkit (clips as functions of time, easing, grounding, key reduction, events exported as server tick constants and client timeline instructions), two-bone IK for solved contact, pixel-art helpers for item, particle and GUI sprites, sounds wiring (`sounds.json`, subtitles, a self-registering sounds class), an NBT structure writer, spring tuning from the client trace, release staging from the verified receipt and plan helpers. `mob/`: a small example creature to replace. `build_assets.py all --validate` is the offline gate (rig rules, cube budget, UV bounds, `model-check`, palette, loop continuity, grounding, look checklist). It needs numpy and Pillow and creates its own virtual environment; the toolkit core stays standard-library only.
- New `kit PROJECT bonemath|trace|springs|layer|geomob`: Java kits for GeckoLib mobs. `BoneMath` (same-frame bone transforms, model to world, chain segments), `SpringBones` (data-driven secondary motion: measured acceleration, fixed 4 ms steps, hitch and teleport guards, soft clamps, a traced tuning statistic), `SharedBoneLayer` (a second geometry that follows the main bones), `DevTrace`, and `geomob`: a compiling GeckoLib mob skeleton (entity with base and action controllers and server-timed contact, model with head look and springs, renderer, self-registering content class, spawn egg, lang, loot table, dependency declaration).
- New `kit PROJECT home --mob NAME`, the pipeline's `world` command and `guide worldgen`: a mob that belongs to a place. A home block whose block entity forms the mob, adopts an existing one and re-forms it (instead of an entity stored in a structure template); a structure type that anchors a template to a natural fluid surface read from the generator's base column (cave lava, the Nether lava sea, water), with its template piece; structure templates built from code with the structure, structure-set, template-pool, biome-tag and natural-spawn data, validated for the "all four files" rule; GameTests that the home forms exactly one resident and that the fluid scanner obeys its rules.
- `verify --client --world normal`: the screenshot run in a normal-terrain world with structure generation on (the flat test world has it off, where a structure's placement check passes but nothing ever generates). The engine gains a bounded `locate` step that logs a trace and flies the camera to the structure.
- `devshots` is now a scripted engine plus a scene script the project owns: `DevShots.java` (replaced by `--force`) plays steps built in `DevScenes.java` (never overwritten): commands, camera stations, framed shots, server-side actions, burst frames, trace lines. Starter scenes: turntable, UV orientation proof (including straight above and below) and night. `verify --client --scenes a,b` runs chosen scenes; the receipt records the filter and warns about runs of identical consecutive screenshots (a clicked window freezes the camera). `s.tag("name")` labels the trace lines of a scene; the spring solver ignores the velocity step of a scripted teleport.
- New `devlog PROJECT [--rules FILE] [--gate NAME]`: gates the client run's log. Built in: the script finished, no exception names the mod or its libraries, no sound event without a sound, no missing model or texture. With a rules JSON it checks `MCFORGE-TRACE kind key=value` lines: bounds, counts, distinct values, per-group reductions (last, max, p90 ...) and ratios between selections, with a per-kind summary for choosing thresholds.
- New guides: `guide worldgen` (above), `guide mobs` (the build path and order of work for a character mob, modelling, texture, animation, secondary motion, behaviour, proof) and `guide api` (verified NeoForge 21.1.265 and GeckoLib 4.9.3 signatures and behaviours, with the commands to re-verify them). `guide list` shows all guides, including private ones on the machine: Markdown files in `local/guides/` beside the toolkit or in folders named by `MCFORGE_GUIDES` load through `guide NAME`, are never packaged and survive updates. `plan` routes character-mob requests to the new path and names local guides.
- `voxel`: new shapes `intersect`, `halfspace` and `torus`, per-blob `texels_per_pixel`, and a white band on the UV test texture that shows where v starts.
- Fixed: the per-face UV direction of top and bottom faces. GeckoLib 4.9.3 maps `up` with u toward -X and v toward -Z and `down` with u toward -X and v toward +Z (read from its quad builder); `guide entities` and `preview` had both faces wrong, so previews of non-symmetric top or bottom textures were mirrored.
- Fixed: `voxel` placed blobs so that same-facing faces could sit 0.005 px apart while `model-check` flags anything under 0.01 px; the placement window is now 0.012 px.
- Fixed: `libs --add SLUG --version NUMBER` wrote the version number into the Gradle coordinate, which can resolve another loader's file. It now resolves the release of that number for the project's loader and writes its version id.
- Fixed: the screenshot driver waited forever on a new game directory, which opens the accessibility onboarding screen before the title screen.
- `guide entities`: a second geometry must come from `GeckoLibCache` (not `GeoModel.getBakedModel`), glow masks must be non-empty and the base texture's size, tracked bone matrices lag a frame and carry an offset in their rotation part, frame-rate independent spring filtering, the traced tuning statistic. `guide testing`: the scripted driver, `devlog`, repeatable scenes, harness habits that removed flaky runs, a run with the target pack's mods loaded. `guide audio`: levelling short sounds by RMS, vanilla loudness targets, take selection by measurement, staging generated audio outside the mod.

## 1.3.1 - 2026-11-15

Maintenance release from a full audit. No command, option or file format was removed.

- Fixed: the installed launcher (`Minecraft-Forge.cmd` / `Minecraft-Forge`) changed into the install folder, so a relative path such as `pack mypack` wrote inside the toolkit install. It now runs in the caller's folder and finds the package through `PYTHONPATH` (`-P`, so a folder named `mcforge` beside you cannot shadow it). Reinstall with `install --force` to get the new launcher.
- Fixed: malformed input (a truncated PNG, a lock file without `mod_id`, two keyframes at one time) printed a Python traceback and exited 1, the code for "problems found". Every command that cannot run now prints one JSON error line and exits 2; exit codes are documented in the README.
- Fixed: `search` always filtered to NeoForge. New `--loader neoforge|fabric|forge|quilt` (default unchanged).
- Fixed: `pack PATH --zip` named the archive `My.zip` for a folder `My.Pack`, and refused an existing ZIP only after writing the pack folder. It now writes `PATH.zip` and checks first.
- Fixed: `targets` and `doctor` reported no loader version for the Fabric targets; they now show Fabric Loader 0.20.1, the version the templates pin.
- Fixed: a fetched Fabric template compared Loom versions as text (`1.5.8` counted as newer than `1.19`).
- `deploy --apply` also backs up a file that already has the destination name but was not recognised as this mod, instead of overwriting it.
- `verify` replaces a lock left by a killed run (its recorded process no longer exists) and notes it in the receipt; a live lock names its run, process and path. `verify --check` accepts the project path in any letter case on Windows.
- `add`, `asset`, `bbmodel` and `voxel --project` refuse a project inside a launcher instance or behind a link, like `init` and `verify` already did.
- `scripts/package.py` hash-checks all seven bundled templates, not only the default one.
- `install` lists the backups earlier updates left (`backups`); the README covers update and removal.
- CI runs once per commit (pushes to main and pull requests), not again for tags and pull-request branches.

## 1.3.0 - 2026-11-14

Lessons from a large animated GeckoLib companion mob (NeoForge 1.21.1, GeckoLib 4.9.3), turned into commands.

- New `voxel SPEC.json`: implicit shapes (ellipsoids, superellipsoids, tapered capsules, boxes, unions, smooth unions, subtractions) become voxel cubes for GeckoLib: a greedy partition per blob (no self z-fighting by construction), a checked sub-pixel offset per blob against earlier blobs, buried faces left out of the per-face UV map (GeckoLib builds no quad for them), a packed texture, a UV test texture, a Blockbench project and a `model-check` report. Example: `templates/voxel/example.json`.
- `preview` renders GeckoLib `.geo.json` with the game's entity lighting (`--vanilla-light` for other models), poses it from an animation (`--animation FILE --clip NAME --time T`), skips missing faces like GeckoLib, and is much faster on large models.
- New `ground`: keys the root bone so the lowest leg point sits at y = 0 on every keyframe of the chosen clips. Its pose evaluator (Blockbench space, GeckoLib's Z-Y-X rotation order) reproduced in-game-proven root offsets of a shipped 941-cube model to within 0.001 px.
- New `audio-check PROJECT`: `sounds.json` events against registered `SoundEvent` ids and OGG files, plus channels, sample rate, duration, streaming and (with FFmpeg) loudness spread.
- New `devshots PROJECT` and `verify PROJECT --client` (NeoForge 1.21.1 with the test mod): a generated development-only client run creates a flat world, photographs the subject from ten stations and quits; the receipt records the screenshots and `client_load: passed`. First run here: a generated `add mob` creature rendered in a real client.
- `guide entities`: voxel modelling, preview lighting, grounding, underwater breathing tag and water movement attribute, attack reach, `TamableAnimal` sitting and guard goals, custom-coloured drip particles. `guide testing`: mock players are not in the level, fast-pass guards, `time set` delay, camera distances, richer scene recipes, dev-run log noise. `guide audio`: `audio-check`, shared-GPU generation, deriving variants, loudness matching. `guide workflow`: `python -I` and sibling imports.
- Public text: the code of conduct is reworded in neutral terms, and the release hygiene gate now rejects a list of blocked words (stored only as hashes) in every tracked file.

## 1.2.0 - 2026-11-14

Lessons from a finished GeckoLib horse mob (NeoForge 1.21.1, GeckoLib 4.9.3).

- Fixed: `guide testing` put the arena's centre at `(7, 1, 7)`, which is the floor block. GameTest positions are relative to the structure block and the template sits one block above it, so mobs stand at y = 2; a mob at y = 1 suffocates in the floor. The starter and `tests` now ship `ArenaTests` with `STAND = (7, 2, 7)`, `FLOOR`, and a regression test that keeps a horse there for 100 ticks and requires it alive, unhurt and on the floor (run in CI on Windows and Linux).
- New `--no-examples` for `init` and `quickstart` on every target: no example block, item, creative tab or their names (NeoForge/Forge main classes keep their empty registers and config; Fabric skips the generated examples). With `--with-tests` the test mod keeps the arena, report writer, load test and arena test, without the example recipe provider and its two tests. CI now builds and server-loads every MDK target this way.
- New `model-check FILE`: lists z-fighting (same-facing, coplanar, overlapping faces) in a `.bbmodel`, `.geo.json` or block model, skips overlaps another cube covers (containing or touching them from outside), and exits 1 while any remain.
- `verify` excludes every root `run-*` game directory (for example `run-devshots/`), so a screenshot run between `verify` and `verify --check` no longer invalidates the receipt.
- Fixed: `Minecraft-Forge.ps1` aborted a successful run under Windows PowerShell 5.1 when the caller merged stderr (`2>&1`): the first progress line became a terminating error. The `gradle` command now prints its log path and exit code on stdout; JSON commands keep progress on stderr, and `MCFORGE_INFO=off` hides it. `sources --project PATH QUERY` prints each `Source:` header on stdout with its matches.
- `doctor --project` warns when `gradle.properties` starts with a UTF-8 byte-order mark (Windows PowerShell 5.1 `Set-Content -Encoding utf8`) and refuses to read pins when Gradle would lose the first property.
- `guide testing`: client screenshot driver keeps running unattended (no pause on lost focus, closes the pause screen), entity tags are server-only, deterministic actions through the integrated server, breeding and natural-spawn GameTests. `guide entities`: client-side animation predicates read synced state only, horse flags, GeckoLib baby scaling, layer re-rendering, glowmask per texture variant, cutout per-texel alpha, keyed-plus-procedural bone drift, UV directions per face, spring tuning target, rideable horse values, horse armor on a custom model, inverted-hull outline glow. `guide tools` and `guide workflow`: Windows PowerShell 5.1 pitfalls.

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

- Replace the generic Contributor Covenant with the project's own code of conduct: any content is allowed except backdoors, content that exploits minors, malware and hidden destructive behavior.

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
