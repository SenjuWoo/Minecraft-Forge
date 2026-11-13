"""Rebuild mcforge/data/libraries.json from Modrinth's public API.

Maintainer action; requires network. The curated list below only says which
projects to look up and why a mod author would use them. Everything else in
the output (title, loaders, licence, links, supported Minecraft range) is read
from the project's own Modrinth record, and a slug that no longer resolves is
dropped rather than guessed.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.modrinth.com/v2/projects?ids="
AGENT = "Minecraft-Forge (library catalog maintenance)"

# slug -> (category, what it gives a mod author)
CURATED = {
    "fabric-api": ("core", "Fabric's standard hooks: registries, events, networking, rendering, data generation"),
    "forgified-fabric-api": ("core", "Fabric API implemented on NeoForge, for mods ported from Fabric"),
    "connector": ("core", "Runs Fabric mods on NeoForge; a compatibility target, not a build dependency"),
    "architectury-api": ("multiloader", "One API over Fabric, Forge and NeoForge for registries, events and networking"),
    "balm": ("multiloader", "Multi-loader abstraction layer for content, config and networking"),
    "puzzles-lib": ("multiloader", "Multi-loader library with registration, config and event helpers"),
    "bookshelf-lib": ("multiloader", "Shared utility code: registration, data loading, commands"),
    "resourceful-lib": ("multiloader", "Cross-loader registries, networking and codec utilities"),
    "moonlight": ("multiloader", "Dynamic assets and data, custom map markers, fluid and misc helpers"),
    "framework": ("multiloader", "Config, networking and synced data keys across loaders"),
    "cloth-config": ("config", "Config screen builder used by many mods"),
    "yacl": ("config", "YetAnotherConfigLib: declarative config screens"),
    "forge-config-api-port": ("config", "NeoForge/Forge config system on every loader"),
    "midnightlib": ("config", "Small annotation-driven config library"),
    "fzzy-config": ("config", "Kotlin-friendly config with generated screens and sync"),
    "modmenu": ("config", "Fabric mod list screen; where config screens are opened"),
    "geckolib": ("animation", "Keyframed entity, block, item and armor animation from Blockbench"),
    "azurelib": ("animation", "Animation engine in the GeckoLib family"),
    "playeranimator": ("animation", "Keyframed animations for the player model"),
    "smartbrainlib": ("entity", "Brain-based mob AI builders, a cleaner alternative to goals"),
    "entity-model-features": ("rendering", "Custom entity models from resource packs (OptiFine CEM format)"),
    "entity-texture-features": ("rendering", "Random, emissive and conditional entity textures from resource packs"),
    "sodium": ("rendering", "Rendering engine most packs use; test rendering code against it"),
    "iris": ("rendering", "Shader pack loader; shader packs target its pipeline"),
    "curios": ("equipment", "Extra equipment slots (rings, belts, charms) on NeoForge/Forge"),
    "trinkets": ("equipment", "Extra equipment slots on Fabric"),
    "accessories": ("equipment", "Data-driven equipment slots on every loader"),
    "caelus": ("equipment", "Elytra flight as an attribute, for custom wings"),
    "pehkui": ("entity", "Entity scaling API"),
    "jei": ("recipes", "Recipe viewer; plugin API for custom recipe categories"),
    "rei": ("recipes", "Recipe viewer with its own plugin API"),
    "emi": ("recipes", "Recipe viewer with its own plugin API"),
    "patchouli": ("books", "Data-driven in-game guide books"),
    "jade": ("info", "Block/entity tooltip overlay with a provider API"),
    "wthit": ("info", "Block/entity tooltip overlay with a provider API"),
    "the-one-probe": ("info", "Block/entity probe overlay with a provider API"),
    "kubejs": ("scripting", "Pack scripting: recipes, events and simple content without compiling a mod"),
    "terrablender": ("worldgen", "Adds biomes to the overworld and nether without replacing vanilla regions"),
    "lithostitched": ("worldgen", "Data-driven worldgen modifiers for compatibility"),
    "yungs-api": ("worldgen", "Structure and jigsaw utilities"),
    "glitchcore": ("multiloader", "Multi-loader core used by Biomes O' Plenty family mods"),
    "kotlin-for-forge": ("language", "Kotlin language adapter for NeoForge/Forge"),
    "fabric-language-kotlin": ("language", "Kotlin language adapter for Fabric"),
    "owo-lib": ("ui", "Declarative UI, config and networking for Fabric"),
    "cardinal-components-api": ("data", "Attach data components to entities, chunks, worlds and items on Fabric"),
    "create": ("content", "Mechanical contraptions; large API for kinetic blocks"),
    "create-fabric": ("content", "Create on Fabric"),
    "mekanism": ("content", "Tech mod with an API for chemicals and energy"),
    "ae2": ("content", "Applied Energistics 2: storage network API"),
    "cc-tweaked": ("content", "Programmable computers; peripheral API"),
    "botarium": ("content", "Cross-loader energy, fluid and item transfer API"),
    "collective": ("multiloader", "Shared library for a large family of small mods"),
    "placebo": ("core", "NeoForge/Forge utility library"),
    "citadel": ("animation", "Entity animation and utility library on NeoForge/Forge"),
    "creativecore": ("ui", "GUI, config and networking library"),
    "supermartijn642s-core-lib": ("multiloader", "Registration, GUI and networking helpers"),
    "supermartijn642s-config-lib": ("config", "Small cross-loader config library"),
    "iceberg": ("ui", "Tooltip and UI utility library"),
    "prism-lib": ("ui", "Colour utility library"),
    "polymer": ("server", "Server-side content that vanilla clients can see"),
    "spark": ("diagnostics", "Profiler; use it to measure tick and memory cost of a mod"),
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def version_key(value: str):
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def main() -> int:
    slugs = sorted(CURATED)
    rows = []
    for start in range(0, len(slugs), 40):
        rows += json.loads(fetch(API + urllib.parse.quote(json.dumps(slugs[start:start + 40]))))
        time.sleep(0.3)
    found = {row["slug"]: row for row in rows}
    libraries = {}
    for slug in slugs:
        row = found.get(slug)
        if not row:
            print(f"dropped (not on Modrinth under this slug): {slug}", file=sys.stderr)
            continue
        releases = sorted((value for value in row.get("game_versions", []) if value.replace(".", "").isdigit()), key=version_key)
        category, purpose = CURATED[slug]
        libraries[slug] = {
            "title": row["title"], "category": category, "purpose": purpose, "project_id": row["id"],
            "loaders": sorted(loader for loader in row.get("loaders", []) if loader in ("fabric", "forge", "neoforge", "quilt")),
            "license": (row.get("license") or {}).get("id"), "source": row.get("source_url"), "docs": row.get("wiki_url"),
            "issues": row.get("issues_url"), "page": f"https://modrinth.com/mod/{slug}",
            "minecraft": {"oldest": releases[0], "newest": releases[-1]} if releases else None,
            "client_side": row.get("client_side"), "server_side": row.get("server_side"),
            "maven": f"maven.modrinth:{slug}:<version>",
        }
    output = ROOT / "mcforge/data/libraries.json"
    output.write_text(json.dumps({"schema": 1, "source": "https://api.modrinth.com/v2", "generated": time.strftime("%Y-%m-%d"),
                                  "note": "Titles, loaders, licences, links and version ranges come from each project's Modrinth record. "
                                          "The maven coordinate is Modrinth's own repository (https://api.modrinth.com/maven); "
                                          "resolve an exact version with: libs --resolve SLUG.",
                                  "libraries": libraries}, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"libraries": len(libraries), "dropped": sorted(set(slugs) - set(libraries))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
