# Libraries mods build on

`libs` lists a catalog of popular libraries and APIs (about 60): loader cores, multi-loader layers, config screens, animation, equipment slots, recipe viewers, tooltips, worldgen, scripting, language adapters and the big content mods that others integrate with. Titles, loaders, licences, links and Minecraft ranges come from each project's Modrinth record (`scripts/build_libraries.py`), and the catalog is read offline.

```powershell
.\Minecraft-Forge.ps1 libs --loader fabric --minecraft 1.20.1
.\Minecraft-Forge.ps1 libs --category animation
.\Minecraft-Forge.ps1 libs --query slots
.\Minecraft-Forge.ps1 libs --resolve geckolib --project D:\Mods\MyMod
.\Minecraft-Forge.ps1 libs --add geckolib --project D:\Mods\MyMod
```

Categories: `core multiloader config animation entity rendering equipment recipes books info scripting worldgen language ui data content server diagnostics`.

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
