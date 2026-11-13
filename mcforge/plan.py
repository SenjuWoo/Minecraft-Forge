"""`plan`: route a plain-language request to commands, guides and pitfalls before any file is written.

Routing is keyword based and deliberately conservative: it names the first
commands and the one guide to read, never edits anything, and says when the
request belongs in a pack instead of a compiled mod.
"""
from __future__ import annotations

import re

ROUTES = [
    (("shader", "shaderpack", "iris", "optifine", "glsl"), "shader pack",
     ["pack NEW_PATH --kind shader --name NAME --minecraft VERSION"], "packs",
     ["Shader packs are not mods: no loader, no Gradle", "The toolkit cannot compile GLSL; load the pack in a client and read the log"]),
    (("resource pack", "resourcepack", "retexture", "texture pack"), "resource pack",
     ["pack NEW_PATH --kind resource --name NAME --minecraft VERSION --retexture block/stone"], "packs",
     ["A resource pack replaces vanilla files at the same path; no Java needed"]),
    (("datapack", "data pack", "mcfunction", "function", "loot table tweak"), "data pack",
     ["pack NEW_PATH --kind data --name NAME --minecraft VERSION"], "packs",
     ["Recipes, tags, loot and functions need no compiled mod; KubeJS covers pack-level scripting"]),
    (("blockbench", "bbmodel", "custom model"), "Blockbench model",
     ["bbmodel PROJECT FILE.bbmodel --block ID", "bbmodel PROJECT FILE.bbmodel --entity ID", "preview PROJECT FILE.bbmodel"], "content",
     ["Block models: one rotation axis per cube; entity models: rotate bones, not cubes", "Embed the texture in the .bbmodel before importing"]),
    (("animation", "animated", "geckolib", "keyframe", "physics", "boss fight"), "animated entity",
     ["libs --add geckolib --project PROJECT", "guide entities"], "entities",
     ["Scripted .geo.json/animation JSON: rotation [-x,-y,z], pivot [-x,y,z]; animation rotation adds to rest",
      "Prove orientation with a UV test texture in a client screenshot run before texturing",
      "Procedural bones (look, springs) must not be keyed by any animation"]),
    (("sound", "sfx", "voice", "music", "audio", "subtitle"), "sounds",
     ["guide audio"], "audio",
     ["sounds.json keys, SoundEvent ids and OGG paths must agree; positional sounds are mono OGG Vorbis",
      "Single-speaker TTS spells interjections letter by letter; use non-verbal tags and a reference voice",
      "Packaged is not heard: report audio unverified unless someone listened"]),
    (("mob", "entity", "creature", "monster", "boss", "animal", "pet"), "mob",
     ["add PROJECT mob NAME [--shape quadruped|biped|blob] [--hostile]", "preview PROJECT blockbench/NAME.bbmodel"], "content",
     ["Spawning in the world needs biome modifiers or spawn placements; the spawn egg works immediately",
      "Keyframed animation beyond walk/look: GeckoLib (libs --resolve geckolib --project PROJECT)"]),
    (("armor", "armour", "helmet", "chestplate", "leggings", "boots"), "armor set",
     ["add PROJECT armor NAME --tier iron --repair ITEM"], "content",
     ["1.21.2+ moved armor textures to equipment assets; the generator follows the project's version"]),
    (("sword", "pickaxe", "axe", "shovel", "hoe", "tool", "weapon"), "tools or weapons",
     ["add PROJECT toolset NAME --tier iron --repair ITEM", "add PROJECT sword NAME"], "content",
     ["Ranged weapons (bows, guns) are custom Item subclasses: start from add item, then follow guide content"]),
    (("furniture", "chair", "table", "lamp", "shelf", "cabinet", "bench", "stool", "decor"), "furniture",
     ["add PROJECT furniture NAME --shape chair|table|stool|bench|shelf|cabinet|lamp|pedestal"], "content",
     ["Sitting needs an invisible seat entity; the generated block handles shape, facing and drops"]),
    (("food", "eat", "snack", "meal"), "food", ["add PROJECT food NAME"], "content", []),
    (("block", "ore", "brick", "stone"), "block", ["add PROJECT block NAME --style stone|metal|gem|wood|organic|arcane"], "content",
     ["Ore generation needs worldgen JSON (configured/placed features plus a biome modifier)"]),
    (("item", "ingot", "gem", "material"), "item", ["add PROJECT item NAME [--shape ingot|gemstone|orb]"], "content", []),
    (("library", "dependency", "api", "geckolib", "curios", "trinkets", "jei", "architectury", "cloth"), "library",
     ["libs --loader LOADER --minecraft VERSION", "libs --resolve SLUG --project PROJECT", "libs --add SLUG --project PROJECT"], "libraries",
     ["A resolved release is a candidate: build and test it", "Declare the dependency in your mod metadata too"]),
    (("deploy", "install into", "my pack", "atlauncher", "prism", "curseforge", "modrinth app", "instance"), "deploy to an instance",
     ["instances", "deploy PROJECT --instance INSTANCE", "deploy PROJECT --instance INSTANCE --apply"], "launchers",
     ["Close the game first; deploy keeps a backup of any replaced JAR", "Deploying is not a runtime test"]),
    (("crash", "log", "broken pack", "won't start"), "pack diagnosis",
     ["instances", "inventory --instance INSTANCE --output NEW_FILE"], "workflow",
     ["Read the matching crash report and debug.log; a named class is not proof of the culprit"]),
    (("port", "update to", "upgrade"), "port or update",
     ["doctor --project PROJECT", "updates PROJECT"], "workflow",
     ["Another Minecraft version is a port: new template, new API, new tests", "Update candidates are not compatibility proof"]),
]
LOADER_WORDS = {"neoforge": "neoforge", "neo forge": "neoforge", "fabric": "fabric", "quilt": "fabric", "forge": "forge"}


def plan(request: str) -> dict:
    text = request.lower()
    version = re.search(r"\b(1\.\d{1,2}(?:\.\d{1,2})?|2\d\.\d(?:\.\d)?)\b", text)
    loader = next((value for word, value in LOADER_WORDS.items() if re.search(r"\b" + word + r"\b", text)), None)
    matched = []
    for words, label, commands, guide, pitfalls in ROUTES:
        if any(re.search(r"\b" + re.escape(word), text) for word in words):
            matched.append({"route": label, "commands": commands, "guide": guide, "pitfalls": pitfalls})
    packs_only = matched and all(route["guide"] == "packs" for route in matched)
    steps = []
    if not packs_only:
        init = "quickstart NEW_PATH --mod-id ID --package dev.you.mod --name NAME"
        if loader or version:
            init += f" --loader {loader or 'neoforge'}" + (f" --minecraft {version[1]}" if version else "")
        steps.append({"step": "create or open the project", "commands": ["instances (to match an existing pack)", init, "targets"],
                      "guide": loader or "neoforge"})
    steps += matched or [{"route": "general mod", "commands": ["add PROJECT KIND NAME"], "guide": "content", "pitfalls": []}]
    if not packs_only:
        steps.append({"step": "prove it", "commands": ["verify PROJECT  (NeoForge before 1.21.5: tests PROJECT first)", "verify PROJECT --check"],
                      "guide": "testing", "pitfalls": ["Build, server load, client rendering and gameplay are separate claims"]})
    return {"request": request, "loader": loader, "minecraft": version[1] if version else None, "mod_needed": not packs_only, "steps": steps,
            "note": "Routing only; nothing was written. Read the named guide before writing code (guide NAME)."}
