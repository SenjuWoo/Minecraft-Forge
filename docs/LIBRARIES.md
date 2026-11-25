# Libraries mods build on

`libs` lists a catalog of popular libraries and APIs (about 70): loader cores, multi-loader layers, config screens, animation, equipment slots, recipe viewers, tooltips, worldgen, scripting, language adapters and the big content mods that others integrate with. Titles, loaders, licences, links and Minecraft ranges come from each project's Modrinth record (`scripts/build_libraries.py`), and the catalog is read offline.

```powershell
.\Minecraft-Forge.ps1 libs --loader fabric --minecraft 1.20.1
.\Minecraft-Forge.ps1 libs --category animation
.\Minecraft-Forge.ps1 libs --query slots
.\Minecraft-Forge.ps1 libs --resolve geckolib --project D:\Mods\MyMod
.\Minecraft-Forge.ps1 libs --add geckolib --project D:\Mods\MyMod
```

Categories: `core multiloader config animation entity rendering equipment recipes books info scripting worldgen language ui data content server diagnostics performance`.

## Resolve and add

`--resolve` asks Modrinth for the newest release matching the project's loader and Minecraft version and prints the version, file, size, SHA-1/SHA-512 and declared dependencies. `--add` writes it into `build.gradle` as one marked block:

```groovy
// mcforge libs: geckolib (...)
repositories { maven { name = "Modrinth"; url = "https://api.modrinth.com/maven"; content { includeGroup "maven.modrinth" } } }
dependencies { implementation "maven.modrinth:geckolib:Grwn5rUB" }
// end mcforge libs: geckolib
```

- The coordinate uses the Modrinth **version id**, not the version number: one number can name files for several loaders and Minecraft versions (a 4.8.4 coordinate once resolved to a 1.21.4 file for a 1.20.1 project). The id is exact.
- The configuration follows the build system: `modImplementation` on remapped Fabric, `implementation fg.deobf(...)` on ForgeGradle 6, `implementation` elsewhere. Running `--add` again replaces the block. `--version` pins a specific id or number.
- Then declare the dependency in your mod metadata (`neoforge.mods.toml` / `mods.toml` `[[dependencies.<modid>]]`, or `fabric.mod.json` `depends`) with the library's mod id, add its required libraries, and run `verify`. The game-test server loads the library, so a wrong version fails there.

A resolved release is a candidate, not compatibility proof. Read the library's own docs for its API; its source is linked in the catalog (`source`, `docs`).

## Installed reality first

For a mod meant for an existing pack, match the pack: `inventory --instance PATH` lists the exact library versions already installed (`jar PATH` for one file). Building against the version the pack ships avoids a second copy at runtime.

## Performance base and rendering boundaries (1.21.1 NeoForge, measured 2026-11-24/25)

Two audits of a 221-mod 1.21.1 NeoForge pack (Sodium 0.8.13, Iris 1.8.14, Distant Horizons 3.3.3, BSL 10.1.1, RTX 4080 SUPER, 16-thread CPU, 2560x1440) produced these rules.

**Measure in motion.** A fixed camera hides what players complain about. The runs that settled these rules flew a spectator camera about 1000 blocks out over new terrain at sprint-flight speed (22 blocks/s) and back, sampled the render thread's frame time every tick (`Minecraft.getFrameTimeNs()`), GPU load twice a second (`nvidia-smi`), how many chunks ahead the client had loaded, and six screenshots per leg; then repeated the route over a world where the same corridor already existed. Frame rate was never the limit (130-400 fps, GPU-bound); world streaming was.

**Base optimisers that coexist:** ModernFix, FerriteCore, ImmediatelyFast, EntityCulling, BadOptimizations, Structure Layout Optimizer (needs Resourceful Config), Lithium. Lithium and ModernFix both overwrite `BiomeMixin.getTemperature` and `SortedArraySetMixin.removeIf`; set `mixin.world.temperature_cache=false` and `mixin.collections.chunk_tickets=false` in `config/lithium.properties` to keep the warnings out.

**Updates.**
- Do not take a Sodium beta while a closed-source mod compiled against the Sodium API is installed. Sodium 0.8.14-beta.2 removed `VertexBufferWriter.push(MemoryStack, long, int, VertexFormat)`; Physics Mod Pro still called it, so the game crashed on the first entity render after joining a world (`NoSuchMethodError`, and `AbstractMethodError` on entity death). Every declared version range was satisfied.
- Sodium Extra and Flerovium betas require the matching Sodium beta (Sodium Extra 0.9.6-beta.1 exactly `0.8.14-beta.2`, Flerovium 1.2.1 `[0.8.14-beta.2,0.9)`); they roll back together.
- Run `links --instance PATH` after every update and before launching: it reads the class files and reports calls into another mod that the installed version no longer has.

**Upscalers.** One render-scale or frame-generation mod at most; Metal Upscaler and PixelScale both replace the render target and conflict. Neither held up:
- Metal Upscaler 0.5.0 (DLSS, OpenGL to D3D12 handoff) in a valid run (frame generation off, real 1440p output, 77% render scale): 178 -> 84 fps. Its large render-thread share is time blocked in its native call.
- PixelScale 1.0.0 (FSR3 temporal, 77%): 207 -> 256 fps on the heavy leg, but visible pixelation, missing water and holes under a shader pack.
- Test an upscaler with your own scene and look at the image, not only the counter.

**Distant Horizons with a shader pack.**
- With Iris active, the shader pack's own DH program decides where far terrain starts. BSL discards every LOD fragment nearer than `far - (DH_OVERDRAW + 0.75) * 16` blocks; the default 1.0 hides LODs within about 165 of 192 blocks, so any real chunk that is late inside that ring is a hole you see caves through, whatever `DistantHorizons.toml` says. Set `DH_OVERDRAW=9.0` in `shaderpacks/<pack>.txt` (LODs from about 36-52 blocks).
- Keep DH `overdrawPrevention` at `"0.2"` (DH's own automatic value when a shader pack is active), so DH's near plane stays inside the shader's radius.
- DH 3.3.3 skips its vanilla fade and far fade when a shader pack is in use (`ClientApi.shouldRenderFade()`), so `vanillaFadeMode` changes nothing under shaders.
- Cost over fully generated terrain: about 9% (142/148 -> 129/136 fps). What remains: a dithered band where LODs start, visible only where real chunks are missing, and empty fog where neither chunks nor LODs exist yet.
- Do not use mods that reshape the vanilla render volume (Better FPS Distance and similar); DH draws nothing inside it.

**Distant Horizons generation.**
- `pauseIfMovingQuickly = false`: otherwise DH stops generating exactly when you fly into new terrain.
- `numberOfThreads = 12` and `threadRunTimeRatio = "1.0"` on a 16-thread CPU: DH's generator did 60% more work and its LODs covered the missing chunks on the return leg at sprint-flight speed (before: open walls at the edge of the generated strip).
- With custom worldgen (Tectonic, BWG, TerraBlender): `generatorPlan = "CHUNKS_ONLY"` (the surface estimate guesses wrong and real LODs replace it later: terrain popping) and `enableCaveCulling = false` (it drops visible terrain below the cull height).
- `showUpdateQueueOverloadedChatWarning = true` while tuning: DH says in chat when its chunk update queue overflows (holes in LODs).
- Real chunk generation (the vanilla worker pool) is the slowest part in new terrain: under 2 of 13 workers busy. C2ME addresses that; it is an alpha for 1.21.1 NeoForge.

**Physics Mod Pro under shaders.**
- `oceanPhysics = false`: its FFT ocean replaces the shader water (about 9% of the render thread).
- `vinePhysics = false`: every vine and kelp piece is drawn separately, and again in the shadow pass (20.6% of the render thread over a kelp ocean; 272 -> 315 and 399 fps in two runs).

**What not to switch to.** Rust rewrites of Minecraft (clients and servers) load no Java or NeoForge mods and none targets 1.21.1; a modded pack cannot move to them. No gap found here needed a new client mod: every fix above is configuration, a version choice, or an existing mod.

**Housekeeping.**
- Orphaned libraries are dead weight: check reverse dependencies in each `neoforge.mods.toml` before removing a library; mods removed from a pack leave their libs behind (Tensura -> Manascore, Weather2 -> Coroutil, BOP -> GlitchCore).
- Profile before and after with spark (`/sparkc profiler start --thread *`, `stop --save-to-file`); the `.sparkprofile` is a protobuf `SamplerData` and can be read without the spark mod.
