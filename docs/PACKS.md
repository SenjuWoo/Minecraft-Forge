# Packs without a compiled mod

Many requests need no Java at all. `pack` creates the three kinds; pack formats and folder names come from facts read out of each release's client JAR (`mcforge/data/minecraft_versions.json`, 1.14 to 26.3).

```powershell
.\Minecraft-Forge.ps1 pack D:\Packs\RubyLook --kind resource --name "Ruby Look" --minecraft 1.21.1 --retexture block/stone --retexture item/iron_sword --zip
.\Minecraft-Forge.ps1 pack D:\Packs\Tweaks --kind data --name "Tweaks" --minecraft 1.20.1
.\Minecraft-Forge.ps1 pack D:\Packs\WarmPost --kind shader --name "Warm Post"
```

## Resource pack

`pack.mcmeta` with the right `pack_format` (or `min_format`/`max_format` on releases that use major.minor pack versions) and, for every `--retexture`, a procedural replacement at that vanilla texture path. Install into `resourcepacks/`. Replace the generated textures with your own art; `preview PROJECT FILE.png` zooms any texture for review.

## Data pack

A load function that prints a chat line, the `minecraft:load` function tag, and a shapeless recipe (dirt + wheat seeds -> grass block) in the JSON shape that release uses: `result.item` before 1.20.5, `result.id` after; ingredient objects before 1.21.2, plain ids after. Folder names follow the 1.21 rename (`functions` -> `function`, `recipes` -> `recipe`, `tags/functions` -> `tags/function`). Install into `saves/<world>/datapacks/` and run `/reload`.

Recipes, tags, loot tables, advancements, functions and most worldgen are data: try a data pack (or KubeJS in a pack that has it) before writing a mod.

## A resource pack with models the game cannot read

Packs that support many releases sometimes ship models in a newer model format for blocks the older game only has through a mod (a backport, for example). The older game rejects the whole model file, logs `Unable to load model`, and the block renders purple and black. Seen on 1.21.1 with a pack that targets everything up to 26.x: Euler `x`/`y`/`z` element rotations, angles of 67.5, 90 or 180 degrees, `shade_direction_override`, `light_emission` and texture objects (`{"sprite": ...}`).

`packcompat` writes a small overlay pack that holds only the rewritten files; everything else still comes from the original pack, which is never changed:

```powershell
.\Minecraft-Forge.ps1 packcompat "<pack>.zip" --minecraft 1.21.1 --out D:\Packs\Pack-compat [--mod-jar "<mod>.jar"]
.\Minecraft-Forge.ps1 packcompat "<pack>.zip" --minecraft 1.21.1 --instance "<instance folder>"           # plan only
.\Minecraft-Forge.ps1 packcompat "<pack>.zip" --minecraft 1.21.1 --instance "<instance folder>" --apply   # writes resourcepacks/<pack>-compat
```

- It reads the pack the way the target does: root files plus the overlay folders whose `formats` range includes the target's pack format (in 1.21.1 a later overlay wins over earlier ones and over the root; NeoForge's `neoforge:overlays` come after the vanilla ones). Overlays for newer formats are skipped and listed.
- Rewrites: one rotation axis (the largest Euler component; dropped components are reported), angles clamped to -45..45 in 22.5 steps (reported), `shade_direction_override: "up"` -> `shade: false`, `light_emission` -> NeoForge `neoforge_data.block_light`, texture objects -> the sprite string. Each rewritten file lists its fixes and fallbacks.
- `--mod-jar`: a pack blockstate written for a snapshot of a block (property names the mod's block does not have) is replaced by the mod's own blockstate. A mod blockstate keyed only by `""` lists no properties and gives no verdict.
- `--out` inside a launcher instance is refused; `--instance` plans and `--apply` writes only `resourcepacks/<pack>-compat`. The command never edits `options.txt`: it prints the `resourcePacks` entry and where it goes. The list runs bottom to top, so the overlay goes directly **after** the original pack's entry (or above it in the Resource Packs screen).
- A rerun replaces its own previous output (marked by `mcforge-packcompat.json`); a folder with other files is refused.
- The rules were checked on 1.21.1 against packs written for 26.x. For other targets the output says so: some fields may already be valid there.

Check in a client: count `Unable to load model` lines in `latest.log` before and after. One limit stays: every enabled pack's blockstate is parsed, even one a higher pack overrides, so a hidden snapshot blockstate keeps logging parse warnings while the overlay's copy is the one that renders.

## Shader pack

A post-processing pack for **Iris** or **OptiFine**: `shaders/final.vsh` and `final.fsh` (GLSL 1.20) with saturation, warmth and vignette as settings-screen options (`shaders.properties`, `lang/en_us.lang`). Install into `shaderpacks/`. Extend it with `composite*.fsh` passes, `gbuffers_*` programs for geometry and `shadow.*` for shadows, following the [Iris](https://github.com/IrisShaders/ShaderDoc) / [OptiFine](https://github.com/sp614x/optifine/tree/master/OptiFineDoc/doc) shader documentation.

The toolkit cannot compile GLSL or start a client: load the pack and read the log for compile errors. Resource-pack core shaders (vanilla `assets/minecraft/shaders/`) change between releases; read the target version's own files before overriding one.
