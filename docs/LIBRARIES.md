# Libraries mods build on

`libs` lists a catalog of popular libraries and APIs (about 60): loader cores, multi-loader layers, config screens, animation, equipment slots, recipe viewers, tooltips, worldgen, scripting, language adapters and the big content mods that others integrate with. Titles, loaders, licences, links and Minecraft ranges come from each project's Modrinth record (`scripts/build_libraries.py`), and the catalog is read offline.

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

## Performance stack and rendering boundaries (1.21.1 NeoForge, measured 2026-11-24)

A pack audit on a 221-mod 1.21.1 NeoForge pack (Sodium 0.8.13, Iris 1.8.14, DH 3.3.3, BSL 10.1.1, RTX 4080 SUPER, 2560x1440) produced these rules:

- Base optimisers that coexist: ModernFix, FerriteCore, ImmediatelyFast, EntityCulling, BadOptimizations, Structure Layout Optimizer (needs Resourceful Config), Lithium. Lithium and ModernFix both overwrite `BiomeMixin.getTemperature` and `SortedArraySetMixin.removeIf`; set `mixin.world.temperature_cache=false` and `mixin.collections.chunk_tickets=false` in `config/lithium.properties` to keep the warnings out.
- One render-scale/frame-generation mod only. Metal Upscaler 0.5.0 (DLSS) and PixelScale both replace the render target and video settings; together they conflict. Measured: DLSS at 77% render scale took 51.9% of the render thread (`dlssEvaluate`) and dropped the average from 178 to 84 fps under shaders. Test an upscaler with your own scene before shipping it in a pack.
- Distant Horizons with custom worldgen (Tectonic, BWG, TerraBlender): `generatorPlan = "CHUNKS_ONLY"` (the surface estimate guesses wrong, then real LODs replace it, which shows as terrain popping), `enableCaveCulling = false` (it drops visible terrain below the cull height), `numberOfThreads = 6` on an 8-core CPU.
- DH holes at the vanilla render border: do not use mods that reshape the vanilla render volume (Better FPS Distance and similar); DH draws nothing inside it. Keep `overdrawPrevention` at `"0.5"`, `ditherDhFade = false`, `vanillaFadeMode = "DOUBLE_PASS"`.
- Physics Mod Pro: `oceanPhysics = false` under shaders (its FFT ocean replaces the shader water and cost ~9% of the render thread).
- Orphaned libraries are dead weight: check reverse dependencies in each `neoforge.mods.toml` before removing a library; mods removed from a pack leave their libs behind (Tensura -> Manascore, Weather2 -> Coroutil, BOP -> GlitchCore).
- Profile before and after with spark (`/sparkc profiler start --thread *`, `stop --save-to-file`); the `.sparkprofile` is a protobuf `SamplerData` and can be read without the spark mod.
