# Free procedural assets

`asset` generates original placeholder art and the resource/data files needed to
see it in-game. It uses only the Python standard library: no paid API, no
account, no downloaded art, and no external process. The same project + id +
style + size always produces the same PNG bytes.

## What it makes

For a **block**:

- `assets/<modid>/blockstates/<id>.json`
- `assets/<modid>/models/block/<id>.json` (`minecraft:block/cube_all`)
- `assets/<modid>/models/item/<id>.json` (parented to the block model)
- `assets/<modid>/textures/block/<id>.png` (RGBA)
- `data/<modid>/loot_table/blocks/<id>.json` (drops the block item)
- `block.<modid>.<id>` in `assets/<modid>/lang/en_us.json`

For an **item**:

- `assets/<modid>/models/item/<id>.json` (`minecraft:item/generated`)
- `assets/<modid>/textures/item/<id>.png` (RGBA, transparent outside the shape)
- `item.<modid>.<id>` in `assets/<modid>/lang/en_us.json`

It also writes `mcforge-assets.json` at the project root with the style, size,
texture hashes and generated file list.

## Use it

```powershell
# Dress the scaffold's registered example_block and example_item
.\Minecraft-Forge.ps1 asset "D:\YourProjects\MyMod"

# Add a gem block and an item with an explicit style and 32x32 textures
.\Minecraft-Forge.ps1 asset "D:\YourProjects\MyMod" --id ruby_block:block --id ruby:item --style gem --size 32

# Replace existing generated files intentionally
.\Minecraft-Forge.ps1 asset "D:\YourProjects\MyMod" --id ruby_block:block --force
```

`quickstart` does `init --with-tests` and the default asset pass in one command:

```powershell
.\Minecraft-Forge.ps1 quickstart "D:\YourProjects\MyMod" --mod-id mymod --package dev.yourname.mymod --name "My Mod"
```

## Rules and limits

- IDs must match `[a-z0-9_]{2,64}`. New IDs must also be registered in Java; the
  generator writes resources and data, not registration code.
- Existing files are skipped unless `--force` is passed. `en_us.json` is merged,
  so existing keys are preserved.
- Styles: `auto`, `stone`, `wood`, `gem`, `metal`, `organic`, `arcane`. `auto`
  reads words in the id (`oak_plank` → wood, `ruby_gem` → gem, `iron_ingot` →
  metal, `moss_leaf` → organic, `void_rune` → arcane; otherwise stone).
- Sizes: 16 or 32 pixels. Output is deliberately placeholder-quality: readable
  silhouettes and palettes, not final hand-painted art.
- No sounds, animated textures, block entities, custom models or Java code are
  generated. Use the free tools below for those gaps.

## Free tools that fill the remaining gaps

| Gap | Free tool | Why |
|---|---|---|
| Painting/replacing textures | [Krita](https://krita.org/) or [GIMP](https://www.gimp.org/) | Layered raster editing, export PNG |
| Complex block/item models and animation | [Blockbench](https://www.blockbench.net/) | Minecraft model formats and previews |
| Batch resize/palette/format work | [ImageMagick](https://imagemagick.org/) | `magick`/`convert` in a script |
| OGG sounds and music | [FFmpeg](https://ffmpeg.org/) or [Audacity](https://www.audacityteam.org/) | Minecraft uses OGG Vorbis |
| 3D assets | [Blender](https://www.blender.org/) | Export glTF/OBJ for custom pipelines |

`doctor` reports which of `magick`, `ffmpeg`, `blockbench`, `krita`, `gimp` and
`audacity` are on `PATH`. Missing tools are optional; the built-in generator
needs none of them. No paid asset service is required or configured.
