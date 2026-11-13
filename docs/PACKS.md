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

## Shader pack

A post-processing pack for **Iris** or **OptiFine**: `shaders/final.vsh` and `final.fsh` (GLSL 1.20) with saturation, warmth and vignette as settings-screen options (`shaders.properties`, `lang/en_us.lang`). Install into `shaderpacks/`. Extend it with `composite*.fsh` passes, `gbuffers_*` programs for geometry and `shadow.*` for shadows, following the [Iris](https://github.com/IrisShaders/ShaderDoc) / [OptiFine](https://github.com/sp614x/optifine/tree/master/OptiFineDoc/doc) shader documentation.

The toolkit cannot compile GLSL or start a client: load the pack and read the log for compile errors. Resource-pack core shaders (vanilla `assets/minecraft/shaders/`) change between releases; read the target version's own files before overriding one.
